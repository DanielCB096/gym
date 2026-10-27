from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.classes import (
    InvalidReservationState,
    ReservationNotFound,
    SessionFull,
    create_class_room,
    create_class_session,
    create_class_type,
    reserve_seat,
)
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.portal.classes import (
    MemberClassNotAllowed,
    cancel_member_reservation,
    list_member_classes,
    reserve_member_class,
)


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


def _seed_member(
    session: Session,
    *,
    email: str,
    first_name: str = "Ana",
    with_membership: bool = True,
    membership_status: str = "active",
    ends_at: datetime | None = None,
):
    now = datetime.now(timezone.utc)
    member = Member(
        first_name=first_name,
        last_name="Demo",
        email=email,
        status="active",
    )
    session.add(member)
    session.flush()
    if with_membership:
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
                status=membership_status,
                starts_at=(ends_at - timedelta(days=30)) if ends_at else (now - timedelta(days=1)),
                ends_at=ends_at or (now + timedelta(days=29)),
            )
        )
    session.commit()
    return member.id


def _seed_catalog(session: Session) -> tuple[str, str]:
    class_type = create_class_type(session, name="Spinning", description="Ciclismo indoor")
    room = create_class_room(session, name="Salón A", capacity=10)
    return class_type.id, room.id


def _iso(value: datetime) -> str:
    return value.isoformat()


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_member_class_list_reserve_waitlist_and_cancel(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    starts_at = now + timedelta(days=2)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        _seed_member(session, email="ana@example.com")
        _seed_member(session, email="beto@example.com", first_name="Beto")
        _seed_member(session, email="carla@example.com", first_name="Carla", with_membership=False)
        class_type_id, room_id = _seed_catalog(session)
        included = create_class_session(
            session,
            title="Spinning 6am",
            class_type_id=class_type_id,
            room_id=room_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            capacity=1,
        )
        premium = create_class_session(
            session,
            title="Spinning premium",
            class_type_id=class_type_id,
            room_id=room_id,
            starts_at=starts_at + timedelta(hours=3),
            ends_at=starts_at + timedelta(hours=4),
            capacity=5,
            access_type="premium",
            extra_price_cents=5000,
        )
        past = create_class_session(
            session,
            title="Spinning de ayer",
            class_type_id=class_type_id,
            starts_at=now - timedelta(days=1),
            ends_at=now - timedelta(days=1) + timedelta(hours=1),
            capacity=5,
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana_headers = _member_headers(client, "ana@example.com")
            beto_headers = _member_headers(client, "beto@example.com")
            carla_headers = _member_headers(client, "carla@example.com")

            listing = client.get("/member/classes", headers=ana_headers)
            assert listing.status_code == 200, listing.text
            body = listing.json()
            assert body["total"] == 2
            items = {item["id"]: item for item in body["items"]}
            assert str(past.id) not in items

            included_item = items[str(included.id)]
            assert included_item["title"] == "Spinning 6am"
            assert included_item["class_type_name"] == "Spinning"
            assert included_item["room_name"] == "Salón A"
            assert included_item["spots_left"] == 1
            assert included_item["can_reserve"] is True
            assert included_item["blocked_reason"] is None
            assert included_item["reservation"] is None

            premium_item = items[str(premium.id)]
            assert premium_item["can_reserve"] is False
            assert premium_item["blocked_reason"] == "premium_class"

            carla_listing = client.get("/member/classes", headers=carla_headers)
            assert carla_listing.status_code == 200
            carla_items = {item["id"]: item for item in carla_listing.json()["items"]}
            assert carla_items[str(included.id)]["can_reserve"] is False
            assert carla_items[str(included.id)]["blocked_reason"] == "membership_inactive"

            assert (
                client.post(
                    f"/member/classes/sessions/{premium.id}/reservations",
                    headers=ana_headers,
                ).status_code
                == 409
            )
            past_reservation = client.post(
                f"/member/classes/sessions/{past.id}/reservations",
                headers=ana_headers,
            )
            assert past_reservation.status_code == 409
            assert "comenzó" in past_reservation.json()["detail"]

            reserved = client.post(
                f"/member/classes/sessions/{included.id}/reservations",
                headers=ana_headers,
            )
            assert reserved.status_code == 201, reserved.text
            ana_reservation = reserved.json()
            assert ana_reservation["status"] == "reserved"
            assert ana_reservation["waitlist_position"] is None
            assert ana_reservation["late_cancellation"] is False

            duplicate = client.post(
                f"/member/classes/sessions/{included.id}/reservations",
                headers=ana_headers,
            )
            assert duplicate.status_code == 409

            after_reservation = client.get("/member/classes", headers=ana_headers).json()
            ana_item = next(
                item for item in after_reservation["items"] if item["id"] == str(included.id)
            )
            assert ana_item["can_reserve"] is False
            assert ana_item["blocked_reason"] == "already_reserved"
            assert ana_item["reservation"]["id"] == ana_reservation["id"]
            assert ana_item["reservation"]["status"] == "reserved"

            waitlisted = client.post(
                f"/member/classes/sessions/{included.id}/reservations",
                headers=beto_headers,
            )
            assert waitlisted.status_code == 201, waitlisted.text
            assert waitlisted.json()["status"] == "waitlist"
            assert waitlisted.json()["waitlist_position"] == 1

            stolen = client.post(
                f"/member/classes/reservations/{ana_reservation['id']}/cancel",
                headers=beto_headers,
            )
            assert stolen.status_code == 404

            cancelled = client.post(
                f"/member/classes/reservations/{ana_reservation['id']}/cancel",
                headers=ana_headers,
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            assert cancelled.json()["late_cancellation"] is False

            beto_listing = client.get("/member/classes", headers=beto_headers).json()
            beto_item = next(
                item for item in beto_listing["items"] if item["id"] == str(included.id)
            )
            assert beto_item["reservation"]["status"] == "reserved"
            assert beto_item["reservation"]["waitlist_position"] is None

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
            assert client.get("/member/classes", headers=staff_headers).status_code == 401
            assert (
                client.post(
                    f"/member/classes/sessions/{included.id}/reservations",
                    headers=staff_headers,
                ).status_code
                == 401
            )

            inactive_booking = client.post(
                f"/member/classes/sessions/{included.id}/reservations",
                headers=carla_headers,
            )
            assert inactive_booking.status_code == 409
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_member_classes_full_without_waitlist_is_not_bookable(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    ana_id = _seed_member(session, email="ana@example.com")
    beto_id = _seed_member(session, email="beto@example.com", first_name="Beto")
    class_type_id, _ = _seed_catalog(session)
    starts_at = datetime.now(timezone.utc) + timedelta(days=1)
    full = create_class_session(
        session,
        title="Clase llena",
        class_type_id=class_type_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        capacity=1,
        waitlist_enabled=False,
    )
    reserve_seat(session, full.id, member_id=beto_id, origin="reception")

    page = list_member_classes(session, ana_id)
    item = next(item for item in page.items if item.id == full.id)
    assert item.can_reserve is False
    assert item.blocked_reason == "full"
    assert item.spots_left == 0

    with pytest.raises(SessionFull):
        reserve_member_class(session, ana_id, full.id)


def test_member_cannot_cancel_started_class_or_other_member_reservation(
    session: Session, monkeypatch
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    ana_id = _seed_member(session, email="ana@example.com")
    beto_id = _seed_member(session, email="beto@example.com", first_name="Beto")
    class_type_id, _ = _seed_catalog(session)
    starts_at = datetime.now(timezone.utc) + timedelta(hours=2)
    class_session = create_class_session(
        session,
        title="Spinning 6am",
        class_type_id=class_type_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        capacity=5,
    )
    reservation = reserve_member_class(session, ana_id, class_session.id)

    with pytest.raises(ReservationNotFound):
        cancel_member_reservation(session, beto_id, reservation.id)

    with pytest.raises(InvalidReservationState):
        cancel_member_reservation(
            session,
            ana_id,
            reservation.id,
            now=starts_at + timedelta(minutes=5),
        )

    cancelled = cancel_member_reservation(
        session,
        ana_id,
        reservation.id,
        now=starts_at - timedelta(hours=1),
    )
    assert cancelled.status == "cancelled"


def test_expired_membership_blocks_new_reservations(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    now = datetime.now(timezone.utc)
    ana_id = _seed_member(
        session,
        email="ana@example.com",
        ends_at=now - timedelta(days=1),
    )
    class_type_id, _ = _seed_catalog(session)
    starts_at = now + timedelta(days=1)
    class_session = create_class_session(
        session,
        title="Spinning 6am",
        class_type_id=class_type_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        capacity=5,
    )

    page = list_member_classes(session, ana_id)
    item = next(item for item in page.items if item.id == class_session.id)
    assert item.can_reserve is False
    assert item.blocked_reason == "membership_inactive"

    with pytest.raises(MemberClassNotAllowed):
        reserve_member_class(session, ana_id, class_session.id)
