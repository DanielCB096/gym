from base64 import b64encode
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.memberships.conekta_payment_methods import (
    ConektaPaymentMethods,
    ConektaRenewalOrder,
    ConektaSavedCard,
)
from app.modules.memberships.gateway import ChargeOutcome, ChargeStatus, VerifiedWebhook
from app.modules.memberships.models import (
    Member,
    MemberConsent,
    MemberPaymentMethodSetup,
    Membership,
    MembershipEvent,
    Payment,
    PaymentAttempt,
    PaymentMethod,
    Plan,
)
from app.modules.memberships.payment_method_security import decrypt_payment_reference
from app.modules.memberships.service import process_verified_webhook


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


def test_due_member_captures_card_and_starts_only_the_confirmable_renewal(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("SECRET_KEY", "payment-method-setup-test-secret")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_SANDBOX_API_KEY", "key_test_private")
    monkeypatch.setenv("CONEKTA_SANDBOX_PUBLIC_KEY", "key_test_public")
    monkeypatch.setenv("MEMBER_PAYMENT_METHOD_URL", "https://gym.example.test/member/payment-method")
    monkeypatch.setenv(
        "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY",
        b64encode(b"payment-method-encryption-key!!!").decode("ascii"),
    )
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
    email = "due-member@example.com"
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        member = Member(
            first_name="Ana",
            last_name="Demo",
            email=email,
            phone="+525555555555",
            status="active",
        )
        plan = Plan(
            code=f"DUE-{uuid4().hex[:8].upper()}",
            name="Mensual",
            duration_days=30,
            price_cents=50000,
        )
        session.add_all([member, plan])
        session.flush()
        membership = Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="active",
            starts_at=now - timedelta(days=30),
            ends_at=now - timedelta(seconds=1),
            auto_renew=True,
        )
        session.add(membership)
        session.flush()
        session.add_all(
            [
                MemberConsent(
                    member_id=member.id,
                    consent_type="privacy_notice",
                    document_version="privacy-v1",
                    accepted_at=now - timedelta(days=30),
                ),
                MemberConsent(
                    member_id=member.id,
                    consent_type="membership_auto_renewal",
                    document_version="auto-renewal-v1",
                    evidence_digest="a" * 64,
                    accepted_at=now - timedelta(days=20),
                ),
            ]
        )
        old_membership_id = membership.id
        session.commit()

    calls: list[str] = []

    def save_card(
        _: ConektaPaymentMethods,
        *,
        member_name: str,
        member_email: str | None,
        member_phone: str | None,
        card_token: str,
        idempotency_key: str,
    ) -> ConektaSavedCard:
        calls.append("save")
        assert member_name == "Ana Demo"
        assert member_email == email
        assert member_phone == "+525555555555"
        assert card_token == "tok_sandbox_card_1"
        assert idempotency_key
        return ConektaSavedCard("cus_sandbox_1", "src_sandbox_1")

    def create_order(
        _: ConektaPaymentMethods,
        *,
        customer_id: str,
        payment_source_id: str,
        plan_name: str,
        amount_cents: int,
        currency: str,
        membership_id: str,
        payment_attempt_id: str,
    ) -> ConektaRenewalOrder:
        calls.append("charge")
        assert customer_id == "cus_sandbox_1"
        assert payment_source_id == "src_sandbox_1"
        assert plan_name == "Mensual"
        assert amount_cents == 50000
        assert currency == "MXN"
        assert UUID(membership_id)
        assert UUID(payment_attempt_id)
        return ConektaRenewalOrder("ord_sandbox_renewal_1")

    monkeypatch.setattr(ConektaPaymentMethods, "save_card", save_card)
    monkeypatch.setattr(ConektaPaymentMethods, "create_renewal_order", create_order)
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            headers = _member_token(client, email)
            started = client.post(
                "/member/membership/payment-method/setup",
                headers=headers,
            )
            assert started.status_code == 200, started.text
            setup_url = started.json()["setup_url"]
            assert setup_url.startswith("https://gym.example.test/member/payment-method#")
            setup_token = setup_url.partition("#")[2]
            assert len(setup_token) >= 40
            assert started.json()["amount_cents"] == 50000

            with Session(engine) as session:
                setup = session.exec(select(MemberPaymentMethodSetup)).one()
                assert setup.status == "pending"
                assert setup.token_digest == sha256(setup_token.encode("ascii")).hexdigest()
                assert setup.token_digest != setup_token

            config = client.post(
                "/member/membership/payment-method/setup/config",
                json={"setup_token": setup_token},
            )
            assert config.status_code == 200, config.text
            assert config.json() == {
                "public_key": "key_test_public",
                "plan_name": "Mensual",
                "amount_cents": 50000,
                "currency": "MXN",
            }
            assert config.headers["cache-control"] == "no-store"
            assert config.headers["referrer-policy"] == "no-referrer"

            monkeypatch.delenv("MEMBERSHIP_PAYMENT_ENCRYPTION_KEY")
            missing_key = client.post(
                "/member/membership/payment-method/setup/complete",
                json={
                    "setup_token": setup_token,
                    "card_token": "tok_sandbox_card_1",
                },
            )
            assert missing_key.status_code == 503, missing_key.text
            assert calls == []
            monkeypatch.setenv(
                "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY",
                b64encode(b"payment-method-encryption-key!!!").decode("ascii"),
            )

            complete = client.post(
                "/member/membership/payment-method/setup/complete",
                json={
                    "setup_token": setup_token,
                    "card_token": "tok_sandbox_card_1",
                },
            )
            replay = client.post(
                "/member/membership/payment-method/setup/complete",
                json={
                    "setup_token": setup_token,
                    "card_token": "tok_sandbox_card_1",
                },
            )
            assert complete.status_code == 200, complete.text
            assert complete.json()["status"] == "processing"
            assert replay.status_code == 200, replay.text
            assert replay.json()["idempotent_replay"] is True
            assert calls == ["save", "charge"]
            with Session(engine) as session:
                setup = session.exec(select(MemberPaymentMethodSetup)).one()
                setup.expires_at = now - timedelta(seconds=1)
                session.add(setup)
                session.commit()
            expired_replay = client.post(
                "/member/membership/payment-method/setup/complete",
                json={
                    "setup_token": setup_token,
                    "card_token": "tok_sandbox_card_1",
                },
            )
            assert expired_replay.status_code == 409, expired_replay.text

            with Session(engine) as session:
                old_membership = session.get(Membership, old_membership_id)
                new_memberships = session.exec(
                    select(Membership).where(Membership.id != old_membership_id)
                ).all()
                payment_method = session.exec(select(PaymentMethod)).one()
                attempt = session.exec(select(PaymentAttempt)).one()
                setup = session.exec(select(MemberPaymentMethodSetup)).one()
                assert old_membership is not None and old_membership.status == "expired"
                assert len(new_memberships) == 1
                assert new_memberships[0].status == "pending_payment"
                assert new_memberships[0].auto_renew is True
                assert attempt.status == "processing"
                assert attempt.provider_order_id == "ord_sandbox_renewal_1"
                assert payment_method.provider_method_id != "src_sandbox_1"
                assert b"src_sandbox_1" not in payment_method.encrypted_provider_token
                assert decrypt_payment_reference(
                    payment_method.member_id,
                    payment_method.encrypted_provider_token,
                ) == ("cus_sandbox_1", "src_sandbox_1")
                assert setup.status == "submitted"
                assert setup.payment_attempt_id == attempt.id
                assert len(
                    session.exec(
                        select(MembershipEvent).where(
                            MembershipEvent.event_type == "expired"
                        )
                    ).all()
                ) == 1
                assert session.exec(select(Payment)).all() == []
                paid_at = now + timedelta(minutes=2)
                process_verified_webhook(
                    session,
                    VerifiedWebhook(
                        provider="conekta",
                        provider_event_id="evt_sandbox_paid",
                        event_type="order.paid",
                        payload_sha256="c" * 64,
                        payment_attempt_id=attempt.id,
                        outcome=ChargeOutcome(
                            status=ChargeStatus.SUCCEEDED,
                            provider_reference="ch_sandbox_renewal_1",
                            occurred_at=paid_at,
                        ),
                    ),
                )
                session.refresh(new_memberships[0])
                payment = session.exec(select(Payment)).one()
                renewed_starts_at = new_memberships[0].starts_at.replace(
                    tzinfo=timezone.utc
                )
                renewed_ends_at = new_memberships[0].ends_at.replace(
                    tzinfo=timezone.utc
                )
                assert new_memberships[0].status == "active"
                assert renewed_starts_at == paid_at
                assert renewed_ends_at == paid_at + timedelta(days=30)
                assert payment.period_starts_at.replace(tzinfo=timezone.utc) == paid_at
                assert payment.period_ends_at.replace(tzinfo=timezone.utc) == renewed_ends_at
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_member_cannot_open_card_capture_before_membership_expiry(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("SECRET_KEY", "payment-method-setup-not-due-secret")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_SANDBOX_API_KEY", "key_test_private")
    monkeypatch.setenv("CONEKTA_SANDBOX_PUBLIC_KEY", "key_test_public")
    monkeypatch.setenv("MEMBER_PAYMENT_METHOD_URL", "https://gym.example.test/member/payment-method")
    monkeypatch.setenv(
        "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY",
        b64encode(b"payment-method-encryption-key!!!").decode("ascii"),
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    email = "not-due-member@example.com"
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
        plan = Plan(
            code=f"NOT-DUE-{uuid4().hex[:8].upper()}",
            name="Mensual",
            duration_days=30,
            price_cents=50000,
        )
        session.add_all([member, plan])
        session.flush()
        membership = Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="active",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=29),
            auto_renew=True,
        )
        session.add(membership)
        session.flush()
        session.add(
            MemberConsent(
                member_id=member.id,
                consent_type="membership_auto_renewal",
                document_version="auto-renewal-v1",
                evidence_digest="b" * 64,
                accepted_at=now - timedelta(days=1),
            )
        )
        session.commit()

    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/member/membership/payment-method/setup",
                headers=_member_token(client, email),
            )
            assert response.status_code == 409, response.text
            with Session(engine) as session:
                assert session.exec(select(MemberPaymentMethodSetup)).all() == []
                assert session.exec(select(PaymentAttempt)).all() == []
                assert session.exec(select(Payment)).all() == []
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
