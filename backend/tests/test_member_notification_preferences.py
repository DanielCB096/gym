"""The member's push switches, one per category of notice.

The inbox keeps everything; a switch only decides whether a notice also rings
the phone. These tests pin the category map, the defaults, the per-member
isolation and the fact that muting cancels what is already waiting without
erasing the notice or the delivery history.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, select

from app.main import app, get_session
from app.modules.memberships.models import Member
from app.modules.notifications.models import (
    MEMBER_NOTIFICATION_CATEGORIES,
    NOTIFICATION_CATEGORY_BY_KIND,
    NOTIFICATION_KINDS,
    MemberNotification,
    MemberNotificationPreference,
    MemberPushDelivery,
)
from app.modules.notifications.preferences import (
    PreferenceError,
    PreferenceMemberNotFound,
    UnknownNotificationCategory,
    category_for_kind,
    is_push_enabled,
    list_member_preferences,
    update_member_preferences,
)
from app.modules.notifications.push import register_member_push_token
from app.modules.notifications.service import create_notification

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)
TOKEN = "ExponentPushToken[prefsAAA111]"


def _member(session: Session, *, email: str) -> Member:
    member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def _reserve(session: Session, member: Member, *, title: str = "Spinning 6am") -> MemberNotification:
    notice = create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Tu lugar en la clase está confirmado",
        body=f"Ya tienes tu lugar reservado en {title} del 01/11/2026 a las 06:00.",
        now=NOW,
    )
    session.commit()
    return notice


def _invoice(session: Session, member: Member) -> MemberNotification:
    notice = create_notification(
        session,
        member_id=member.id,
        kind="invoice_stamped",
        title="Factura timbrada",
        body="Tu factura A-1 por $500.00 MXN ya está lista.",
        dedupe_key=f"invoice_stamped:{member.id}",
        now=NOW,
    )
    session.commit()
    return notice


def test_every_notice_kind_belongs_to_exactly_one_category() -> None:
    assert set(NOTIFICATION_CATEGORY_BY_KIND) == set(NOTIFICATION_KINDS)
    assert set(NOTIFICATION_CATEGORY_BY_KIND.values()) == set(
        MEMBER_NOTIFICATION_CATEGORIES
    )
    for kind in NOTIFICATION_KINDS:
        assert category_for_kind(kind) in MEMBER_NOTIFICATION_CATEGORIES

    with pytest.raises(PreferenceError):
        category_for_kind("kind_que_no_existe")


def test_a_member_without_rows_has_every_switch_on(session: Session) -> None:
    member = _member(session, email="ana@example.test")

    items = list_member_preferences(session, member.id)

    assert [item.category for item in items] == list(MEMBER_NOTIFICATION_CATEGORIES)
    assert all(item.push_enabled is True for item in items)
    assert all(item.updated_at is None for item in items)
    assert is_push_enabled(session, member.id, "class_reserved") is True


def test_a_partial_update_leaves_the_other_switches_alone(session: Session) -> None:
    member = _member(session, email="ana@example.test")

    update_member_preferences(session, member.id, {"training": False}, now=NOW)
    update_member_preferences(session, member.id, {"billing": False}, now=NOW)

    stored = {
        item.category: item for item in list_member_preferences(session, member.id)
    }
    assert stored["training"].push_enabled is False
    assert stored["billing"].push_enabled is False
    assert stored["classes"].push_enabled is True
    assert stored["training"].updated_at == NOW

    row = session.exec(
        select(MemberNotificationPreference).where(
            MemberNotificationPreference.member_id == member.id,
            MemberNotificationPreference.category == "training",
        )
    ).one()
    assert row.push_enabled is False


def test_an_unknown_category_or_member_is_rejected(session: Session) -> None:
    member = _member(session, email="ana@example.test")

    with pytest.raises(UnknownNotificationCategory):
        update_member_preferences(session, member.id, {"cursos": False})
    with pytest.raises(PreferenceMemberNotFound):
        update_member_preferences(session, UUID(int=0), {"classes": False})


def test_muting_a_category_writes_the_inbox_and_skips_the_push(session: Session) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN, platform="ios", now=NOW)

    _reserve(session, member)
    assert len(session.exec(select(MemberPushDelivery)).all()) == 1

    update_member_preferences(session, member.id, {"classes": False}, now=NOW)
    _reserve(session, member, title="Spinning 7am")

    # Muting also cancels the push the first notice had already queued, and the
    # second notice is written without queueing anything.
    assert len(session.exec(select(MemberNotification)).all()) == 2
    assert session.exec(select(MemberPushDelivery)).all() == []


def test_muting_deletes_only_the_pending_pushes_of_that_category(
    session: Session,
) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN, platform="ios", now=NOW)

    class_notice = _reserve(session, member)
    invoice_notice = _invoice(session, member)
    assert len(session.exec(select(MemberPushDelivery)).all()) == 2

    update_member_preferences(session, member.id, {"classes": False}, now=NOW)

    remaining = session.exec(select(MemberPushDelivery)).all()
    assert len(remaining) == 1
    assert remaining[0].notification_id == invoice_notice.id
    assert session.get(MemberNotification, class_notice.id) is not None


def test_muting_cancels_a_retry_without_erasing_its_history(session: Session) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN, platform="ios", now=NOW)
    _reserve(session, member)

    delivery = session.exec(select(MemberPushDelivery)).one()
    delivery.status = "failed"
    delivery.attempts = 1
    delivery.error = "Expo no respondió."
    delivery.next_attempt_at = NOW + timedelta(minutes=5)
    session.add(delivery)
    session.commit()

    update_member_preferences(session, member.id, {"classes": False}, now=NOW)

    session.refresh(delivery)
    assert delivery.status == "failed"
    assert delivery.error == "Expo no respondió."
    assert delivery.next_attempt_at is None


def test_the_switch_is_per_member(session: Session) -> None:
    ana = _member(session, email="ana@example.test")
    beto = _member(session, email="beto@example.test")
    register_member_push_token(session, ana.id, token=TOKEN, platform="ios", now=NOW)
    register_member_push_token(
        session, beto.id, token="ExpoPushToken[prefsBBB222]", platform="android", now=NOW
    )

    update_member_preferences(session, ana.id, {"classes": False}, now=NOW)
    _reserve(session, ana)
    _reserve(session, beto)

    deliveries = session.exec(select(MemberPushDelivery)).all()
    assert [row.member_id for row in deliveries] == [beto.id]
    assert is_push_enabled(session, ana.id, "class_reserved") is False
    assert is_push_enabled(session, beto.id, "class_reserved") is True


def test_switching_a_category_back_on_resumes_the_pushes(session: Session) -> None:
    member = _member(session, email="ana@example.test")
    register_member_push_token(session, member.id, token=TOKEN, platform="ios", now=NOW)

    update_member_preferences(session, member.id, {"classes": False}, now=NOW)
    _reserve(session, member)
    assert session.exec(select(MemberPushDelivery)).all() == []

    update_member_preferences(session, member.id, {"classes": True}, now=NOW)
    _reserve(session, member, title="Spinning 8am")

    assert len(session.exec(select(MemberPushDelivery)).all()) == 1


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


def _session_override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _prepare(monkeypatch) -> object:
    monkeypatch.setenv("SECRET_KEY", "test-notification-preferences-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _member(session, email="ana@example.com")
    return engine


def test_the_api_returns_every_category(monkeypatch) -> None:
    engine = _prepare(monkeypatch)
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana@example.com")
            response = client.get("/member/notification-preferences", headers=ana)
            assert response.status_code == 200, response.text
            items = response.json()["items"]
            assert [item["category"] for item in items] == list(
                MEMBER_NOTIFICATION_CATEGORIES
            )
            assert all(item["push_enabled"] is True for item in items)
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_the_api_updates_a_switch_and_persists_it(monkeypatch) -> None:
    engine = _prepare(monkeypatch)
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana@example.com")

            off = client.patch(
                "/member/notification-preferences",
                headers=ana,
                json={"categories": [{"category": "physio", "push_enabled": False}]},
            )
            assert off.status_code == 200, off.text
            stored = {item["category"]: item for item in off.json()["items"]}
            assert stored["physio"]["push_enabled"] is False
            assert stored["physio"]["updated_at"] is not None
            assert stored["classes"]["push_enabled"] is True

            # Repeating the same value is idempotent: the other switches stay put.
            again = client.patch(
                "/member/notification-preferences",
                headers=ana,
                json={"categories": [{"category": "physio", "push_enabled": False}]},
            )
            assert again.status_code == 200, again.text

            reread = client.get("/member/notification-preferences", headers=ana)
            assert reread.status_code == 200, reread.text
            items = {item["category"]: item for item in reread.json()["items"]}
            assert items["physio"]["push_enabled"] is False
            assert items["equipment"]["push_enabled"] is True
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_the_api_rejects_bad_payloads_and_requires_a_session(monkeypatch) -> None:
    engine = _prepare(monkeypatch)
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            anonymous = client.get("/member/notification-preferences")
            assert anonymous.status_code == 401

            ana = _member_headers(client, "ana@example.com")
            empty = client.patch(
                "/member/notification-preferences", headers=ana, json={"categories": []}
            )
            assert empty.status_code == 422

            unknown = client.patch(
                "/member/notification-preferences",
                headers=ana,
                json={"categories": [{"category": "cursos", "push_enabled": False}]},
            )
            assert unknown.status_code == 422

            duplicated = client.patch(
                "/member/notification-preferences",
                headers=ana,
                json={
                    "categories": [
                        {"category": "classes", "push_enabled": False},
                        {"category": "classes", "push_enabled": True},
                    ]
                },
            )
            assert duplicated.status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_muting_through_the_api_stops_the_next_push(monkeypatch) -> None:
    engine = _prepare(monkeypatch)
    app.dependency_overrides[get_session] = _session_override(engine)
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana@example.com")
            registered = client.post(
                "/member/push-tokens",
                headers=ana,
                json={"token": TOKEN, "platform": "ios"},
            )
            assert registered.status_code == 201, registered.text

            muted = client.patch(
                "/member/notification-preferences",
                headers=ana,
                json={"categories": [{"category": "classes", "push_enabled": False}]},
            )
            assert muted.status_code == 200, muted.text
    finally:
        app.dependency_overrides.pop(get_session, None)

    with Session(engine) as session:
        member = session.exec(select(Member)).one()
        notice = create_notification(
            session,
            member_id=member.id,
            kind="class_reserved",
            title="Tu lugar en la clase está confirmado",
            body="Ya tienes tu lugar reservado en Spinning del 01/11/2026 a las 06:00.",
            now=NOW,
        )
        session.commit()
        assert notice is not None
        assert session.exec(select(MemberPushDelivery)).all() == []

    engine.dispose()
