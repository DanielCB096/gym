"""Web Push for the panel's staff accounts.

The browser registers one subscription with its push service; each new notice
queues one delivery per active subscription in the same transaction, and the
post-response pass encrypts and sends it with the club's VAPID key. These tests
cover the subscription validation and transfer, the queue built with the
notice, the pass in preview mode, the retirement of a browser the push service
reports as gone, the manual retry and the API permissions.
"""

import base64
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.models import AppUser
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications import webpush as webpush_module
from app.modules.notifications.models import (
    StaffPushDelivery,
    StaffPushSubscription,
)
from app.modules.notifications.service import create_staff_notification
from app.modules.notifications.webpush import (
    InvalidPushSubscription,
    StaffPushDeliveryNotFound,
    StaffPushDeliveryRetryNotAllowed,
    StaffPushError,
    StaffPushSendResult,
    StaffPushSubscriptionNotFound,
    WebPushDeliveryFailed,
    WebPushSubscriptionGone,
    deactivate_staff_push_subscription,
    list_staff_push_deliveries,
    list_staff_push_subscriptions,
    read_staff_push_config,
    register_staff_push_subscription,
    retry_staff_push_delivery,
    send_pending_staff_push_deliveries,
    staff_push_delivery_counts,
)

NOW = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)
ENDPOINT = "https://push.example.com/send/abc123ABCdef"
SENT = StaffPushSendResult(status="sent")


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _keys() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    p256dh = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return _base64url(p256dh), _base64url(os.urandom(16))


def _user(session: Session, *, email: str = "trainer@example.com", status: str = "active") -> UUID:
    ensure_default_access_control(session)
    user = register_user(session, email=email, password="trainer-strong-password", role_codes=("trainer",))
    if status != user.status:
        user.status = status
        session.add(user)
        session.commit()
    return user.id


def _subscribe(session: Session, user_id: UUID, endpoint: str = ENDPOINT) -> StaffPushSubscription:
    p256dh, auth = _keys()
    return register_staff_push_subscription(
        session,
        user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent="Mozilla/5.0 (panel)",
        now=NOW,
    )


def _notice(session: Session, user_id: UUID, *, title: str = "Rutina por revisar") -> None:
    create_staff_notification(
        session,
        user_id=user_id,
        kind="workout_pending_review",
        title=title,
        body="La rutina de Ana espera tu revisión.",
        now=NOW,
    )
    session.commit()


def test_subscription_validation_rejects_bad_endpoints_and_keys(session: Session) -> None:
    user_id = _user(session)
    p256dh, auth = _keys()

    with pytest.raises(InvalidPushSubscription):
        register_staff_push_subscription(
            session, user_id, endpoint="http://evil.example.com/x", p256dh=p256dh, auth=auth
        )
    with pytest.raises(InvalidPushSubscription):
        register_staff_push_subscription(
            session, user_id, endpoint=ENDPOINT, p256dh="short", auth=auth
        )
    with pytest.raises(InvalidPushSubscription):
        register_staff_push_subscription(
            session, user_id, endpoint=ENDPOINT, p256dh=p256dh, auth=_base64url(b"too-short")
        )
    # Localhost is the only plain-http endpoint the panel accepts (development).
    row = register_staff_push_subscription(
        session,
        user_id,
        endpoint="http://localhost:8010/push/demo",
        p256dh=p256dh,
        auth=auth,
    )
    assert row.endpoint == "http://localhost:8010/push/demo"


def test_the_same_browser_follows_the_account_that_registers_it_last(session: Session) -> None:
    first = _user(session, email="trainer@example.com")
    second = _user(session, email="manager@example.com")
    row = _subscribe(session, first)
    p256dh, auth = _keys()

    transferred = register_staff_push_subscription(
        session, second, endpoint=ENDPOINT, p256dh=p256dh, auth=auth, now=NOW
    )

    assert transferred.id == row.id
    assert transferred.user_id == second
    assert list_staff_push_subscriptions(session, first) == []
    assert [item.id for item in list_staff_push_subscriptions(session, second)] == [row.id]


