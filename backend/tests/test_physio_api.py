"""End-to-end coverage of the physiotherapy room (increment 1).

The module's promise is narrow and testable: a pack is a prepaid balance, a
single session is charged only on attendance, and a no-show never touches money
or balance. These tests drive the panel API so the sale, the shift and the
appointment stay in sync the way reception uses them.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from app.main import app, get_session
from app.modules.identity.models import Employee
from app.modules.memberships.models import Member
from app.modules.physio.models import MAX_DURATION_MINUTES, PhysioService
from app.modules.physio.service import (
    InvalidPhysioData,
    create_physio_service,
    update_physio_service,
)
from app.timezone import club_date
from test_classes_api import (
    _add_member,
    _build_engine,
    _login,
    _override,
    _seed_users,
)


def _utc_iso(value: datetime) -> str:
    """SQLite drops ``tzinfo``, so responses come back as naive UTC strings."""
    return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def _add_therapist(session: Session, *, first: str = "Tere", status: str = "active"):
    employee = Employee(
        employee_number=f"EMP-{uuid4().hex[:8]}",
        first_name=first,
        last_name="Fisio",
        job_title="Fisioterapeuta",
        status=status,
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee.id


def _open_shift(client: TestClient, headers: dict[str, str]) -> dict:
    opened = client.post(
        "/admin/cash-sessions", headers=headers, json={"opening_cash_cents": 0}
    )
    assert opened.status_code == 201, opened.text
    return opened.json()


def _create_service(
    client: TestClient,
    headers: dict[str, str],
    *,
    code: str = "DESCARGA",
    name: str = "Descarga muscular",
    duration_minutes: int = 30,
    price_cents: int = 50000,
):
    return client.post(
        "/admin/physio/services",
        headers=headers,
        json={
            "code": code,
            "name": name,
            "description": "Masaje de descarga",
            "duration_minutes": duration_minutes,
            "price_cents": price_cents,
        },
    )


def _create_offer(
    client: TestClient,
    headers: dict[str, str],
    *,
    service_id: str,
    name: str = "Paquete de 2 sesiones",
    sessions: int = 2,
    price_cents: int = 80000,
    validity_days: int = 31,
):
    return client.post(
        "/admin/physio/offers",
        headers=headers,
        json={
            "service_id": service_id,
            "name": name,
            "sessions": sessions,
            "price_cents": price_cents,
            "validity_days": validity_days,
        },
    )


def _sell_pack(
    client: TestClient,
    headers: dict[str, str],
    *,
    member_id,
    offer_id: str,
    payment_method: str = "cash",
):
    return client.post(
        "/admin/physio/packs",
        headers=headers,
        json={
            "member_id": str(member_id),
            "offer_id": offer_id,
            "payment_method": payment_method,
        },
    )


def _book(
    client: TestClient,
    headers: dict[str, str],
    *,
    member_id,
    service_id: str,
    therapist_id,
    starts_at: datetime,
    room: str | None = "Consultorio 1",
):
    return client.post(
        "/admin/physio/appointments",
        headers=headers,
        json={
            "member_id": str(member_id),
            "service_id": service_id,
            "therapist_employee_id": str(therapist_id),
            "starts_at": starts_at.isoformat(),
            "room": room,
        },
    )


def _attend(
    client: TestClient,
    headers: dict[str, str],
    appointment_id: str,
    *,
    attended: bool = True,
    payment_method: str | None = None,
):
    payload: dict[str, object] = {"attended": attended}
    if payment_method is not None:
        payload["payment_method"] = payment_method
    return client.post(
        f"/admin/physio/appointments/{appointment_id}/attendance",
        headers=headers,
        json=payload,
    )


def _catalog(client: TestClient, headers: dict[str, str]):
    service = _create_service(client, headers)
    assert service.status_code == 201, service.text
    offer = _create_offer(client, headers, service_id=service.json()["id"])
    assert offer.status_code == 201, offer.text
    return service.json(), offer.json()


def test_service_duration_ceiling_matches_api_service_and_database() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            service = _create_service(
                client, manager, duration_minutes=MAX_DURATION_MINUTES
            )
            assert service.status_code == 201, service.text
            service_id = service.json()["id"]

            rejected = _create_service(
                client,
                manager,
                code="EXCESO",
                duration_minutes=MAX_DURATION_MINUTES + 1,
            )
            assert rejected.status_code == 422, rejected.text

            rejected_update = client.patch(
                f"/admin/physio/services/{service_id}",
                headers=manager,
                json={"duration_minutes": MAX_DURATION_MINUTES + 1},
            )
            assert rejected_update.status_code == 422, rejected_update.text
            listed = client.get("/admin/physio/services", headers=manager)
            assert listed.status_code == 200, listed.text
            assert listed.json()[0]["duration_minutes"] == MAX_DURATION_MINUTES
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        with pytest.raises(InvalidPhysioData, match=str(MAX_DURATION_MINUTES)):
            create_physio_service(
                session,
                code="DIRECT",
                name="Duración excesiva",
                duration_minutes=MAX_DURATION_MINUTES + 1,
                price_cents=50000,
            )
        session.rollback()

        with pytest.raises(InvalidPhysioData, match=str(MAX_DURATION_MINUTES)):
            update_physio_service(
                session,
                UUID(service_id),
                duration_minutes=MAX_DURATION_MINUTES + 1,
            )
        session.rollback()

        session.add(
            PhysioService(
                code="ORM",
                name="Duración excesiva",
                duration_minutes=MAX_DURATION_MINUTES + 1,
                price_cents=50000,
            )
        )
        with pytest.raises(IntegrityError, match="ck_physio_services_duration_max"):
            session.commit()
        session.rollback()
        assert session.exec(select(func.count()).select_from(PhysioService)).one()[0] == 1


def test_catalog_permissions_and_discount_snapshot() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")

            service, offer = _catalog(client, manager)
            assert service["code"] == "DESCARGA"
            assert offer["sessions"] == 2
            assert offer["list_price_cents"] == 100000
            assert offer["price_cents"] == 80000
            assert offer["savings_cents"] == 20000
            assert offer["discount_percent"] == 20
            assert offer["payment_mode"] == "single"

            duplicate = _create_service(client, manager)
            assert duplicate.status_code == 409, duplicate.text

            # Reception operates the room; trainers only read it.
            assert client.get("/admin/physio/services", headers=trainer).status_code == 200
            assert client.get("/admin/physio/offers", headers=trainer).status_code == 200
            forbidden = _create_service(client, trainer, code="OTRO", name="Otra")
            assert forbidden.status_code == 403, forbidden.text
            assert (
                client.get("/admin/physio/therapists", headers=reception).status_code == 200
            )

            # The list price is a snapshot: changing the single price later does
            # not rewrite the offer that was created.
            patched = client.patch(
                f"/admin/physio/services/{service['id']}",
                headers=reception,
                json={"price_cents": 60000},
            )
            assert patched.status_code == 200, patched.text
            offers = client.get("/admin/physio/offers", headers=manager).json()
            assert offers[0]["list_price_cents"] == 100000
            assert offers[0]["savings_cents"] == 20000

            # An offer can never cost more than its sessions at list price.
            overpriced = _create_offer(
                client,
                manager,
                service_id=service["id"],
                name="Paquete caro",
                price_cents=200000,
            )
            assert overpriced.status_code == 422, overpriced.text
    finally:
        app.dependency_overrides.clear()


def test_pack_sale_requires_an_open_shift_and_lands_in_the_ledger() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")
        inactive_id = _add_member(session, first="Beto", status="inactive")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            _, offer = _catalog(client, manager)

            blocked = _sell_pack(
                client, reception, member_id=member_id, offer_id=offer["id"]
            )
            assert blocked.status_code == 409, blocked.text
            assert "turno de caja" in blocked.json()["detail"]

            _open_shift(client, reception)
            sold = _sell_pack(client, reception, member_id=member_id, offer_id=offer["id"])
            assert sold.status_code == 201, sold.text
            pack = sold.json()
            assert pack["sessions_total"] == 2
            assert pack["sessions_used"] == 0
            assert pack["remaining_sessions"] == 2
            assert pack["status"] == "active"
            assert pack["price_cents"] == 80000
            assert pack["member_name"] == "Ana Demo"
            assert pack["service_name"] == "Descarga muscular"

            # The pack is one service sale with its own SKU.
            sales = client.get("/admin/sales", headers=manager).json()
            assert sales["total"] == 1
            sale = sales["items"][0]
            assert sale["total_cents"] == 80000
            assert sale["lines"][0]["product_id"] is None
            assert sale["lines"][0]["sku"] == "FISIO"
            assert "Paquete de fisioterapia" in sale["lines"][0]["product_name"]

            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["cash_sales_cents"] == 80000

            listed = client.get(
                f"/admin/physio/packs?member_id={member_id}", headers=reception
            ).json()
            assert len(listed) == 1
            assert listed[0]["sale_id"] == sale["id"]

            assert (
                _sell_pack(client, reception, member_id=inactive_id, offer_id=offer["id"]).status_code
                == 422
            )
            assert (
                _sell_pack(client, trainer, member_id=member_id, offer_id=offer["id"]).status_code
                == 403
            )
    finally:
        app.dependency_overrides.clear()


def test_booking_links_the_pack_and_rejects_overlaps() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")
        other_id = _add_member(session, first="Beto")
        therapist_id = _add_therapist(session)
        second_therapist = _add_therapist(session, first="Luis")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            service, offer = _catalog(client, manager)
            _open_shift(client, reception)
            sold = _sell_pack(client, reception, member_id=member_id, offer_id=offer["id"])
            assert sold.status_code == 201, sold.text

            start = datetime.now(timezone.utc) + timedelta(days=1)
            start = start.replace(hour=15, minute=0, second=0, microsecond=0)
            booked = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start,
            )
            assert booked.status_code == 201, booked.text
            appointment = booked.json()
            assert appointment["status"] == "scheduled"
            assert appointment["pack_id"] == sold.json()["id"]
            assert appointment["pack_remaining_sessions"] == 2
            assert appointment["therapist_name"] == "Tere Fisio"
            assert appointment["ends_at"] == _utc_iso(start + timedelta(minutes=30))

            overlap = _book(
                client,
                reception,
                member_id=other_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start + timedelta(minutes=10),
            )
            assert overlap.status_code == 409, overlap.text
            assert "encima" in overlap.json()["detail"]

            same_start = _book(
                client,
                reception,
                member_id=other_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start,
            )
            assert same_start.status_code == 409, same_start.text

            # Another therapist can take the same time, and a member without a
            # pack gets a single session payable at attendance.
            parallel = _book(
                client,
                reception,
                member_id=other_id,
                service_id=service["id"],
                therapist_id=second_therapist,
                starts_at=start,
            )
            assert parallel.status_code == 201, parallel.text
            assert parallel.json()["pack_id"] is None

            # The agenda of the day shows both and the pack link.
            day = club_date(start).isoformat()
            agenda = client.get(
                f"/admin/physio/appointments?date={day}&therapist_id={therapist_id}",
                headers=reception,
            ).json()
            assert len(agenda) == 1
            assert agenda[0]["id"] == appointment["id"]

            # Cancelling frees the exact hour for a new booking.
            cancelled = client.post(
                f"/admin/physio/appointments/{appointment['id']}/cancel",
                headers=reception,
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            rebooked = _book(
                client,
                reception,
                member_id=other_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=start,
            )
            assert rebooked.status_code == 201, rebooked.text

            # Moving revalidates the overlap.
            moved = client.patch(
                f"/admin/physio/appointments/{rebooked.json()['id']}",
                headers=reception,
                json={"starts_at": (start + timedelta(hours=1)).isoformat()},
            )
            assert moved.status_code == 200, moved.text
            assert moved.json()["starts_at"] == _utc_iso(start + timedelta(hours=1))
            assert moved.json()["ends_at"] == _utc_iso(
                start + timedelta(hours=1, minutes=30)
            )

            onto_other = client.patch(
                f"/admin/physio/appointments/{rebooked.json()['id']}",
                headers=reception,
                json={"therapist_employee_id": str(second_therapist)},
            )
            assert onto_other.status_code == 200, onto_other.text
            assert onto_other.json()["therapist_employee_id"] == str(second_therapist)
            assert onto_other.json()["starts_at"] == moved.json()["starts_at"]
    finally:
        app.dependency_overrides.clear()


def test_rooms_cannot_double_book_the_same_hour() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")
        other_id = _add_member(session, first="Beto")
        therapist_id = _add_therapist(session)
        second_therapist = _add_therapist(session, first="Luis")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            service, _ = _catalog(client, manager)
            room_a = client.post(
                "/admin/physio/rooms", headers=manager, json={"name": "Sala A"}
            )
            assert room_a.status_code == 201, room_a.text
            room_b = client.post(
                "/admin/physio/rooms", headers=manager, json={"name": "Sala B"}
            )
            assert room_b.status_code == 201, room_b.text
            room_a_id = room_a.json()["id"]
            room_b_id = room_b.json()["id"]

            start = datetime.now(timezone.utc) + timedelta(days=1)
            start = start.replace(hour=15, minute=0, second=0, microsecond=0)

            def book(member, therapist, when: datetime, room_id: str | None):
                payload = {
                    "member_id": str(member),
                    "service_id": service["id"],
                    "therapist_employee_id": str(therapist),
                    "starts_at": when.isoformat(),
                }
                if room_id is None:
                    payload["room"] = "Sala A"
                else:
                    payload["room_id"] = room_id
                return client.post(
                    "/admin/physio/appointments", headers=reception, json=payload
                )

            first = book(member_id, therapist_id, start, room_a_id)
            assert first.status_code == 201, first.text
            assert first.json()["room_id"] == room_a_id
            assert first.json()["room"] == "Sala A"

            # Another therapist at the same hour still cannot use the room.
            clash = book(
                other_id, second_therapist, start + timedelta(minutes=10), room_a_id
            )
            assert clash.status_code == 409, clash.text
            assert "consultorio" in clash.json()["detail"]

            # Another room, or the same room at another hour, is fine.
            other_room = book(
                other_id, second_therapist, start + timedelta(minutes=10), room_b_id
            )
            assert other_room.status_code == 201, other_room.text
            later = book(other_id, second_therapist, start + timedelta(hours=1), room_a_id)
            assert later.status_code == 201, later.text

            # Moving revalidates the room that will actually be stored.
            moved_clash = client.patch(
                f"/admin/physio/appointments/{other_room.json()['id']}",
                headers=reception,
                json={"room_id": room_a_id},
            )
            assert moved_clash.status_code == 409, moved_clash.text
            assert "consultorio" in moved_clash.json()["detail"]
            moved = client.patch(
                f"/admin/physio/appointments/{other_room.json()['id']}",
                headers=reception,
                json={
                    "room_id": room_a_id,
                    "starts_at": (start + timedelta(hours=2)).isoformat(),
                },
            )
            assert moved.status_code == 200, moved.text
            assert moved.json()["room_id"] == room_a_id

            # Keeping the same room while moving an hour later is allowed.
            kept = client.patch(
                f"/admin/physio/appointments/{moved.json()['id']}",
                headers=reception,
                json={"starts_at": (start + timedelta(hours=2, minutes=5)).isoformat()},
            )
            assert kept.status_code == 200, kept.text
            assert kept.json()["room_id"] == room_a_id

            # Cancelling frees the room for the same hour.
            cancelled = client.post(
                f"/admin/physio/appointments/{first.json()['id']}/cancel",
                headers=reception,
            )
            assert cancelled.status_code == 200, cancelled.text
            freed = book(
                other_id, second_therapist, start + timedelta(minutes=10), room_a_id
            )
            assert freed.status_code == 201, freed.text

            # Legacy free-text rooms have no catalog id, so they stay outside
            # the check; the panel sends room_id for catalog rooms.
            free_text = client.post(
                "/admin/physio/appointments",
                headers=reception,
                json={
                    "member_id": str(member_id),
                    "service_id": service["id"],
                    "therapist_employee_id": str(therapist_id),
                    "starts_at": (start + timedelta(hours=3)).isoformat(),
                    "room": "Sala A",
                },
            )
            assert free_text.status_code == 201, free_text.text
            assert free_text.json()["room_id"] is None
    finally:
        app.dependency_overrides.clear()


def test_out_of_validity_appointment_falls_back_to_a_single_session() -> None:
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
            offer = _create_offer(
                client,
                manager,
                service_id=service["id"],
                validity_days=1,
            ).json()
            _open_shift(client, reception)
            assert (
                _sell_pack(client, reception, member_id=member_id, offer_id=offer["id"]).status_code
                == 201
            )

            # The pack expires in one day: a later appointment is not covered.
            start = (datetime.now(timezone.utc) + timedelta(days=5)).replace(
                hour=15, minute=0, second=0, microsecond=0
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
            assert booked.json()["pack_id"] is None
            assert booked.json()["pack_remaining_sessions"] is None
    finally:
        app.dependency_overrides.clear()


def test_attendance_with_pack_consumes_one_credit_and_corrects_it() -> None:
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

            starts_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            booked = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=starts_at,
            )
            assert booked.status_code == 201, booked.text
            appointment_id = booked.json()["id"]

            attended = _attend(client, reception, appointment_id)
            assert attended.status_code == 200, attended.text
            body = attended.json()
            assert body["status"] == "attended"
            assert body["pack_remaining_sessions"] == 1
            assert body["charge_sale_id"] is None
            # The only sale is still the pack: attendance created no charge.
            assert client.get("/admin/sales", headers=manager).json()["total"] == 1
            packs = client.get(
                f"/admin/physio/packs?member_id={member_id}", headers=reception
            ).json()
            assert packs[0]["sessions_used"] == 1
            assert packs[0]["remaining_sessions"] == 1

            # Marking again never consumes twice.
            again = _attend(client, reception, appointment_id)
            assert again.status_code == 200
            assert client.get(
                f"/admin/physio/packs?member_id={member_id}", headers=reception
            ).json()[0]["sessions_used"] == 1

            # A correction inside the window returns the credit.
            corrected = _attend(client, reception, appointment_id, attended=False)
            assert corrected.status_code == 200, corrected.text
            assert corrected.json()["status"] == "no_show"
            pack_after = client.get(
                f"/admin/physio/packs?member_id={member_id}", headers=reception
            ).json()[0]
            assert pack_after["sessions_used"] == 0
            assert pack_after["remaining_sessions"] == 2
            assert client.get("/admin/sales", headers=manager).json()["total"] == 1
            assert len(client.get("/admin/sales/returns", headers=manager).json()["items"]) == 0

            # Marking it attended again consumes once more.
            returned = _attend(client, reception, appointment_id)
            assert returned.status_code == 200, returned.text
            assert client.get(
                f"/admin/physio/packs?member_id={member_id}", headers=reception
            ).json()[0]["sessions_used"] == 1

            # A no-show by itself never touches the balance.
            second = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=starts_at - timedelta(hours=1),
            )
            no_show = _attend(client, reception, second.json()["id"], attended=False)
            assert no_show.status_code == 200, no_show.text
            assert client.get(
                f"/admin/physio/packs?member_id={member_id}", headers=reception
            ).json()[0]["sessions_used"] == 1
            assert client.get("/admin/sales", headers=manager).json()["total"] == 1
    finally:
        app.dependency_overrides.clear()


def test_single_session_is_charged_on_attendance_and_refunded_on_correction() -> None:
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

            starts_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            booked = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=starts_at,
            )
            assert booked.status_code == 201, booked.text
            appointment_id = booked.json()["id"]

            # The charge needs a payment method and an open shift.
            no_method = _attend(client, reception, appointment_id)
            assert no_method.status_code == 409, no_method.text
            assert "forma de pago" in no_method.json()["detail"]
            with_method = _attend(client, reception, appointment_id, payment_method="cash")
            assert with_method.status_code == 409, with_method.text
            assert "turno de caja" in with_method.json()["detail"]
            # The failed marks left the appointment pending, uncharged.
            agenda = client.get(
                f"/admin/physio/appointments?date={club_date(starts_at).isoformat()}",
                headers=reception,
            ).json()
            assert agenda[0]["status"] == "scheduled"
            assert agenda[0]["charge_sale_id"] is None

            _open_shift(client, reception)
            charged = _attend(
                client, reception, appointment_id, payment_method="cash"
            )
            assert charged.status_code == 200, charged.text
            body = charged.json()
            assert body["status"] == "attended"
            assert body["pack_id"] is None
            assert body["charge_status"] == "completed"
            assert body["charge_cents"] == 50000
            assert body["charge_payment_method"] == "cash"

            sale = client.get("/admin/sales", headers=manager).json()["items"][0]
            assert sale["total_cents"] == 50000
            assert sale["lines"][0]["sku"] == "FISIO"
            assert sale["lines"][0]["product_id"] is None
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["cash_sales_cents"] == 50000

            # Correcting to no-show refunds the charge and creates no debt.
            corrected = _attend(client, reception, appointment_id, attended=False)
            assert corrected.status_code == 200, corrected.text
            assert corrected.json()["status"] == "no_show"
            assert corrected.json()["charge_status"] == "refunded"
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["cash_refunds_cents"] == 50000
            assert current["expected_cash_cents"] == 0
            assert len(client.get("/admin/sales/returns", headers=manager).json()["items"]) == 1

            # Correcting back charges again, in the method chosen this time.
            recharged = _attend(
                client, reception, appointment_id, payment_method="card"
            )
            assert recharged.status_code == 200, recharged.text
            assert recharged.json()["charge_status"] == "completed"
            assert recharged.json()["charge_payment_method"] == "card"
            assert client.get("/admin/sales", headers=manager).json()["total"] == 2
    finally:
        app.dependency_overrides.clear()


def test_exhausted_pack_at_attendance_charges_only_with_a_method() -> None:
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
            offer = _create_offer(
                client,
                manager,
                service_id=service["id"],
                name="Paquete de 1 sesión",
                sessions=1,
                price_cents=50000,
            ).json()
            _open_shift(client, reception)
            pack = _sell_pack(
                client, reception, member_id=member_id, offer_id=offer["id"]
            ).json()

            starts_at = datetime.now(timezone.utc) - timedelta(minutes=70)
            first = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=starts_at,
            ).json()
            second = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=starts_at + timedelta(minutes=65),
            ).json()
            assert first["pack_id"] == pack["id"]
            assert second["pack_id"] == pack["id"]

            # The first visit uses the only credit.
            assert _attend(client, reception, first["id"]).status_code == 200

            # The second finds the linked pack exhausted and refuses to charge
            # without asking how.
            refused = _attend(client, reception, second["id"])
            assert refused.status_code == 409, refused.text
            assert "forma de pago" in refused.json()["detail"]
            assert client.get("/admin/sales", headers=manager).json()["total"] == 1

            charged = _attend(client, reception, second["id"], payment_method="transfer")
            assert charged.status_code == 200, charged.text
            assert charged.json()["status"] == "attended"
            assert charged.json()["pack_id"] is None
            assert charged.json()["charge_cents"] == 50000
            assert charged.json()["charge_payment_method"] == "transfer"
    finally:
        app.dependency_overrides.clear()


def test_marking_outside_the_window_and_close_day() -> None:
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

            now = datetime.now(timezone.utc)
            old_start = now - timedelta(days=3)
            old = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=old_start,
            ).json()
            closed = _attend(client, reception, old["id"])
            assert closed.status_code == 409, closed.text
            assert "ventana" in closed.json()["detail"]

            # A pending appointment that already ended closes as no-show and
            # never touches money or balance.
            finished_start = now - timedelta(hours=2)
            finished = _book(
                client,
                reception,
                member_id=member_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=finished_start,
            ).json()
            day = club_date(finished_start).isoformat()
            result = client.post(
                "/admin/physio/appointments/close-day",
                headers=reception,
                json={"date": day},
            )
            assert result.status_code == 200, result.text
            body = result.json()
            assert body["closed"] == 1
            assert body["appointments"][0]["status"] == "no_show"
            assert client.get("/admin/sales", headers=manager).json()["total"] == 0
            assert (
                client.get(
                    f"/admin/physio/packs?member_id={member_id}", headers=reception
                ).json()
                == []
            )

            # A second close is a no-op.
            again = client.post(
                "/admin/physio/appointments/close-day",
                headers=reception,
                json={"date": day},
            )
            assert again.status_code == 200
            assert again.json()["closed"] == 0
    finally:
        app.dependency_overrides.clear()
