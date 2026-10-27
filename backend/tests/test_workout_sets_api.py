from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.routines import (
    InvalidWorkoutData,
    RoutineItemInput,
    WorkoutSetInput,
    create_assignment,
    create_exercise,
    create_routine,
    list_workouts,
    log_workout,
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


def _seed_member(session: Session, *, email: str) -> Member:
    now = datetime.now(timezone.utc)
    member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
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
            ends_at=now + timedelta(days=25),
        )
    )
    session.commit()
    return member


def _seed_routine(session: Session):
    press = create_exercise(
        session,
        name=f"Press banca {uuid4().hex[:4]}",
        muscle_group="Pecho",
        category="Fuerza",
    )
    squat = create_exercise(
        session,
        name=f"Sentadilla {uuid4().hex[:4]}",
        muscle_group="Pierna",
        category="Fuerza",
    )
    outside = create_exercise(
        session,
        name=f"Remo {uuid4().hex[:4]}",
        muscle_group="Espalda",
        category="Fuerza",
    )
    routine = create_routine(
        session,
        name="Full body",
        objective="Fuerza general",
        items=[
            RoutineItemInput(exercise_id=press.id, sets=4, reps="10", rest_seconds=60),
            RoutineItemInput(exercise_id=squat.id, sets=3, reps="12", rest_seconds=90),
        ],
    )
    return routine.routine.id, press, squat, outside


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_workout_sets_round_trip_through_app_and_panel(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-workout-sets-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    today = datetime.now(timezone.utc).date()
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        ana = _seed_member(session, email="ana@example.com")
        routine_id, press, squat, outside = _seed_routine(session)
        assignment = create_assignment(
            session,
            routine_id=routine_id,
            member_id=ana.id,
            start_date=today - timedelta(days=10),
        )
        assignment_id = assignment.id

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana_headers = _member_headers(client, "ana@example.com")
            created = client.post(
                f"/member/routines/{assignment_id}/workouts",
                headers=ana_headers,
                json={
                    "performed_at": (today - timedelta(days=1)).isoformat(),
                    "duration_minutes": 50,
                    "perceived_effort": 8,
                    "sets": [
                        {"exercise_id": str(squat.id), "set_number": 1, "reps": 12},
                        {
                            "exercise_id": str(press.id),
                            "set_number": 1,
                            "reps": 10,
                            "weight_kg": 60,
                        },
                        {
                            "exercise_id": str(press.id),
                            "set_number": 2,
                            "reps": 8,
                            "weight_kg": 62.5,
                        },
                    ],
                },
            )
            assert created.status_code == 201, created.text
            workout = created.json()
            assert [(item["exercise_name"], item["position"], item["set_number"]) for item in workout["sets"]] == [
                (press.name, 1, 1),
                (press.name, 1, 2),
                (squat.name, 2, 1),
            ]
            assert workout["sets"][0]["reps"] == 10
            assert workout["sets"][0]["weight_kg"] == 60
            assert workout["sets"][1]["weight_kg"] == 62.5
            assert workout["sets"][2]["weight_kg"] is None

            detail = client.get(f"/member/routines/{assignment_id}", headers=ana_headers).json()
            assert len(detail["workouts"][0]["sets"]) == 3

            plain = client.post(
                f"/member/routines/{assignment_id}/workouts",
                headers=ana_headers,
                json={"performed_at": today.isoformat()},
            )
            assert plain.status_code == 201, plain.text
            assert plain.json()["sets"] == []

            outside_plan = client.post(
                f"/member/routines/{assignment_id}/workouts",
                headers=ana_headers,
                json={
                    "performed_at": today.isoformat(),
                    "sets": [
                        {"exercise_id": str(outside.id), "set_number": 1, "reps": 10}
                    ],
                },
            )
            assert outside_plan.status_code == 422, outside_plan.text
            assert "no pertenece" in outside_plan.json()["detail"]

            repeated = client.post(
                f"/member/routines/{assignment_id}/workouts",
                headers=ana_headers,
                json={
                    "performed_at": today.isoformat(),
                    "sets": [
                        {"exercise_id": str(press.id), "set_number": 1, "reps": 10},
                        {"exercise_id": str(press.id), "set_number": 1, "reps": 8},
                    ],
                },
            )
            assert repeated.status_code == 422, repeated.text

            invalid_reps = client.post(
                f"/member/routines/{assignment_id}/workouts",
                headers=ana_headers,
                json={
                    "performed_at": today.isoformat(),
                    "sets": [
                        {"exercise_id": str(press.id), "set_number": 1, "reps": 0}
                    ],
                },
            )
            assert invalid_reps.status_code == 422

            invalid_weight = client.post(
                f"/member/routines/{assignment_id}/workouts",
                headers=ana_headers,
                json={
                    "performed_at": today.isoformat(),
                    "sets": [
                        {
                            "exercise_id": str(press.id),
                            "set_number": 1,
                            "reps": 10,
                            "weight_kg": 1001,
                        }
                    ],
                },
            )
            assert invalid_weight.status_code == 422

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

            staff_workouts = {
                item["id"]: item
                for item in client.get(
                    f"/admin/routines/assignments/{assignment_id}/workouts",
                    headers=staff_headers,
                ).json()
            }
            assert len(staff_workouts[workout["id"]]["sets"]) == 3
            assert staff_workouts[plain.json()["id"]]["sets"] == []

            staff_created = client.post(
                f"/admin/routines/assignments/{assignment_id}/workouts",
                headers=staff_headers,
                json={
                    "performed_at": today.isoformat(),
                    "sets": [
                        {
                            "exercise_id": str(squat.id),
                            "set_number": 1,
                            "reps": 15,
                            "weight_kg": 35,
                        }
                    ],
                },
            )
            assert staff_created.status_code == 201, staff_created.text
            assert staff_created.json()["origin"] == "staff"
            assert staff_created.json()["sets"][0]["exercise_name"] == squat.name

            reviewed = client.post(
                f"/admin/routines/workouts/{workout['id']}/review",
                headers=staff_headers,
            )
            assert reviewed.status_code == 200, reviewed.text
            assert len(reviewed.json()["sets"]) == 3
            assert reviewed.json()["status"] == "reviewed"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_workout_sets_validate_against_the_frozen_plan(session: Session) -> None:
    ana = _seed_member(session, email="ana@example.com")
    routine_id, press, squat, outside = _seed_routine(session)
    today = datetime.now(timezone.utc).date()
    assignment = create_assignment(
        session,
        routine_id=routine_id,
        member_id=ana.id,
        start_date=today - timedelta(days=1),
    )

    without_sets = log_workout(session, assignment.id, performed_at=today)
    assert without_sets.sets == []

    with pytest.raises(InvalidWorkoutData):
        log_workout(
            session,
            assignment.id,
            performed_at=today,
            sets=[WorkoutSetInput(exercise_id=outside.id, set_number=1, reps=10)],
        )

    with pytest.raises(InvalidWorkoutData):
        log_workout(
            session,
            assignment.id,
            performed_at=today,
            sets=[
                WorkoutSetInput(exercise_id=press.id, set_number=1, reps=10),
                WorkoutSetInput(exercise_id=press.id, set_number=1, reps=8),
            ],
        )

    with pytest.raises(InvalidWorkoutData):
        log_workout(
            session,
            assignment.id,
            performed_at=today,
            sets=[WorkoutSetInput(exercise_id=press.id, set_number=0, reps=10)],
        )

    with pytest.raises(InvalidWorkoutData):
        log_workout(
            session,
            assignment.id,
            performed_at=today,
            sets=[WorkoutSetInput(exercise_id=press.id, set_number=1, reps=101)],
        )

    with pytest.raises(InvalidWorkoutData):
        log_workout(
            session,
            assignment.id,
            performed_at=today,
            sets=[
                WorkoutSetInput(
                    exercise_id=press.id, set_number=1, reps=10, weight_kg=1001
                )
            ],
        )

    with pytest.raises(InvalidWorkoutData):
        log_workout(
            session,
            assignment.id,
            performed_at=today,
            sets=[
                WorkoutSetInput(exercise_id=press.id, set_number=1, reps=10)
                for _ in range(61)
            ],
        )

    stored = log_workout(
        session,
        assignment.id,
        performed_at=today,
        sets=[
            WorkoutSetInput(exercise_id=squat.id, set_number=2, reps=12, weight_kg=45),
            WorkoutSetInput(exercise_id=press.id, set_number=1, reps=10, weight_kg=60),
        ],
    )
    assert [(item.position, item.set_number) for item in stored.sets] == [(1, 1), (2, 2)]
    listed = list_workouts(session, assignment_id=assignment.id)
    assert len(listed[0].sets) == 2
