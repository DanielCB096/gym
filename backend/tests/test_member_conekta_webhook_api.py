import base64
import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.memberships.models import (
    Member,
    Membership,
    Payment,
    PaymentAttempt,
    Plan,
    ProviderWebhookEvent,
)


def _session_override(engine):
    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return override_session


def _webhook_payload(
    *,
    event_id: str = "evt_sandbox_1",
    amount: int = 50000,
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": "order.paid",
            "livemode": False,
            "created_at": 1793479500,
            "data": {
                "object": {
                    "id": "ord_sandbox_1",
                    "object": "order",
                    "livemode": False,
                    "amount": amount,
                    "currency": "MXN",
                    "payment_status": "paid",
                    "charges": {"data": [{"id": "ch_sandbox_1", "status": "paid"}]},
                }
            },
        },
        separators=(",", ":"),
    ).encode()


def _declined_webhook_payload() -> bytes:
    return json.dumps(
        {
            "id": "evt_declined_1",
            "object": "event",
            "type": "charge.created",
            "livemode": False,
            "data": {
                "object": {
                    "id": "ch_declined_1",
                    "object": "charge",
                    "livemode": False,
                    "order_id": "ord_sandbox_1",
                    "amount": 50000,
                    "currency": "MXN",
                    "status": "declined",
                }
            },
        },
        separators=(",", ":"),
    ).encode()


def _sign(private_key, payload: bytes) -> str:
    signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def test_signed_sandbox_webhook_confirms_checkout_once(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_WEBHOOK_PUBLIC_KEY", public_key_pem)

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
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        member = Member(first_name="Ana", last_name="Demo", email="webhook@example.com")
        plan = Plan(
            code=f"WEBHOOK-{uuid4().hex[:8].upper()}",
            name="Mensual",
            duration_days=30,
            price_cents=50000,
        )
        session.add_all([member, plan])
        session.flush()
        membership = Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="pending_payment",
            starts_at=now,
            ends_at=now + timedelta(days=30),
            auto_renew=False,
        )
        session.add(membership)
        session.flush()
        attempt = PaymentAttempt(
            membership_id=membership.id,
            method="card",
            provider="conekta",
            provider_order_id="ord_sandbox_1",
            idempotency_key="webhook-test-key",
            request_fingerprint="f" * 64,
            attempt_number=1,
            amount_cents=50000,
            currency="MXN",
            status="pending",
            due_at=now,
        )
        session.add(attempt)
        session.commit()
        membership_id = membership.id

    app.dependency_overrides[get_session] = _session_override(engine)
    payload = _webhook_payload()
    headers = {
        "Digest": _sign(private_key, payload),
        "Content-Type": "application/json",
    }
    declined_payload = _declined_webhook_payload()
    try:
        with TestClient(app) as client:
            declined = client.post(
                "/webhooks/conekta/membership",
                content=declined_payload,
                headers={
                    "Digest": _sign(private_key, declined_payload),
                    "Content-Type": "application/json",
                },
            )
            assert declined.status_code == 200, declined.text
            assert declined.json() == {"status": "processed"}

            with Session(engine) as session:
                membership = session.get(Membership, membership_id)
                attempt = session.exec(select(PaymentAttempt)).one()
                assert membership is not None and membership.status == "pending_payment"
                assert attempt.status == "failed"
                assert session.exec(select(Payment)).all() == []

            first = client.post(
                "/webhooks/conekta/membership",
                content=payload,
                headers=headers,
            )
            replay = client.post(
                "/webhooks/conekta/membership",
                content=payload,
                headers=headers,
            )
            assert first.status_code == 200, first.text
            assert first.json() == {"status": "processed"}
            assert replay.status_code == 200, replay.text
            assert replay.json() == {"status": "duplicate"}

        with Session(engine) as session:
            membership = session.get(Membership, membership_id)
            assert membership is not None and membership.status == "active"
            assert len(session.exec(select(Payment)).all()) == 1
            assert len(session.exec(select(ProviderWebhookEvent)).all()) == 2
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_signed_webhook_rejects_amount_mismatch_without_confirming(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_WEBHOOK_PUBLIC_KEY", public_key_pem)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        member = Member(first_name="Luis", last_name="Demo", email="mismatch@example.com")
        plan = Plan(
            code=f"MISMATCH-{uuid4().hex[:8].upper()}",
            name="Mensual",
            duration_days=30,
            price_cents=50000,
        )
        session.add_all([member, plan])
        session.flush()
        membership = Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="pending_payment",
            starts_at=now,
            ends_at=now + timedelta(days=30),
        )
        session.add(membership)
        session.flush()
        session.add(
            PaymentAttempt(
                membership_id=membership.id,
                method="card",
                provider="conekta",
                provider_order_id="ord_sandbox_1",
                idempotency_key="webhook-mismatch-key",
                request_fingerprint="a" * 64,
                attempt_number=1,
                amount_cents=50000,
                currency="MXN",
                status="pending",
                due_at=now,
            )
        )
        session.commit()
        membership_id = membership.id

    app.dependency_overrides[get_session] = _session_override(engine)
    payload = _webhook_payload(event_id="evt_mismatch", amount=49999)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/webhooks/conekta/membership",
                content=payload,
                headers={
                    "Digest": _sign(private_key, payload),
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 409, response.text

        with Session(engine) as session:
            membership = session.get(Membership, membership_id)
            assert membership is not None and membership.status == "pending_payment"
            assert session.exec(select(Payment)).all() == []
            rejected_events = session.exec(select(ProviderWebhookEvent)).all()
            assert len(rejected_events) == 1
            assert rejected_events[0].status == "failed"
            assert rejected_events[0].error_code == "rejected_amount_mismatch"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_invalid_signature_does_not_confirm_payment(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_WEBHOOK_PUBLIC_KEY", public_key_pem)
    payload = _webhook_payload()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/webhooks/conekta/membership",
                content=payload,
                headers={
                    "Digest": _sign(other_private_key, payload),
                    "Content-Type": "application/json",
                },
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
