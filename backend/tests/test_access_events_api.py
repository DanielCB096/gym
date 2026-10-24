from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.access.models import AccessDecision, AccessDirection, AccessReason
from app.modules.access.service import record_access_event
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan


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


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _decision(member_id, authorized: bool, reason: AccessReason, now: datetime) -> AccessDecision:
    return AccessDecision(
        event_id=uuid4(),
        member_id=member_id,
        authorized=authorized,
        reason=reason,
        direction=AccessDirection.ENTRY,
        occurred_at=now,
        offline=False,
    )


def _seed(session: Session, now: datetime) -> UUID:
    ensure_default_access_control(session)
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
    plan = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    session.add(plan)
    session.flush()
    member = Member(first_name="Ana", last_name="Lopez", email="ana@example.com", status="active")
    session.add(member)
    session.flush()
    session.add(
        Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="active",
            starts_at=now - timedelta(days=10),
            ends_at=now + timedelta(days=20),
        )
    )
    session.commit()

    record_access_event(
        session,
        _decision(member.id, True, AccessReason.ENTRY_ALLOWED, now),
        reader_id="Entrada principal",
    )
    record_access_event(
        session,
        _decision(member.id, False, AccessReason.MEMBERSHIP_EXPIRED, now),
        reader_id="Entrada principal",
    )
    # Manual override for a known member.
    record_access_event(
        session,
        _decision(member.id, True, AccessReason.ENTRY_ALLOWED, now),
        reader_id="Recepción",
        source="manual",
    )
    # Unknown card denied at a reader: stored with a null member.
    record_access_event(
        session,
        _decision(uuid4(), False, AccessReason.SNAPSHOT_MISSING, now),
        reader_id="Acceso lateral",
    )
    return member.id


def test_access_events_listing_and_dashboard() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        _seed(session, now)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            assert client.get("/admin/access-events").status_code == 401
            assert client.get("/admin/dashboard").status_code == 401

            headers = _login(client, "reception@example.com", "reception-strong-password")

            directory = client.get("/admin/access-events", headers=headers)
            assert directory.status_code == 200
            body = directory.json()
            assert body["total"] == 4
            assert body["summary"] == {"total": 4, "authorized": 1, "denied": 2, "manual": 1}
            enriched = next(item for item in body["items"] if item["member_id"] is not None)
            assert enriched["member_name"] == "Ana Lopez"
            assert enriched["plan_name"] == "Mensual"
            unknown = next(item for item in body["items"] if item["member_id"] is None)
            assert unknown["reader_id"] == "Acceso lateral"

            denied = client.get("/admin/access-events", headers=headers, params={"state": "denied"}).json()
            assert denied["total"] == 2
            assert {item["reason"] for item in denied["items"]} == {"membership_expired", "snapshot_missing"}

            manual = client.get("/admin/access-events", headers=headers, params={"state": "manual"}).json()
            assert manual["total"] == 1
            assert manual["items"][0]["source"] == "manual"

            searched = client.get("/admin/access-events", headers=headers, params={"search": "lopez"}).json()
            assert searched["total"] == 3

            searched_reader = client.get("/admin/access-events", headers=headers, params={"search": "lateral"}).json()
            assert searched_reader["total"] == 1

            assert client.get("/admin/access-events", headers=headers, params={"state": "nope"}).status_code == 422

            dashboard = client.get("/admin/dashboard", headers=headers)
            assert dashboard.status_code == 200
            dashboard_body = dashboard.json()
            assert dashboard_body["members"] == {
                "total": 1,
                "active": 1,
                "expiring_soon": 0,
                "frozen": 0,
                "pending": 0,
            }
            assert dashboard_body["access"]["entries_today"] == 2
            assert dashboard_body["access"]["denied_today"] == 2

            accountant_headers = _login(client, "accountant@example.com", "accountant-strong-password")
            assert client.get("/admin/access-events", headers=accountant_headers).status_code == 403
            assert client.get("/admin/dashboard", headers=accountant_headers).status_code == 200
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_manual_access_endpoint() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        member_id = _seed(session, now)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            payload = {"member_id": str(member_id), "note": "Cortesía autorizada por dirección"}
            assert client.post("/admin/access-events/manual", json=payload).status_code == 401

            reception_headers = _login(client, "reception@example.com", "reception-strong-password")
            created = client.post("/admin/access-events/manual", headers=reception_headers, json=payload)
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["source"] == "manual"
            assert body["authorized"] is True
            assert body["direction"] == "entry"
            assert body["reason"] == "manual_override"
            assert body["note"] == "Cortesía autorizada por dirección"
            assert body["reader_id"] == "Recepción"
            assert body["member_id"] == str(member_id)
            assert body["member_name"] == "Ana Lopez"
            assert body["plan_name"] == "Mensual"

            manual = client.get("/admin/access-events", headers=reception_headers, params={"state": "manual"}).json()
            assert manual["total"] == 2
            assert manual["summary"]["manual"] == 2
            assert manual["items"][0]["note"] == "Cortesía autorizada por dirección"

            missing = client.post(
                "/admin/access-events/manual",
                headers=reception_headers,
                json={"member_id": str(uuid4()), "note": None},
            )
            assert missing.status_code == 404

            too_long = client.post(
                "/admin/access-events/manual",
                headers=reception_headers,
                json={"member_id": str(member_id), "note": "x" * 201},
            )
            assert too_long.status_code == 422

            accountant_headers = _login(client, "accountant@example.com", "accountant-strong-password")
            assert client.post(
                "/admin/access-events/manual", headers=accountant_headers, json=payload
            ).status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
