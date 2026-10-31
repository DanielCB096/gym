"""PostgreSQL-only checks for the physiotherapy room row lock (ADR-069).

Skipped unless ``TEST_POSTGRES_URL`` points at a disposable PostgreSQL
database. SQLite drops ``FOR UPDATE``, so the regular suite cannot show that
the room serialises two bookings: both would read the free room and insert an
appointment. The room row lock is what forces the second transaction to wait
and then trip over the first one.
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
from app.modules.memberships.models import Member
from app.modules.physio import service as physio_service
from app.modules.physio.models import (
    PhysioAppointment,
    PhysioRoom,
    PhysioService,
)
from app.modules.physio.service import (
    PhysioSlotConflict,
    create_physio_appointment,
    move_physio_appointment,
)

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
def slow_pack_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    # The room row is locked before the pack lookup, so the pause keeps the
    # lock held long enough for the second thread to queue behind it.
    original = physio_service._resolve_pack_for

    def _slow_resolve(*args, **kwargs):
        time.sleep(0.3)
        return original(*args, **kwargs)

    monkeypatch.setattr(physio_service, "_resolve_pack_for", _slow_resolve)


def _seed(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:8]
    member = Member(
        first_name="Ana",
        last_name="Sala concurrencia",
        email=f"room-{suffix}@example.com",
        status="active",
    )
    first_therapist = Employee(
        employee_number=f"EMP-{suffix}-A",
        first_name="Tere",
        last_name="Fisio",
        job_title="Fisioterapeuta",
        status="active",
    )
    second_therapist = Employee(
        employee_number=f"EMP-{suffix}-B",
        first_name="Luis",
        last_name="Fisio",
        job_title="Fisioterapeuta",
        status="active",
    )
    service = PhysioService(
        code=f"DESCARGA-{suffix}",
        name="Descarga muscular",
        duration_minutes=30,
        price_cents=50000,
    )
    room = PhysioRoom(name=f"Consultorio {suffix}")
    session.add(member)
    session.add(first_therapist)
    session.add(second_therapist)
    session.add(service)
    session.add(room)
    session.commit()
    return (
        member.id,
        service.id,
        room.id,
        first_therapist.id,
        second_therapist.id,
    )


def _run_together(targets: list) -> list[object]:
    barrier = threading.Barrier(len(targets))
    results: list[object] = []

    def _wrap(target):
        def _run() -> None:
            try:
                results.append(target(barrier))
            except Exception as error:  # noqa: BLE001 - asserted by the caller
                results.append(error)

        return _run

    threads = [threading.Thread(target=_wrap(target)) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    return results


def _room_conflicts(results: list[object]) -> list[PhysioSlotConflict]:
    return [result for result in results if isinstance(result, PhysioSlotConflict)]


def _count_room_appointments(engine, room_id: uuid.UUID) -> int:
    with Session(engine) as session:
        return int(
            session.exec(
                select(func.count(PhysioAppointment.id)).where(
                    PhysioAppointment.room_id == room_id,
                    PhysioAppointment.status != "cancelled",
                )
            ).one()
            or 0
        )


def test_two_simultaneous_bookings_of_the_same_room_keep_one(engine) -> None:
    with Session(engine) as session:
        member_id, service_id, room_id, first_therapist, second_therapist = _seed(session)

    starts_at = datetime.now(timezone.utc) + timedelta(days=1)

    def _book(therapist_id: uuid.UUID):
        def _run(barrier: threading.Barrier):
            with Session(engine) as session:
                barrier.wait(timeout=10)
                return create_physio_appointment(
                    session,
                    member_id=member_id,
                    service_id=service_id,
                    therapist_employee_id=therapist_id,
                    starts_at=starts_at,
                    room_id=room_id,
                )

        return _run

    results = _run_together([_book(first_therapist), _book(second_therapist)])

    conflicts = _room_conflicts(results)
    assert len(conflicts) == 1, results
    assert "consultorio" in str(conflicts[0]).lower()
    created = [result for result in results if not isinstance(result, Exception)]
    assert len(created) == 1, results
    assert _count_room_appointments(engine, room_id) == 1


def test_two_simultaneous_moves_into_the_same_room_keep_one(engine) -> None:
    with Session(engine) as session:
        member_id, service_id, room_id, first_therapist, second_therapist = _seed(session)
        morning = datetime.now(timezone.utc) + timedelta(days=1, hours=10)
        first_appointment = create_physio_appointment(
            session,
            member_id=member_id,
            service_id=service_id,
            therapist_employee_id=first_therapist,
            starts_at=morning,
        )
        second_appointment = create_physio_appointment(
            session,
            member_id=member_id,
            service_id=service_id,
            therapist_employee_id=second_therapist,
            starts_at=morning + timedelta(hours=1),
        )

    target = (datetime.now(timezone.utc) + timedelta(days=1, hours=15)).replace(
        minute=0, second=0, microsecond=0
    )

    def _move(appointment_id: uuid.UUID):
        def _run(barrier: threading.Barrier):
            with Session(engine) as session:
                barrier.wait(timeout=10)
                return move_physio_appointment(
                    session,
                    appointment_id,
                    starts_at=target,
                    room_id=room_id,
                )

        return _run

    results = _run_together(
        [_move(first_appointment.id), _move(second_appointment.id)]
    )

    conflicts = _room_conflicts(results)
    assert len(conflicts) == 1, results
    assert "consultorio" in str(conflicts[0]).lower()
    assert len([result for result in results if not isinstance(result, Exception)]) == 1
    assert _count_room_appointments(engine, room_id) == 1

    # The losing transaction rolls back and its appointment stays where it was.
    winner_id = next(
        result.id for result in results if not isinstance(result, Exception)
    )
    loser_id = (
        second_appointment.id
        if winner_id == first_appointment.id
        else first_appointment.id
    )
    with Session(engine) as session:
        loser = session.get(PhysioAppointment, loser_id)
        assert loser is not None
        assert loser.room_id is None
