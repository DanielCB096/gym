"""PostgreSQL-only check for the therapist partial-overlap race (ADR-072).

Skipped unless ``TEST_POSTGRES_URL`` points at a disposable PostgreSQL
database. SQLite drops ``FOR UPDATE``, so the regular suite cannot show that
two receptionists booking overlapping hours for the same therapist serialise:
both would read the free agenda and insert. The unique index only guards the
exact same start, so the employee row lock is what stops the partial overlap.
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
from app.modules.physio.models import PhysioAppointment, PhysioService
from app.modules.physio.service import (
    PhysioSlotConflict,
    create_physio_appointment,
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
    # The therapist row is locked before the pack lookup, so the pause keeps
    # the lock held long enough for the second thread to queue behind it.
    original = physio_service._resolve_pack_for

    def _slow_resolve(*args, **kwargs):
        time.sleep(0.3)
        return original(*args, **kwargs)

    monkeypatch.setattr(physio_service, "_resolve_pack_for", _slow_resolve)


def _seed(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:8]
    member = Member(
        first_name="Ana",
        last_name="Agenda concurrencia",
        email=f"therapist-{suffix}@example.com",
        status="active",
    )
    therapist = Employee(
        employee_number=f"EMP-{suffix}",
        first_name="Tere",
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
    session.add(member)
    session.add(therapist)
    session.add(service)
    session.commit()
    return member.id, service.id, therapist.id


def test_simultaneous_partial_overlaps_for_the_same_therapist_keep_one(engine) -> None:
    with Session(engine) as session:
        member_id, service_id, therapist_id = _seed(session)

    # 10:00 and 10:10 with a 30-minute service: the starts differ, so the
    # unique index lets both through unless the employee row serialises them.
    base = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    starts = [base, base + timedelta(minutes=10)]

    barrier = threading.Barrier(2)
    results: list[object] = []

    def _book(starts_at: datetime) -> None:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                results.append(
                    create_physio_appointment(
                        session,
                        member_id=member_id,
                        service_id=service_id,
                        therapist_employee_id=therapist_id,
                        starts_at=starts_at,
                    )
                )
            except Exception as error:  # noqa: BLE001 - asserted below
                session.rollback()
                results.append(error)

    threads = [threading.Thread(target=_book, args=(slot,)) for slot in starts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    conflicts = [result for result in results if isinstance(result, PhysioSlotConflict)]
    assert len(conflicts) == 1, results
    assert "fisioterapeuta" in str(conflicts[0]).lower()
    assert len([result for result in results if not isinstance(result, Exception)]) == 1

    with Session(engine) as session:
        count = session.exec(
            select(func.count(PhysioAppointment.id)).where(
                PhysioAppointment.therapist_employee_id == therapist_id,
                PhysioAppointment.status != "cancelled",
            )
        ).one()
        assert int(count or 0) == 1
