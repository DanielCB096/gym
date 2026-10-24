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
from app.modules.maintenance.service import create_equipment, create_ticket

YESTERDAY = date.today() - timedelta(days=1)
IN_30_DAYS = date.today() + timedelta(days=30)


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
    register_user(session, email="maint@example.com", password="maint-strong-password", role_codes=("maintenance",))
    register_user(session, email="trainer@example.com", password="trainer-strong-password", role_codes=("trainer",))
    register_user(session, email="reception@example.com", password="reception-strong-password", role_codes=("reception",))
    register_user(session, email="accountant@example.com", password="accountant-strong-password", role_codes=("accountant",))


def _add_employee(session: Session, *, first: str = "Luis") -> str:
    employee = Employee(
        employee_number=f"E-{uuid4().hex[:6]}",
        first_name=first,
        last_name="Técnico",
        job_title="Mantenimiento",
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return str(employee.id)


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_equipment(client: TestClient, headers: dict[str, str], *, name: str, **extra) -> dict:
    payload = {"name": name, "category": "Cardio", **extra}
    response = client.post("/admin/maintenance/equipment", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_equipment_registry_and_permissions() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            assert client.get("/admin/maintenance/equipment").status_code == 401

            manager = _login(client, "manager@example.com", "manager-strong-password")
            maintenance = _login(client, "maint@example.com", "maint-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")

            # Reporting is a front-desk/trainer job; managing is not.
            assert client.get("/admin/maintenance/equipment", headers=reception).status_code == 200
            assert client.get("/admin/maintenance/equipment", headers=trainer).status_code == 200
            assert client.get("/admin/maintenance/equipment", headers=accountant).status_code == 403
            assert client.post(
                "/admin/maintenance/equipment",
                headers=reception,
                json={"name": "Caminadora", "category": "Cardio"},
            ).status_code == 403
            assert client.post(
                "/admin/maintenance/equipment",
                headers=trainer,
                json={"name": "Caminadora", "category": "Cardio"},
            ).status_code == 403

            bike = _create_equipment(
                client,
                maintenance,
                name="Bicicleta estática",
                location="Cardio",
                serial_number="SN-001",
                purchase_cost_cents=2500000,
                acquired_on=YESTERDAY.isoformat(),
                useful_life_months=60,
            )
            assert bike["status"] == "operational"
            assert bike["open_tickets"] == 0
            treadmill = _create_equipment(
                client, manager, name="Caminadora", location="Cardio", serial_number="SN-002"
            )
            press = _create_equipment(
                client, manager, name="Prensa de pierna", category="Fuerza", location="Pesas"
            )

            # Unknown/duplicate identifiers are rejected.
            assert client.post(
                "/admin/maintenance/equipment",
                headers=manager,
                json={"name": "Otra", "category": "Cardio", "serial_number": "sn-001"},
            ).status_code == 409
            assert client.post(
                "/admin/maintenance/equipment",
                headers=manager,
                json={"name": "", "category": "Cardio"},
            ).status_code == 422

            directory = client.get("/admin/maintenance/equipment", headers=manager).json()
            assert directory["total"] == 3
            assert directory["summary"]["operational"] == 3
            assert directory["locations"] == ["Cardio", "Pesas"]
            assert directory["categories"] == ["Cardio", "Fuerza"]
            filtered = client.get(
                "/admin/maintenance/equipment", headers=manager, params={"location": "cardio"}
            ).json()
            assert filtered["total"] == 2
            searched = client.get(
                "/admin/maintenance/equipment", headers=manager, params={"search": "SN-002"}
            ).json()
            assert searched["total"] == 1

            options = client.get("/admin/maintenance/equipment/options", headers=trainer).json()
            assert len(options) == 3

            # Reception may take a machine out of service (report permission).
            changed = client.post(
                f"/admin/maintenance/equipment/{press['id']}/status",
                headers=reception,
                json={"status": "out_of_service"},
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["status"] == "out_of_service"

            detail = client.get(
                f"/admin/maintenance/equipment/{bike['id']}", headers=maintenance
            ).json()
            assert detail["equipment"]["serial_number"] == "SN-001"
            assert detail["tickets"] == []
            assert detail["records"] == []
            assert client.get(f"/admin/maintenance/equipment/{uuid4()}", headers=manager).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_critical_ticket_blocks_and_resolve_restores() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        technician_id = _add_employee(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")

            treadmill = _create_equipment(client, manager, name="Caminadora", location="Cardio")

            # Reception can report the fault; a critical one blocks the machine.
            reported = client.post(
                "/admin/maintenance/tickets",
                headers=reception,
                json={
                    "equipment_id": treadmill["id"],
                    "title": "Banda rota",
                    "severity": "critical",
                    "description": "Se rompió la banda al correr",
                },
            )
            assert reported.status_code == 201, reported.text
            ticket = reported.json()
            assert ticket["status"] == "open"
            assert ticket["blocked_equipment"] is True
            assert ticket["code"].startswith("MT-")

            blocked = client.get(
                f"/admin/maintenance/equipment/{treadmill['id']}", headers=manager
            ).json()
            assert blocked["equipment"]["status"] == "out_of_service"
            assert blocked["equipment"]["open_tickets"] == 1
            assert len(blocked["tickets"]) == 1

            # Reception cannot resolve it.
            assert client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/resolve",
                headers=reception,
                json={"resolution_notes": "Cambio de banda"},
            ).status_code == 403

            # Resolution needs an explanation.
            assert client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/resolve",
                headers=manager,
                json={},
            ).status_code == 422

            started = client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/start", headers=manager
            )
            assert started.status_code == 200
            assert started.json()["status"] == "in_progress"

            resolved = client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/resolve",
                headers=manager,
                json={
                    "resolution_notes": "Cambio de banda y calibración",
                    "cost_cents": 185000,
                    "technician_id": technician_id,
                    "next_due_on": IN_30_DAYS.isoformat(),
                },
            )
            assert resolved.status_code == 200, resolved.text
            body = resolved.json()
            assert body["ticket"]["status"] == "resolved"
            assert body["ticket"]["cost_cents"] == 185000
            assert body["record"]["kind"] == "corrective"
            assert body["record"]["cost_cents"] == 185000
            assert body["record"]["technician_name"] == "Luis Técnico"

            # Resolving restores the machine and schedules the next preventive.
            after = client.get(
                f"/admin/maintenance/equipment/{treadmill['id']}", headers=manager
            ).json()
            assert after["equipment"]["status"] == "operational"
            assert after["equipment"]["next_preventive_due"] == IN_30_DAYS.isoformat()
            assert after["equipment"]["open_tickets"] == 0
            assert len(after["records"]) == 1

            # A closed ticket is immutable.
            assert client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/resolve",
                headers=manager,
                json={"resolution_notes": "Otra vez"},
            ).status_code == 409
            assert client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/cancel",
                headers=manager,
                json={"reason": "Ya no aplica"},
            ).status_code == 409
            assert client.patch(
                f"/admin/maintenance/tickets/{ticket['id']}", headers=manager, json={"title": "X"}
            ).status_code == 409

            # Escalating a live ticket to critical blocks the machine.
            minor = client.post(
                "/admin/maintenance/tickets",
                headers=manager,
                json={"equipment_id": treadmill["id"], "title": "Ruido leve", "severity": "low"},
            ).json()
            escalated = client.patch(
                f"/admin/maintenance/tickets/{minor['id']}",
                headers=manager,
                json={"severity": "critical"},
            )
            assert escalated.status_code == 200, escalated.text
            assert escalated.json()["blocked_equipment"] is True
            assert client.get(
                f"/admin/maintenance/equipment/{treadmill['id']}", headers=manager
            ).json()["equipment"]["status"] == "out_of_service"

            # Cancelling a blocking ticket hands the machine back.
            cancelled = client.post(
                f"/admin/maintenance/tickets/{minor['id']}/cancel",
                headers=manager,
                json={"reason": "Falsa alarma"},
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            assert client.get(
                f"/admin/maintenance/equipment/{treadmill['id']}", headers=manager
            ).json()["equipment"]["status"] == "operational"
    finally:
        app.dependency_overrides.clear()


def test_records_checklists_and_service_status() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        technician_id = _add_employee(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            maintenance = _login(client, "maint@example.com", "maint-strong-password")

            bike = _create_equipment(
                client,
                manager,
                name="Bicicleta",
                location="Cardio",
                next_preventive_due=YESTERDAY.isoformat(),
            )
            rack = _create_equipment(client, manager, name="Rack", category="Fuerza", location="Pesas")

            overview = client.get("/admin/maintenance/overview", headers=manager).json()
            assert overview["equipment_total"] == 2
            assert overview["preventives_due"] == 1

            # A preventive record may schedule the next due date.
            recorded = client.post(
                f"/admin/maintenance/equipment/{bike['id']}/records",
                headers=maintenance,
                json={
                    "kind": "preventive",
                    "summary": "Lubricación y ajuste",
                    "cost_cents": 45000,
                    "technician_id": technician_id,
                    "next_due_on": IN_30_DAYS.isoformat(),
                },
            )
            assert recorded.status_code == 201, recorded.text
            assert recorded.json()["equipment_name"] == "Bicicleta"

            assert client.post(
                f"/admin/maintenance/equipment/{bike['id']}/records",
                headers=maintenance,
                json={"kind": "preventive", "summary": "", "cost_cents": 0},
            ).status_code == 422
            assert client.post(
                f"/admin/maintenance/equipment/{bike['id']}/records",
                headers=maintenance,
                json={"kind": "invalid", "summary": "Algo"},
            ).status_code == 422

            refreshed = client.get(
                f"/admin/maintenance/equipment/{bike['id']}", headers=manager
            ).json()
            assert refreshed["equipment"]["next_preventive_due"] == IN_30_DAYS.isoformat()
            assert refreshed["equipment"]["last_maintenance_at"] is not None

            overview = client.get("/admin/maintenance/overview", headers=manager).json()
            assert overview["preventives_due"] == 0
            assert overview["records_last_30_days"] == 1

            listing = client.get("/admin/maintenance/records", headers=manager).json()
            assert listing["total"] == 1
            assert listing["total_cost_cents"] == 45000
            assert client.get(
                "/admin/maintenance/records", headers=manager, params={"kind": "cleaning"}
            ).json()["total"] == 0

            # A checklist observation must be described.
            assert client.post(
                "/admin/maintenance/checklists",
                headers=maintenance,
                json={"area": "Vestidores", "result": "observation"},
            ).status_code == 422
            checklist = client.post(
                "/admin/maintenance/checklists",
                headers=maintenance,
                json={"area": "Vestidores", "result": "observation", "observations": "Fuga en regadera"},
            )
            assert checklist.status_code == 201, checklist.text
            assert checklist.json()["performer_email"] == "maint@example.com"
            client.post(
                "/admin/maintenance/checklists",
                headers=maintenance,
                json={"area": "Piso de pesas", "result": "ok"},
            )
            checklists = client.get("/admin/maintenance/checklists", headers=manager).json()
            assert checklists["total"] == 2
            assert client.get(
                "/admin/maintenance/checklists", headers=manager, params={"area": "vestidores"}
            ).json()["total"] == 1

            status = client.get("/admin/maintenance/service-status", headers=manager).json()
            by_area = {item["area"]: item for item in status}
            assert by_area["Cardio"]["availability"] == "available"
            assert by_area["Pesas"]["total"] == 1

            # Retiring removes the unit from the live fleet but keeps its history.
            retired = client.post(f"/admin/maintenance/equipment/{rack['id']}/retire", headers=manager)
            assert retired.status_code == 200, retired.text
            assert retired.json()["status"] == "retired"
            assert client.patch(
                f"/admin/maintenance/equipment/{rack['id']}", headers=manager, json={"name": "Otro"}
            ).status_code == 409
            assert client.post(
                "/admin/maintenance/tickets",
                headers=manager,
                json={"equipment_id": rack["id"], "title": "Falla"},
            ).status_code == 409
            assert client.post(f"/admin/maintenance/equipment/{rack['id']}/retire", headers=manager).status_code == 409

            directory = client.get("/admin/maintenance/equipment", headers=manager).json()
            assert directory["total"] == 1
            assert directory["summary"]["retired"] == 1
            with_retired = client.get(
                "/admin/maintenance/equipment", headers=manager, params={"include_retired": True}
            ).json()
            assert with_retired["total"] == 2
            assert client.get(
                "/admin/maintenance/equipment", headers=manager, params={"status": "retired"}
            ).json()["total"] == 1

            # An open ticket blocks retirement.
            ticket = client.post(
                "/admin/maintenance/tickets",
                headers=manager,
                json={"equipment_id": bike["id"], "title": "Revisión pendiente"},
            ).json()
            assert client.post(
                f"/admin/maintenance/equipment/{bike['id']}/retire", headers=manager
            ).status_code == 409
            client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/cancel",
                headers=manager,
                json={"reason": "Duplicado"},
            )
            assert client.post(
                f"/admin/maintenance/equipment/{bike['id']}/retire", headers=manager
            ).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_repair_lifecycle_parks_and_releases_the_unit() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            bike = _create_equipment(client, manager, name="Bicicleta", location="Cardio")

            def status() -> str:
                return client.get(
                    f"/admin/maintenance/equipment/{bike['id']}", headers=manager
                ).json()["equipment"]["status"]

            # A low severity ticket does not touch the machine...
            ticket = client.post(
                "/admin/maintenance/tickets",
                headers=manager,
                json={"equipment_id": bike["id"], "title": "Ruido leve", "severity": "low"},
            ).json()
            assert ticket["blocked_equipment"] is False
            assert status() == "operational"

            # ...starting the repair parks it in maintenance...
            started = client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/start", headers=manager
            )
            assert started.status_code == 200
            assert status() == "maintenance"

            # ...and resolving it hands it back to where it was.
            resolved = client.post(
                f"/admin/maintenance/tickets/{ticket['id']}/resolve",
                headers=manager,
                json={"resolution_notes": "Ajuste de rodamiento y engrase"},
            )
            assert resolved.status_code == 200, resolved.text
            assert status() == "operational"

            # Resolving a ticket that never held the machine must leave the
            # status untouched (it used to be forced to "inspection").
            client.post(
                f"/admin/maintenance/equipment/{bike['id']}/status",
                headers=manager,
                json={"status": "inspection"},
            )
            other = client.post(
                "/admin/maintenance/tickets",
                headers=manager,
                json={"equipment_id": bike["id"], "title": "Solo un comentario", "severity": "low"},
            ).json()
            assert client.post(
                f"/admin/maintenance/tickets/{other['id']}/resolve",
                headers=manager,
                json={"resolution_notes": "Sin hallazgos"},
            ).status_code == 200
            assert status() == "inspection"
    finally:
        app.dependency_overrides.clear()


