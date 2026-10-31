"""Push notifications for the member app.

The inbox already holds every notice; the push queue is the part that rings the
phone. A token belongs to one installation and follows the account that signed
in last, each notice queues one row per active device, and a device Expo reports
as uninstalled is retired instead of retried forever.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.classes import create_class_room, create_class_session, create_class_type
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.notifications import push as push_module
from app.modules.notifications.models import (
    MemberNotification,
    MemberPushDelivery,
    MemberPushToken,
)
from app.modules.notifications.push import (
    InvalidPushPlatform,
    InvalidPushToken,
    PushDeliveryFailed,
    PushMemberNotFound,
    PushTokenUnregistered,
    clean_push_token,
    deactivate_member_push_token,
    register_member_push_token,
    send_pending_member_push_deliveries,
)
from app.modules.notifications.service import create_notification

NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)
TOKEN_A = "ExponentPushToken[aaaAAA111]"
TOKEN_B = "ExpoPushToken[bbbBBB222]"
TOKEN_C = "ExponentPushToken[cccCCC333]"


def _member(session: Session, *, email: str) -> Member:
    member = Member(
        first_name="Ana", last_name="Demo", email=email, status="active"
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def test_a_token_is_validated_and_registered(session: Session) -> None:
    member = _member(session, email="ana@example.test")

    for raw in (
        "",
        "ExponentPushToken[]",
        "ExponentPushToken[con espacio]",
        "OtroFormato[abc]",
        "ExponentPushToken[" + "a" * 300 + "]",
    ):
        with pytest.raises(InvalidPushToken):
            clean_push_token(raw)
    assert clean_push_token(f"  {TOKEN_A}  ") == TOKEN_A

    with pytest.raises(InvalidPushPlatform):
        register_member_push_token(
            session, member.id, token=TOKEN_A, platform="windows", now=NOW
        )
    with pytest.raises(PushMemberNotFound):
        register_member_push_token(
            session, uuid4(), token=TOKEN_A, platform="ios", now=NOW
        )

    row = register_member_push_token(
        session, member.id, token=TOKEN_A, platform="ios", now=NOW
    )
    assert row.active is True
    assert row.platform == "ios"
    assert row.last_seen_at.replace(tzinfo=timezone.utc) == NOW
    assert row.deactivated_at is None


def test_the_token_follows_the_account_that_signed_in_last(session: Session) -> None:
    ana = _member(session, email="ana@example.test")
    beto = _member(session, email="beto@example.test")

    first = register_member_push_token(
        session, ana.id, token=TOKEN_A, platform="ios", now=NOW
    )
    moved = register_member_push_token(
        session,
        beto.id,
        token=TOKEN_A,
        platform="android",
        now=NOW + timedelta(minutes=1),
    )
    assert moved.id == first.id
    assert moved.member_id == beto.id
    assert moved.platform == "android"
    assert len(session.exec(select(MemberPushToken)).all()) == 1

    create_notification(
        session,
        member_id=ana.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()
    assert session.exec(select(MemberPushDelivery)).all() == []


def test_one_push_is_queued_per_active_device(session: Session) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN_A, platform="ios", now=NOW)
    register_member_push_token(
        session, member.id, token=TOKEN_B, platform="android", now=NOW
    )
    register_member_push_token(
        session, member.id, token=TOKEN_C, platform="android", now=NOW
    )
    assert deactivate_member_push_token(session, member.id, TOKEN_C, now=NOW) is True

    notice = create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()

    deliveries = session.exec(select(MemberPushDelivery)).all()
    assert {row.token for row in deliveries} == {TOKEN_A, TOKEN_B}
    assert all(row.notification_id == notice.id for row in deliveries)
    assert all(row.status == "pending" for row in deliveries)


def test_a_replayed_notice_does_not_queue_twice(session: Session) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN_A, platform="ios", now=NOW)

    def notice():
        return create_notification(
            session,
            member_id=member.id,
            kind="membership_expiring",
            title="Tu membresía está por vencer",
            body="Te quedan 2 días de acceso.",
            dedupe_key="membership-expiring:2026-10-30",
            now=NOW,
        )

    first = notice()
    second = notice()
    session.commit()

    assert second.id == first.id
    assert len(session.exec(select(MemberPushDelivery)).all()) == 1


def test_the_preview_simulates_the_send(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN_A, platform="ios", now=NOW)
    register_member_push_token(
        session, member.id, token=TOKEN_B, platform="android", now=NOW
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

    result = send_pending_member_push_deliveries(session, now=NOW)

    assert result.attempted == 2
    assert result.simulated == 2
    assert result.remaining == 0
    deliveries = session.exec(select(MemberPushDelivery)).all()
    assert {row.status for row in deliveries} == {"simulated"}
    assert all(row.attempts == 1 for row in deliveries)
    assert all(
        row.sent_at is not None
        and row.sent_at.replace(tzinfo=timezone.utc) == NOW
        for row in deliveries
    )


def test_an_uninstalled_app_retires_the_token(session: Session, monkeypatch) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN_A, platform="ios", now=NOW)
    create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()

    def uninstalled(**_kwargs) -> str:
        raise PushTokenUnregistered("La app ya no está instalada.")

    monkeypatch.setattr(push_module, "send_expo_push", uninstalled)
    result = send_pending_member_push_deliveries(session, now=NOW)

    assert result.deactivated == 1
    assert result.failed == 1
    token = session.exec(select(MemberPushToken)).one()
    assert token.active is False
    assert token.deactivated_at is not None
    assert token.deactivated_at.replace(tzinfo=timezone.utc) == NOW
    delivery = session.exec(select(MemberPushDelivery)).one()
    assert delivery.status == "failed"
    assert "ya no está instalada" in (delivery.error or "")


def test_a_failed_push_keeps_the_device(session: Session, monkeypatch) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN_A, platform="ios", now=NOW)
    create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()

    def unavailable(**_kwargs) -> str:
        raise PushDeliveryFailed("El servicio de notificaciones respondió 503.")

    monkeypatch.setattr(push_module, "send_expo_push", unavailable)
    result = send_pending_member_push_deliveries(session, now=NOW)

    assert result.failed == 1
    assert result.deactivated == 0
    assert session.exec(select(MemberPushToken)).one().active is True
    assert session.exec(select(MemberPushDelivery)).one().status == "failed"


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


def _seed_member(session: Session, *, email: str, ends_in: timedelta) -> UUID:
    now = datetime.now(timezone.utc)
    member = Member(
        first_name="Ana", last_name="Demo", email=email, status="active"
    )
    session.add(member)
    session.flush()
    plan = Plan(
        code=f"PLAN-{uuid4().hex[:8].upper()}",
        name="Mensual",
        duration_days=30,
        price_cents=50000,
    )
    session.add(plan)
    session.flush()
    session.add(
        Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="active",
            starts_at=now - timedelta(days=5),
            ends_at=now + ends_in,
        )
    )
    session.commit()
    return member.id


def _prepare() -> tuple[object, dict[str, UUID]]:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    ids: dict[str, UUID] = {}
    with Session(engine) as session:
        ids["ana"] = _seed_member(
            session, email="ana@example.com", ends_in=timedelta(days=2)
        )
        class_type = create_class_type(
            session, name="Spinning", description="Ciclismo indoor"
        )
        room = create_class_room(session, name="Salón A", capacity=10)
        session_row = create_class_session(
            session,
            title="Spinning 6am",
            class_type_id=class_type.id,
            room_id=room.id,
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=1),
            capacity=5,
        )
        ids["class"] = session_row.id
    return engine, ids


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _session_override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def test_the_device_registers_and_the_notice_rings_it(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-push-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana@example.com")

            registered = client.post(
                "/member/push-tokens",
                headers=ana,
                json={"token": TOKEN_A, "platform": "ios"},
            )
            assert registered.status_code == 201, registered.text
            assert registered.json()["active"] is True
            assert registered.json()["platform"] == "ios"

            invalid = client.post(
                "/member/push-tokens",
                headers=ana,
                json={"token": "no-es-un-token", "platform": "ios"},
            )
            assert invalid.status_code == 422
            wrong_platform = client.post(
                "/member/push-tokens",
                headers=ana,
                json={"token": TOKEN_B, "platform": "windows"},
            )
            assert wrong_platform.status_code == 422

            # Reading the inbox materialises the expiring reminder without a
            # push: the member is already looking at it.
            inbox = client.get("/member/notifications", headers=ana)
            assert inbox.status_code == 200, inbox.text
            assert inbox.json()["items"][0]["kind"] == "membership_expiring"

            reserved = client.post(
                f"/member/classes/sessions/{ids['class']}/reservations", headers=ana
            )
            assert reserved.status_code == 201, reserved.text
    finally:
        app.dependency_overrides.pop(get_session, None)

    with Session(engine) as session:
        kinds = {row.kind for row in session.exec(select(MemberNotification)).all()}
        assert "class_reserved" in kinds
        assert "membership_expiring" in kinds
        deliveries = session.exec(select(MemberPushDelivery)).all()
        assert [row.status for row in deliveries] == ["simulated"]
        notice = session.get(MemberNotification, deliveries[0].notification_id)
        assert notice is not None and notice.kind == "class_reserved"
        assert deliveries[0].token == TOKEN_A

    engine.dispose()


def test_signing_out_silences_every_device(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-push-logout-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine, _ = _prepare()
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana@example.com")
            for token in (TOKEN_A, TOKEN_B):
                created = client.post(
                    "/member/push-tokens",
                    headers=ana,
                    json={"token": token, "platform": "android"},
                )
                assert created.status_code == 201, created.text

            logout = client.post("/member/auth/logout", headers=ana)
            assert logout.status_code == 204, logout.text
    finally:
        app.dependency_overrides.pop(get_session, None)

    with Session(engine) as session:
        tokens = session.exec(select(MemberPushToken)).all()
        assert len(tokens) == 2
        assert all(row.active is False for row in tokens)
        assert all(row.deactivated_at is not None for row in tokens)

    engine.dispose()
