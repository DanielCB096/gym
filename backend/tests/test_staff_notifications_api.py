"""Staff notification inbox: the trainer and the technician each see their own work."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, func
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.models import AppUser, Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.notifications.models import StaffNotification
from app.modules.routines import (
    RoutineItemInput,
    create_assignment,
    create_exercise,
    create_routine,
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


def _employee(
    session: Session, *, number: str, first_name: str, last_name: str, job_title: str
) -> UUID:
    employee = Employee(
        employee_number=number,
        first_name=first_name,
        last_name=last_name,
        email=f"{number.lower()}@example.com",
        job_title=job_title,
    )
    session.add(employee)
    session.flush()
    return employee.id


def _notifications_for(session: Session, user_id: UUID) -> int:
    return int(
        session.exec(
            select(func.count(StaffNotification.id)).where(StaffNotification.user_id == user_id)
        ).one()
        or 0
    )


def _prepare() -> tuple[object, dict[str, UUID | str]]:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    ids: dict[str, UUID | str] = {"today": now.date().isoformat()}
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )

        trainer_employee = _employee(
            session, number="T-001", first_name="Sofía", last_name="Pérez", job_title="Entrenadora"
        )
        technician_employee = _employee(
            session, number="M-001", first_name="Iván", last_name="Ruiz", job_title="Técnico"
        )
        ghost_employee = _employee(
            session, number="M-002", first_name="Nora", last_name="Silva", job_title="Técnica"
        )
        unlinked_employee = _employee(
            session, number="M-003", first_name="Beto", last_name="García", job_title="Técnico"
        )

        register_user(
            session,
            email="trainer@example.com",
            password="trainer-strong-password",
            employee_id=trainer_employee,
            role_codes=("trainer",),
        )
        register_user(
            session,
            email="tech@example.com",
            password="tecnico-strong-password",
            employee_id=technician_employee,
            role_codes=("maintenance",),
        )
        ghost = register_user(
            session,
            email="ghost@example.com",
            password="ghost-strong-password",
            employee_id=ghost_employee,
            role_codes=("maintenance",),
        )
        # An account that was closed is not an audience: nobody should be told
        # about work that lands on a person who cannot sign in.
        row = session.get(AppUser, ghost.id)
        row.status = "disabled"
        session.add(row)
        session.commit()

        ids["trainer_employee"] = trainer_employee
        ids["technician_employee"] = technician_employee
        ids["unlinked_employee"] = unlinked_employee
        ids["ghost_user"] = ghost.id

        member = Member(
            first_name="Luis",
            last_name="Demo",
            email="socio@example.com",
            status="active",
        )
        session.add(member)
        session.flush()
        plan = Plan(code=f"PLAN-{uuid4().hex[:8].upper()}", name="Mensual", duration_days=30, price_cents=50000)
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
        ids["member"] = member.id

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
            items=[RoutineItemInput(exercise_id=press.id, sets=3, reps="10")],
        )
        assignment = create_assignment(
            session,
            routine_id=routine.routine.id,
            member_id=member.id,
            start_date=now.date() - timedelta(days=3),
            trainer_id=trainer_employee,
        )
        ids["assignment"] = assignment.id
    return engine, ids


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _inbox(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get(
        "/admin/notifications", headers=headers, params={"page_size": 50}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_trainer_and_the_technician_see_their_own_work(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-staff-notifications-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            technician = _login(client, "tech@example.com", "tecnico-strong-password")
            socio = _member_headers(client, "socio@example.com")

            # The member logs a workout themselves: the trainer is the one with
            # the pending review, so the notice goes to the trainer's account.
            logged = client.post(
                f"/member/routines/{ids['assignment']}/workouts",
                headers=socio,
                json={"performed_at": ids["today"], "duration_minutes": 45},
            )
            assert logged.status_code == 201, logged.text

            inbox = _inbox(client, trainer)
            assert inbox["total"] == 1
            assert inbox["unread_total"] == 1
            assert inbox["pages"] == 1
            pending = inbox["items"][0]
            assert pending["kind"] == "workout_pending_review"
            assert pending["ref_id"] == logged.json()["id"]
            assert pending["read_at"] is None
            assert "Luis" in pending["body"]
            assert "Full body" in pending["body"]
            assert "pendiente de tu revisión" in pending["body"]

            # A workout the staff logged is already being watched: no notice.
            staff_logged = client.post(
                f"/admin/routines/assignments/{ids['assignment']}/workouts",
                headers=owner,
                json={"performed_at": ids["today"], "duration_minutes": 60},
            )
            assert staff_logged.status_code == 201, staff_logged.text
            assert _inbox(client, trainer)["total"] == 1

            # An employee whose account was disabled receives nothing.
            with Session(engine) as session:
                assert _notifications_for(session, ids["ghost_user"]) == 0

            equipment = client.post(
                "/admin/maintenance/equipment",
                headers=owner,
                json={"name": "Cinta 1", "category": "Cardio", "useful_life_months": 60},
            )
            assert equipment.status_code == 201, equipment.text
            equipment_id = equipment.json()["id"]

            # A ticket nobody was handed is nobody's news yet.
            unassigned = client.post(
                "/admin/maintenance/tickets",
                headers=owner,
                json={"equipment_id": equipment_id, "title": "Ruido en la polea", "severity": "low"},
            )
            assert unassigned.status_code == 201, unassigned.text
            assert _inbox(client, technician)["total"] == 0

            ticket = client.post(
                "/admin/maintenance/tickets",
                headers=owner,
                json={
                    "equipment_id": equipment_id,
                    "title": "Banda suelta",
                    "severity": "low",
                    "assigned_to": str(ids["technician_employee"]),
                },
            )
            assert ticket.status_code == 201, ticket.text
            assigned = _inbox(client, technician)
            assert assigned["total"] == 1
            assert assigned["items"][0]["kind"] == "maintenance_ticket_assigned"
            assert assigned["items"][0]["ref_id"] == ticket.json()["id"]
            assert "Cinta 1" in assigned["items"][0]["body"]
            assert "Banda suelta" in assigned["items"][0]["body"]

            # Saving the same technician again does not repeat the notice, and
            # handing the ticket to someone without an account adds none either.
            ticket_id = ticket.json()["id"]
            same = client.patch(
                f"/admin/maintenance/tickets/{ticket_id}",
                headers=owner,
                json={"assigned_to": str(ids["technician_employee"])},
            )
            assert same.status_code == 200, same.text
            assert _inbox(client, technician)["total"] == 1
            elsewhere = client.patch(
                f"/admin/maintenance/tickets/{ticket_id}",
                headers=owner,
                json={"assigned_to": str(ids["unlinked_employee"])},
            )
            assert elsewhere.status_code == 200, elsewhere.text
            assert _inbox(client, technician)["total"] == 1

            # Acknowledging: one at a time, idempotent, then the whole inbox.
            notice_id = assigned["items"][0]["id"]
            marked = client.post(f"/admin/notifications/{notice_id}/read", headers=technician)
            assert marked.status_code == 200, marked.text
            assert marked.json()["read_at"] is not None
            assert client.get(
                "/admin/notifications/unread-count", headers=technician
            ).json() == {"unread": 0}
            again = client.post(f"/admin/notifications/{notice_id}/read", headers=technician)
            assert again.status_code == 200, again.text
            assert client.post("/admin/notifications/read-all", headers=technician).json() == {
                "updated": 0
            }
            # The trainer still owes their review: read-all is per account.
            assert client.get("/admin/notifications/unread-count", headers=trainer).json() == {
                "unread": 1
            }
            assert client.post("/admin/notifications/read-all", headers=trainer).json() == {
                "updated": 1
            }
            assert client.get("/admin/notifications/unread-count", headers=trainer).json() == {
                "unread": 0
            }
    finally:
        app.dependency_overrides.clear()


def test_the_staff_inbox_is_scoped_to_the_authenticated_user(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-staff-notifications-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            socio = _member_headers(client, "socio@example.com")
            member_token = socio["Authorization"].removeprefix("Bearer ")

            logged = client.post(
                f"/member/routines/{ids['assignment']}/workouts",
                headers=socio,
                json={"performed_at": ids["today"]},
            )
            assert logged.status_code == 201, logged.text
            notice_id = _inbox(client, trainer)["items"][0]["id"]

            assert client.get("/admin/notifications").status_code == 401
            assert client.get("/admin/notifications/unread-count").status_code == 401
            # A member token is not a staff token.
            member_headers = {"Authorization": f"Bearer {member_token}"}
            assert client.get("/admin/notifications", headers=member_headers).status_code == 401
            assert client.post(
                f"/admin/notifications/{notice_id}/read", headers=member_headers
            ).status_code == 401
            assert client.post(
                "/admin/notifications/read-all", headers=member_headers
            ).status_code == 401

            # Another account cannot list it, mark it or clear it.
            assert _inbox(client, owner)["total"] == 0
            assert client.get("/admin/notifications/unread-count", headers=owner).json() == {
                "unread": 0
            }
            assert client.post(f"/admin/notifications/{notice_id}/read", headers=owner).status_code == 404
            assert client.post(
                f"/admin/notifications/{uuid4()}/read", headers=trainer
            ).status_code == 404
            assert client.post("/admin/notifications/read-all", headers=owner).json() == {
                "updated": 0
            }

            # The owner keeps the workout pending because only its own inbox moved.
            assert client.get("/admin/notifications/unread-count", headers=trainer).json() == {
                "unread": 1
            }
            assert client.post(
                f"/admin/notifications/{notice_id}/read", headers=trainer
            ).status_code == 200
            with Session(engine) as session:
                workout = client.get(
                    f"/admin/routines/assignments/{ids['assignment']}/workouts",
                    headers=owner,
                ).json()
                assert [item["status"] for item in workout] == ["logged"]
                assert _notifications_for(session, ids["ghost_user"]) == 0
    finally:
        app.dependency_overrides.clear()
