from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.maintenance import create_equipment, set_equipment_status
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.portal.routines import (
    get_member_progress,
    get_member_routine,
    list_member_routines,
)
from app.modules.portal.service import MemberPortalError
from app.modules.routines import (
    AssignmentNotFound,
    RoutineItemInput,
    complete_assignment,
    create_assignment,
    create_exercise,
    create_member_goal,
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


def _seed_routine(session: Session, *, objective: str = "Fuerza general", equipment_id=None):
    press = create_exercise(
        session,
        name=f"Press banca {uuid4().hex[:4]}",
        muscle_group="Pecho",
        category="Fuerza",
        equipment_id=equipment_id,
    )
    squat = create_exercise(
        session,
        name=f"Sentadilla {uuid4().hex[:4]}",
        muscle_group="Piernas",
        category="Fuerza",
    )
    routine = create_routine(
        session,
        name="Full body",
        objective=objective,
        items=[
            RoutineItemInput(
                exercise_id=press.id,
                sets=4,
                reps="10",
                rest_seconds=60,
                load_note="20 kg",
                notes="Tempo controlado",
            ),
            RoutineItemInput(exercise_id=squat.id, sets=3, reps="12"),
        ],
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


def test_member_routine_list_detail_and_progress(monkeypatch) -> None:
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
        bench = create_equipment(session, name="Banco plano", category="Fuerza")
        routine_id = _seed_routine(session, equipment_id=bench.id)
        finished = create_assignment(
            session,
            routine_id=routine_id,
            member_id=ana_id,
            start_date=today - timedelta(days=60),
        )
        complete_assignment(session, finished.id, now=datetime.now(timezone.utc))
        active = create_assignment(
            session,
            routine_id=routine_id,
            member_id=ana_id,
            start_date=today - timedelta(days=10),
            frequency_per_week=3,
            notes="Progresión semanal",
        )
        log_workout(
            session,
            active.id,
            performed_at=today - timedelta(days=3),
            duration_minutes=55,
            perceived_effort=7,
        )
        log_workout(
            session,
            active.id,
            performed_at=today - timedelta(days=1),
            duration_minutes=60,
            perceived_effort=8,
        )
        record_measurement(
            session,
            ana_id,
            measured_at=datetime.now(timezone.utc) - timedelta(days=5),
            weight_kg=70,
        )
        create_member_goal(
            session,
            ana_id,
            metric="weight_kg",
            direction="decrease",
            target_value=65,
        )
        record_measurement(
            session,
            ana_id,
            measured_at=datetime.now(timezone.utc) - timedelta(days=1),
            weight_kg=68,
        )
        set_equipment_status(session, bench.id, status="maintenance")
        active_id = active.id

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana_headers = _member_headers(client, "ana@example.com")
            beto_headers = _member_headers(client, "beto@example.com")

            listing = client.get("/member/routines", headers=ana_headers)
            assert listing.status_code == 200, listing.text
            body = listing.json()
            assert body["total"] == 2
            assert body["active"] == 1
            assert body["completed"] == 1
            assert body["cancelled"] == 0
            assert body["items"][0]["id"] == str(active_id)
            assert body["items"][0]["status"] == "active"
            assert body["items"][0]["workouts_logged"] == 2
            assert body["items"][0]["frequency_per_week"] == 3
            assert body["items"][1]["status"] == "completed"
            assert "member_id" not in body["items"][0]

            detail = client.get(f"/member/routines/{active_id}", headers=ana_headers)
            assert detail.status_code == 200, detail.text
            payload = detail.json()
            assert payload["assignment"]["id"] == str(active_id)
            assert payload["assignment"]["routine_name"] == "Full body"
            assert payload["assignment"]["notes"] == "Progresión semanal"
            assert payload["objective"] == "Fuerza general"
            assert [line["exercise_name"] for line in payload["plan"]][0].startswith("Press banca")
            assert payload["plan"][0]["sets"] == 4
            assert payload["plan"][0]["reps"] == "10"
            assert payload["plan"][0]["rest_seconds"] == 60
            assert payload["plan"][0]["load_note"] == "20 kg"
            # La app del socio marca la línea a partir de este campo: es el estado
            # vivo del equipo, no el que tenía la rutina al asignarse.
            assert payload["plan"][0]["equipment_status"] == "maintenance"
            assert payload["plan"][1]["equipment_status"] is None
            assert len(payload["workouts"]) == 2
            assert payload["workouts"][0]["performed_at"] == (today - timedelta(days=1)).isoformat()
            assert "member_email" not in payload["assignment"]

            progress = client.get("/member/progress", headers=ana_headers)
            assert progress.status_code == 200, progress.text
            data = progress.json()
            assert data["workouts_total"] == 2
            assert data["workouts_last_30_days"] == 2
            assert data["last_workout_at"] == (today - timedelta(days=1)).isoformat()
            assert len(data["measurements"]) == 2
            assert data["latest_measurement"]["weight_kg"] == 68
            assert len(data["goals"]) == 1
            goal = data["goals"][0]
            assert goal["metric"] == "weight_kg"
            assert goal["baseline_value"] == 70
            assert goal["current_value"] == 68
            assert goal["status"] == "active"

            empty = client.get("/member/routines", headers=beto_headers).json()
            assert empty["total"] == 0
            assert empty["items"] == []

            foreign = client.get(f"/member/routines/{active_id}", headers=beto_headers)
            assert foreign.status_code == 404

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
            assert client.get("/member/routines", headers=staff_headers).status_code == 401
            assert client.get("/member/progress", headers=staff_headers).status_code == 401
            assert (
                client.get(f"/member/routines/{active_id}", headers=staff_headers).status_code
                == 401
            )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_member_routine_detail_hides_other_assignments(session: Session) -> None:
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
        get_member_routine(session, beto_id, assignment.id)

    with pytest.raises(AssignmentNotFound):
        get_member_routine(session, ana_id, uuid4())


def test_member_routines_empty_progress_and_unknown_member(session: Session) -> None:
    ana_id = _seed_member(session, email="ana@example.com")

    listing = list_member_routines(session, ana_id)
    assert listing.total == 0
    assert listing.items == []

    progress = get_member_progress(session, ana_id)
    assert progress.workouts_total == 0
    assert progress.workouts_last_30_days == 0
    assert progress.last_workout_at is None
    assert progress.latest_measurement is None
    assert progress.measurements == []
    assert progress.goals == []

    with pytest.raises(MemberPortalError):
        list_member_routines(session, uuid4())
