"""Receipts for the member pushes Expo accepted.

``sent`` only means Expo took the message; the receipt tied to its ticket says
whether the phone got it. These tests cover the ticket kept from the send, the
receipt stored per delivery, the device retired when Expo reports it gone, the
wait before asking an unanswered ticket again, the 24-hour expiry and the panel
endpoint that runs the pass by hand.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member
from app.modules.notifications import delivery as delivery_module
from app.modules.notifications import push as push_module
from app.modules.notifications import push_receipts as receipts_module
from app.modules.notifications.delivery import email_message_for_notice
from app.modules.notifications.models import (
    MemberPushDelivery,
    MemberPushDeliveryReceipt,
    MemberPushToken,
    StaffNotification,
    StaffNotificationDelivery,
)
from app.modules.notifications.push import (
    register_member_push_token,
    send_expo_push,
)
from app.modules.notifications.push_receipts import (
    ExpoReceipt,
    PushReceiptsFailed,
    fetch_expo_receipts,
    sync_member_push_receipts,
)
from app.modules.notifications.service import create_notification

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)
TOKEN_A = "ExponentPushToken[aaaAAA111]"
TICKET = "tkt-0001"


def _member(session: Session, *, email: str = "ana@example.test") -> Member:
    member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def _sent_delivery(
    session: Session, *, ticket: str | None = TICKET, sent_at: datetime = NOW
) -> tuple[Member, MemberPushDelivery]:
    """A delivery Expo accepted: the notice, its queued row and the ticket."""

    member = _member(session)
    register_member_push_token(
        session, member.id, token=TOKEN_A, platform="android", now=sent_at
    )
    notice = create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=sent_at,
    )
    session.commit()
    delivery = session.exec(
        select(MemberPushDelivery).where(
            MemberPushDelivery.notification_id == notice.id
        )
    ).one()
    delivery.status = "sent"
    delivery.attempts = 1
    delivery.last_attempt_at = sent_at
    delivery.sent_at = sent_at
    delivery.expo_ticket_id = ticket
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return member, delivery


def _receipts(session: Session) -> list[MemberPushDeliveryReceipt]:
    return list(session.exec(select(MemberPushDeliveryReceipt)).all())


def _staff_accounts(session: Session) -> dict[str, UUID]:
    """Owner, reception and trainer: the first two operate the push queue."""

    ensure_default_access_control(session)
    accounts: dict[str, UUID] = {}
    for role in ("owner", "reception", "trainer"):
        user = register_user(
            session,
            email=f"{role}@example.com",
            password=f"{role}-strong-password",
            role_codes=(role,),
            now=NOW,
        )
        accounts[role] = user.id
    return accounts


def test_the_send_keeps_the_ticket_expo_answers(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "false")
    captured: list[dict[str, object]] = []

    def fake_post(url, *, json, timeout, headers):
        captured.append({"url": url, "json": json, "timeout": timeout})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "ok", "id": TICKET}},
        )

    monkeypatch.setattr(push_module.httpx, "post", fake_post)
    result = send_expo_push(
        token=TOKEN_A, title="Reserva confirmada", body="Spinning 6am.", data={}
    )

    assert result.status == "sent"
    assert result.ticket_id == TICKET
    assert captured[0]["json"] == [
        {
            "to": TOKEN_A,
            "title": "Reserva confirmada",
            "body": "Spinning 6am.",
            "sound": "default",
            "data": {},
        }
    ]


def test_the_delivery_keeps_the_ticket_after_the_pass(session: Session, monkeypatch) -> None:
    member = _member(session)
    register_member_push_token(
        session, member.id, token=TOKEN_A, platform="android", now=NOW
    )
    create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()

    monkeypatch.setattr(
        push_module,
        "send_expo_push",
        lambda **_kwargs: push_module.PushSendResult(status="sent", ticket_id=TICKET),
    )
    push_module.send_pending_member_push_deliveries(session, now=NOW)

    delivery = session.exec(select(MemberPushDelivery)).one()
    assert delivery.expo_ticket_id == TICKET
    assert delivery.receipt_checked_at is None


def test_a_delivered_receipt_is_stored_once(session: Session, monkeypatch) -> None:
    _, delivery = _sent_delivery(session)
    monkeypatch.setattr(
        receipts_module,
        "fetch_expo_receipts",
        lambda ids: {TICKET: ExpoReceipt(status="ok", code=None, message=None)},
    )

    result = sync_member_push_receipts(session, now=NOW + timedelta(minutes=1))

    assert (result.checked, result.delivered, result.errors) == (1, 1, 0)
    assert result.pending == 0
    [receipt] = _receipts(session)
    assert receipt.status == "ok"
    assert receipt.detail is None
    session.refresh(delivery)
    assert delivery.receipt_checked_at is not None
    # The queue's own status is not rewritten by the receipt.
    assert delivery.status == "sent"

    again = sync_member_push_receipts(session, now=NOW + timedelta(minutes=2))
    assert again.checked == 0
    assert len(_receipts(session)) == 1


def test_an_error_receipt_retires_the_device(session: Session, monkeypatch) -> None:
    _staff_accounts(session)
    member, _ = _sent_delivery(session)
    monkeypatch.setattr(
        receipts_module,
        "fetch_expo_receipts",
        lambda ids: {
            TICKET: ExpoReceipt(
                status="error",
                code="DeviceNotRegistered",
                message="The recipient device is not registered.",
            )
        },
    )

    result = sync_member_push_receipts(session, now=NOW + timedelta(minutes=1))

    assert (result.errors, result.delivered, result.deactivated) == (1, 0, 1)
    [receipt] = _receipts(session)
    assert receipt.status == "error"
    assert "DeviceNotRegistered" in (receipt.detail or "")
    token = session.exec(select(MemberPushToken)).one()
    assert token.member_id == member.id
    assert token.active is False
    assert token.deactivated_at is not None
    # The device leaving the store is not a delivery failure worth a notice.
    assert session.exec(select(StaffNotification)).all() == []


def test_a_delivered_receipt_does_not_alert_the_staff(
    session: Session, monkeypatch
) -> None:
    _staff_accounts(session)
    _sent_delivery(session)
    monkeypatch.setattr(
        receipts_module,
        "fetch_expo_receipts",
        lambda ids: {TICKET: ExpoReceipt(status="ok", code=None, message=None)},
    )

    sync_member_push_receipts(session, now=NOW + timedelta(minutes=1))

    assert session.exec(select(StaffNotification)).all() == []


def test_an_error_receipt_alerts_the_accounts_that_operate_the_queue(
    session: Session, monkeypatch
) -> None:
    accounts = _staff_accounts(session)
    _, delivery = _sent_delivery(session)
    monkeypatch.setattr(
        receipts_module,
        "fetch_expo_receipts",
        lambda ids: {
            TICKET: ExpoReceipt(
                status="error",
                code="MessageTooBig",
                message="The message was too large.",
            )
        },
    )

    result = sync_member_push_receipts(session, now=NOW + timedelta(minutes=1))

    assert result.errors == 1
    notices = list(session.exec(select(StaffNotification)).all())
    assert {row.user_id for row in notices} == {
        accounts["owner"],
        accounts["reception"],
    }
    assert {row.kind for row in notices} == {"member_push_receipt_failed"}
    assert all(row.ref_id == delivery.id for row in notices)
    assert all("Ana Demo" in row.body for row in notices)
    assert all("«Push del socio»" in row.body for row in notices)
    assert all("MessageTooBig" in row.body for row in notices)
    assert all(
        row.dedupe_key
        == f"member_push_receipt_failed:{delivery.id}:{row.user_id}"
        for row in notices
    )

    emails = list(session.exec(select(StaffNotificationDelivery)).all())
    assert {row.recipient for row in emails} == {
        "owner@example.com",
        "reception@example.com",
    }
    subject, body = email_message_for_notice(notices[0])
    assert subject.startswith("[Avisos] ")
    assert "Push del socio" in body


def test_an_unanswered_ticket_waits_before_asking_again(session: Session, monkeypatch) -> None:
    _, delivery = _sent_delivery(session)
    calls: list[list[str]] = []

    def no_answer(ids):
        calls.append(ids)
        return {}

    monkeypatch.setattr(receipts_module, "fetch_expo_receipts", no_answer)

    first = sync_member_push_receipts(session, now=NOW + timedelta(minutes=1))
    assert first.checked == 1
    assert first.pending == 1
    assert _receipts(session) == []
    session.refresh(delivery)
    assert delivery.receipt_checked_at is not None

    early = sync_member_push_receipts(session, now=NOW + timedelta(minutes=5))
    assert early.checked == 0
    assert len(calls) == 1

    later = sync_member_push_receipts(session, now=NOW + timedelta(minutes=20))
    assert later.checked == 1
    assert len(calls) == 2


def test_a_ticket_past_24_hours_expires_without_asking(session: Session, monkeypatch) -> None:
    _staff_accounts(session)
    _, delivery = _sent_delivery(session, sent_at=NOW - timedelta(hours=25))

    def offline(ids):
        raise AssertionError("un ticket vencido no se consulta")

    monkeypatch.setattr(receipts_module, "fetch_expo_receipts", offline)

    result = sync_member_push_receipts(session, now=NOW)

    assert (result.checked, result.expired, result.pending) == (1, 1, 0)
    [receipt] = _receipts(session)
    assert receipt.status == "expired"
    assert "24 horas" in (receipt.detail or "")
    session.refresh(delivery)
    assert delivery.expo_ticket_id == TICKET
    # No answer is not an error: nobody gets a notice.
    assert session.exec(select(StaffNotification)).all() == []


def test_preview_defers_without_contacting_expo(session: Session, monkeypatch) -> None:
    _staff_accounts(session)
    _sent_delivery(session)
    monkeypatch.setattr(receipts_module, "preview_mode", lambda: True)

    def offline(ids):
        raise AssertionError("la vista previa no consulta acuses reales")

    monkeypatch.setattr(receipts_module, "fetch_expo_receipts", offline)

    result = sync_member_push_receipts(session, now=NOW)

    assert result.deferred is True
    assert result.checked == 0
    assert result.pending == 1
    assert _receipts(session) == []
    assert session.exec(select(StaffNotification)).all() == []


def test_the_preview_argument_defers_without_the_environment_flag(
    session: Session, monkeypatch
) -> None:
    _sent_delivery(session)
    monkeypatch.setattr(receipts_module, "preview_mode", lambda: False)
    monkeypatch.setattr(
        receipts_module, "fetch_expo_receipts", lambda ids: pytest.fail("no debe llamar")
    )

    result = sync_member_push_receipts(session, now=NOW, preview=True)

    assert result.deferred is True
    assert result.pending == 1


def test_fetching_receipts_survives_a_transport_error(monkeypatch) -> None:
    def unreachable(*_args, **_kwargs):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(receipts_module.httpx, "post", unreachable)
    with pytest.raises(PushReceiptsFailed):
        fetch_expo_receipts([TICKET])


def test_fetching_receipts_rejects_a_server_error(monkeypatch) -> None:
    monkeypatch.setattr(
        receipts_module.httpx,
        "post",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=503, json=lambda: {"errors": [{"code": "UNAVAILABLE"}]}
        ),
    )
    with pytest.raises(PushReceiptsFailed):
        fetch_expo_receipts([TICKET])


def test_fetching_receipts_reads_the_ticket_answers(monkeypatch) -> None:
    captured: list[object] = []

    def fake_post(url, *, json, timeout, headers):
        captured.append(json)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": {
                    TICKET: {
                        "status": "ok",
                        "id": TICKET,
                        "message": None,
                        "details": None,
                    },
                    "tkt-0002": {
                        "status": "error",
                        "message": "Device is not registered",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                }
            },
        )

    monkeypatch.setattr(receipts_module.httpx, "post", fake_post)
    answers = fetch_expo_receipts([TICKET, "tkt-0002", "tkt-0003"])

    assert captured == [{"ids": [TICKET, "tkt-0002", "tkt-0003"]}]
    assert answers[TICKET] == ExpoReceipt(status="ok", code=None, message=None)
    assert answers["tkt-0002"] == ExpoReceipt(
        status="error",
        code="DeviceNotRegistered",
        message="Device is not registered",
    )
    # Expo did not answer for tkt-0003 yet: it is not an error.
    assert "tkt-0003" not in answers


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


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_the_panel_runs_the_pass_and_shows_the_receipt(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-push-receipts-secret")
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as seed:
        ensure_default_access_control(seed)
        register_user(
            seed,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        register_user(
            seed,
            email="trainer@example.com",
            password="trainer-correct-horse-battery",
            role_codes=("trainer",),
        )
        _sent_delivery(seed)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        receipts_module,
        "fetch_expo_receipts",
        lambda ids: {TICKET: ExpoReceipt(status="ok", code=None, message=None)},
    )
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-correct-horse-battery")
            trainer = _login(client, "trainer@example.com", "trainer-correct-horse-battery")

            assert client.post(
                "/admin/notifications/push-deliveries/receipts"
            ).status_code == 401
            assert client.post(
                "/admin/notifications/push-deliveries/receipts", headers=trainer
            ).status_code == 403

            synced = client.post(
                "/admin/notifications/push-deliveries/receipts", headers=owner
            )
            assert synced.status_code == 200, synced.text
            payload = synced.json()
            assert payload["checked"] == 1
            assert payload["delivered"] == 1
            assert payload["pending"] == 0
            assert payload["deferred"] is False

            board = client.get(
                "/admin/notifications/push-deliveries", headers=owner
            )
            assert board.status_code == 200, board.text
            item = board.json()["items"][0]
            assert item["status"] == "sent"
            assert item["receipt_status"] == "ok"
            assert item["receipt_detail"] is None
            assert item["receipt_at"] is not None

            repeated = client.post(
                "/admin/notifications/push-deliveries/receipts", headers=owner
            )
            assert repeated.json()["checked"] == 0
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_the_panel_flushes_the_error_alert_email(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-push-receipts-secret")
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as seed:
        ensure_default_access_control(seed)
        register_user(
            seed,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        _sent_delivery(seed, sent_at=datetime.now(timezone.utc))

    posted: list[dict[str, object]] = []

    def fake_send_email(**kwargs):
        posted.append(kwargs)
        return "sent"

    monkeypatch.setattr(delivery_module, "send_email", fake_send_email)
    monkeypatch.setattr(
        receipts_module,
        "fetch_expo_receipts",
        lambda ids: {
            TICKET: ExpoReceipt(
                status="error",
                code="MessageTooBig",
                message="The message was too large.",
            )
        },
    )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-correct-horse-battery")
            synced = client.post(
                "/admin/notifications/push-deliveries/receipts", headers=owner
            )
            assert synced.status_code == 200, synced.text
            assert synced.json()["errors"] == 1
    finally:
        app.dependency_overrides.pop(get_session, None)

    # The post-response hook drained the alert the pass had just queued.
    assert [row["recipient"] for row in posted] == ["owner@example.com"]
    assert str(posted[0]["subject"]).startswith("[Avisos] ")
    with Session(engine) as check:
        emails = list(check.exec(select(StaffNotificationDelivery)).all())
        assert len(emails) == 1
        assert emails[0].status == "sent"
    engine.dispose()
