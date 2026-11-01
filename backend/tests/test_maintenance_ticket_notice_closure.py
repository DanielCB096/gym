"""Closing a maintenance ticket closes the notice that assigned it."""

from collections.abc import Iterator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.models import Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications.models import StaffNotification


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


def _prepare() -> tuple[object, dict[str, UUID]]:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        technician = Employee(
            employee_number="M-080",
            first_name="Iván",
            last_name="Ruiz",
            email="m080@example.com",
            job_title="Técnico",
        )
        session.add(technician)
        session.flush()
        register_user(
            session,
            email="tech@example.com",
            password="tech-strong-password",
            employee_id=technician.id,
            role_codes=("maintenance",),
        )
        session.commit()
        ids = {"technician_employee": technician.id}
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


def _equipment(client: TestClient, owner: dict[str, str], name: str) -> str:
    created = client.post(
        "/admin/maintenance/equipment",
        headers=owner,
        json={"name": name, "category": "Cardio", "useful_life_months": 60},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _ticket(
    client: TestClient,
    owner: dict[str, str],
    equipment_id: str,
    *,
    title: str,
    assigned_to: UUID | None,
) -> str:
    body = {"equipment_id": equipment_id, "title": title, "severity": "low"}
    if assigned_to is not None:
        body["assigned_to"] = str(assigned_to)
    created = client.post("/admin/maintenance/tickets", headers=owner, json=body)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _notices(engine) -> list[StaffNotification]:
    with Session(engine) as session:
        return list(session.exec(select(StaffNotification)).all())


def _badge(client: TestClient, technician: dict[str, str]) -> int:
    response = client.get("/admin/notifications/unread-count", headers=technician)
    assert response.status_code == 200, response.text
    return response.json()["unread"]


def _resolve(client: TestClient, owner: dict[str, str], ticket_id: str) -> None:
    resolved = client.post(
        f"/admin/maintenance/tickets/{ticket_id}/resolve",
        headers=owner,
        json={"resolution_notes": "Se revisó la máquina y quedó operativa."},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["ticket"]["status"] == "resolved"


def test_resolving_the_ticket_closes_the_assigned_notice() -> None:
    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            technician = _login(client, "tech@example.com", "tech-strong-password")
            equipment_id = _equipment(client, owner, "Banda 080")
            ticket_id = _ticket(
                client,
                owner,
                equipment_id,
                title="Banda suelta",
                assigned_to=ids["technician_employee"],
            )

            notice = _notices(engine)[0]
            assert notice.kind == "maintenance_ticket_assigned"
            assert notice.resolved_at is None
            assert _badge(client, technician) == 1

            _resolve(client, owner, ticket_id)

            notice = _notices(engine)[0]
            assert notice.resolved_at is not None
            assert notice.read_at is not None
            assert _badge(client, technician) == 0
            inbox = client.get("/admin/notifications", headers=technician)
            assert inbox.status_code == 200, inbox.text
            item = inbox.json()["items"][0]
            assert item["resolved_at"] is not None
            assert item["read_at"] is not None
    finally:
        app.dependency_overrides.clear()


def test_cancelling_the_ticket_closes_the_assigned_notice() -> None:
    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            technician = _login(client, "tech@example.com", "tech-strong-password")
            equipment_id = _equipment(client, owner, "Caminadora 080")
            ticket_id = _ticket(
                client,
                owner,
                equipment_id,
                title="Ruido al caminar",
                assigned_to=ids["technician_employee"],
            )
            assert _badge(client, technician) == 1

            cancelled = client.post(
                f"/admin/maintenance/tickets/{ticket_id}/cancel",
                headers=owner,
                json={"reason": "Se atendió como parte de otra visita."},
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"

            notice = _notices(engine)[0]
            assert notice.resolved_at is not None
            assert notice.read_at is not None
            assert _badge(client, technician) == 0
    finally:
        app.dependency_overrides.clear()


def test_resolving_one_ticket_leaves_the_other_notice_open() -> None:
    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            technician = _login(client, "tech@example.com", "tech-strong-password")
            equipment_id = _equipment(client, owner, "Elíptica 080")
            first = _ticket(
                client,
                owner,
                equipment_id,
                title="Polea derecha",
                assigned_to=ids["technician_employee"],
            )
            second = _ticket(
                client,
                owner,
                equipment_id,
                title="Polea izquierda",
                assigned_to=ids["technician_employee"],
            )
            assert _badge(client, technician) == 2

            _resolve(client, owner, first)

            by_ref = {str(notice.ref_id): notice for notice in _notices(engine)}
            assert by_ref[first].resolved_at is not None
            assert by_ref[second].resolved_at is None
            assert _badge(client, technician) == 1
    finally:
        app.dependency_overrides.clear()


def test_reading_the_notice_keeps_it_owed_until_the_ticket_closes() -> None:
    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            technician = _login(client, "tech@example.com", "tech-strong-password")
            equipment_id = _equipment(client, owner, "Remo 080")
            ticket_id = _ticket(
                client,
                owner,
                equipment_id,
                title="Cable deshilachado",
                assigned_to=ids["technician_employee"],
            )
            notice_id = _notices(engine)[0].id

            marked = client.post(
                f"/admin/notifications/{notice_id}/read", headers=technician
            )
            assert marked.status_code == 200, marked.text
            assert marked.json()["read_at"] is not None
            # Reading is not doing: the badge still owes the ticket.
            assert _badge(client, technician) == 1
            assert _notices(engine)[0].resolved_at is None

            _resolve(client, owner, ticket_id)

            assert _badge(client, technician) == 0
            assert _notices(engine)[0].resolved_at is not None
    finally:
        app.dependency_overrides.clear()


def test_resolving_a_ticket_nobody_was_assigned_touches_no_notice() -> None:
    engine, _ = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            equipment_id = _equipment(client, owner, "Bicicleta 080")
            ticket_id = _ticket(
                client,
                owner,
                equipment_id,
                title="Asiento flojo",
                assigned_to=None,
            )
            assert _notices(engine) == []

            _resolve(client, owner, ticket_id)

            assert _notices(engine) == []
    finally:
        app.dependency_overrides.clear()
