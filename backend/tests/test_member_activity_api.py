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
from app.modules.portal.routines import log_member_workout, record_member_measurement
from app.modules.portal.service import MemberPortalError
from app.modules.routines import (
    AssignmentNotFound,
    RoutineItemInput,
    complete_assignment,
    create_assignment,
    create_exercise,
    create_member_goal,
    create_routine,
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


def _seed_member(session: Session, *, email: str, first_name: str = "Ana"):
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
            ends_at=now + timedelta(days=25),
        )
    )
    session.commit()
    return member.id


def _seed_routine(session: Session):
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
        items=[RoutineItemInput(exercise_id=press.id, sets=4, reps="10", rest_seconds=60)],
    )
    return routine.routine.id


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_member_logs_workout_and_measurement(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
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
        ana_id = _seed_member(session, email="ana@example.com")
        _seed_member(session, email="beto@example.com", first_name="Beto")
        routine_id = _seed_routine(session)
        finished = create_assignment(
            session,
            routine_id=routine_id,
            member_id=ana_id,
            start_date=today - timedelta(days=40),
        )
        complete_assignment(session, finished.id, now=datetime.now(timezone.utc))
        active = create_assignment(
            session,
            routine_id=routine_id,
            member_id=ana_id,
            start_date=today - timedelta(days=10),
            frequency_per_week=3,
        )
        record_measurement(session, ana_id, weight_kg=70)
        create_member_goal(
            session,
            ana_id,
            metric="weight_kg",
            direction="decrease",
            target_value=65,
        )
        active_id = active.id
        finished_id = finished.id

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana_headers = _member_headers(client, "ana@example.com")
            beto_headers = _member_headers(client, "beto@example.com")

            created = client.post(
                f"/member/routines/{active_id}/workouts",
                headers=ana_headers,
                json={
                    "performed_at": (today - timedelta(days=1)).isoformat(),
                    "duration_minutes": 55,
                    "perceived_effort": 7,
                    "notes": "Última serie al fallo",
                },
            )
            assert created.status_code == 201, created.text
            workout = created.json()
            assert workout["origin"] == "app"
            assert workout["status"] == "logged"
            assert workout["reviewed_at"] is None
            assert workout["performed_at"] == (today - timedelta(days=1)).isoformat()

            detail = client.get(f"/member/routines/{active_id}", headers=ana_headers).json()
            assert len(detail["workouts"]) == 1
            assert detail["workouts"][0]["origin"] == "app"
            assert detail["workouts"][0]["notes"] == "Última serie al fallo"

            measured = client.post(
                "/member/progress/measurements",
                headers=ana_headers,
                json={
                    "measured_at": datetime.now(timezone.utc).isoformat(),
                    "weight_kg": 68.5,
                    "waist_cm": 82,
                    "notes": "Medición en casa",
                },
            )
            assert measured.status_code == 201, measured.text
            measurement = measured.json()
            assert measurement["origin"] == "app"
            assert measurement["weight_kg"] == 68.5
            assert measurement["waist_cm"] == 82

            progress = client.get("/member/progress", headers=ana_headers).json()
            assert progress["workouts_total"] == 1
            assert progress["measurements"][0]["origin"] == "app"
            assert progress["latest_measurement"]["weight_kg"] == 68.5
            assert progress["goals"][0]["current_value"] == 68.5
            assert progress["goals"][0]["status"] == "active"

            foreign = client.post(
                f"/member/routines/{active_id}/workouts",
                headers=beto_headers,
                json={"performed_at": today.isoformat()},
            )
            assert foreign.status_code == 404

            closed = client.post(
                f"/member/routines/{finished_id}/workouts",
                headers=ana_headers,
                json={"performed_at": today.isoformat()},
            )
            assert closed.status_code == 409

            future = client.post(
                f"/member/routines/{active_id}/workouts",
                headers=ana_headers,
                json={"performed_at": (today + timedelta(days=1)).isoformat()},
            )
            assert future.status_code == 422

            empty_measurement = client.post(
                "/member/progress/measurements",
                headers=ana_headers,
                json={"notes": "Sin datos"},
            )
            assert empty_measurement.status_code == 422

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

            staff_workouts = client.get(
                f"/admin/routines/assignments/{active_id}/workouts",
                headers=staff_headers,
            ).json()
            assert staff_workouts[0]["origin"] == "app"
            staff_measurements = client.get(
                f"/admin/routines/members/{ana_id}/measurements",
                headers=staff_headers,
            ).json()
            assert staff_measurements[0]["origin"] == "app"

            reviewed = client.post(
                f"/admin/routines/workouts/{workout['id']}/review",
                headers=staff_headers,
            )
            assert reviewed.status_code == 200, reviewed.text
            assert reviewed.json()["status"] == "reviewed"
            assert reviewed.json()["origin"] == "app"

            reviewed_detail = client.get(
                f"/member/routines/{active_id}", headers=ana_headers
            ).json()
            assert reviewed_detail["workouts"][0]["status"] == "reviewed"

            assert (
                client.post(
                    f"/member/routines/{active_id}/workouts",
                    headers=staff_headers,
                    json={"performed_at": today.isoformat()},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/member/progress/measurements",
                    headers=staff_headers,
                    json={"weight_kg": 68},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    f"/admin/routines/workouts/{workout['id']}/review",
                    headers=ana_headers,
                ).status_code
                == 401
            )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_member_activity_rejects_foreign_and_unknown_resources(session: Session) -> None:
    ana_id = _seed_member(session, email="ana@example.com")
    beto_id = _seed_member(session, email="beto@example.com", first_name="Beto")
    routine_id = _seed_routine(session)
    assignment = create_assignment(
        session,
        routine_id=routine_id,
        member_id=ana_id,
        start_date=datetime.now(timezone.utc).date(),
    )

    with pytest.raises(AssignmentNotFound):
        log_member_workout(
            session,
            beto_id,
            assignment.id,
            performed_at=datetime.now(timezone.utc).date(),
        )

    with pytest.raises(AssignmentNotFound):
        log_member_workout(
            session,
            ana_id,
            uuid4(),
            performed_at=datetime.now(timezone.utc).date(),
        )

    with pytest.raises(MemberPortalError):
        record_member_measurement(session, uuid4(), weight_kg=68)
