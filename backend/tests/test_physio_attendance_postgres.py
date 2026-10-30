"""PostgreSQL-only check for the physiotherapy double-mark race.

Skipped unless ``TEST_POSTGRES_URL`` points at a disposable PostgreSQL
database. SQLite drops ``FOR UPDATE``, so the regular suite cannot show that
two receptionists marking the same single session at the same time charge it
once. The test serialises through the appointment row lock and asserts a single
completed sale.
"""

import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, func, select

# Importing the app registers every table (including physio) for ``create_all``.
import app.main  # noqa: F401
from app.modules.identity.models import Employee
from app.modules.inventory.models import Sale
from app.modules.inventory.service import (
    close_cash_session,
    current_cash_session,
    open_cash_session,
)
from app.modules.memberships.models import Member
from app.modules.physio.models import PhysioService
from app.modules.physio.service import (
    create_physio_appointment,
    mark_physio_attendance,
)
from app.modules.physio import service as physio_service

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL no definido; usa una base desechable",
)


@pytest.fixture(scope="module")
def engine():
    pg_engine = create_engine(POSTGRES_URL)
    SQLModel.metadata.create_all(pg_engine)
    yield pg_engine
    pg_engine.dispose()


@pytest.fixture(autouse=True)
def clean_register(engine) -> None:
    with Session(engine) as session:
        open_shift = current_cash_session(session)
        if open_shift is not None:
            close_cash_session(
                session,
                open_shift.id,
                counted_cash_cents=0,
                notes="Cierre entre pruebas",
            )
    yield


def _seed(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    member = Member(
        first_name="Ana",
        last_name="Fisio concurrencia",
        email=f"{uuid.uuid4().hex[:10]}@example.com",
        status="active",
    )
    therapist = Employee(
        employee_number=f"EMP-{uuid.uuid4().hex[:8]}",
        first_name="Tere",
        last_name="Fisio",
        job_title="Fisioterapeuta",
        status="active",
    )
    service = PhysioService(
        code=f"DESCARGA-{uuid.uuid4().hex[:6]}",
        name="Descarga muscular",
        duration_minutes=30,
        price_cents=50000,
    )
    session.add(member)
    session.add(therapist)
    session.add(service)
    session.commit()
    appointment = create_physio_appointment(
        session,
        member_id=member.id,
        service_id=service.id,
        therapist_employee_id=therapist.id,
        starts_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    return appointment.id, member.id, service.id


def test_two_simultaneous_marks_charge_only_once(engine, monkeypatch) -> None:
    with Session(engine) as session:
        appointment_id, member_id, service_id = _seed(session)
        open_cash_session(session, opening_cash_cents=0)

    # Widen the window between reading the appointment and charging it. The row
    # lock is what keeps the second mark from charging a second time.
    original = physio_service._consume_or_charge

    def _slow_consume(*args, **kwargs):
        time.sleep(0.5)
        return original(*args, **kwargs)

    monkeypatch.setattr(physio_service, "_consume_or_charge", _slow_consume)

    barrier = threading.Barrier(2)
    results: list[object] = []

    def _mark() -> None:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                results.append(
                    mark_physio_attendance(
                        session,
                        appointment_id,
                        attended=True,
                        payment_method="cash",
                    )
                )
            except Exception as error:  # noqa: BLE001 - asserted below
                session.rollback()
                results.append(error)

    threads = [threading.Thread(target=_mark) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    failures = [result for result in results if isinstance(result, Exception)]
    assert failures == [], failures
    assert len(results) == 2
    assert all(result.status == "attended" for result in results)

    with Session(engine) as session:
        charges = session.exec(
            select(func.count(Sale.id)).where(
                Sale.physio_appointment_id == appointment_id
            )
        ).one()
        assert int(charges or 0) == 1, "exactly one charge should exist"
        sale = session.exec(
            select(Sale).where(Sale.physio_appointment_id == appointment_id)
        ).one()
        assert sale.total_cents == 50000
        assert sale.status == "completed"
