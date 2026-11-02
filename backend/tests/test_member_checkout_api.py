from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
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
    MembershipEvent,
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
    other_email = "another-member@example.com"
    with Session(engine) as session:
        member = Member(first_name="Ana", last_name="Demo", email=email, status="pending")
        other_member = Member(
            first_name="Luis",
            last_name="Demo",
            email=other_email,
            status="pending",
        )
        plan = Plan(
            code=f"CHECKOUT-{uuid4().hex[:8].upper()}",
            name="Mensual",
            duration_days=30,
            price_cents=50000,
        )
        session.add_all([member, other_member, plan])
        session.flush()
        session.add(
            MemberConsent(
                member_id=member.id,
                consent_type="privacy_notice",
                document_version="v1",
                accepted_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            MemberConsent(
                member_id=other_member.id,
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
            plans = client.get("/member/membership/plans", headers=headers)
            assert plans.status_code == 200, plans.text
            assert plans.json()["checkout_enabled"] is True
            assert plans.json()["eligible"] is True
            assert plans.json()["items"] == [
                {
                    "id": str(plan_id),
                    "name": "Mensual",
                    "duration_days": 30,
                    "price_cents": 50000,
                    "currency": "MXN",
                }
            ]
            assert plans.json()["pending_checkout"] is None
            monkeypatch.delenv("CONEKTA_SANDBOX_API_KEY")
            unavailable = client.get("/member/membership/plans", headers=headers)
            assert unavailable.status_code == 200, unavailable.text
            assert unavailable.json() == {
                "checkout_enabled": False,
                "eligible": True,
                "items": [],
                "pending_checkout": None,
            }
            monkeypatch.setenv("CONEKTA_SANDBOX_API_KEY", "test-api-key")
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
            resumed = client.get("/member/membership/plans", headers=headers)
            assert resumed.json() == {
                "checkout_enabled": True,
                "eligible": False,
                "items": [],
                "pending_checkout": {
                    "plan": {
                        "id": str(plan_id),
                        "name": "Mensual",
                        "duration_days": 30,
                        "price_cents": 50000,
                        "currency": "MXN",
                    },
                    "idempotency_key": "member-checkout-key-1",
                    "checkout_url": "https://pay.conektame.io/link/sandbox_1",
                },
            }
            other_headers = _member_token(client, other_email)
            other_plans = client.get("/member/membership/plans", headers=other_headers)
            assert other_plans.status_code == 200, other_plans.text
            assert other_plans.json()["eligible"] is True
            assert other_plans.json()["pending_checkout"] is None

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


def test_member_can_record_and_revoke_auto_renewal_consent_without_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("SECRET_KEY", "renewal-consent-test-secret")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    email = "renewal-member@example.com"
    with Session(engine) as session:
        member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
        plan = Plan(
            code=f"RENEWAL-{uuid4().hex[:8].upper()}",
            name="Mensual",
            duration_days=30,
            price_cents=50000,
        )
        now = datetime.now(timezone.utc)
        membership = Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="active",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=29),
        )
        session.add_all([member, plan, membership])
        session.flush()
        session.add(
            MemberConsent(
                member_id=member.id,
                consent_type="privacy_notice",
                document_version="v1",
                accepted_at=now - timedelta(days=1),
            )
        )
        membership_id = membership.id
        session.commit()

    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            headers = _member_token(client, email)
            initial = client.get("/member/membership/auto-renewal", headers=headers)
            assert initial.status_code == 200, initial.text
            assert initial.json()["eligible"] is True
            assert initial.json()["enabled"] is False
            assert initial.json()["payment_method_ready"] is False
            assert "No se realizará un cargo" in initial.json()["consent_text"]

            enabled = client.post(
                "/member/membership/auto-renewal",
                headers=headers,
                json={"enabled": True},
            )
            replay = client.post(
                "/member/membership/auto-renewal",
                headers=headers,
                json={"enabled": True},
            )
            assert enabled.status_code == 200, enabled.text
            assert enabled.json()["enabled"] is True
            assert enabled.json()["first_renewal_requires_member_action"] is True
            assert replay.status_code == 200, replay.text
            assert replay.json()["enabled"] is True

            with Session(engine) as session:
                consent = session.exec(
                    select(MemberConsent).where(
                        MemberConsent.consent_type == "membership_auto_renewal"
                    )
                ).all()
                events = session.exec(
                    select(MembershipEvent).where(
                        MembershipEvent.event_type == "auto_renewal_enabled"
                    )
                ).all()
                assert len(consent) == 1
                assert consent[0].evidence_digest is not None
                assert len(consent[0].evidence_digest) == 64
                assert len(events) == 1
                assert events[0].membership_id == membership_id
                assert session.exec(select(PaymentAttempt)).all() == []
                assert session.exec(select(Payment)).all() == []

            disabled = client.post(
                "/member/membership/auto-renewal",
                headers=headers,
                json={"enabled": False},
            )
            assert disabled.status_code == 200, disabled.text
            assert disabled.json()["enabled"] is False

            with Session(engine) as session:
                consent = session.exec(
                    select(MemberConsent).where(
                        MemberConsent.consent_type == "membership_auto_renewal"
                    )
                ).one()
                membership = session.get(Membership, membership_id)
                events = session.exec(
                    select(MembershipEvent).where(
                        MembershipEvent.event_type == "auto_renewal_revoked"
                    )
                ).all()
                assert consent.revoked_at is not None
                assert membership is not None and membership.auto_renew is False
                assert len(events) == 1
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
