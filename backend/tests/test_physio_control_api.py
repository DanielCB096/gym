"""End-to-end coverage of the physiotherapy control layer (increment 3).

The room now has a catalog of rooms and specialties, a way to correct a pack
without refunding it (extend or void, always audited) and a report that reads
the appointments, not only the money. These tests drive the panel API the way
reception and management use it.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from app.main import app, get_session
from app.modules.notifications.models import MemberNotification
from app.timezone import club_date
from test_classes_api import (
    _add_member,
    _build_engine,
    _login,
    _override,
    _seed_users,
)
from test_physio_api import (
    _add_therapist,
    _attend,
    _book,
    _catalog,
    _create_offer,
    _create_service,
    _open_shift,
    _sell_pack,
    _utc_iso,
)


def _create_room(client: TestClient, headers: dict[str, str], name: str):
    return client.post("/admin/physio/rooms", headers=headers, json={"name": name})


def _create_specialty(client: TestClient, headers: dict[str, str], name: str):
    return client.post(
        "/admin/physio/specialties", headers=headers, json={"name": name}
    )


def _book_with_room(
    client: TestClient,
    headers: dict[str, str],
    *,
    member_id,
    service_id: str,
    therapist_id,
    starts_at: datetime,
    room_id: str | None = None,
    room: str | None = None,
):
    return client.post(
        "/admin/physio/appointments",
        headers=headers,
        json={
            "member_id": str(member_id),
            "service_id": service_id,
            "therapist_employee_id": str(therapist_id),
            "starts_at": starts_at.isoformat(),
            **({"room_id": room_id} if room_id is not None else {}),
            **({"room": room} if room is not None else {}),
        },
    )


def _pack_detail(client: TestClient, headers: dict[str, str], pack_id: str):
    return client.get(f"/admin/physio/packs/{pack_id}", headers=headers)


def test_room_and_specialty_catalog_feeds_the_therapist_profile() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        therapist_id = _add_therapist(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")

            room = _create_room(client, reception, "Consultorio 1")
            assert room.status_code == 201, room.text
            assert room.json()["name"] == "Consultorio 1"

            duplicate = _create_room(client, manager, "consultorio 1")
            assert duplicate.status_code == 409, duplicate.text

            forbidden = _create_room(client, trainer, "Consultorio 3")
            assert forbidden.status_code == 403, forbidden.text

            specialty = _create_specialty(client, reception, "Terapia deportiva")
            assert specialty.status_code == 201, specialty.text
            assert _create_specialty(
                client, manager, "TERAPIA DEPORTIVA"
            ).status_code == 409

            rooms = client.get("/admin/physio/rooms", headers=trainer).json()
            assert [item["name"] for item in rooms] == ["Consultorio 1"]
            specialties = client.get(
                "/admin/physio/specialties", headers=trainer
            ).json()
            assert [item["name"] for item in specialties] == ["Terapia deportiva"]

            profile = client.patch(
                f"/admin/physio/therapists/{therapist_id}",
                headers=reception,
                json={
                    "specialty_id": specialty.json()["id"],
                    "room_id": room.json()["id"],
                },
            )
            assert profile.status_code == 200, profile.text
            assert profile.json()["specialty_name"] == "Terapia deportiva"
            assert profile.json()["room_name"] == "Consultorio 1"

            cleared = client.patch(
                f"/admin/physio/therapists/{therapist_id}",
                headers=manager,
                json={"room_id": None},
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["room_id"] is None
            assert cleared.json()["specialty_name"] == "Terapia deportiva"

            # A deactivated room cannot be used but stays in the catalog.
            deactivated = client.patch(
                f"/admin/physio/rooms/{room.json()['id']}",
                headers=reception,
                json={"is_active": False},
            )
            assert deactivated.status_code == 200, deactivated.text
            assert deactivated.json()["is_active"] is False
            assert client.get("/admin/physio/rooms", headers=reception).json()[0][
                "is_active"
            ] is False
    finally:
        app.dependency_overrides.clear()


def test_booking_uses_the_room_catalog_and_the_therapist_default() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")
        therapist_id = _add_therapist(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            service = _create_service(client, manager).json()

            first = _create_room(client, reception, "Consultorio 1").json()
            second = _create_room(client, reception, "Consultorio 2").json()
            assert client.patch(
                f"/admin/physio/therapists/{therapist_id}",
                headers=reception,
                json={"room_id": first["id"]},
            ).status_code == 200

            start = datetime.now(timezone.utc) + timedelta(days=1)
            start = start.replace(hour=11, minute=0, second=0, microsecond=0)

            # No room chosen: the therapist's default fills the gap.
            defaulted = _book_with_room(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start,
            )
            assert defaulted.status_code == 201, defaulted.text
            assert defaulted.json()["room_id"] == first["id"]
            assert defaulted.json()["room"] == "Consultorio 1"

            explicit = _book_with_room(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start + timedelta(hours=1),
                room_id=second["id"],
            )
            assert explicit.status_code == 201, explicit.text
            assert explicit.json()["room_id"] == second["id"]
            assert explicit.json()["room"] == "Consultorio 2"

            # A free text room still works and leaves the link empty.
            free = _book_with_room(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start + timedelta(hours=2),
                room="Área de camillas",
            )
            assert free.status_code == 201, free.text
            assert free.json()["room_id"] is None
            assert free.json()["room"] == "Área de camillas"

            moved = client.patch(
                f"/admin/physio/appointments/{defaulted.json()['id']}",
                headers=reception,
                json={"room_id": second["id"]},
            )
            assert moved.status_code == 200, moved.text
            assert moved.json()["room_id"] == second["id"]
            assert moved.json()["room"] == "Consultorio 2"

            # Passing null clears both the link and the frozen name.
            cleared = client.patch(
                f"/admin/physio/appointments/{explicit.json()['id']}",
                headers=reception,
                json={"room_id": None},
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["room_id"] is None
            assert cleared.json()["room"] is None

            # A deactivated room cannot be booked.
            assert client.patch(
                f"/admin/physio/rooms/{second['id']}",
                headers=reception,
                json={"is_active": False},
            ).status_code == 200
            rejected = _book_with_room(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start + timedelta(hours=3),
                room_id=second["id"],
            )
            assert rejected.status_code == 409, rejected.text
            assert "desactivado" in rejected.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_extending_a_pack_adds_days_and_audits_the_change() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            service = _create_service(client, manager).json()
            offer = _create_offer(
                client,
                manager,
                service_id=service["id"],
                validity_days=1,
            ).json()
            _open_shift(client, reception)
            pack = _sell_pack(
                client, reception, member_id=member_id, offer_id=offer["id"]
            ).json()
            original_until = datetime.fromisoformat(pack["valid_until"])
            assert pack["extended_days"] == 0

            # Operating the agenda is not the same as correcting a balance.
            forbidden = client.post(
                f"/admin/physio/packs/{pack['id']}/extend",
                headers=reception,
                json={"days": 10, "reason": "Cortesía"},
            )
            assert forbidden.status_code == 403, forbidden.text

            extended = client.post(
                f"/admin/physio/packs/{pack['id']}/extend",
                headers=manager,
                json={"days": 10, "reason": "Paciente con reposo médico"},
            )
            assert extended.status_code == 200, extended.text
            detail = extended.json()
            assert detail["pack"]["extended_days"] == 10
            new_until = datetime.fromisoformat(detail["pack"]["valid_until"])
            assert new_until >= original_until + timedelta(days=10) - timedelta(minutes=1)
            assert detail["pack"]["remaining_sessions"] == 2
            assert len(detail["adjustments"]) == 1
            adjustment = detail["adjustments"][0]
            assert adjustment["kind"] == "extension"
            assert adjustment["days"] == 10
            assert adjustment["reason"] == "Paciente con reposo médico"

            # The pack endpoint returns the same audit trail.
            fetched = _pack_detail(client, reception, pack["id"])
            assert fetched.status_code == 200, fetched.text
            assert fetched.json()["adjustments"][0]["id"] == adjustment["id"]

            assert client.post(
                f"/admin/physio/packs/{pack['id']}/extend",
                headers=manager,
                json={"days": 0, "reason": "Cortesía"},
            ).status_code == 422
            assert client.post(
                f"/admin/physio/packs/{pack['id']}/extend",
                headers=manager,
                json={"days": 5, "reason": "   "},
            ).status_code == 422
            assert client.post(
                f"/admin/physio/packs/{pack['id']}/extend",
                headers=manager,
                json={"days": 400, "reason": "Demasiado"},
            ).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_voiding_a_pack_cancels_future_sessions_and_never_refunds() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")
        therapist_id = _add_therapist(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            service, offer = _catalog(client, manager)
            _open_shift(client, reception)
            pack = _sell_pack(
                client, reception, member_id=member_id, offer_id=offer["id"]
            ).json()

            start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            booked = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start,
            )
            assert booked.status_code == 201, booked.text
            assert booked.json()["pack_id"] == pack["id"]

            forbidden = client.post(
                f"/admin/physio/packs/{pack['id']}/void",
                headers=reception,
                json={"reason": "Paquete mal vendido"},
            )
            assert forbidden.status_code == 403, forbidden.text

            voided = client.post(
                f"/admin/physio/packs/{pack['id']}/void",
                headers=manager,
                json={"reason": "Paquete mal vendido en recepción"},
            )
            assert voided.status_code == 200, voided.text
            body = voided.json()
            assert body["cancelled_appointments"] == 1
            assert body["pack"]["status"] == "voided"
            assert body["pack"]["remaining_sessions"] == 0
            assert body["pack"]["voided_sessions"] == 2
            assert body["pack"]["void_reason"] == "Paquete mal vendido en recepción"
            assert body["pack"]["voided_at"] is not None
            assert body["adjustments"][-1]["kind"] == "void"
            assert body["adjustments"][-1]["days"] is None

            agenda = client.get(
                f"/admin/physio/appointments?date={club_date(start).isoformat()}",
                headers=reception,
            ).json()
            assert agenda[0]["status"] == "cancelled"

            # Voiding is not a refund: the sale and the register stay untouched.
            sales = client.get("/admin/sales", headers=manager).json()
            assert sales["total"] == 1
            assert sales["items"][0]["status"] == "completed"
            assert client.get("/admin/sales/returns", headers=manager).json()["items"] == []
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["cash_refunds_cents"] == 0

            with Session(engine) as session:
                notices = session.exec(
                    select(MemberNotification).where(
                        MemberNotification.kind == "physio_appointment_cancelled"
                    )
                ).all()
                assert len(notices) == 1
                assert notices[0].ref_id is not None

            # Neither repeating the void nor extending it afterwards is allowed.
            assert client.post(
                f"/admin/physio/packs/{pack['id']}/void",
                headers=manager,
                json={"reason": "Otra vez"},
            ).status_code == 409
            assert client.post(
                f"/admin/physio/packs/{pack['id']}/extend",
                headers=manager,
                json={"days": 10, "reason": "Tarde"},
            ).status_code == 409

            listed = client.get(
                f"/admin/physio/packs?member_id={member_id}", headers=reception
            ).json()
            assert listed[0]["status"] == "voided"
            assert listed[0]["remaining_sessions"] == 0

            # The voided pack no longer covers a new appointment.
            rebooked = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start + timedelta(hours=1),
            )
            assert rebooked.status_code == 201, rebooked.text
            assert rebooked.json()["pack_id"] is None
    finally:
        app.dependency_overrides.clear()


def test_report_and_csv_reconcile_appointments_with_the_ledger() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")
        other_id = _add_member(session, first="Beto")
        therapist_id = _add_therapist(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            service, offer = _catalog(client, manager)
            _open_shift(client, reception)
            pack = _sell_pack(
                client, reception, member_id=member_id, offer_id=offer["id"]
            ).json()

            now = datetime.now(timezone.utc)
            covered = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=now - timedelta(minutes=5),
            ).json()
            assert _attend(client, reception, covered["id"]).status_code == 200

            single = _book(
                client,
                reception,
                member_id=other_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=now - timedelta(minutes=35),
            ).json()
            charged = _attend(
                client, reception, single["id"], payment_method="cash"
            )
            assert charged.status_code == 200, charged.text

            no_show = _book(
                client,
                reception,
                member_id=other_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=now - timedelta(minutes=70),
            ).json()
            assert _attend(
                client, reception, no_show["id"], attended=False
            ).status_code == 200

            day = club_date(now).isoformat()
            params = {"date_from": day, "date_to": day}
            report = client.get(
                "/admin/physio/report", headers=manager, params=params
            )
            assert report.status_code == 200, report.text
            body = report.json()

            assert body["totals"]["appointments"] == 3
            assert body["totals"]["attended"] == 2
            assert body["totals"]["no_show"] == 1
            assert body["totals"]["scheduled"] == 0
            assert body["totals"]["attendance_rate_percent"] == 67
            assert body["totals"]["no_show_rate_percent"] == 33

            assert body["revenue"]["package_cents"] == 80000
            assert body["revenue"]["single_cents"] == 50000
            assert body["revenue"]["refunded_cents"] == 0
            assert body["revenue"]["net_cents"] == 130000
            assert body["revenue"]["packages_sold"] == 1
            assert body["revenue"]["sessions_sold"] == 2
            assert body["revenue"]["single_charges"] == 1
            assert body["revenue"]["discount_cents"] == 20000

            assert body["occupancy"]["therapists"] == 1
            assert body["occupancy"]["booked_minutes"] == 90
            assert body["occupancy"]["available_minutes"] == 480
            assert 0 < body["occupancy"]["percent"] <= 100

            assert body["daily"][0]["appointments"] == 3
            assert body["daily"][0]["revenue_cents"] == 130000
            assert body["by_therapist"][0]["attended"] == 2
            assert body["by_service"][0]["single_charges"] == 1
            assert body["by_service"][0]["single_revenue_cents"] == 50000
            assert body["by_hour"]
            assert body["adjustments"] == {
                "extended": 0,
                "extended_days": 0,
                "voided": 0,
                "voided_sessions": 0,
            }

            # The same period exports as a daily CSV.
            export = client.get(
                "/admin/physio/report/export", headers=manager, params=params
            )
            assert export.status_code == 200, export.text
            assert export.headers["content-type"].startswith("text/csv")
            assert "reporte-fisioterapia" in export.headers["content-disposition"]
            lines = export.text.strip().splitlines()
            assert lines[0].startswith("Fecha,Citas,Atendidas")
            assert lines[1] == f"{day},3,2,1,0,1300.00"

            # Reading the money is a finance permission, not an agenda one.
            assert client.get(
                "/admin/physio/report", headers=reception, params=params
            ).status_code == 403
            assert client.get(
                "/admin/physio/report", headers=accountant, params=params
            ).status_code == 200
            assert client.get("/admin/physio/report").status_code == 401
    finally:
        app.dependency_overrides.clear()
