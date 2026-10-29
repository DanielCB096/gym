from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member

FUTURE = datetime(2030, 1, 15, 18, 0, tzinfo=timezone.utc)
PAST = datetime(2020, 1, 15, 18, 0, tzinfo=timezone.utc)


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


def _seed_users(session: Session) -> None:
    ensure_default_access_control(session)
    register_user(
        session,
        email="manager@example.com",
        password="manager-strong-password",
        role_codes=("manager",),
    )
    register_user(
        session,
        email="trainer@example.com",
        password="trainer-strong-password",
        role_codes=("trainer",),
    )
    register_user(
        session,
        email="reception@example.com",
        password="reception-strong-password",
        role_codes=("reception",),
    )
    register_user(
        session,
        email="accountant@example.com",
        password="accountant-strong-password",
        role_codes=("accountant",),
    )


def _add_member(session: Session, *, status: str = "active", first: str = "Socio"):
    member = Member(
        first_name=first,
        last_name="Demo",
        email=f"{uuid4().hex[:10]}@example.com",
        status=status,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member.id


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _iso(value: datetime) -> str:
    return value.isoformat()


def _create_catalog(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    type_response = client.post(
        "/admin/classes/types",
        headers=headers,
        json={"name": "Spinning", "description": "Ciclismo indoor"},
    )
    assert type_response.status_code == 201, type_response.text
    room_response = client.post(
        "/admin/classes/rooms",
        headers=headers,
        json={"name": "Salón A", "capacity": 20},
    )
    assert room_response.status_code == 201, room_response.text
    return type_response.json()["id"], room_response.json()["id"]


def _create_session(
    client: TestClient,
    headers: dict[str, str],
    *,
    class_type_id: str,
    room_id: str | None = None,
    capacity: int = 2,
    starts_at: datetime = FUTURE,
    waitlist_enabled: bool = True,
    title: str = "Spinning 6am",
    access_type: str = "included",
    extra_price_cents: int = 0,
):
    payload = {
        "title": title,
        "class_type_id": class_type_id,
        "starts_at": _iso(starts_at),
        "ends_at": _iso(starts_at + timedelta(hours=1)),
        "capacity": capacity,
        "waitlist_enabled": waitlist_enabled,
        "access_type": access_type,
        "extra_price_cents": extra_price_cents,
    }
    if room_id is not None:
        payload["room_id"] = room_id
    return client.post("/admin/classes/sessions", headers=headers, json=payload)


def test_class_catalog_and_permissions() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            assert client.get("/admin/classes/sessions").status_code == 401

            manager = _login(client, "manager@example.com", "manager-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")

            # The class management matrix is owner/manager/trainer only.
            assert client.get("/admin/classes/sessions", headers=reception).status_code == 403
            assert client.get("/admin/classes/sessions", headers=accountant).status_code == 403
            assert client.post(
                "/admin/classes/types", headers=reception, json={"name": "Yoga"}
            ).status_code == 403
            assert client.get("/admin/classes/sessions", headers=trainer).status_code == 200

            type_id, room_id = _create_catalog(client, manager)
            assert client.post(
                "/admin/classes/types", headers=manager, json={"name": "SPINNING"}
            ).status_code == 409
            assert client.post(
                "/admin/classes/rooms", headers=manager, json={"name": "salón a", "capacity": 10}
            ).status_code == 409
            assert client.post(
                "/admin/classes/rooms", headers=manager, json={"name": "Salón B", "capacity": 0}
            ).status_code == 422

            types = client.get("/admin/classes/types", headers=trainer).json()
            assert [item["name"] for item in types] == ["Spinning"]
            rooms = client.get("/admin/classes/rooms", headers=trainer).json()
            assert rooms[0]["capacity"] == 20
            assert client.get("/admin/classes/instructors", headers=trainer).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_session_creation_validation_and_listing() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            type_id, room_id = _create_catalog(client, manager)

            bad_window = client.post(
                "/admin/classes/sessions",
                headers=manager,
                json={
                    "title": "Mala",
                    "class_type_id": type_id,
                    "starts_at": _iso(FUTURE),
                    "ends_at": _iso(FUTURE),
                    "capacity": 5,
                },
            )
            assert bad_window.status_code == 422

            missing_type = client.post(
                "/admin/classes/sessions",
                headers=manager,
                json={
                    "title": "Sin tipo",
                    "class_type_id": str(uuid4()),
                    "starts_at": _iso(FUTURE),
                    "ends_at": _iso(FUTURE + timedelta(hours=1)),
                    "capacity": 5,
                },
            )
            assert missing_type.status_code == 404

            created = _create_session(client, manager, class_type_id=type_id, room_id=room_id, capacity=3)
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["class_type_name"] == "Spinning"
            assert body["room_name"] == "Salón A"
            assert body["status"] == "scheduled"
            assert body["spots_left"] == 3
            session_id = body["id"]

            directory = client.get("/admin/classes/sessions", headers=manager).json()
            assert directory["total"] == 1
            assert directory["summary"]["scheduled"] == 1
            assert directory["summary"]["cancelled"] == 0
            assert directory["summary"]["upcoming"] == 1

            by_status = client.get("/admin/classes/sessions", headers=manager, params={"status": "cancelled"}).json()
            assert by_status["total"] == 0
            assert client.get(
                "/admin/classes/sessions", headers=manager, params={"search": "spinning"}
            ).json()["total"] == 1

            # Capacity can be edited, but only above the seated reservations.
            patched = client.patch(
                f"/admin/classes/sessions/{session_id}",
                headers=manager,
                json={"title": "Spinning 7am", "capacity": 5},
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["title"] == "Spinning 7am"
            assert patched.json()["capacity"] == 5

            cleared = client.patch(
                f"/admin/classes/sessions/{session_id}",
                headers=manager,
                json={"room_id": None, "notes": "Llevar toalla"},
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["room_id"] is None
            assert cleared.json()["notes"] == "Llevar toalla"
    finally:
        app.dependency_overrides.clear()


def test_capacity_waitlist_promotion_and_attendance() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        first = _add_member(session, first="Ana")
        second = _add_member(session, first="Beto")
        third = _add_member(session, first="Caro")
        fourth = _add_member(session, first="Dora", status="inactive")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            type_id, room_id = _create_catalog(client, manager)
            created = _create_session(client, manager, class_type_id=type_id, room_id=room_id, capacity=2)
            session_id = created.json()["id"]

            def reserve(member_id) -> object:
                return client.post(
                    f"/admin/classes/sessions/{session_id}/reservations",
                    headers=manager,
                    json={"member_id": str(member_id), "origin": "reception"},
                )

            first_reservation = reserve(first)
            assert first_reservation.status_code == 201, first_reservation.text
            assert first_reservation.json()["status"] == "reserved"
            assert reserve(second).json()["status"] == "reserved"

            # Room is full: the next member joins the ordered waitlist.
            waitlisted = reserve(third)
            assert waitlisted.status_code == 201, waitlisted.text
            assert waitlisted.json()["status"] == "waitlist"
            assert waitlisted.json()["waitlist_position"] == 1

            # Same member cannot hold two live reservations.
            assert reserve(first).status_code == 409
            # Unknown or inactive members are rejected.
            assert reserve(uuid4()).status_code == 404
            assert reserve(fourth).status_code == 404

            roster = client.get(
                f"/admin/classes/sessions/{session_id}/reservations", headers=manager
            ).json()
            assert roster["session"]["reserved_count"] == 2
            assert roster["session"]["waitlist_count"] == 1
            assert roster["session"]["spots_left"] == 0
            assert [item["status"] for item in roster["reservations"]] == [
                "reserved",
                "reserved",
                "waitlist",
            ]

            # Cancelling a seat promotes the first member of the waitlist.
            cancelled = client.post(
                f"/admin/classes/reservations/{first_reservation.json()['id']}/cancel",
                headers=manager,
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"

            roster = client.get(
                f"/admin/classes/sessions/{session_id}/reservations", headers=manager
            ).json()
            statuses = {item["member_name"]: item["status"] for item in roster["reservations"]}
            assert statuses["Caro Demo"] == "reserved"
            assert roster["session"]["waitlist_count"] == 0
            assert roster["session"]["reserved_count"] == 2

            # Attendance can only be marked on a confirmed seat.
            promoted = next(item for item in roster["reservations"] if item["member_name"] == "Caro Demo")
            assert client.post(
                f"/admin/classes/reservations/{promoted['id']}/attendance",
                headers=manager,
                json={"attended": True},
            ).json()["status"] == "attended"

            attended = next(item for item in roster["reservations"] if item["member_name"] == "Beto Demo")
            assert client.post(
                f"/admin/classes/reservations/{attended['id']}/attendance",
                headers=manager,
                json={"attended": False},
            ).json()["status"] == "no_show"
    finally:
        app.dependency_overrides.clear()


def test_waitlist_disabled_late_cancellation_and_session_cancel() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        first = _add_member(session, first="Ana")
        second = _add_member(session, first="Beto")
        third = _add_member(session, first="Caro")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            type_id, _ = _create_catalog(client, manager)

            closed = _create_session(
                client, manager, class_type_id=type_id, capacity=1, waitlist_enabled=False
            )
            closed_id = closed.json()["id"]
            assert client.post(
                f"/admin/classes/sessions/{closed_id}/reservations",
                headers=manager,
                json={"member_id": str(first)},
            ).status_code == 201
            assert client.post(
                f"/admin/classes/sessions/{closed_id}/reservations",
                headers=manager,
                json={"member_id": str(second)},
            ).status_code == 409

            # A class that already started flags late cancellations.
            past = _create_session(client, manager, class_type_id=type_id, capacity=5, starts_at=PAST)
            past_id = past.json()["id"]
            past_reservation = client.post(
                f"/admin/classes/sessions/{past_id}/reservations",
                headers=manager,
                json={"member_id": str(third)},
            ).json()
            cancelled = client.post(
                f"/admin/classes/reservations/{past_reservation['id']}/cancel", headers=manager
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["late_cancellation"] is True

            # Cancelling the session cancels every live reservation.
            future = _create_session(client, manager, class_type_id=type_id, capacity=5)
            future_id = future.json()["id"]
            client.post(
                f"/admin/classes/sessions/{future_id}/reservations",
                headers=manager,
                json={"member_id": str(first)},
            )
            cancelled_session = client.post(
                f"/admin/classes/sessions/{future_id}/cancel", headers=manager
            )
            assert cancelled_session.status_code == 200, cancelled_session.text
            assert cancelled_session.json()["status"] == "cancelled"

            roster = client.get(
                f"/admin/classes/sessions/{future_id}/reservations", headers=manager
            ).json()
            assert roster["reservations"] == []
            assert client.post(
                f"/admin/classes/sessions/{future_id}/reservations",
                headers=manager,
                json={"member_id": str(second)},
            ).status_code == 409
            # Cancelling twice is rejected.
            assert client.post(
                f"/admin/classes/sessions/{future_id}/cancel", headers=manager
            ).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_summary_and_total_are_not_inflated_by_the_search_filter() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        members = [_add_member(session, first=name) for name in ("Ana", "Beto", "Caro")]

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            spinning, room_id = _create_catalog(client, manager)
            yoga = client.post("/admin/classes/types", headers=manager, json={"name": "Yoga"})
            assert yoga.status_code == 201, yoga.text
            assert client.post(
                "/admin/classes/types", headers=manager, json={"name": "Boxeo"}
            ).status_code == 201

            cardio_morning = _create_session(
                client, manager, class_type_id=spinning, room_id=room_id, capacity=2
            )
            assert cardio_morning.status_code == 201, cardio_morning.text
            cardio_later = _create_session(
                client,
                manager,
                class_type_id=yoga.json()["id"],
                room_id=room_id,
                capacity=2,
                starts_at=FUTURE + timedelta(days=1),
                title="Cardio 7am",
            )
            boxing = _create_session(
                client,
                manager,
                class_type_id=spinning,
                room_id=room_id,
                capacity=2,
                starts_at=FUTURE + timedelta(days=2),
                title="Boxeo 8am",
            )
            for created in (cardio_later, boxing):
                assert created.status_code == 201, created.text

            # Two seated reservations and one waitlist, all on the first class.
            for member_id in members:
                reserved = client.post(
                    f"/admin/classes/sessions/{cardio_morning.json()['id']}/reservations",
                    headers=manager,
                    json={"member_id": str(member_id), "origin": "reception"},
                )
                assert reserved.status_code == 201, reserved.text

            everything = client.get("/admin/classes/sessions", headers=manager).json()
            assert everything["total"] == 3
            assert everything["summary"] == {
                "total": 3,
                "scheduled": 3,
                "cancelled": 0,
                "upcoming": 3,
                "reserved_total": 2,
                "waitlist_total": 1,
            }

            # The search matches ClassType.name, so every aggregate over the
            # filtered set must keep counting each session exactly once.
            by_title = client.get(
                "/admin/classes/sessions", headers=manager, params={"search": "spinning 6am"}
            ).json()
            assert by_title["total"] == 1
            assert by_title["summary"] == {
                "total": 1,
                "scheduled": 1,
                "cancelled": 0,
                "upcoming": 1,
                "reserved_total": 2,
                "waitlist_total": 1,
            }

            by_type = client.get(
                "/admin/classes/sessions", headers=manager, params={"search": "yoga"}
            ).json()
            assert [item["id"] for item in by_type["items"]] == [cardio_later.json()["id"]]
            assert by_type["total"] == 1
            assert by_type["summary"]["total"] == 1
            assert by_type["summary"]["reserved_total"] == 0
            assert by_type["summary"]["waitlist_total"] == 0

            two_of_three = client.get(
                "/admin/classes/sessions", headers=manager, params={"search": "sal"}
            ).json()
            assert two_of_three["total"] == 0
            assert two_of_three["summary"]["total"] == 0
    finally:
        app.dependency_overrides.clear()
