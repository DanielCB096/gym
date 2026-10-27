from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.classes import create_class_room, create_class_session, create_class_type
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.routines import (
    RoutineItemInput,
    create_assignment,
    create_exercise,
    create_routine,
    log_workout,
    record_measurement,
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
    ends_in: timedelta = timedelta(days=25),
) -> UUID:
    now = datetime.now(timezone.utc)
    member = Member(first_name=first_name, last_name="Demo", email=email, status="active")
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
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        ids["ana"] = _seed_member(session, email="ana@example.com", ends_in=timedelta(days=2))
        ids["beto"] = _seed_member(
            session, email="beto@example.com", first_name="Beto"
        )

        press = create_exercise(
            session,
            name=f"Press banca {uuid4().hex[:4]}",
            muscle_group="Pecho",
            category="Fuerza",
        )
        routine = create_routine(
            session,
            name="Full body",
            objective="Fuerza general",
            items=[RoutineItemInput(exercise_id=press.id, sets=4, reps="10")],
        )
        assignment = create_assignment(
            session,
            routine_id=routine.routine.id,
            member_id=ids["ana"],
            start_date=now.date() - timedelta(days=3),
        )
        workout = log_workout(session, assignment.id, performed_at=now.date() - timedelta(days=1))
        ids["workout"] = workout.id
        record_measurement(session, ids["ana"], weight_kg=70)

        class_type = create_class_type(session, name="Spinning", description="Ciclismo indoor")
        room = create_class_room(session, name="Salón A", capacity=10)
        seated = create_class_session(
            session,
            title="Spinning 6am",
            class_type_id=class_type.id,
            room_id=room.id,
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=1),
            capacity=1,
        )
        ids["class"] = seated.id
    return engine, ids


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _kinds(client: TestClient, headers: dict[str, str]) -> list[str]:
    inbox = client.get(
        "/member/notifications", headers=headers, params={"page_size": 50}
    )
    assert inbox.status_code == 200, inbox.text
    return [item["kind"] for item in inbox.json()["items"]]


