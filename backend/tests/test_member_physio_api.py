"""Member-facing physiotherapy: read-only overview and the three notices.

The app never books or cancels; it only shows the pack balance, the next
appointment and what happened before. The notices are written by the same
transaction that books, moves or cancels the appointment, so the inbox and the
agenda can never disagree.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.main import app, get_session
from app.modules.memberships.models import Member
from test_classes_api import _build_engine, _login, _override, _seed_users
from test_physio_api import (
    _add_therapist,
    _attend,
    _book,
    _catalog,
    _create_service,
    _open_shift,
    _sell_pack,
)


def _seat_member(
    session: Session, *, email: str, first_name: str = "Ana"
) -> Member:
    member = Member(
        first_name=first_name,
        last_name="Demo",
        email=email,
        status="active",
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _inbox_kinds(client: TestClient, headers: dict[str, str]) -> list[str]:
    inbox = client.get(
        "/member/notifications", headers=headers, params={"page_size": 50}
    )
    assert inbox.status_code == 200, inbox.text
    return [item["kind"] for item in inbox.json()["items"]]


def test_member_physio_overview_and_notices(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-physio-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        ana = _seat_member(session, email="ana@example.com")
        _seat_member(session, email="beto@example.com", first_name="Beto")
        therapist_id = _add_therapist(session)
        ana_id = ana.id

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            ana_headers = _member_headers(client, "ana@example.com")
            beto_headers = _member_headers(client, "beto@example.com")
            _open_shift(client, reception)
            service, offer = _catalog(client, reception)
            pack = _sell_pack(
                client,
                reception,
                member_id=ana_id,
                offer_id=offer["id"],
            )
            assert pack.status_code == 201, pack.text

            base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
            booked = _book(
                client,
                reception,
                member_id=ana_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=base + timedelta(days=1),
            )
            assert booked.status_code == 201, booked.text
            appointment = booked.json()
            assert appointment["pack_id"] == pack.json()["id"]

            scheduled = client.get(
                "/member/notifications", headers=ana_headers
            ).json()["items"]
            kinds = _inbox_kinds(client, ana_headers)
            assert kinds.count("physio_appointment_scheduled") == 1
            message = next(
                item for item in scheduled if item["kind"] == "physio_appointment_scheduled"
            )
            assert message["ref_id"] == appointment["id"]
            assert "Descarga muscular" in message["body"]
            assert "Tere Fisio" in message["body"]
            assert "Llega 10 minutos antes" in message["body"]

            moved_at = base + timedelta(days=2)
            moved = client.patch(
                f"/admin/physio/appointments/{appointment['id']}",
                headers=reception,
                json={"starts_at": moved_at.isoformat()},
            )
            assert moved.status_code == 200, moved.text
            after_move = _inbox_kinds(client, ana_headers)
            assert after_move.count("physio_appointment_rescheduled") == 1

            # Patching the same slot again changes nothing, so it must not
            # announce a move that did not happen.
            untouched = client.patch(
                f"/admin/physio/appointments/{appointment['id']}",
                headers=reception,
                json={"starts_at": moved_at.isoformat()},
            )
            assert untouched.status_code == 200, untouched.text
            assert _inbox_kinds(client, ana_headers).count(
                "physio_appointment_rescheduled"
            ) == 1

            cancelled = _book(
                client,
                reception,
                member_id=ana_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=base + timedelta(days=3),
            )
            assert cancelled.status_code == 201, cancelled.text
            cancelled_id = cancelled.json()["id"]
            response = client.post(
                f"/admin/physio/appointments/{cancelled_id}/cancel",
                headers=reception,
            )
            assert response.status_code == 200, response.text
            assert _inbox_kinds(client, ana_headers).count(
                "physio_appointment_cancelled"
            ) == 1

            overview = client.get("/member/physio", headers=ana_headers)
            assert overview.status_code == 200, overview.text
            body = overview.json()

            assert len(body["packs"]) == 1
            pack_view = body["packs"][0]
            assert pack_view["remaining_sessions"] == 2
            assert pack_view["sessions_used"] == 0
            assert pack_view["status"] == "active"
            assert pack_view["offer_name"] == offer["name"]

            assert body["next_appointment"]["id"] == appointment["id"]
            assert body["next_appointment"]["service_name"] == "Descarga muscular"
            assert body["next_appointment"]["therapist_name"] == "Tere Fisio"
            assert body["next_appointment"]["covered_by_pack"] is True
            assert body["history"][0]["id"] == cancelled_id
            assert body["history"][0]["status"] == "cancelled"

            # Another member only ever sees their own rows.
            other = client.get("/member/physio", headers=beto_headers).json()
            assert other == {"packs": [], "next_appointment": None, "history": []}

            assert client.get("/member/physio").status_code == 401

            # Attendance can only be marked from the start of the appointment,
            # so the slot is moved into the last-day window the room allows.
            past = client.patch(
                f"/admin/physio/appointments/{appointment['id']}",
                headers=reception,
                json={"starts_at": (base - timedelta(days=1)).isoformat()},
            )
            assert past.status_code == 200, past.text
            attended = _attend(client, reception, appointment["id"])
            assert attended.status_code == 200, attended.text

            after = client.get("/member/physio", headers=ana_headers).json()
            assert after["packs"][0]["sessions_used"] == 1
            assert after["packs"][0]["remaining_sessions"] == 1
            assert after["next_appointment"] is None
            assert [item["status"] for item in after["history"]] == [
                "cancelled",
                "attended",
            ]
            assert after["history"][1]["covered_by_pack"] is True
    finally:
        app.dependency_overrides.clear()


def test_physio_reminder_is_materialised_once(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-physio-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        ana = _seat_member(session, email="ana@example.com")
        therapist_id = _add_therapist(session)
        ana_id = ana.id

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            ana_headers = _member_headers(client, "ana@example.com")
            service = _create_service(client, reception).json()

            now = datetime.now(timezone.utc).replace(microsecond=0)
            soon = now + timedelta(hours=20)
            booked = _book(
                client,
                reception,
                member_id=ana_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=soon,
            )
            assert booked.status_code == 201, booked.text
            appointment_id = booked.json()["id"]

            # Opening the inbox in the last day writes the reminder once.
            kinds = _inbox_kinds(client, ana_headers)
            assert kinds.count("physio_reminder") == 1
            reminder = next(
                item
                for item in client.get(
                    "/member/notifications", headers=ana_headers
                ).json()["items"]
                if item["kind"] == "physio_reminder"
            )
            assert reminder["ref_id"] == appointment_id
            assert "Descarga muscular" in reminder["body"]
            assert "Llega 10 minutos antes" in reminder["body"]

            assert _inbox_kinds(client, ana_headers).count("physio_reminder") == 1

            # An appointment beyond the window does not get one yet.
            far = _book(
                client,
                reception,
                member_id=ana_id,
                service_id=service["id"],
                therapist_id=therapist_id,
                starts_at=now + timedelta(hours=40),
            )
            assert far.status_code == 201, far.text
            assert _inbox_kinds(client, ana_headers).count("physio_reminder") == 1

            # Cancelling stops new reminders but keeps the one already sent.
            assert client.post(
                f"/admin/physio/appointments/{appointment_id}/cancel",
                headers=reception,
            ).status_code == 200
            assert _inbox_kinds(client, ana_headers).count("physio_reminder") == 1
    finally:
        app.dependency_overrides.clear()


def test_member_sees_a_voided_pack_without_credits(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-physio-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        ana = _seat_member(session, email="ana@example.com")
        ana_id = ana.id

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            ana_headers = _member_headers(client, "ana@example.com")
            _, offer = _catalog(client, reception)
            _open_shift(client, reception)
            pack = _sell_pack(
                client, reception, member_id=ana_id, offer_id=offer["id"]
            )
            assert pack.status_code == 201, pack.text

            active = client.get("/member/physio", headers=ana_headers).json()
            assert active["packs"][0]["status"] == "active"
            assert active["packs"][0]["remaining_sessions"] == 2

            voided = client.post(
                f"/admin/physio/packs/{pack.json()['id']}/void",
                headers=manager,
                json={"reason": "Cortesía mal registrada"},
            )
            assert voided.status_code == 200, voided.text

            after = client.get("/member/physio", headers=ana_headers).json()
            assert after["packs"][0]["status"] == "voided"
            assert after["packs"][0]["remaining_sessions"] == 0
    finally:
        app.dependency_overrides.clear()
