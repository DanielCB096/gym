from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.models import Employee
from app.modules.identity.service import ensure_default_access_control, register_user


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

            # The admin listing shows both scheduled shifts.
            listing = client.get("/admin/staff/shifts", headers=owner)
            assert listing.status_code == 200
            assert {item["id"] for item in listing.json()} >= {shift_id, other_shift}
            manual_row = next(item for item in listing.json() if item["id"] == other_shift)
            assert manual_row["attendance"]["check_in_source"] == "manual"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
