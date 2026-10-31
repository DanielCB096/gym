"""Panel queue for the member push channel.

The push rows are written with the notice, but until this cut nobody could see
them: a failed push sat in the table with no screen and no way to retry. These
tests cover the listing (token masked, member and notice joined), the counts and
the manual retry, which keeps the attempt history and never duplicates a row.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member
from app.modules.notifications import push as push_module
from app.modules.notifications.models import (
    MemberNotification,
    MemberPushDelivery,
    MemberPushToken,
)
from app.modules.notifications.push import (
    PushDeliveryFailed,
    PushDeliveryNotFound,
    PushDeliveryRetryNotAllowed,
    PushError,
    PushTokenUnregistered,
    list_member_push_deliveries,
    mask_push_token,
    member_push_delivery_counts,
    register_member_push_token,
    retry_member_push_delivery,
    send_pending_member_push_deliveries,
)
from app.modules.notifications.service import create_notification

NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)
TOKEN_A = "ExponentPushToken[aaaAAA111]"


def _member(session: Session, *, email: str = "ana@example.test") -> Member:
    member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def _queue(session: Session, member: Member, *, title: str = "Reserva confirmada") -> None:
    create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title=title,
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()


def test_the_token_is_masked_for_the_panel() -> None:
    assert mask_push_token(TOKEN_A) == "…A111"
    assert mask_push_token("ExpoPushToken[bbbBBB222]") == "…B222"
    assert mask_push_token("abc") == "…"
    assert mask_push_token("ExponentPushToken[abc]") == "…"


def test_listing_and_counts_expose_the_queue(session: Session) -> None:
    member = _member(session)
    register_member_push_token(session, member.id, token=TOKEN_A, platform="ios", now=NOW)
    _queue(session, member)

    counts = member_push_delivery_counts(session)
    assert (counts.pending, counts.sent, counts.simulated, counts.failed) == (1, 0, 0, 0)
    assert counts.active_tokens == 1

    board = list_member_push_deliveries(session)
    assert board.total == 1
    item = board.items[0]
    assert item.member_name == "Ana Demo"
    assert item.member_email == "ana@example.test"
    assert item.kind == "class_reserved"
    assert item.title == "Reserva confirmada"
    assert item.device == "…A111"
    assert TOKEN_A not in item.device
    assert item.status == "pending"
    assert item.attempts == 0
    assert item.sent_at is None

    with pytest.raises(PushError):
        list_member_push_deliveries(session, status_filter="bogus")

    sent_board = list_member_push_deliveries(session, status_filter="sent")
    assert sent_board.total == 0


def test_retry_only_accepts_a_failed_delivery(session: Session, monkeypatch) -> None:
    member = _member(session)
    register_member_push_token(session, member.id, token=TOKEN_A, platform="android", now=NOW)
    _queue(session, member)

    def broken(**_kwargs) -> str:
        raise PushDeliveryFailed("El servicio de notificaciones respondió 503.")

    monkeypatch.setattr(push_module, "send_expo_push", broken)
    send_pending_member_push_deliveries(session, now=NOW)
    failed = session.exec(select(MemberPushDelivery)).one()
    assert failed.status == "failed"

    calls: list[dict[str, object]] = []

    def working(**kwargs) -> str:
        calls.append(kwargs)
        return "sent"

    monkeypatch.setattr(push_module, "send_expo_push", working)
    retried = retry_member_push_delivery(session, failed.id, now=NOW)

    assert retried.status == "sent"
    assert retried.attempts == 2
    assert retried.error is None
    assert retried.sent_at is not None
    assert len(calls) == 1
    assert calls[0]["token"] == TOKEN_A
    assert session.exec(select(MemberPushDelivery)).one().status == "sent"

    with pytest.raises(PushDeliveryRetryNotAllowed):
        retry_member_push_delivery(session, failed.id, now=NOW)
    with pytest.raises(PushDeliveryNotFound):
        retry_member_push_delivery(session, uuid4(), now=NOW)


def test_retrying_an_uninstalled_app_retires_the_token(session: Session, monkeypatch) -> None:
    member = _member(session)
    register_member_push_token(session, member.id, token=TOKEN_A, platform="ios", now=NOW)
    _queue(session, member)

    def broken(**_kwargs) -> str:
        raise PushDeliveryFailed("El servicio de notificaciones respondió 503.")

    monkeypatch.setattr(push_module, "send_expo_push", broken)
    send_pending_member_push_deliveries(session, now=NOW)
    failed = session.exec(select(MemberPushDelivery)).one()

    def uninstalled(**_kwargs) -> str:
        raise PushTokenUnregistered("La app ya no está instalada.")

    monkeypatch.setattr(push_module, "send_expo_push", uninstalled)
    retried = retry_member_push_delivery(session, failed.id, now=NOW)

    assert retried.status == "failed"
    assert retried.attempts == 2
    assert "ya no está instalada" in (retried.error or "")
    token = session.exec(select(MemberPushToken)).one()
    assert token.active is False
    assert member_push_delivery_counts(session).active_tokens == 0


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


def _seed(engine) -> None:
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        register_user(
            session,
            email="trainer@example.com",
            password="trainer-correct-horse-battery",
            role_codes=("trainer",),
        )
        register_user(
            session,
            email="maintenance@example.com",
            password="maintenance-correct-horse-battery",
            role_codes=("maintenance",),
        )
        member = Member(
            first_name="Ana", last_name="Demo", email="ana@example.com", status="active"
        )
        session.add(member)
        session.commit()
        register_member_push_token(
            session, member.id, token=TOKEN_A, platform="ios", now=NOW
        )
        _queue(session, member)


def test_push_delivery_queue_api(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-push-queue-secret")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    _seed(engine)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    def broken(**_kwargs) -> str:
        raise PushDeliveryFailed("El servicio de notificaciones respondió 503.")

    monkeypatch.setattr(push_module, "send_expo_push", broken)
    try:
        with TestClient(app) as client:

            def headers(email: str, password: str) -> dict[str, str]:
                response = client.post(
                    "/auth/login", json={"email": email, "password": password}
                )
                assert response.status_code == 200, response.text
                return {"Authorization": f"Bearer {response.json()['access_token']}"}

            owner = headers("owner@example.com", "owner-correct-horse-battery")
            trainer = headers("trainer@example.com", "trainer-correct-horse-battery")
            maintenance = headers(
                "maintenance@example.com", "maintenance-correct-horse-battery"
            )

            board = client.get("/admin/notifications/push-deliveries", headers=owner)
            assert board.status_code == 200, board.text
            payload = board.json()
            assert payload["counts"] == {
                "pending": 1,
                "sent": 0,
                "simulated": 0,
                "failed": 0,
                "active_tokens": 1,
            }
            assert payload["total"] == 1
            item = payload["items"][0]
            assert item["member_name"] == "Ana Demo"
            assert item["member_email"] == "ana@example.com"
            assert item["kind"] == "class_reserved"
            assert item["device"] == "…A111"
            assert item["status"] == "pending"

            # Reading needs attendance.read; draining and retrying attendance.manage.
            assert client.get(
                "/admin/notifications/push-deliveries", headers=trainer
            ).status_code == 200
            assert client.get(
                "/admin/notifications/push-deliveries", headers=maintenance
            ).status_code == 403
            assert client.post(
                "/admin/notifications/push-deliveries/send", headers=trainer
            ).status_code == 403
            assert client.post(
                f"/admin/notifications/push-deliveries/{uuid4()}/retry",
                headers=maintenance,
            ).status_code == 403

            assert client.get(
                "/admin/notifications/push-deliveries?status=bogus", headers=owner
            ).status_code == 422

            sent = client.post("/admin/notifications/push-deliveries/send", headers=owner)
            assert sent.status_code == 200, sent.text
            assert sent.json() == {
                "attempted": 1,
                "sent": 0,
                "simulated": 0,
                "failed": 1,
                "deactivated": 0,
                "remaining": 0,
            }

            failed_board = client.get(
                "/admin/notifications/push-deliveries?status=failed", headers=owner
            )
            assert failed_board.status_code == 200
            failed_item = failed_board.json()["items"][0]
            assert failed_item["status"] == "failed"
            assert "503" in failed_item["error"]
            assert failed_item["sent_at"] is None

            assert client.post(
                f"/admin/notifications/push-deliveries/{uuid4()}/retry", headers=owner
            ).status_code == 404

            def working(**_kwargs) -> str:
                return "sent"

            monkeypatch.setattr(push_module, "send_expo_push", working)
            retried = client.post(
                f"/admin/notifications/push-deliveries/{failed_item['id']}/retry",
                headers=owner,
            )
            assert retried.status_code == 200, retried.text
            assert retried.json()["status"] == "sent"
            assert retried.json()["attempts"] == 2
            assert retried.json()["error"] is None
            assert retried.json()["sent_at"] is not None

            # A sent row is final; an empty pass is a no-op.
            assert client.post(
                f"/admin/notifications/push-deliveries/{failed_item['id']}/retry",
                headers=owner,
            ).status_code == 409
            empty = client.post(
                "/admin/notifications/push-deliveries/send", headers=owner
            )
            assert empty.status_code == 200
            assert empty.json()["attempted"] == 0
    finally:
        app.dependency_overrides.pop(get_session, None)

    with Session(engine) as session:
        assert session.exec(select(MemberNotification)).one().kind == "class_reserved"
        assert session.exec(select(MemberPushDelivery)).one().status == "sent"

    engine.dispose()
