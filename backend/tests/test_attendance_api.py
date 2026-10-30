from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.models import Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.staffing.models import StaffAttendanceRequest


def test_attendance_scheduling_and_self_service() -> None:
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

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        register_user(
            session,
            email="trainer@example.com",
            password="trainer-correct-horse-battery",
            role_codes=("trainer",),
        )
        first = Employee(
            employee_number="EMP-1",
            first_name="Ana",
            last_name="Ruiz",
            email="ana@example.test",
            job_title="Recepción",
        )
        second = Employee(
            employee_number="EMP-2",
            first_name="Luis",
            last_name="Soto",
            email="luis@example.test",
            job_title="Mantenimiento",
        )
        session.add_all([first, second])
        session.commit()
        register_user(
            session,
            email="ana@example.com",
            password="ana-correct-horse-battery",
            employee_id=first.id,
            role_codes=("reception",),
        )
        register_user(
            session,
            email="maintenance@example.com",
            password="maintenance-correct-horse-battery",
            role_codes=("maintenance",),
        )
        first_id, second_id = first.id, second.id

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:

            def token(email: str, password: str) -> str:
                response = client.post("/auth/login", json={"email": email, "password": password})
                assert response.status_code == 200
                return response.json()["access_token"]

            owner = {"Authorization": f"Bearer {token('owner@example.com', 'owner-correct-horse-battery')}"}
            trainer = {"Authorization": f"Bearer {token('trainer@example.com', 'trainer-correct-horse-battery')}"}
            ana = {"Authorization": f"Bearer {token('ana@example.com', 'ana-correct-horse-battery')}"}
            maintenance = {
                "Authorization": f"Bearer {token('maintenance@example.com', 'maintenance-correct-horse-battery')}"
            }

            now = datetime.now(timezone.utc).replace(microsecond=0)
            shift_body = {
                "starts_at": now.isoformat(),
                "ends_at": (now + timedelta(hours=8)).isoformat(),
            }

            # Scheduling requires attendance.manage.
            assert client.post(
                f"/admin/staff/{first_id}/shifts", json=shift_body, headers=trainer
            ).status_code == 403

            created = client.post(f"/admin/staff/{first_id}/shifts", json=shift_body, headers=owner)
            assert created.status_code == 201
            shift_id = created.json()["id"]

            # Naive datetimes are rejected instead of reaching the service.
            assert client.post(
                f"/admin/staff/{first_id}/shifts",
                json={"starts_at": "2026-10-16T14:00:00", "ends_at": "2026-10-16T22:00:00"},
                headers=owner,
            ).status_code == 422

            # The employee sees only their own shifts.
            board = client.get("/staff/attendance", headers=ana)
            assert board.status_code == 200
            items = board.json()["items"]
            assert [item["id"] for item in items] == [shift_id]
            assert items[0]["attendance"] is None

            # Self clock-in and idempotent replay.
            request_id = str(uuid4())
            check_in = client.post(
                "/staff/attendance/clock-in",
                json={"shift_id": shift_id, "request_id": request_id},
                headers=ana,
            )
            assert check_in.status_code == 200
            assert check_in.json()["check_in_at"] is not None
            replay = client.post(
                "/staff/attendance/clock-in",
                json={"shift_id": shift_id, "request_id": request_id},
                headers=ana,
            )
            assert replay.status_code == 200
            assert replay.json()["id"] == check_in.json()["id"]

            # Check-out closes the attendance.
            assert client.post(
                "/staff/attendance/clock-out",
                json={"shift_id": shift_id, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 200

            # Another employee's shift cannot be marked from self-service.
            other_shift = client.post(
                f"/admin/staff/{second_id}/shifts", json=shift_body, headers=owner
            ).json()["id"]
            assert client.post(
                "/staff/attendance/clock-in",
                json={"shift_id": other_shift, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 403

            # An account without a linked employee cannot use self-service.
            assert client.get("/staff/attendance", headers=owner).status_code == 409

            # A missing mark is filled manually by someone with
            # attendance.manage; the trainer has only attendance.self.
            manual_body = {
                "shift_id": other_shift,
                "request_id": str(uuid4()),
                "event_type": "check_in",
                "occurred_at": now.isoformat(),
                "reason": "No pudo marcar la entrada",
            }
            assert client.post(
                "/admin/staff/attendance", json=manual_body, headers=trainer
            ).status_code == 403
            manual = client.post("/admin/staff/attendance", json=manual_body, headers=ana)
            assert manual.status_code == 200
            assert manual.json()["check_in_source"] == "manual"

            # A registered mark can be rewritten by attendance.manage; the
            # original punch stays in the event log with the reason.
            attendance_id = check_in.json()["id"]
            correction_body = {
                "request_id": str(uuid4()),
                "event_type": "check_in",
                "occurred_at": (now - timedelta(hours=1)).isoformat(),
                "reason": "La marca anterior quedó mal",
            }
            assert client.post(
                f"/admin/staff/attendance/{attendance_id}/corrections",
                json=correction_body,
                headers=trainer,
            ).status_code == 403
            corrected = client.post(
                f"/admin/staff/attendance/{attendance_id}/corrections",
                json=correction_body,
                headers=ana,
            )
            assert corrected.status_code == 200
            assert corrected.json()["check_in_source"] == "correction"
            assert client.post(
                f"/admin/staff/attendance/{attendance_id}/corrections",
                json={**correction_body, "request_id": str(uuid4()), "occurred_at": "2026-10-16T14:00:00"},
                headers=ana,
            ).status_code == 422
            # A mark that does not exist is filled, not corrected.
            assert client.post(
                f"/admin/staff/attendance/{manual.json()['id']}/corrections",
                json={
                    "request_id": str(uuid4()),
                    "event_type": "check_out",
                    "occurred_at": (now + timedelta(hours=7)).isoformat(),
                    "reason": "Salida sin marca",
                },
                headers=ana,
            ).status_code == 409
            assert client.post(
                f"/admin/staff/attendance/{uuid4()}/corrections",
                json={**correction_body, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 404

            # Repeating the same mark is rejected, and a naive datetime never
            # reaches the service.
            assert client.post(
                "/admin/staff/attendance",
                json={**manual_body, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 409
            assert client.post(
                "/admin/staff/attendance",
                json={**manual_body, "request_id": str(uuid4()), "occurred_at": "2026-10-16T14:00:00"},
                headers=ana,
            ).status_code == 422

            # The club's attendance policy is configurable and reaches the
            # employee board so «Mi jornada» can explain the real window.
            assert client.get("/staff/attendance", headers=ana).json()["settings"] == {
                "check_in_early_grace_minutes": 15,
                "lateness_tolerance_minutes": 0,
                "attendance_request_sla_hours": 24,
            }
            assert client.get("/admin/staff/settings", headers=trainer).status_code == 403
            assert client.get("/admin/staff/settings", headers=owner).json()[
                "lateness_tolerance_minutes"
            ] == 0
            policy = {
                "check_in_early_grace_minutes": 30,
                "lateness_tolerance_minutes": 10,
                "attendance_request_sla_hours": 48,
            }
            assert client.patch(
                "/admin/staff/settings", json=policy, headers=trainer
            ).status_code == 403
            assert client.patch(
                "/admin/staff/settings",
                json={**policy, "check_in_early_grace_minutes": 241},
                headers=owner,
            ).status_code == 422
            changed = client.patch("/admin/staff/settings", json=policy, headers=owner)
            assert changed.status_code == 200
            assert changed.json()["check_in_early_grace_minutes"] == 30
            assert client.get("/staff/attendance", headers=ana).json()["settings"] == policy

            # The audit log is readable with attendance.read and keeps the actor
            # and motive of every mark.
            events_path = f"/admin/staff/attendance/{attendance_id}/events"
            assert client.get(events_path, headers=maintenance).status_code == 403
            log = client.get(events_path, headers=trainer)
            assert log.status_code == 200
            items = log.json()["items"]
            assert sorted(item["event_type"] for item in items) == [
                "check_in",
                "check_in_correction",
                "check_out",
            ]
            correction_event = next(
                item for item in items if item["event_type"] == "check_in_correction"
            )
            assert correction_event["reason"] == "La marca anterior quedó mal"
            assert correction_event["actor_email"] == "ana@example.com"
            assert client.get(
                f"/admin/staff/attendance/{uuid4()}/events", headers=trainer
            ).status_code == 404

            # A stray mark can be annulled with a reason; voiding the exit keeps
            # the entry, voiding the entry frees the shift.
            void_path = f"/admin/staff/attendance/{attendance_id}/voids"
            void_out = {"request_id": str(uuid4()), "mark": "check_out", "reason": "Salió por error"}
            assert client.post(void_path, json=void_out, headers=trainer).status_code == 403
            assert client.post(
                void_path, json={**void_out, "reason": "   "}, headers=ana
            ).status_code == 422
            voided = client.post(void_path, json=void_out, headers=ana)
            assert voided.status_code == 200
            assert voided.json()["check_out_at"] is None
            assert voided.json()["voided_at"] is None
            assert client.post(
                void_path, json={**void_out, "mark": "check_in"}, headers=ana
            ).status_code == 409
            assert client.post(
                f"/admin/staff/attendance/{uuid4()}/voids",
                json={**void_out, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 404
            assert client.post(
                "/staff/attendance/clock-out",
                json={"shift_id": shift_id, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 200

            void_in = client.post(
                void_path,
                json={"request_id": str(uuid4()), "mark": "check_in", "reason": "Era otro turno, no el de hoy"},
                headers=ana,
            )
            assert void_in.status_code == 200
            assert void_in.json()["voided_at"] is not None
            board = client.get("/staff/attendance", headers=ana)
            assert board.json()["items"][0]["attendance"] is None
            assert client.post(
                "/staff/attendance/clock-in",
                json={"shift_id": shift_id, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 200
            assert client.get("/staff/attendance", headers=ana).json()["items"][0][
                "attendance"
            ] is not None

            # The admin listing shows both scheduled shifts.
            listing = client.get("/admin/staff/shifts", headers=owner)
            assert listing.status_code == 200
            assert {item["id"] for item in listing.json()} >= {shift_id, other_shift}
            manual_row = next(item for item in listing.json() if item["id"] == other_shift)
            assert manual_row["attendance"]["check_in_source"] == "manual"

            # Every policy change keeps its actor and the previous values; an
            # identical save writes nothing.
            events_path = "/admin/staff/settings/events"
            assert client.get(events_path, headers=trainer).status_code == 403
            assert client.get(events_path, headers=maintenance).status_code == 403
            history = client.get(events_path, headers=owner).json()["items"]
            assert len(history) == 1
            assert history[0]["actor_email"] == "owner@example.com"
            assert (
                history[0]["previous_check_in_early_grace_minutes"],
                history[0]["previous_lateness_tolerance_minutes"],
                history[0]["previous_attendance_request_sla_hours"],
            ) == (15, 0, 24)
            assert (history[0]["check_in_early_grace_minutes"], history[0]["lateness_tolerance_minutes"]) == (30, 10)
            assert history[0]["attendance_request_sla_hours"] == 48
            assert client.patch("/admin/staff/settings", json=policy, headers=owner).status_code == 200
            assert len(client.get(events_path, headers=owner).json()["items"]) == 1

            # The employee asks for a correction; it does not touch the mark
            # until a supervisor decides.
            own = client.get("/staff/attendance", headers=ana).json()["items"][0]["attendance"]
            request_body = {
                "mark": "check_in",
                "action": "correct",
                "proposed_at": (now - timedelta(minutes=10)).isoformat(),
                "justification": "Entré antes de las 14:00 y marqué tarde",
            }
            requests_path = f"/staff/attendance/{own['id']}/requests"
            assert client.post(
                requests_path,
                json={**request_body, "proposed_at": "2026-10-16T14:00:00"},
                headers=ana,
            ).status_code == 422
            assert client.post(requests_path, json=request_body, headers=owner).status_code == 409
            created = client.post(requests_path, json=request_body, headers=ana)
            assert created.status_code == 201
            request_id = created.json()["id"]
            assert created.json()["status"] == "pending"
            # Every instant in the payload carries UTC, so the panel can render it
            # in the club's timezone instead of reading a naive string as local time.
            assert created.json()["proposed_at"].endswith("Z")
            assert created.json()["current_check_in_at"].endswith("Z")
            assert created.json()["current_check_out_at"] is None
            assert client.post(
                requests_path,
                json={**request_body, "justification": "Quiero cambiarla otra vez"},
                headers=ana,
            ).status_code == 409

            mine = client.get("/staff/attendance/requests", headers=ana)
            assert mine.status_code == 200
            assert [(item["id"], item["status"]) for item in mine.json()["items"]] == [
                (request_id, "pending")
            ]
            assert mine.json()["items"][0]["current_check_in_at"].endswith("Z")
            assert client.get("/staff/attendance/requests", headers=owner).status_code == 409

            queue_path = "/admin/staff/attendance/requests"
            assert client.get(queue_path, headers=maintenance).status_code == 403
            queue = client.get(f"{queue_path}?status=pending", headers=trainer)
            assert queue.status_code == 200
            assert [item["id"] for item in queue.json()["items"]] == [request_id]
            assert queue.json()["items"][0]["employee_name"] == "Ana Ruiz"
            assert queue.json()["items"][0]["current_check_in_at"].endswith("Z")
            assert client.get(f"{queue_path}?status=nope", headers=trainer).status_code == 422
            inbox = client.get("/admin/notifications", headers=owner).json()["items"]
            assert any(item["kind"] == "attendance_request_pending" for item in inbox)

            # A request that passes the club's term is flagged as overdue and the
            # owner —not the requester— is escalated in the inbox. The notice is
            # written once even if the queue is opened again.
            with Session(engine) as session:
                row = session.get(StaffAttendanceRequest, UUID(request_id))
                assert row is not None
                row.due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
                session.add(row)
                session.commit()
            overdue_queue = client.get(f"{queue_path}?status=pending", headers=trainer)
            assert overdue_queue.json()["items"][0]["overdue"] is True
            assert overdue_queue.json()["items"][0]["due_at"].endswith("Z")
            assert client.get("/staff/attendance/requests", headers=ana).json()["items"][0][
                "overdue"
            ] is True
            owner_inbox = client.get("/admin/notifications", headers=owner).json()["items"]
            overdue_notices = [
                item for item in owner_inbox if item["kind"] == "attendance_request_overdue"
            ]
            assert len(overdue_notices) == 1
            assert overdue_notices[0]["resolved_at"] is None
            assert "Ana Ruiz" in overdue_notices[0]["body"]
            client.get(f"{queue_path}?status=pending", headers=trainer)
            assert len(
                [
                    item
                    for item in client.get("/admin/notifications", headers=owner).json()["items"]
                    if item["kind"] == "attendance_request_overdue"
                ]
            ) == 1
            ana_inbox = client.get("/admin/notifications", headers=ana).json()["items"]
            assert all(item["kind"] != "attendance_request_overdue" for item in ana_inbox)

            # Nobody decides their own request, even holding attendance.manage.
            decision_path = f"{queue_path}/{request_id}/decision"
            assert client.post(
                decision_path, json={"decision": "approved"}, headers=ana
            ).status_code == 403
            assert client.post(
                decision_path, json={"decision": "approved"}, headers=trainer
            ).status_code == 403
            decided = client.post(
                decision_path,
                json={"decision": "approved", "note": "Confirmado con recepción"},
                headers=owner,
            )
            assert decided.status_code == 200
            assert decided.json()["status"] == "approved"
            assert decided.json()["decision_note"] == "Confirmado con recepción"
            assert decided.json()["current_check_in_at"].endswith("Z")
            assert datetime.fromisoformat(decided.json()["current_check_in_at"]) == now - timedelta(
                minutes=10
            )
            corrected_row = client.get("/staff/attendance", headers=ana).json()["items"][0]["attendance"]
            assert corrected_row["check_in_source"] == "correction"
            assert datetime.fromisoformat(corrected_row["check_in_at"]) == now - timedelta(minutes=10)
            # The log names the request that produced the change; the other marks
            # were not requested and stay unlinked.
            approved_log = client.get(
                f"/admin/staff/attendance/{own['id']}/events", headers=trainer
            ).json()["items"]
            approved_event = next(
                item for item in approved_log if item["reason"].startswith("Solicitud del colaborador")
            )
            assert approved_event["attendance_request_id"] == request_id
            assert all(
                item["attendance_request_id"] is None
                for item in approved_log
                if item["id"] != approved_event["id"]
            )
            resolved_notice = next(
                item
                for item in client.get("/admin/notifications", headers=owner).json()["items"]
                if item["kind"] == "attendance_request_overdue"
            )
            assert resolved_notice["resolved_at"] is not None
            assert client.post(
                decision_path, json={"decision": "approved"}, headers=owner
            ).status_code == 409
            paid = client.post(
                f"{queue_path}/{uuid4()}/decision", json={"decision": "approved"}, headers=owner
            )
            assert paid.status_code == 404

            # A rejected request needs a reason and leaves the mark untouched.
            second = client.post(
                requests_path,
                json={
                    "mark": "check_in",
                    "action": "correct",
                    "proposed_at": (now - timedelta(minutes=25)).isoformat(),
                    "justification": "Quiero registrar la hora exacta",
                },
                headers=ana,
            )
            assert second.status_code == 201
            second_id = second.json()["id"]
            assert client.post(
                f"{queue_path}/{second_id}/decision", json={"decision": "rejected"}, headers=owner
            ).status_code == 422
            rejected = client.post(
                f"{queue_path}/{second_id}/decision",
                json={"decision": "rejected", "note": "La cámara no lo confirma"},
                headers=owner,
            )
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "rejected"
            assert client.get("/staff/attendance", headers=ana).json()["items"][0]["attendance"][
                "check_in_source"
            ] == "correction"
            assert [
                item["status"]
                for item in client.get("/staff/attendance/requests", headers=ana).json()["items"]
            ] == ["rejected", "approved"]

            # The annulment log groups the voids by operator.
            annulments_path = "/admin/staff/attendance/annulments"
            assert client.get(f"{annulments_path}?days=7", headers=maintenance).status_code == 403
            assert client.get(f"{annulments_path}?days=0", headers=owner).status_code == 422
            report = client.get(f"{annulments_path}?days=7", headers=trainer)
            assert report.status_code == 200
            payload = report.json()
            assert payload["total"] == 2
            assert {row["actor_email"] for row in payload["by_operator"]} == {"ana@example.com"}
            assert {row["total"] for row in payload["by_operator"]} == {2}
            assert {item["event_type"] for item in payload["items"]} == {
                "attendance_voided",
                "check_out_voided",
            }
            # Both annulments came from the panel, so none carries a request.
            assert all(item["attendance_request_id"] is None for item in payload["items"])
            only_voids = client.get(
                f"{annulments_path}?days=7&employee_id={first_id}", headers=owner
            ).json()
            assert only_voids["total"] == 2
            empty = client.get(
                f"{annulments_path}?days=7&employee_id={second_id}", headers=owner
            ).json()
            assert empty["total"] == 0 and empty["by_operator"] == []

            # The same report downloads as CSV, quoting any motive with commas.
            csv_path = f"{annulments_path}.csv"
            assert client.get(f"{csv_path}?days=7", headers=maintenance).status_code == 403
            assert client.get(f"{csv_path}?days=0", headers=owner).status_code == 422
            export = client.get(f"{csv_path}?days=7", headers=trainer)
            assert export.status_code == 200
            assert export.headers["content-type"].startswith("text/csv")
            assert (
                'attachment; filename="anulaciones-asistencia-7d-'
                in export.headers["content-disposition"]
            )
            lines = export.text.splitlines()
            assert lines[0] == (
                "Fecha y hora,Colaborador,Marca,Responsable,Origen,Solicitud,Motivo"
            )
            # Newest first: the entry void was made after the exit void.
            assert len(lines) == 3
            assert "Entrada anulada" in lines[1]
            assert '"Era otro turno, no el de hoy"' in lines[1]
            assert "Salida anulada" in lines[2]
            assert all(",Ana Ruiz,Panel,," in line for line in lines[1:])
            filtered = client.get(f"{csv_path}?days=7&employee_id={second_id}", headers=trainer)
            assert filtered.text.splitlines() == [lines[0]]
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