def test_exercise_equipment_link_flags_unavailable_machine() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            press = _create_equipment(client, manager, name="Prensa", category="Fuerza", location="Pesas")

            created = client.post(
                "/admin/routines/exercises",
                headers=manager,
                json={
                    "name": "Prensa inclinada",
                    "muscle_group": "Piernas",
                    "category": "Fuerza",
                    "equipment_id": press["id"],
                },
            )
            assert created.status_code == 201, created.text
            exercise = created.json()
            assert exercise["equipment_id"] == press["id"]
            assert exercise["equipment_status"] == "operational"

            # Unknown and retired equipment are rejected (422, like an unknown
            # trainer in a routine).
            assert client.post(
                "/admin/routines/exercises",
                headers=manager,
                json={
                    "name": "Máquina fantasma",
                    "muscle_group": "Piernas",
                    "category": "Fuerza",
                    "equipment_id": str(uuid4()),
                },
            ).status_code == 422

            routine = client.post(
                "/admin/routines",
                headers=manager,
                json={
                    "name": "Piernas",
                    "items": [{"exercise_id": exercise["id"], "sets": 4, "reps": "10"}],
                },
            ).json()
            plan = client.get(
                f"/admin/routines/{routine['routine']['id']}", headers=manager
            ).json()
            assert plan["items"][0]["equipment_status"] == "operational"

            # Taking the machine out of service shows up in the plan.
            client.post(
                f"/admin/maintenance/equipment/{press['id']}/status",
                headers=manager,
                json={"status": "maintenance"},
            )
            plan = client.get(
                f"/admin/routines/{routine['routine']['id']}", headers=manager
            ).json()
            assert plan["items"][0]["equipment_status"] == "maintenance"

            # The equipment detail lists the exercises that depend on it.
            detail = client.get(
                f"/admin/maintenance/equipment/{press['id']}", headers=manager
            ).json()
            assert [item["name"] for item in detail["exercises"]] == ["Prensa inclinada"]

            # A retired machine cannot be linked to a new exercise.
            client.post(f"/admin/maintenance/equipment/{press['id']}/retire", headers=manager)
            assert client.post(
                "/admin/routines/exercises",
                headers=manager,
                json={
                    "name": "Otra prensa",
                    "muscle_group": "Piernas",
                    "category": "Fuerza",
                    "equipment_id": press["id"],
                },
            ).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_ticket_code_carries_the_club_calendar_day() -> None:
    """``MT-…`` uses the club's local day, not the UTC day (Mexico is UTC-6)."""

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        equipment = create_equipment(session, name="Caminadora", category="Cardio")
        # 2026-10-19 02:00 UTC == 2026-10-18 20:00 in Mexico.
        ticket = create_ticket(
            session,
            equipment_id=equipment.id,
            title="Banda floja",
            now=datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc),
        )
        assert ticket.code.startswith("MT-20261018-"), ticket.code
    engine.dispose()
