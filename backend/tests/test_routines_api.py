from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.models import Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member

PAST = date(2026, 1, 1)
FUTURE = date(2099, 1, 1)


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
    register_user(session, email="manager@example.com", password="manager-strong-password", role_codes=("manager",))
    register_user(session, email="trainer@example.com", password="trainer-strong-password", role_codes=("trainer",))
    register_user(session, email="reception@example.com", password="reception-strong-password", role_codes=("reception",))
    register_user(session, email="accountant@example.com", password="accountant-strong-password", role_codes=("accountant",))


def _add_member(session: Session, *, status: str = "active", first: str = "Socio") -> str:
    member = Member(
        first_name=first,
        last_name="Demo",
        email=f"{uuid4().hex[:10]}@example.com",
        status=status,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return str(member.id)


def _add_employee(session: Session, *, first: str = "Luis") -> str:
    employee = Employee(
        employee_number=f"E-{uuid4().hex[:6]}",
        first_name=first,
        last_name="Coach",
        job_title="Entrenador",
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return str(employee.id)


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _create_exercise(client: TestClient, headers: dict[str, str], *, name: str, muscle: str = "Piernas") -> dict:
    response = client.post(
        "/admin/routines/exercises",
        headers=headers,
        json={"name": name, "muscle_group": muscle, "category": "Fuerza"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_routine(client: TestClient, headers: dict[str, str], exercise_ids: list[str], *, name: str = "Fuerza 3 días") -> dict:
    response = client.post(
        "/admin/routines",
        headers=headers,
        json={
            "name": name,
            "objective": "Hipertrofia",
            "items": [
                {"exercise_id": exercise_id, "sets": 4, "reps": "8", "rest_seconds": 90}
                for exercise_id in exercise_ids
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_exercise_library_and_permissions() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            assert client.get("/admin/routines").status_code == 401

            manager = _login(client, "manager@example.com", "manager-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")

            # Routines are owner/manager/trainer only.
            assert client.get("/admin/routines", headers=reception).status_code == 403
            assert client.get("/admin/routines/exercises", headers=accountant).status_code == 403
            assert client.post(
                "/admin/routines/exercises",
                headers=reception,
                json={"name": "Sentadilla", "muscle_group": "Piernas", "category": "Fuerza"},
            ).status_code == 403
            assert client.get("/admin/routines", headers=trainer).status_code == 200

            squat = _create_exercise(client, manager, name="Sentadilla", muscle="Piernas")
            _create_exercise(client, trainer, name="Press banca", muscle="Pecho")
            assert client.post(
                "/admin/routines/exercises",
                headers=manager,
                json={"name": "SENTADILLA", "muscle_group": "Piernas", "category": "Fuerza"},
            ).status_code == 409
            assert client.post(
                "/admin/routines/exercises",
                headers=manager,
                json={"name": "Remo", "muscle_group": "", "category": "Fuerza"},
            ).status_code == 422

            directory = client.get("/admin/routines/exercises", headers=trainer).json()
            assert directory["total"] == 2
            assert directory["muscle_groups"] == ["Pecho", "Piernas"]
            filtered = client.get(
                "/admin/routines/exercises", headers=trainer, params={"muscle_group": "piernas"}
            ).json()
            assert filtered["total"] == 1

            deactivated = client.patch(
                f"/admin/routines/exercises/{squat['id']}",
                headers=manager,
                json={"is_active": False},
            )
            assert deactivated.status_code == 200, deactivated.text
            assert deactivated.json()["is_active"] is False
            assert client.get("/admin/routines/exercises", headers=manager).json()["total"] == 1
            assert client.get(
                "/admin/routines/exercises", headers=manager, params={"include_inactive": True}
            ).json()["total"] == 2
    finally:
        app.dependency_overrides.clear()


def test_routine_versioning() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        trainer_id = _add_employee(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            squat = _create_exercise(client, manager, name="Sentadilla")
            bench = _create_exercise(client, manager, name="Press banca", muscle="Pecho")

            # An empty plan is rejected by the request model.
            assert client.post(
                "/admin/routines", headers=manager, json={"name": "Vacía", "items": []}
            ).status_code == 422
            # Unknown exercise and unknown trainer are rejected.
            unknown = client.post(
                "/admin/routines",
                headers=manager,
                json={"name": "X", "items": [{"exercise_id": str(uuid4()), "sets": 3, "reps": "10"}]},
            )
            assert unknown.status_code == 404
            bad_trainer = client.post(
                "/admin/routines",
                headers=manager,
                json={
                    "name": "Y",
                    "trainer_id": str(uuid4()),
                    "items": [{"exercise_id": squat["id"], "sets": 3, "reps": "10"}],
                },
            )
            assert bad_trainer.status_code == 422
            # The same exercise cannot appear twice in one version.
            duplicated = client.post(
                "/admin/routines",
                headers=manager,
                json={
                    "name": "Z",
                    "items": [
                        {"exercise_id": squat["id"], "sets": 3, "reps": "10"},
                        {"exercise_id": squat["id"], "sets": 3, "reps": "10"},
                    ],
                },
            )
            assert duplicated.status_code == 422

            routine = _create_routine(client, manager, [squat["id"], bench["id"]])
            routine_id = routine["routine"]["id"]
            assert routine["routine"]["version"] == 1
            assert routine["routine"]["item_count"] == 2
            assert len(routine["items"]) == 2
            assert [revision["version"] for revision in routine["revisions"]] == [1]

            replaced = client.put(
                f"/admin/routines/{routine_id}/items",
                headers=manager,
                json={
                    "reason": "Subir carga",
                    "items": [
                        {"exercise_id": squat["id"], "sets": 5, "reps": "5", "rest_seconds": 120},
                        {"exercise_id": bench["id"], "sets": 4, "reps": "8"},
                    ],
                },
            )
            assert replaced.status_code == 200, replaced.text
            body = replaced.json()
            assert body["routine"]["version"] == 2
            assert body["items"][0]["sets"] == 5
            assert [revision["version"] for revision in body["revisions"]] == [2, 1]
            assert body["revisions"][0]["reason"] == "Subir carga"

            # The previous version stays readable for the audit trail.
            old = client.get(f"/admin/routines/{routine_id}", headers=manager, params={"version": 1}).json()
            assert old["items"][0]["sets"] == 4
            assert old["routine"]["version"] == 2

            archived = client.post(f"/admin/routines/{routine_id}/archive", headers=manager)
            assert archived.status_code == 200, archived.text
            assert archived.json()["routine"]["status"] == "archived"
            assert client.post(f"/admin/routines/{routine_id}/archive", headers=manager).status_code == 409
            assert client.put(
                f"/admin/routines/{routine_id}/items",
                headers=manager,
                json={"items": [{"exercise_id": squat["id"], "sets": 3, "reps": "10"}]},
            ).status_code == 409

            # A deactivated exercise can no longer enter a plan.
            client.patch(f"/admin/routines/exercises/{bench['id']}", headers=manager, json={"is_active": False})
            inactive = client.post(
                "/admin/routines",
                headers=manager,
                json={"name": "Con inactivo", "items": [{"exercise_id": bench["id"], "sets": 3, "reps": "10"}]},
            )
            assert inactive.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_assignments_and_workouts() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")
        inactive_id = _add_member(session, first="Beto", status="inactive")
        other_id = _add_member(session, first="Caro")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            squat = _create_exercise(client, manager, name="Sentadilla")
            routine = _create_routine(client, manager, [squat["id"]])
            routine_id = routine["routine"]["id"]

            created = client.post(
                "/admin/routines/assignments",
                headers=manager,
                json={
                    "routine_id": routine_id,
                    "member_id": member_id,
                    "start_date": PAST.isoformat(),
                    "frequency_per_week": 3,
                },
            )
            assert created.status_code == 201, created.text
            assignment = created.json()
            assignment_id = assignment["id"]
            assert assignment["routine_version"] == 1
            assert assignment["status"] == "active"
            assert assignment["routine_name"] == "Fuerza 3 días"

            # One live assignment per member and routine.
            duplicate = client.post(
                "/admin/routines/assignments",
                headers=manager,
                json={"routine_id": routine_id, "member_id": member_id, "start_date": PAST.isoformat()},
            )
            assert duplicate.status_code == 409
            # Unknown routine / inactive member / bad date range.
            assert client.post(
                "/admin/routines/assignments",
                headers=manager,
                json={"routine_id": str(uuid4()), "member_id": member_id, "start_date": PAST.isoformat()},
            ).status_code == 404
            assert client.post(
                "/admin/routines/assignments",
                headers=manager,
                json={"routine_id": routine_id, "member_id": inactive_id, "start_date": PAST.isoformat()},
            ).status_code == 404
            assert client.post(
                "/admin/routines/assignments",
                headers=manager,
                json={
                    "routine_id": routine_id,
                    "member_id": other_id,
                    "start_date": "2030-06-01",
                    "end_date": "2030-01-01",
                },
            ).status_code == 422

            detail = client.get(f"/admin/routines/assignments/{assignment_id}", headers=manager).json()
            assert [line["exercise_name"] for line in detail["plan"]] == ["Sentadilla"]

            # A workout is logged against the active assignment.
            logged = client.post(
                f"/admin/routines/assignments/{assignment_id}/workouts",
                headers=manager,
                json={
                    "performed_at": PAST.isoformat(),
                    "duration_minutes": 55,
                    "perceived_effort": 8,
                    "notes": "Buen día",
                },
            )
            assert logged.status_code == 201, logged.text
            workout_id = logged.json()["id"]
            assert logged.json()["status"] == "logged"

            assert client.post(
                f"/admin/routines/assignments/{assignment_id}/workouts",
                headers=manager,
                json={"performed_at": FUTURE.isoformat()},
            ).status_code == 422
            assert client.post(
                f"/admin/routines/assignments/{assignment_id}/workouts",
                headers=manager,
                json={"performed_at": PAST.isoformat(), "perceived_effort": 11},
            ).status_code == 422

            reviewed = client.post(f"/admin/routines/workouts/{workout_id}/review", headers=manager)
            assert reviewed.status_code == 200, reviewed.text
            assert reviewed.json()["status"] == "reviewed"
            assert client.post(f"/admin/routines/workouts/{workout_id}/review", headers=manager).status_code == 409

            workouts = client.get(
                f"/admin/routines/assignments/{assignment_id}/workouts", headers=manager
            ).json()
            assert len(workouts) == 1

            listing = client.get(
                "/admin/routines/assignments", headers=manager, params={"member_id": member_id}
            ).json()
            assert listing["summary"]["active"] == 1
            assert listing["items"][0]["workouts_logged"] == 1

            # Closing the assignment blocks new workouts.
            assert client.post(
                f"/admin/routines/assignments/{assignment_id}/complete", headers=manager
            ).json()["status"] == "completed"
            assert client.post(
                f"/admin/routines/assignments/{assignment_id}/workouts",
                headers=manager,
                json={"performed_at": PAST.isoformat()},
            ).status_code == 409
            assert client.post(
                f"/admin/routines/assignments/{assignment_id}/cancel", headers=manager
            ).status_code == 409

            # A workout cannot predate its assignment.
            future_assignment = client.post(
                "/admin/routines/assignments",
                headers=manager,
                json={"routine_id": routine_id, "member_id": other_id, "start_date": "2030-01-01"},
            ).json()
            assert client.post(
                f"/admin/routines/assignments/{future_assignment['id']}/workouts",
                headers=manager,
                json={"performed_at": date.today().isoformat()},
            ).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_measurements_progress_and_overview() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            squat = _create_exercise(client, manager, name="Sentadilla")
            routine = _create_routine(client, manager, [squat["id"]])
            assignment = client.post(
                "/admin/routines/assignments",
                headers=manager,
                json={"routine_id": routine["routine"]["id"], "member_id": member_id, "start_date": PAST.isoformat()},
            ).json()
            client.post(
                f"/admin/routines/assignments/{assignment['id']}/workouts",
                headers=manager,
                json={"performed_at": PAST.isoformat(), "duration_minutes": 45},
            )

            # At least one metric is required.
            assert client.post(
                f"/admin/routines/members/{member_id}/measurements", headers=manager, json={}
            ).status_code == 422
            assert client.post(
                f"/admin/routines/members/{member_id}/measurements",
                headers=manager,
                json={"weight_kg": 0},
            ).status_code == 422

            first = client.post(
                f"/admin/routines/members/{member_id}/measurements",
                headers=manager,
                json={
                    "measured_at": datetime(2026, 1, 10, 10, tzinfo=timezone.utc).isoformat(),
                    "weight_kg": 72.5,
                    "waist_cm": 80,
                },
            )
            assert first.status_code == 201, first.text
            assert first.json()["weight_kg"] == 72.5
            client.post(
                f"/admin/routines/members/{member_id}/measurements",
                headers=manager,
                json={"weight_kg": 71.8},
            )

            history = client.get(
                f"/admin/routines/members/{member_id}/measurements", headers=manager
            ).json()
            assert len(history) == 2
            assert history[0]["weight_kg"] == 71.8

            progress = client.get(
                f"/admin/routines/members/{member_id}/progress", headers=manager
            ).json()
            assert progress["active_assignments"] == 1
            assert progress["workouts_total"] == 1
            assert progress["latest_measurement"]["weight_kg"] == 71.8
            assert len(progress["measurements"]) == 2

            # Unknown member is a 404.
            assert client.get(
                f"/admin/routines/members/{uuid4()}/progress", headers=manager
            ).status_code == 404

            overview = client.get("/admin/routines/overview", headers=manager).json()
            assert overview["exercises"] == 1
            assert overview["routines_active"] == 1
            assert overview["assignments_active"] == 1

            # A second routine shows up in the directory summary.
            client.post(
                "/admin/routines",
                headers=manager,
                json={"name": "Movilidad", "items": [{"exercise_id": squat["id"], "sets": 3, "reps": "12"}]},
            )
            directory = client.get("/admin/routines", headers=manager).json()
            assert directory["summary"]["active"] == 2
            assert client.get(
                "/admin/routines", headers=manager, params={"search": "movilidad"}
            ).json()["total"] == 1
    finally:
        app.dependency_overrides.clear()
