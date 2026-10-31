from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.memberships.conekta_checkout import ConektaHostedCheckout
from app.modules.memberships.gateway import HostedCheckout
from app.modules.memberships.models import (
    Member,
    MemberConsent,
    Membership,
    Payment,
    PaymentAttempt,
    Plan,
)


def _session_override(engine):
    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return override_session


def _member_token(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_member_can_create_only_idempotent_sandbox_checkout(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("SECRET_KEY", "checkout-test-secret")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_SANDBOX_API_KEY", "test-api-key")
    monkeypatch.setenv("CONEKTA_SUCCESS_URL", "https://gym.example.test/payment/return")
    monkeypatch.setenv("CONEKTA_FAILURE_URL", "https://gym.example.test/payment/failed")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    email = "checkout-member@example.com"
    with Session(engine) as session:
        member = Member(first_name="Ana", last_name="Demo", email=email, status="pending")
        plan = Plan(
            code=f"CHECKOUT-{uuid4().hex[:8].upper()}",
            name="Mensual",
            duration_days=30,
            price_cents=50000,
        )
        session.add_all([member, plan])
        session.flush()
        session.add(
            MemberConsent(
                member_id=member.id,
                consent_type="privacy_notice",
                document_version="v1",
                accepted_at=datetime.now(timezone.utc),
            )
        )
        plan_id = plan.id
        session.commit()

    calls: list[UUID] = []

    def create_checkout(
        _: ConektaHostedCheckout,
        attempt: PaymentAttempt,
        *,
        member_name: str,
        member_email: str | None,
        member_phone: str | None,
        plan_name: str,
        success_url: str,
        failure_url: str,
    ) -> HostedCheckout:
        calls.append(attempt.id)
        assert member_name == "Ana Demo"
        assert member_email == email
        assert member_phone is None
        assert plan_name == "Mensual"
        assert success_url == "https://gym.example.test/payment/return"
        assert failure_url == "https://gym.example.test/payment/failed"
        return HostedCheckout(
            provider_order_id="ord_sandbox_1",
            checkout_url="https://pay.conektame.io/link/sandbox_1",
        )

    monkeypatch.setattr(ConektaHostedCheckout, "create_checkout", create_checkout)
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            headers = _member_token(client, email)
            first = client.post(
                "/member/membership/checkout",
                headers={**headers, "Idempotency-Key": "member-checkout-key-1"},
                json={"plan_id": str(plan_id)},
            )
            replay = client.post(
                "/member/membership/checkout",
                headers={**headers, "Idempotency-Key": "member-checkout-key-1"},
                json={"plan_id": str(plan_id)},
            )
            assert first.status_code == 200, first.text
            assert replay.status_code == 200, replay.text
            assert first.json()["checkout_url"] == "https://pay.conektame.io/link/sandbox_1"
            assert replay.json()["idempotent_replay"] is True
            assert first.json()["membership_id"] == replay.json()["membership_id"]
            assert len(calls) == 1

            with Session(engine) as session:
                membership = session.get(Membership, UUID(first.json()["membership_id"]))
                attempts = session.exec(select(PaymentAttempt)).all()
                assert membership is not None and membership.status == "pending_payment"
                assert len(attempts) == 1
                assert attempts[0].amount_cents == 50000
                assert attempts[0].provider_order_id == "ord_sandbox_1"
                assert session.exec(select(Payment)).all() == []
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