def test_inbox_collects_every_member_event(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-notifications-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine, ids = _prepare()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana@example.com")
            beto = _member_headers(client, "beto@example.com")
            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

            # The expiring reminder has no scheduler: it is written the first time
            # the member reads the inbox, and never repeated for the same window.
            first = client.get("/member/notifications", headers=ana).json()
            assert first["total"] == 1
            assert first["unread_total"] == 1
            assert first["pages"] == 1
            reminder = first["items"][0]
            assert reminder["kind"] == "membership_expiring"
            assert "faltan 2 días" in reminder["body"]
            assert reminder["read_at"] is None
            assert client.get("/member/notifications", headers=ana).json()["total"] == 1
            assert client.get("/member/notifications", headers=beto).json()["total"] == 0

            # A trainer review of a workout nobody had looked at.
            assert client.post(
                f"/admin/routines/workouts/{ids['workout']}/review", headers=staff
            ).status_code == 200

            # The member hits a goal of their own with a self-recorded measurement.
            own_goal = client.post(
                "/member/progress/goals",
                headers=ana,
                json={"metric": "weight_kg", "direction": "decrease", "target_value": 65},
            )
            assert own_goal.status_code == 201, own_goal.text
            client.post("/member/progress/measurements", headers=ana, json={"weight_kg": 64})

            # Reception moves a goal it owns, then cancels it.
            staff_goal = client.post(
                f"/admin/routines/members/{ids['ana']}/goals",
                headers=staff,
                json={"metric": "waist_cm", "direction": "decrease", "target_value": 80},
            )
            assert staff_goal.status_code == 201, staff_goal.text
            goal_id = staff_goal.json()["id"]
            updated = client.patch(
                f"/admin/routines/goals/{goal_id}", headers=staff, json={"target_value": 78}
            )
            assert updated.status_code == 200, updated.text
            assert client.post(
                f"/admin/routines/goals/{goal_id}/cancel", headers=staff
            ).status_code == 200

            # The only goal nobody is notified about is the one the member cancelled.
            chest_goal = client.post(
                "/member/progress/goals",
                headers=ana,
                json={"metric": "chest_cm", "direction": "increase", "target_value": 110},
            )
            assert chest_goal.status_code == 201, chest_goal.text
            assert client.post(
                f"/member/progress/goals/{chest_goal.json()['id']}/cancel", headers=ana
            ).status_code == 200

            # A freed seat promotes the member waiting in line.
            ana_seat = client.post(
                f"/member/classes/sessions/{ids['class']}/reservations", headers=ana
            )
            assert ana_seat.status_code == 201, ana_seat.text
            beto_wait = client.post(
                f"/member/classes/sessions/{ids['class']}/reservations", headers=beto
            )
            assert beto_wait.status_code == 201, beto_wait.text
            assert beto_wait.json()["status"] == "waitlist"
            assert client.post(
                f"/member/classes/reservations/{ana_seat.json()['id']}/cancel", headers=ana
            ).status_code == 200

            ana_inbox = client.get(
                "/member/notifications", headers=ana, params={"page_size": 50}
            ).json()
            assert sorted(item["kind"] for item in ana_inbox["items"]) == [
                "goal_achieved",
                "goal_cancelled_by_staff",
                "goal_updated_by_staff",
                "membership_expiring",
                "workout_reviewed",
            ]
            assert ana_inbox["total"] == 5
            assert _kinds(client, beto) == ["class_waitlist_promoted"]

            by_kind = {item["kind"]: item for item in ana_inbox["items"]}
            achieved = by_kind["goal_achieved"]
            assert "peso" in achieved["body"]
            assert "65 kg" in achieved["body"] and "64 kg" in achieved["body"]
            assert achieved["ref_id"] == own_goal.json()["id"]

            updated_notice = by_kind["goal_updated_by_staff"]
            assert updated_notice["ref_id"] == goal_id
            assert "78 cm" in updated_notice["body"]

            assert by_kind["goal_cancelled_by_staff"]["ref_id"] == goal_id
            assert "cintura" in by_kind["goal_cancelled_by_staff"]["body"]
            assert "Full body" in by_kind["workout_reviewed"]["body"]

            promoted = client.get(
                "/member/notifications", headers=beto, params={"page_size": 50}
            ).json()["items"][0]
            assert "Spinning 6am" in promoted["body"]

            # Acknowledging: one at a time, then the whole inbox.
            unread = client.get("/member/notifications/unread-count", headers=ana).json()
            assert unread["unread"] == 5
            mark_one = client.post(
                f"/member/notifications/{achieved['id']}/read", headers=ana
            )
            assert mark_one.status_code == 200, mark_one.text
            assert mark_one.json()["read_at"] is not None
            assert client.get(
                "/member/notifications/unread-count", headers=ana
            ).json()["unread"] == 4
            assert client.post(
                f"/member/notifications/{achieved['id']}/read", headers=ana
            ).status_code == 200
            assert client.get("/member/notifications/unread-count", headers=ana).json()[
                "unread"
            ] == 4
            assert client.post("/member/notifications/read-all", headers=ana).json() == {
                "updated": 4
            }
            assert client.get("/member/notifications/unread-count", headers=ana).json() == {
                "unread": 0
            }
    finally:
        app.dependency_overrides.clear()


def test_inbox_is_scoped_to_the_authenticated_member(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-notifications-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine, ids = _prepare()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana@example.com")
            beto = _member_headers(client, "beto@example.com")
            staff = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            ).json()["access_token"]

            assert client.get("/member/notifications").status_code == 401
            # A staff token is not a member token.
            assert client.get(
                "/member/notifications", headers={"Authorization": f"Bearer {staff}"}
            ).status_code == 401

            reminder_id = client.get("/member/notifications", headers=ana).json()["items"][0]["id"]
            # Another member cannot acknowledge it.
            assert client.post(
                f"/member/notifications/{reminder_id}/read", headers=beto
            ).status_code == 404
            assert client.post(
                f"/member/notifications/{uuid4()}/read", headers=ana
            ).status_code == 404
            # Beto's inbox stays empty and his read-all touches nothing.
            assert client.get("/member/notifications", headers=beto).json()["total"] == 0
            assert client.post("/member/notifications/read-all", headers=beto).json() == {
                "updated": 0
            }
            assert client.get("/member/notifications/unread-count", headers=ana).json() == {
                "unread": 1
            }
    finally:
        app.dependency_overrides.clear()