def test_deactivation_only_touches_the_owner(session: Session) -> None:
    owner = _user(session, email="trainer@example.com")
    other = _user(session, email="manager@example.com")
    row = _subscribe(session, owner)

    with pytest.raises(StaffPushSubscriptionNotFound):
        deactivate_staff_push_subscription(session, other, row.id)

    item = deactivate_staff_push_subscription(session, owner, row.id, now=NOW)
    assert item.active is False
    assert item.deactivated_at is not None


def test_each_new_notice_queues_one_delivery_per_active_browser(session: Session) -> None:
    user_id = _user(session)
    retired = _subscribe(session, user_id, endpoint="https://push.example.com/send/old000")
    deactivate_staff_push_subscription(session, user_id, retired.id)
    _subscribe(session, user_id)

    _notice(session, user_id)
    deliveries = session.exec(select(StaffPushDelivery)).all()
    assert len(deliveries) == 1
    assert deliveries[0].status == "pending"
    assert deliveries[0].attempts == 0
    assert deliveries[0].endpoint == ENDPOINT

    # A deduplicated replay returns the existing notice and queues nothing new.
    create_staff_notification(
        session,
        user_id=user_id,
        kind="workout_pending_review",
        title="Rutina por revisar",
        body="La rutina de Ana espera tu revisión.",
        dedupe_key="routine-1",
        now=NOW,
    )
    create_staff_notification(
        session,
        user_id=user_id,
        kind="workout_pending_review",
        title="Rutina por revisar",
        body="La rutina de Ana espera tu revisión.",
        dedupe_key="routine-1",
        now=NOW,
    )
    assert len(session.exec(select(StaffPushDelivery)).all()) == 2


def test_a_suspended_account_queues_no_push(session: Session) -> None:
    user_id = _user(session, status="active")
    _subscribe(session, user_id)
    user = session.get(AppUser, user_id)
    assert user is not None
    user.status = "disabled"
    session.add(user)
    session.commit()

    _notice(session, user_id)
    assert session.exec(select(StaffPushDelivery)).all() == []


def test_the_pass_simulates_in_preview_mode(session: Session, monkeypatch) -> None:
    user_id = _user(session)
    _subscribe(session, user_id)
    _notice(session, user_id)
    monkeypatch.setattr(webpush_module, "preview_mode", lambda: True)

    result = send_pending_staff_push_deliveries(session, now=NOW)

    assert (result.attempted, result.sent, result.simulated, result.failed) == (1, 0, 1, 0)
    delivery = session.exec(select(StaffPushDelivery)).one()
    assert delivery.status == "simulated"
    assert delivery.attempts == 1
    assert delivery.sent_at is not None

    # A simulated delivery is not retried: the pass only picks up pending rows.
    again = send_pending_staff_push_deliveries(session, now=NOW)
    assert again.attempted == 0


def test_a_failed_push_waits_for_the_operator(session: Session, monkeypatch) -> None:
    user_id = _user(session)
    _subscribe(session, user_id)
    _notice(session, user_id)

    def broken(**_kwargs) -> StaffPushSendResult:
        raise WebPushDeliveryFailed("El servicio de notificaciones respondió 503.")

    monkeypatch.setattr(webpush_module, "preview_mode", lambda: False)
    monkeypatch.setattr(webpush_module, "send_staff_web_push", broken)
    result = send_pending_staff_push_deliveries(session, now=NOW)

    assert (result.attempted, result.failed, result.deactivated) == (1, 1, 0)
    delivery = session.exec(select(StaffPushDelivery)).one()
    assert delivery.status == "failed"
    assert "503" in (delivery.error or "")

    # No automatic retry: the next pass has nothing pending.
    assert send_pending_staff_push_deliveries(session, now=NOW).attempted == 0

    monkeypatch.setattr(
        webpush_module, "send_staff_web_push", lambda **_kwargs: SENT
    )
    retried = retry_staff_push_delivery(session, delivery.id, now=NOW)
    assert retried.status == "sent"
    assert retried.attempts == 2
    assert retried.error is None

    with pytest.raises(StaffPushDeliveryRetryNotAllowed):
        retry_staff_push_delivery(session, delivery.id, now=NOW)
    with pytest.raises(StaffPushDeliveryNotFound):
        retry_staff_push_delivery(session, uuid4(), now=NOW)


