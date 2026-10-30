from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.mailer import MailDeliveryFailed
from app.modules.identity.models import Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications import delivery as delivery_module


def test_attendance_email_deliveries_api(monkeypatch) -> None:
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
        register_user(
            session,
            email="maintenance@example.com",
            password="maintenance-correct-horse-battery",
            role_codes=("maintenance",),
        )
        employee = Employee(
            employee_number="EMP-300",
            first_name="Ana",
            last_name="Ruiz",
            email="ana.record@example.test",
            job_title="Recepción",
        )
        session.add(employee)
        session.commit()
        register_user(
            session,
            email="ana@example.com",
            password="ana-correct-horse-battery",
            employee_id=employee.id,
            role_codes=("reception",),
        )
        employee_id = employee.id

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    outbox: list[dict[str, str]] = []

    def working_send(*, recipient: str, subject: str, body: str, **_kwargs) -> str:
        outbox.append({"recipient": recipient, "subject": subject, "body": body})
        return "sent"

    monkeypatch.setattr(delivery_module, "send_email", working_send)
    try:
        with TestClient(app) as client:

            def token(email: str, password: str) -> str:
                response = client.post("/auth/login", json={"email": email, "password": password})
                assert response.status_code == 200
                return response.json()["access_token"]

            owner = {"Authorization": f"Bearer {token('owner@example.com', 'owner-correct-horse-battery')}"}
            trainer = {"Authorization": f"Bearer {token('trainer@example.com', 'trainer-correct-horse-battery')}"}
            maintenance = {
                "Authorization": f"Bearer {token('maintenance@example.com', 'maintenance-correct-horse-battery')}"
            }
            ana = {"Authorization": f"Bearer {token('ana@example.com', 'ana-correct-horse-battery')}"}

            now = datetime.now(timezone.utc).replace(microsecond=0)
            shift_id = client.post(
                f"/admin/staff/{employee_id}/shifts",
                json={
                    "starts_at": now.isoformat(),
                    "ends_at": (now + timedelta(hours=8)).isoformat(),
                },
                headers=owner,
            ).json()["id"]
            clock_in = client.post(
                "/staff/attendance/clock-in",
                json={"shift_id": shift_id, "request_id": str(uuid4())},
                headers=ana,
            )
            assert clock_in.status_code == 200
            attendance_id = clock_in.json()["id"]

            # A correction queues the employee notice, and the pass that runs
            # after the response sends it without holding the mark's transaction.
            corrected = client.post(
                f"/admin/staff/attendance/{attendance_id}/corrections",
                json={
                    "request_id": str(uuid4()),
                    "event_type": "check_in",
                    "occurred_at": (now - timedelta(hours=1)).isoformat(),
                    "reason": "La marca anterior quedó mal",
                },
                headers=owner,
            )
            assert corrected.status_code == 200
            assert len(outbox) == 1
            assert outbox[0]["recipient"] == "ana@example.com"
            assert outbox[0]["subject"] == "[Asistencia] Se corrigió tu marca de asistencia"
            assert "La marca anterior quedó mal" in outbox[0]["body"]
            assert "Personal" in outbox[0]["body"]

            board = client.get("/admin/staff/notifications/deliveries", headers=owner)
            assert board.status_code == 200
            payload = board.json()
            assert payload["enabled"] is True
            assert payload["counts"] == {"pending": 0, "sent": 1, "simulated": 0, "failed": 0}
            assert payload["total"] == 1
            assert payload["items"][0]["kind"] == "attendance_corrected"
            assert payload["items"][0]["recipient"] == "ana@example.com"
            assert payload["items"][0]["status"] == "sent"
            assert payload["items"][0]["attempts"] == 1
            assert payload["items"][0]["sent_at"] is not None
            assert payload["items"][0]["last_attempt_at"] is not None

            # Reading the queue needs attendance.read; draining and retrying
            # need attendance.manage.
            assert client.get("/admin/staff/notifications/deliveries", headers=trainer).status_code == 200
            assert client.get("/admin/staff/notifications/deliveries", headers=maintenance).status_code == 403
            assert client.post("/admin/staff/notifications/deliveries/send", headers=trainer).status_code == 403
            assert client.post("/admin/staff/notifications/deliveries/send", headers=maintenance).status_code == 403
            delivery_id = payload["items"][0]["id"]
            assert client.post(
                f"/admin/staff/notifications/deliveries/{delivery_id}/retry", headers=trainer
            ).status_code == 403

            empty_pass = client.post("/admin/staff/notifications/deliveries/send", headers=owner)
            assert empty_pass.status_code == 200
            assert empty_pass.json() == {
                "enabled": True,
                "attempted": 0,
                "sent": 0,
                "simulated": 0,
                "failed": 0,
                "remaining": 0,
            }

            # Only a failed delivery is retryable, and unknown ids are a 404.
            assert client.post(
                f"/admin/staff/notifications/deliveries/{delivery_id}/retry", headers=owner
            ).status_code == 409
            assert client.post(
                f"/admin/staff/notifications/deliveries/{uuid4()}/retry", headers=owner
            ).status_code == 404
            assert client.get(
                "/admin/staff/notifications/deliveries?status=bogus", headers=owner
            ).status_code == 422

            # A transport failure is recorded on the row and can be retried.
            def broken_send(**_kwargs) -> str:
                raise MailDeliveryFailed("No se pudo enviar el aviso de asistencia: 550 relay denied")

            monkeypatch.setattr(delivery_module, "send_email", broken_send)
            assert client.post(
                "/staff/attendance/clock-out",
                json={"shift_id": shift_id, "request_id": str(uuid4())},
                headers=ana,
            ).status_code == 200
            assert client.post(
                f"/admin/staff/attendance/{attendance_id}/corrections",
                json={
                    "request_id": str(uuid4()),
                    "event_type": "check_out",
                    "occurred_at": (now + timedelta(hours=7)).isoformat(),
                    "reason": "La salida quedó antes",
                },
                headers=owner,
            ).status_code == 200

            failed_board = client.get(
                "/admin/staff/notifications/deliveries?status=failed", headers=owner
            )
            assert failed_board.status_code == 200
            failed_payload = failed_board.json()
            assert failed_payload["total"] == 1
            assert failed_payload["counts"]["failed"] == 1
            failed_item = failed_payload["items"][0]
            assert failed_item["status"] == "failed"
            assert "550 relay denied" in failed_item["error"]
            assert failed_item["sent_at"] is None

            monkeypatch.setattr(delivery_module, "send_email", working_send)
            retried = client.post(
                f"/admin/staff/notifications/deliveries/{failed_item['id']}/retry", headers=owner
            )
            assert retried.status_code == 200
            assert retried.json()["status"] == "sent"
            assert retried.json()["attempts"] == 2
            assert retried.json()["error"] is None
            assert retried.json()["sent_at"] is not None
            assert outbox[-1]["recipient"] == "ana@example.com"

            # Turning the channel off stops new deliveries and holds the pass.
            settings = client.patch(
                "/admin/staff/settings",
                json={
                    "check_in_early_grace_minutes": 15,
                    "lateness_tolerance_minutes": 0,
                    "attendance_request_sla_hours": 24,
                    "attendance_email_enabled": False,
                },
                headers=owner,
            )
            assert settings.status_code == 200
            assert settings.json()["attendance_email_enabled"] is False

            before = client.get("/admin/staff/notifications/deliveries", headers=owner).json()
            assert client.post(
                f"/admin/staff/attendance/{attendance_id}/voids",
                json={
                    "request_id": str(uuid4()),
                    "mark": "check_out",
                    "reason": "La salida era de otro día",
                },
                headers=owner,
            ).status_code == 200
            after = client.get("/admin/staff/notifications/deliveries", headers=owner).json()
            assert after["enabled"] is False
            assert after["total"] == before["total"]
            assert len(outbox) == 2

            held = client.post("/admin/staff/notifications/deliveries/send", headers=owner)
            assert held.status_code == 200
            assert held.json()["enabled"] is False
            assert held.json()["attempted"] == 0

            assert client.patch(
                "/admin/staff/settings",
                json={
                    "check_in_early_grace_minutes": 15,
                    "lateness_tolerance_minutes": 0,
                    "attendance_request_sla_hours": 24,
                    "attendance_email_enabled": True,
                },
                headers=owner,
            ).status_code == 200
    finally:
        app.dependency_overrides.pop(get_session, None)
