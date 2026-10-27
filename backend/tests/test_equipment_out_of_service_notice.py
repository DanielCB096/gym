"""A machine that stops working is a broken step in someone's plan.

Only the members whose *live* routine version contains an exercise bound to that
machine are told about it, once per machine and club day, whether the unit was
stopped from the panel or by a critical ticket.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.maintenance import (
    create_equipment,
    create_ticket,
    set_equipment_status,
)
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.notifications import (
    MemberNotification,
    list_member_notifications,
)
from app.modules.routines import (
    RoutineItemInput,
    cancel_assignment,
    create_assignment,
    create_exercise,
    create_routine,
)
from app.timezone import club_date


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


def _seed_member(session: Session, *, first_name: str) -> UUID:
    now = datetime.now(timezone.utc)
    member = Member(
        first_name=first_name,
        last_name="Demo",
        email=f"{first_name.lower()}@example.com",
        status="active",
    )
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
            # Far from every 7/3/1-day window so the expiring reminder never
            # mixes into the counts this module asserts on.
            ends_at=now + timedelta(days=60),
        )
    )
    session.commit()
    return member.id


def _prepare() -> tuple[object, dict[str, UUID]]:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    today = datetime.now(timezone.utc).date()
    ids: dict[str, UUID] = {}
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        ids["ana"] = _seed_member(session, first_name="Ana")
        ids["beto"] = _seed_member(session, first_name="Beto")
        ids["carlos"] = _seed_member(session, first_name="Carlos")

        machine = create_equipment(
            session,
            name="Bicicleta espacial",
            category="Cardio",
            location="Sala de ciclo",
        )
        ids["machine"] = machine.id
        other = create_equipment(session, name="Rack de sentadilla", category="Fuerza")
        ids["other"] = other.id

        cycling = create_exercise(
            session,
            name=f"Bici fija {uuid4().hex[:4]}",
            muscle_group="Pierna",
            category="Cardio",
            equipment_id=machine.id,
        )
        squat = create_exercise(
            session,
            name=f"Sentadilla {uuid4().hex[:4]}",
            muscle_group="Pierna",
            category="Fuerza",
            equipment_id=other.id,
        )
        free = create_exercise(
            session,
            name=f"Plancha {uuid4().hex[:4]}",
            muscle_group="Core",
            category="Movilidad",
        )
        ids["cycling"] = cycling.id
        ids["squat"] = squat.id
        ids["free"] = free.id

        cycling_routine = create_routine(
            session,
            name="Cardio ciclo",
            objective="Resistencia",
            items=[RoutineItemInput(exercise_id=cycling.id, sets=3, reps="15")],
        )
        other_routine = create_routine(
            session,
            name="Fuerza rack",
            objective="Fuerza general",
            items=[RoutineItemInput(exercise_id=squat.id, sets=4, reps="10")],
        )
        free_routine = create_routine(
            session,
            name="Core en tapete",
            objective="Estabilidad",
            items=[RoutineItemInput(exercise_id=free.id, sets=3, reps="45s")],
        )
        ids["assignment_ana"] = create_assignment(
            session,
            routine_id=cycling_routine.routine.id,
            member_id=ids["ana"],
            start_date=today,
        ).id
        ids["assignment_beto"] = create_assignment(
            session,
            routine_id=other_routine.routine.id,
            member_id=ids["beto"],
            start_date=today,
        ).id
        carlos_assignment = create_assignment(
            session,
            routine_id=free_routine.routine.id,
            member_id=ids["carlos"],
            start_date=today,
        )
        cancel_assignment(session, carlos_assignment.id)
    return engine, ids


def _inbox(session: Session, member_id: UUID) -> list:
    return list_member_notifications(session, member_id=member_id, page_size=50).items


def _rows(session: Session, member_id: UUID) -> list:
    return list(
        session.exec(
            select(MemberNotification)
            .where(MemberNotification.member_id == member_id)
            .order_by(MemberNotification.created_at)
        ).all()
    )


def test_only_the_members_whose_plan_uses_the_machine_are_told(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-equipment-notice-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine, ids = _prepare()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

            changed = client.post(
                f"/admin/maintenance/equipment/{ids['machine']}/status",
                headers=staff,
                json={"status": "out_of_service"},
            )
            assert changed.status_code == 200, changed.text

            requested = client.post(
                "/member/auth/request-code", json={"email": "ana@example.com"}
            )
            assert requested.status_code == 202, requested.text
            verified = client.post(
                "/member/auth/verify",
                json={"email": "ana@example.com", "code": requested.json()["preview_code"]},
            )
            assert verified.status_code == 200, verified.text
            ana = {"Authorization": f"Bearer {verified.json()['access_token']}"}

            inbox = client.get("/member/notifications", headers=ana).json()
            assert inbox["total"] == 1
            assert inbox["unread_total"] == 1
            notice = inbox["items"][0]
            assert notice["kind"] == "equipment_out_of_service"
            assert notice["title"] == "Un equipo está fuera de servicio"
            assert "Bicicleta espacial" in notice["body"]
            assert "Sala de ciclo" in notice["body"]
            assert notice["ref_id"] == str(ids["machine"])

            with Session(engine) as session:
                # Ana follows the plan that uses the machine; Beto uses a
                # different unit; Carlos' assignment was cancelled, so nobody
                # tells him about a machine he no longer trains on.
                assert [row.kind for row in _inbox(session, ids["beto"])] == []
                assert [row.kind for row in _inbox(session, ids["carlos"])] == []

                # Bringing it back and stopping it again the same day is the same
                # fact: the club day is part of the dedupe key.
                assert (
                    set_equipment_status(session, ids["machine"], status="operational").status
                    == "operational"
                )
                set_equipment_status(session, ids["machine"], status="out_of_service")
                assert len(_inbox(session, ids["ana"])) == 1

                # A unit already stopped does not announce itself a second time.
                before = len(_inbox(session, ids["ana"]))
                assert (
                    set_equipment_status(session, ids["machine"], status="out_of_service").status
                    == "out_of_service"
                )
                assert len(_inbox(session, ids["ana"])) == before

                # A ticket that stops the other unit tells the member whose plan
                # uses it, and still nobody whose assignment is closed.
                create_ticket(
                    session,
                    equipment_id=ids["other"],
                    title="Banda floja",
                    severity="critical",
                )
                assert [row.kind for row in _rows(session, ids["beto"])] == [
                    "equipment_out_of_service"
                ]
                assert _rows(session, ids["carlos"]) == []
    finally:
        app.dependency_overrides.clear()


def test_a_critical_ticket_announces_the_outage_once_per_club_day() -> None:
    engine, ids = _prepare()
    first_day = datetime.now(timezone.utc) + timedelta(days=1)
    second_day = first_day + timedelta(days=1)
    with Session(engine) as session:
        create_ticket(
            session,
            equipment_id=ids["machine"],
            title="Motor humea",
            severity="critical",
            now=first_day,
        )
        notices = _rows(session, ids["ana"])
        assert [row.kind for row in notices] == ["equipment_out_of_service"]
        # The message is about the machine, not about the ticket that stopped it.
        assert "Motor humea" not in notices[0].body
        assert f"{club_date(first_day):%d/%m/%Y}" in notices[0].body
        assert notices[0].dedupe_key == (
            f"equipment_out_of_service:{ids['machine']}:{ids['ana']}:"
            f"{club_date(first_day):%Y%m%d}"
        )

        # A machine that is already stopped does not announce itself again: the
        # second ticket is the same fact for the member, not a new outage.
        create_ticket(
            session,
            equipment_id=ids["machine"],
            title="Segundo reporte el mismo día",
            severity="critical",
            now=first_day,
        )
        assert len(_rows(session, ids["ana"])) == 1

        # Repaired, then broken again on a later club day: that is a new fact.
        assert (
            set_equipment_status(
                session, ids["machine"], status="operational", now=second_day
            ).status
            == "operational"
        )
        assert len(_rows(session, ids["ana"])) == 1
        create_ticket(
            session,
            equipment_id=ids["machine"],
            title="Vuelve a fallar",
            severity="critical",
            now=second_day,
        )
        assert len(_rows(session, ids["ana"])) == 2