def test_a_browser_the_service_reports_gone_is_retired(session: Session, monkeypatch) -> None:
    user_id = _user(session)
    row = _subscribe(session, user_id)
    _notice(session, user_id)

    def gone(**_kwargs) -> StaffPushSendResult:
        raise WebPushSubscriptionGone("El navegador ya no recibe notificaciones.")

    monkeypatch.setattr(webpush_module, "preview_mode", lambda: False)
    monkeypatch.setattr(webpush_module, "send_staff_web_push", gone)
    result = send_pending_staff_push_deliveries(session, now=NOW)

    assert (result.failed, result.deactivated) == (1, 1)
    assert session.get(StaffPushSubscription, row.id).active is False
    assert staff_push_delivery_counts(session).active_subscriptions == 0


def test_the_queue_lists_the_masked_device_and_its_counts(session: Session) -> None:
    user_id = _user(session)
    _subscribe(session, user_id)
    _notice(session, user_id)

    board = list_staff_push_deliveries(session)
    assert board.total == 1
    item = board.items[0]
    assert item.user_name == "trainer@example.com"
    assert item.device.startswith("push.example.com/…")
    assert ENDPOINT not in item.device
    assert item.kind == "workout_pending_review"
    assert item.status == "pending"

    counts = staff_push_delivery_counts(session)
    assert (counts.pending, counts.sent, counts.simulated, counts.failed) == (1, 0, 0, 0)
    assert counts.active_subscriptions == 1

    with pytest.raises(StaffPushError):
        list_staff_push_deliveries(session, status_filter="bogus")
    assert list_staff_push_deliveries(session, status_filter="failed").total == 0


def test_configuration_is_off_without_the_vapid_key(monkeypatch) -> None:
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    config = read_staff_push_config()
    assert config.enabled is False
    assert config.public_key is None

    monkeypatch.setenv("VAPID_PRIVATE_KEY", _base64url(b"too-short"))
    assert read_staff_push_config().enabled is False

    monkeypatch.setenv("VAPID_PRIVATE_KEY", _base64url(os.urandom(32)))
    monkeypatch.setenv("VAPID_SUBJECT", "not-a-subject")
    assert read_staff_push_config().enabled is False

    monkeypatch.setenv("VAPID_SUBJECT", "mailto:avisos@centro-fit.local")
    enabled = read_staff_push_config()
    assert enabled.enabled is True
    assert enabled.public_key is not None
    assert len(enabled.public_key) == 87


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


def _seed_api(engine) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    with Session(engine) as session:
        ensure_default_access_control(session)
        ids["owner"] = register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        ).id
        ids["trainer"] = register_user(
            session,
            email="trainer@example.com",
            password="trainer-correct-horse-battery",
            role_codes=("trainer",),
        ).id
        ids["maintenance"] = register_user(
            session,
            email="maintenance@example.com",
            password="maintenance-correct-horse-battery",
            role_codes=("maintenance",),
        ).id
        p256dh, auth = _keys()
        register_staff_push_subscription(
            session,
            ids["trainer"],
            endpoint=ENDPOINT,
            p256dh=p256dh,
            auth=auth,
            now=NOW,
        )
        _notice(session, ids["trainer"])
    return ids


