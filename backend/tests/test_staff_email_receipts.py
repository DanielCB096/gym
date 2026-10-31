"""Signed acknowledgements for the staff emails.

The provider reports what happened to a message that already left. The receipt
never rewrites the transport status, the same provider event is stored once, and
only a message the SMTP server accepted can be acknowledged.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.models import AppUser
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications import delivery as delivery_module
from app.modules.notifications.models import (
    StaffNotificationDelivery,
    StaffNotificationDeliveryReceipt,
)
from app.modules.notifications.receipts import (
    ReceiptInvalid,
    ReceiptNotConfigured,
    ReceiptNotFound,
    ReceiptRejected,
    ReceiptSignatureInvalid,
    normalize_message_id,
    parse_delivery_report,
    record_email_receipt,
    signature_for,
    verify_signature,
)
from app.modules.notifications.service import create_staff_notification
from app.modules.notifications.delivery import list_staff_notification_deliveries

NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)
SECRET = "webhook-secret-for-tests"


def _build_engine():
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

    return engine


def _account(session: Session, *, email: str, role: str = "reception") -> AppUser:
    ensure_default_access_control(session)
    return register_user(
        session,
        email=email,
        password="strong-password-for-tests",
        role_codes=(role,),
    )


def _sent_delivery(session: Session, account: AppUser) -> StaffNotificationDelivery:
    create_staff_notification(
        session,
        user_id=account.id,
        kind="attendance_corrected",
        title="Se corrigió tu marca",
        body="Recepción corrigió tu entrada de las 19:30 a las 19:15.",
        now=NOW,
    )
    session.commit()
    delivery = session.exec(select(StaffNotificationDelivery)).one()
    delivery.status = "sent"
    delivery.attempts = 1
    delivery.sent_at = NOW
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


def _report(delivery: StaffNotificationDelivery, **overrides) -> bytes:
    payload = {
        "message_id": delivery.message_id,
        "event_id": f"evt-{uuid4().hex}",
        "event": "delivered",
        "occurred_at": "2026-10-30T18:05:00+00:00",
        "detail": "250 2.0.0 Ok: queued as 4F1",
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def _post(client: TestClient, body: bytes, *, secret: str = SECRET):
    return client.post(
        "/webhooks/email/delivery",
        content=body,
        headers={"X-Email-Signature": signature_for(body, secret)},
    )


def test_enqueue_freezes_the_identifier_the_message_leaves_with(
    session: Session, monkeypatch
) -> None:
    account = _account(session, email="lucia@example.test")
    create_staff_notification(
        session,
        user_id=account.id,
        kind="attendance_corrected",
        title="Se corrigió tu marca",
        body="Cuerpo del aviso.",
        now=NOW,
    )
    delivery = session.exec(select(StaffNotificationDelivery)).one()
    assert delivery.message_id is not None
    assert delivery.message_id.endswith("@centro-fit.local")

    sent: list[str | None] = []

    def fake_send_email(*, recipient: str, subject: str, body: str, **kwargs) -> str:
        sent.append(kwargs.get("message_id"))
        return "sent"

    monkeypatch.setattr(delivery_module, "send_email", fake_send_email)
    delivery_module.send_pending_staff_notification_emails(session, now=NOW)
    assert sent == [delivery.message_id]


def test_a_delivery_receipt_is_listed_with_the_newest_event(session: Session) -> None:
    account = _account(session, email="lucia@example.test")
    delivery = _sent_delivery(session, account)

    report = parse_delivery_report(_report(delivery))
    receipt, created = record_email_receipt(
        session, report, now=NOW + timedelta(minutes=5)
    )
    assert created is True
    assert receipt.delivery_id == delivery.id
    assert receipt.event_type == "delivered"

    item = list_staff_notification_deliveries(session).items[0]
    assert item.status == "sent"
    assert item.ack_status == "delivered"
    assert item.ack_at == datetime(2026, 10, 30, 18, 5, tzinfo=timezone.utc)
    assert "250 2.0.0" in (item.ack_detail or "")

    bounced = parse_delivery_report(
        _report(delivery, event="bounced", detail="550 5.1.1 user unknown")
    )
    record_email_receipt(session, bounced, now=NOW + timedelta(hours=1))

    item = list_staff_notification_deliveries(session).items[0]
    assert item.ack_status == "bounced"
    assert "550" in (item.ack_detail or "")
    assert len(session.exec(select(StaffNotificationDeliveryReceipt)).all()) == 2


def test_the_same_provider_event_is_stored_once(session: Session) -> None:
    account = _account(session, email="lucia@example.test")
    delivery = _sent_delivery(session, account)
    report = parse_delivery_report(_report(delivery))

    first, created = record_email_receipt(session, report, now=NOW)
    replay, repeated = record_email_receipt(
        session, report, now=NOW + timedelta(minutes=1)
    )

    assert created is True
    assert repeated is False
    assert replay.id == first.id
    assert len(session.exec(select(StaffNotificationDeliveryReceipt)).all()) == 1


def test_an_event_id_belongs_to_one_message(session: Session) -> None:
    first_account = _account(session, email="lucia@example.test")
    first = _sent_delivery(session, first_account)

    second_account = _account(session, email="raul@example.test")
    create_staff_notification(
        session,
        user_id=second_account.id,
        kind="attendance_voided",
        title="Se anuló tu salida",
        body="Cuerpo del aviso.",
        now=NOW,
    )
    session.commit()
    second = session.exec(
        select(StaffNotificationDelivery).where(
            StaffNotificationDelivery.notice_id != first.notice_id
        )
    ).one()
    second.status = "sent"
    session.add(second)
    session.commit()

    record_email_receipt(
        session,
        parse_delivery_report(_report(first, event_id="evt-shared")),
        now=NOW,
    )
    with pytest.raises(ReceiptRejected):
        record_email_receipt(
            session,
            parse_delivery_report(_report(second, event_id="evt-shared")),
            now=NOW,
        )


def test_only_a_message_that_left_can_be_acknowledged(session: Session) -> None:
    account = _account(session, email="lucia@example.test")
    create_staff_notification(
        session,
        user_id=account.id,
        kind="attendance_corrected",
        title="Se corrigió tu marca",
        body="Cuerpo del aviso.",
        now=NOW,
    )
    session.commit()
    pending = session.exec(select(StaffNotificationDelivery)).one()
    with pytest.raises(ReceiptRejected) as error:
        record_email_receipt(
            session, parse_delivery_report(_report(pending)), now=NOW
        )
    assert "todavía no se ha enviado" in str(error.value)

    pending.status = "simulated"
    session.add(pending)
    session.commit()
    with pytest.raises(ReceiptRejected):
        record_email_receipt(
            session, parse_delivery_report(_report(pending)), now=NOW
        )


def test_an_unknown_message_id_is_not_found(session: Session) -> None:
    _account(session, email="lucia@example.test")
    body = json.dumps(
        {
            "message_id": "desconocido@centro-fit.local",
            "event_id": "evt-404",
            "event": "delivered",
        }
    ).encode("utf-8")
    with pytest.raises(ReceiptNotFound):
        record_email_receipt(session, parse_delivery_report(body), now=NOW)


def test_the_body_must_respect_the_contract() -> None:
    cases = [
        (b"no es json", "JSON válido"),
        (b"[]", "objeto JSON"),
        (b'{"event_id": "e", "event": "delivered"}', "identificador de mensaje"),
        (b'{"message_id": "m@x", "event": "delivered"}', "identificador de evento"),
        (b'{"message_id": "m@x", "event_id": "e", "event": "opened"}', "delivered"),
        (
            b'{"message_id": "m@x", "event_id": "e", "event": "delivered", '
            b'"occurred_at": "ayer"}',
            "fecha",
        ),
    ]
    for body, expected in cases:
        try:
            parse_delivery_report(body)
        except ReceiptInvalid as error:
            assert expected in str(error), (body, error)
        else:  # pragma: no cover
            raise AssertionError(f"payload accepted: {body!r}")


def test_the_report_normalises_the_message_id_and_clips_the_detail() -> None:
    report = parse_delivery_report(
        json.dumps(
            {
                "message_id": "  <ABC123@Centro-Fit.Local>  ",
                "event_id": " evt-1 ",
                "event": "complained",
                "occurred_at": "2026-10-30T18:05:00Z",
                "detail": "x" * 900,
            }
        ).encode("utf-8")
    )
    assert report.message_id == "abc123@centro-fit.local"
    assert report.provider_event_id == "evt-1"
    assert report.occurred_at == datetime(2026, 10, 30, 18, 5, tzinfo=timezone.utc)
    assert len(report.detail or "") == 500
    assert normalize_message_id("<a@b>") == "a@b"


def test_the_signature_is_mandatory_and_must_match() -> None:
    body = b'{"message_id": "m@x"}'
    verify_signature(body, signature_for(body, SECRET), secret=SECRET)

    for secret, signature, expected in (
        ("", signature_for(body, SECRET), ReceiptNotConfigured),
        (SECRET, None, ReceiptSignatureInvalid),
        (SECRET, "sha256=deadbeef", ReceiptSignatureInvalid),
        (SECRET, signature_for(body, "otro-secreto"), ReceiptSignatureInvalid),
    ):
        try:
            verify_signature(body, signature, secret=secret)
        except expected:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"signature accepted: {secret!r} {signature!r}")


def _panel_deliveries(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get("/admin/staff/notifications/deliveries", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_webhook_stores_the_ack_and_the_panel_shows_it(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-receipts-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", SECRET)

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        owner = _account(session, email="owner@example.com", role="owner")
        delivery = _sent_delivery(session, owner)
        message_id = delivery.message_id
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "strong-password-for-tests"},
            )
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            body = json.dumps(
                {
                    "message_id": f"<{message_id}>",
                    "event_id": "evt-delivered-1",
                    "event": "delivered",
                    "occurred_at": "2026-10-30T18:05:00+00:00",
                    "detail": "250 2.0.0 Ok",
                }
            ).encode("utf-8")
            accepted = _post(client, body)
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["event_type"] == "delivered"
            assert accepted.json()["duplicate"] is False

            replay = _post(client, body)
            assert replay.status_code == 200, replay.text
            assert replay.json()["duplicate"] is True
            assert replay.json()["id"] == accepted.json()["id"]

            board = _panel_deliveries(client, headers)
            assert board["items"][0]["status"] == "sent"
            assert board["items"][0]["ack_status"] == "delivered"
            assert board["items"][0]["ack_detail"] == "250 2.0.0 Ok"

            wrong = client.post(
                "/webhooks/email/delivery",
                content=body,
                headers={"X-Email-Signature": "sha256=deadbeef"},
            )
            assert wrong.status_code == 401
            unsigned = client.post("/webhooks/email/delivery", content=body)
            assert unsigned.status_code == 401

            unknown = _post(
                client,
                json.dumps(
                    {
                        "message_id": "nadie@centro-fit.local",
                        "event_id": "evt-unknown",
                        "event": "bounced",
                    }
                ).encode("utf-8"),
            )
            assert unknown.status_code == 404

            malformed = _post(
                client,
                json.dumps(
                    {"message_id": message_id, "event_id": "evt-2", "event": "opened"}
                ).encode("utf-8"),
            )
            assert malformed.status_code == 422

        monkeypatch.delenv("EMAIL_WEBHOOK_SECRET")
        with TestClient(app) as client:
            missing = _post(client, body)
            assert missing.status_code == 503
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def _session_override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency
