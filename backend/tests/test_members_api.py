from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import (
    Member,
    MemberConsent,
    Membership,
    MembershipEvent,
    Plan,
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


def _seed_directory(session: Session) -> tuple[UUID, UUID]:
    now = datetime.now(timezone.utc)
    monthly = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    annual = Plan(code="ANNUAL", name="Anual", duration_days=365, price_cents=500000)
    session.add(monthly)
    session.add(annual)
    session.flush()

    people = [
        ("Ana", "Lopez", "active", "ana@example.com", now - timedelta(days=10), now + timedelta(days=30), monthly.id),
        ("Carla", "Mendez", "active", "carla@example.com", now - timedelta(days=27), now + timedelta(days=3), monthly.id),
        ("Beto", "Ruiz", "expired", "beto@example.com", now - timedelta(days=60), now - timedelta(days=30), annual.id),
    ]
    for first_name, last_name, status, email, starts_at, ends_at, plan_id in people:
        member = Member(first_name=first_name, last_name=last_name, email=email, status="active")
        session.add(member)
        session.flush()
        session.add(
            Membership(
                member_id=member.id,
                plan_id=plan_id,
                status=status,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )

    # Member without membership, still pending their alta.
    session.add(Member(first_name="Diego", last_name="Soto", email="diego@example.com", status="pending"))
    session.commit()
    return monthly.id, annual.id


def test_admin_members_pagination_search_and_summary() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
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
        _seed_directory(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            assert client.get("/admin/members").status_code == 401

            headers = _login(client, "reception@example.com", "reception-strong-password")

            first_page = client.get("/admin/members", headers=headers, params={"page": 1, "page_size": 2})
            assert first_page.status_code == 200
            body = first_page.json()
            assert body["total"] == 4
            assert body["pages"] == 2
            assert body["page"] == 1
            assert body["page_size"] == 2
            assert [item["last_name"] for item in body["items"]] == ["Lopez", "Mendez"]

            second_page = client.get("/admin/members", headers=headers, params={"page": 2, "page_size": 2})
            assert [item["last_name"] for item in second_page.json()["items"]] == ["Ruiz", "Soto"]

            summary = body["summary"]
            assert summary == {"active": 2, "expiring_soon": 1, "frozen": 0, "pending": 1}

            searched = client.get("/admin/members", headers=headers, params={"search": "carla"})
            searched_body = searched.json()
            assert searched_body["total"] == 1
            assert searched_body["items"][0]["email"] == "carla@example.com"
            # Summary stays club-wide even while searching.
            assert searched_body["summary"]["active"] == 2

            # A full name spans two columns and still has to match.
            full_name = client.get("/admin/members", headers=headers, params={"search": "Carla Mendez"})
            full_name_body = full_name.json()
            assert full_name_body["total"] == 1
            assert full_name_body["items"][0]["email"] == "carla@example.com"

            # Every word has to match, so an unrelated word finds nobody.
            mixed = client.get("/admin/members", headers=headers, params={"search": "Carla Ruiz"})
            assert mixed.json()["total"] == 0

            ana = next(item for item in body["items"] if item["email"] == "ana@example.com")
            assert ana["membership_status"] == "active"
            assert ana["plan_name"] == "Mensual"

            diego = next(item for item in second_page.json()["items"] if item["email"] == "diego@example.com")
            assert diego["membership_status"] is None
            assert diego["plan_name"] is None

            assert client.get("/admin/members", headers=headers, params={"page_size": 0}).status_code == 422

            accountant_headers = _login(client, "accountant@example.com", "accountant-strong-password")
            assert client.get("/admin/members", headers=accountant_headers).status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_admin_members_sorting_and_state_filter() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="reception@example.com",
            password="reception-strong-password",
            role_codes=("reception",),
        )
        monthly_id, annual_id = _seed_directory(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = _login(client, "reception@example.com", "reception-strong-password")

            def names(**params: object) -> list[str]:
                response = client.get("/admin/members", headers=headers, params=params)
                assert response.status_code == 200, response.text
                return [item["last_name"] for item in response.json()["items"]]

            def total(**params: object) -> int:
                response = client.get("/admin/members", headers=headers, params=params)
                assert response.status_code == 200, response.text
                return response.json()["total"]

            assert names() == ["Lopez", "Mendez", "Ruiz", "Soto"]
            assert names(direction="desc") == ["Soto", "Ruiz", "Mendez", "Lopez"]
            # Renewal ascending keeps members without membership last.
            assert names(sort="renewal") == ["Ruiz", "Mendez", "Lopez", "Soto"]
            # Descending still keeps nulls last.
            assert names(sort="renewal", direction="desc") == ["Lopez", "Mendez", "Ruiz", "Soto"]
            assert names(sort="plan")[-1] == "Soto"

            assert total(state="active") == 2
            assert total(state="expiring_soon") == 1
            assert total(state="frozen") == 0
            assert total(state="pending") == 1

            expiring = client.get(
                "/admin/members",
                headers=headers,
                params={"state": "expiring_soon", "sort": "renewal"},
            ).json()
            assert [item["email"] for item in expiring["items"]] == ["carla@example.com"]
            # Summary stays club-wide while filtering.
            assert expiring["summary"]["active"] == 2

            combined = client.get(
                "/admin/members",
                headers=headers,
                params={"search": "mendez", "state": "active"},
            ).json()
            assert combined["total"] == 1

            # Plan options are club-wide and drive the filter.
            options = client.get("/admin/members", headers=headers).json()["plans"]
            assert [option["name"] for option in options] == ["Anual", "Mensual"]
            assert {option["id"] for option in options} == {str(monthly_id), str(annual_id)}
            assert total(plan_id=str(monthly_id)) == 2
            assert total(plan_id=str(annual_id)) == 1
            assert names(plan_id=str(annual_id)) == ["Ruiz"]
            assert total(plan_id=str(uuid4())) == 0
            assert total(plan_id=str(annual_id), state="active") == 0
            # Options stay club-wide while filtering by plan.
            assert len(client.get("/admin/members", headers=headers, params={"plan_id": str(annual_id)}).json()["plans"]) == 2

            assert client.get("/admin/members", headers=headers, params={"sort": "bogus"}).status_code == 422
            assert client.get("/admin/members", headers=headers, params={"direction": "sideways"}).status_code == 422
            assert client.get("/admin/members", headers=headers, params={"state": "bogus"}).status_code == 422
            assert client.get("/admin/members", headers=headers, params={"plan_id": "not-a-uuid"}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_members_register_member() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="reception@example.com",
            password="reception-strong-password",
            role_codes=("reception",),
        )
        register_user(
            session,
            email="trainer@example.com",
            password="trainer-strong-password",
            role_codes=("trainer",),
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            payload = {
                "first_name": "Nuevo",
                "last_name": "Socio",
                "email": "nuevo@example.com",
                "phone": "5551234567",
                "privacy_notice_accepted": True,
            }
            assert client.post("/admin/members", json=payload).status_code == 401

            headers = _login(client, "reception@example.com", "reception-strong-password")
            created = client.post("/admin/members", json=payload, headers=headers)
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["first_name"] == "Nuevo"
            assert body["last_name"] == "Socio"
            assert body["status"] == "pending"
            assert body["consent_recorded"] is True

            # The alta appears in the directory waiting for plan and first charge.
            directory = client.get("/admin/members", headers=headers, params={"search": "nuevo"}).json()
            assert directory["total"] == 1
            assert directory["items"][0]["membership_status"] is None
            assert directory["summary"]["pending"] == 1

            # Duplicate emails are rejected case-insensitively.
            duplicate = client.post(
                "/admin/members",
                json={**payload, "email": "NUEVO@example.com"},
                headers=headers,
            )
            assert duplicate.status_code == 409

            # Consent is optional but reported, and contact can be a phone alone.
            without_consent = client.post(
                "/admin/members",
                json={**payload, "email": None, "phone": "5559999999", "privacy_notice_accepted": False},
                headers=headers,
            )
            assert without_consent.status_code == 201
            assert without_consent.json()["consent_recorded"] is False

            # Names and at least one contact are required.
            assert client.post(
                "/admin/members",
                json={**payload, "first_name": "  "},
                headers=headers,
            ).status_code == 422
            assert client.post(
                "/admin/members",
                json={**payload, "email": None, "phone": None},
                headers=headers,
            ).status_code == 422

            trainer_headers = _login(client, "trainer@example.com", "trainer-strong-password")
            assert client.post(
                "/admin/members",
                json={**payload, "email": "otro@example.com"},
                headers=trainer_headers,
            ).status_code == 403

        with Session(engine) as session:
            consents = session.exec(select(MemberConsent)).all()
            assert len(consents) == 1
            assert consents[0].consent_type == "privacy_notice"
            assert consents[0].document_version == "privacidad-v1"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_admin_members_membership_lifecycle() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="reception@example.com",
            password="reception-strong-password",
            role_codes=("reception",),
        )
        register_user(
            session,
            email="trainer@example.com",
            password="trainer-strong-password",
            role_codes=("trainer",),
        )
        monthly_id, annual_id = _seed_directory(session)
        diego_id = session.exec(select(Member.id).where(Member.email == "diego@example.com")).one()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = _login(client, "reception@example.com", "reception-strong-password")

            # Active plans drive the assignment picker.
            plans = client.get("/admin/plans", headers=headers)
            assert plans.status_code == 200, plans.text
            assert [plan["name"] for plan in plans.json()] == ["Anual", "Mensual"]
            assert client.get("/admin/plans").status_code == 401

            # Editing contact details, keeping email unique.
            updated = client.patch(
                f"/admin/members/{diego_id}",
                json={
                    "first_name": "Diego",
                    "last_name": "Soto",
                    "email": "diego.soto@example.com",
                    "phone": "5551234567",
                },
                headers=headers,
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["email"] == "diego.soto@example.com"
            assert client.patch(
                f"/admin/members/{diego_id}",
                json={"first_name": "Diego", "last_name": "Soto", "email": "ANA@example.com", "phone": None},
                headers=headers,
            ).status_code == 409
            assert client.patch(
                f"/admin/members/{diego_id}",
                json={"first_name": "Diego", "last_name": "Soto", "email": None, "phone": None},
                headers=headers,
            ).status_code == 422
            assert client.patch(
                f"/admin/members/{uuid4()}",
                json={"first_name": "Nadie", "last_name": "Nadie", "email": "nadie@example.com"},
                headers=headers,
            ).status_code == 404

            # Assigning a plan activates the membership without any charge.
            assigned = client.post(
                f"/admin/members/{diego_id}/membership",
                json={"plan_id": str(monthly_id)},
                headers=headers,
            )
            assert assigned.status_code == 200, assigned.text
            body = assigned.json()
            assert body["status"] == "active"
            assert body["previous_status"] is None
            assert body["plan_changed"] is False
            assert body["plan_name"] == "Mensual"
            assert body["auto_renew"] is False

            directory = client.get("/admin/members", headers=headers, params={"search": "diego"}).json()
            diego = directory["items"][0]
            assert diego["membership_status"] == "active"
            assert diego["plan_name"] == "Mensual"
            assert diego["status"] == "active"
            # The pending alta is now an active member.
            assert directory["summary"]["pending"] == 0
            assert directory["summary"]["active"] == 3

            # Changing the plan restarts the period from today.
            changed = client.post(
                f"/admin/members/{diego_id}/membership",
                json={"plan_id": str(annual_id), "auto_renew": True},
                headers=headers,
            ).json()
            assert changed["plan_changed"] is True
            assert changed["previous_status"] == "active"
            assert changed["plan_name"] == "Anual"
            assert changed["auto_renew"] is True

            # Freeze pauses the vigencia and resume brings it back.
            frozen = client.post(
                f"/admin/members/{diego_id}/membership/freeze", headers=headers
            )
            assert frozen.status_code == 200, frozen.text
            assert frozen.json()["status"] == "frozen"
            assert frozen.json()["previous_status"] == "active"
            assert client.get("/admin/members", headers=headers).json()["summary"]["frozen"] == 1

            resumed = client.post(
                f"/admin/members/{diego_id}/membership/resume", headers=headers
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["status"] == "active"

            # Resuming a non-frozen membership is rejected.
            assert client.post(
                f"/admin/members/{diego_id}/membership/resume", headers=headers
            ).status_code == 409

            # Cancelling requires a reason and is terminal.
            assert client.post(
                f"/admin/members/{diego_id}/membership/cancel",
                json={"reason": "   "},
                headers=headers,
            ).status_code == 422
            cancelled = client.post(
                f"/admin/members/{diego_id}/membership/cancel",
                json={"reason": "Se mudó de ciudad"},
                headers=headers,
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            assert client.post(
                f"/admin/members/{diego_id}/membership/freeze", headers=headers
            ).status_code == 404

            # A cancelled membership no longer blocks a fresh alta.
            reassigned = client.post(
                f"/admin/members/{diego_id}/membership",
                json={"plan_id": str(monthly_id)},
                headers=headers,
            ).json()
            assert reassigned["status"] == "active"
            assert reassigned["previous_status"] is None

            # Unknown ids and permissions.
            assert client.post(
                f"/admin/members/{uuid4()}/membership",
                json={"plan_id": str(monthly_id)},
                headers=headers,
            ).status_code == 404
            assert client.post(
                f"/admin/members/{diego_id}/membership",
                json={"plan_id": str(uuid4())},
                headers=headers,
            ).status_code == 404

            trainer_headers = _login(client, "trainer@example.com", "trainer-strong-password")
            assert client.post(
                f"/admin/members/{diego_id}/membership",
                json={"plan_id": str(monthly_id)},
                headers=trainer_headers,
            ).status_code == 403
            assert client.patch(
                f"/admin/members/{diego_id}",
                json={"first_name": "Diego", "last_name": "Soto", "email": "diego.soto@example.com"},
                headers=trainer_headers,
            ).status_code == 403

        with Session(engine) as session:
            events = session.exec(select(MembershipEvent)).all()
            counts: dict[str, int] = {}
            for event in events:
                counts[event.event_type] = counts.get(event.event_type, 0) + 1
            assert counts == {
                "manual_activation": 2,
                "plan_changed": 1,
                "frozen": 1,
                "resumed": 1,
                "cancelled": 1,
            }
            # Manual activation is explicit that no charge was taken.
            manual = next(event for event in events if event.event_type == "manual_activation")
            assert manual.event_metadata == {"plan_id": str(monthly_id), "no_charge": True}
            cancelled_event = next(event for event in events if event.event_type == "cancelled")
            assert cancelled_event.event_metadata == {"reason": "Se mudó de ciudad"}
            assert cancelled_event.from_status == "active"
            assert all(event.actor_type == "employee" for event in events)
            assert all(event.occurred_at is not None for event in events)
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