def test_staff_push_api(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-staff-push-secret")
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    _seed_api(engine)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
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

            config = client.get("/admin/staff/push/config", headers=trainer)
            assert config.status_code == 200
            assert config.json() == {"enabled": False, "public_key": None, "subject": None}

            monkeypatch.setenv("VAPID_PRIVATE_KEY", _base64url(os.urandom(32)))
            enabled = client.get("/admin/staff/push/config", headers=trainer).json()
            assert enabled["enabled"] is True
            assert enabled["subject"] == "mailto:avisos@centro-fit.local"
            assert len(enabled["public_key"]) == 87

            listed = client.get("/admin/staff/push/subscriptions", headers=trainer)
            assert listed.status_code == 200
            devices = listed.json()
            assert len(devices) == 1
            assert devices[0]["device"].startswith("push.example.com/…")
            assert ENDPOINT not in devices[0]["device"]
            assert devices[0]["active"] is True

            # Registering the same browser again from another account moves it.
            p256dh, auth = _keys()
            moved = client.post(
                "/admin/staff/push/subscriptions",
                headers=owner,
                json={
                    "endpoint": ENDPOINT,
                    "keys": {"p256dh": p256dh, "auth": auth},
                    "user_agent": "Firefox/140",
                },
            )
            assert moved.status_code == 201, moved.text
            assert moved.json()["user_agent"] == "Firefox/140"
            assert client.get("/admin/staff/push/subscriptions", headers=trainer).json() == []
            owner_devices = client.get("/admin/staff/push/subscriptions", headers=owner).json()
            assert [item["id"] for item in owner_devices] == [moved.json()["id"]]

            bad = client.post(
                "/admin/staff/push/subscriptions",
                headers=trainer,
                json={
                    "endpoint": "http://evil.example.com/x",
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
            )
            assert bad.status_code == 422

            # The queue is read with attendance.read and drained with manage.
            assert client.get("/admin/staff/push/deliveries", headers=maintenance).status_code == 403
            assert client.get("/admin/staff/push/deliveries", headers=trainer).status_code == 200
            assert client.get(
                "/admin/staff/push/deliveries?status=bogus", headers=owner
            ).status_code == 422
            assert client.post("/admin/staff/push/deliveries/send", headers=trainer).status_code == 403

            board = client.get("/admin/staff/push/deliveries", headers=owner).json()
            assert board["enabled"] is True
            assert board["counts"] == {
                "pending": 1,
                "sent": 0,
                "simulated": 0,
                "failed": 0,
                "active_subscriptions": 1,
            }
            assert board["items"][0]["user_email"] == "trainer@example.com"
            assert board["items"][0]["status"] == "pending"

            monkeypatch.setattr(
                webpush_module,
                "send_staff_web_push",
                lambda **_kwargs: StaffPushSendResult(status="simulated"),
            )
            sent = client.post("/admin/staff/push/deliveries/send", headers=owner)
            assert sent.status_code == 200, sent.text
            assert sent.json() == {
                "attempted": 1,
                "sent": 0,
                "simulated": 1,
                "failed": 0,
                "deactivated": 0,
                "remaining": 0,
                "enabled": True,
            }

            delivery_id = board["items"][0]["id"]
            assert client.post(
                f"/admin/staff/push/deliveries/{delivery_id}/retry", headers=owner
            ).status_code == 409
            assert client.post(
                f"/admin/staff/push/deliveries/{uuid4()}/retry", headers=owner
            ).status_code == 404

            unsubscribed = client.delete(
                f"/admin/staff/push/subscriptions/{moved.json()['id']}", headers=trainer
            )
            assert unsubscribed.status_code == 404
            assert client.delete(
                f"/admin/staff/push/subscriptions/{moved.json()['id']}", headers=owner
            ).status_code == 204
            left = client.get("/admin/staff/push/subscriptions", headers=owner).json()
            assert left[0]["active"] is False
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
