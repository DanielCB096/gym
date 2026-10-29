"""PostgreSQL-only checks for the premium service refund (ADR-033, ADR-034).

Skipped unless ``TEST_POSTGRES_URL`` points at a disposable PostgreSQL
database. SQLite drops ``FOR UPDATE``, so the rest of the suite cannot show
that two simultaneous refunds of the same sale pay once, and it cannot prove
which register shift carries the outflow.
"""

import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, func, select

# Importing the app registers every table: ``create_all`` resolves the foreign
# keys across modules (routines point at the maintenance fleet, for instance)
# and fails when a model is missing.
import app.main  # noqa: F401
from app.modules.classes.models import (
    ClassReservation,
    ClassSession,
    ClassType,
)
from app.modules.inventory import service as inventory_service
from app.modules.inventory.models import Sale, SaleReturn
from app.modules.inventory.service import (
    close_cash_session,
    current_cash_session,
    list_cash_sessions,
    open_cash_session,
    refund_service_sale,
    register_service_sale,
)
from app.modules.memberships.models import Member

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL no definido; usa una base desechable",
)


@pytest.fixture(scope="module")
def engine():
    pg_engine = create_engine(POSTGRES_URL)
    # Never drop: another opt-in module may share the same disposable database.
    SQLModel.metadata.create_all(pg_engine)
    yield pg_engine
    pg_engine.dispose()


@pytest.fixture(autouse=True)
def clean_register(engine) -> None:
    """Close any shift a previous test left open: only one can be open."""
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


def _seed_member(session: Session) -> uuid.UUID:
    member = Member(
        first_name="Ana",
        last_name="Concurrencia",
        email=f"{uuid.uuid4().hex[:10]}@example.com",
        status="active",
    )
    session.add(member)
    session.commit()
    return member.id


def _seed_reservation(session: Session, member_id: uuid.UUID) -> uuid.UUID:
    class_type = ClassType(name=f"Spinning {uuid.uuid4().hex[:6]}")
    session.add(class_type)
    session.flush()
    starts_at = datetime.now(timezone.utc) + timedelta(hours=1)
    class_session = ClassSession(
        title="Spinning premium",
        class_type_id=class_type.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        capacity=8,
        access_type="premium",
        extra_price_cents=15000,
    )
    session.add(class_session)
    session.flush()
    reservation = ClassReservation(
        session_id=class_session.id,
        member_id=member_id,
        status="attended",
        origin="reception",
    )
    session.add(reservation)
    session.commit()
    return reservation.id


def _charge(
    session: Session, member_id: uuid.UUID, reservation_id: uuid.UUID
) -> Sale:
    sale = register_service_sale(
        session,
        member_id=member_id,
        description="Clase premium: Spinning premium",
        amount_cents=15000,
        payment_method="cash",
        class_reservation_id=reservation_id,
    )
    session.commit()
    return sale


def test_two_simultaneous_refunds_pay_only_once(engine, monkeypatch) -> None:
    with Session(engine) as session:
        member_id = _seed_member(session)
        reservation_id = _seed_reservation(session, member_id)
        shift = open_cash_session(session, opening_cash_cents=50000)
        sale = _charge(session, member_id, reservation_id)
        sale_id = sale.id
        shift_id = shift.id

    # Widening the window between reading the sale and committing the return
    # is what makes the race reproducible: without the row lock both registers
    # read ``completed`` inside it and pay twice.
    original_folio = inventory_service._build_return_folio

    def _slow_folio(occurred_at):
        time.sleep(0.5)
        return original_folio(occurred_at)

    monkeypatch.setattr(inventory_service, "_build_return_folio", _slow_folio)

    barrier = threading.Barrier(2)
    results: list[object] = []

    def _refund() -> None:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                results.append(
                    refund_service_sale(
                        session,
                        sale_id,
                        reason="Reembolso simultáneo desde dos cajas",
                    )
                )
                session.commit()
            except Exception as error:  # noqa: BLE001 - asserted below
                session.rollback()
                results.append(error)

    threads = [threading.Thread(target=_refund) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    failures = [result for result in results if isinstance(result, Exception)]
    assert failures == [], failures
    paid = [result for result in results if result is not None]
    assert len(paid) == 1, "exactly one refund should be paid"

    with Session(engine) as session:
        returns = session.exec(
            select(func.count(SaleReturn.id))
            .where(SaleReturn.sale_id == sale_id)
        ).one()
        assert int(returns or 0) == 1
        assert session.get(Sale, sale_id).status == "refunded"
        shift = current_cash_session(session)
        assert shift is not None and shift.id == shift_id
        assert shift.refunds_count == 1
        assert shift.cash_refunds_cents == 15000
        assert shift.cash_sales_cents == 15000
        assert shift.expected_cash_cents == 50000


def test_refund_lands_in_the_shift_that_pays_it(engine) -> None:
    with Session(engine) as session:
        member_id = _seed_member(session)
        reservation_id = _seed_reservation(session, member_id)
        first_shift = open_cash_session(session, opening_cash_cents=0)
        sale = _charge(session, member_id, reservation_id)

        # The sale was rung up in the first register, so that shift expects the
        # cash even after the sale is later refunded.
        closed = close_cash_session(
            session, first_shift.id, counted_cash_cents=15000
        )
        assert closed.cash_sales_cents == 15000
        assert closed.expected_cash_cents == 15000

        second_shift = open_cash_session(session, opening_cash_cents=0)
        refund_service_sale(
            session, sale.id, reason="Se cobró en el turno anterior"
        )
        session.commit()

        # The money leaves the drawer that pays the refund, not the one that
        # collected it: the closed shift is immutable.
        current = current_cash_session(session)
        assert current is not None and current.id == second_shift.id
        assert current.cash_refunds_cents == 15000
        assert current.expected_cash_cents == -15000

        closed_view = next(
            item
            for item in list_cash_sessions(session)
            if item.id == first_shift.id
        )
        assert closed_view.expected_cash_cents == 15000
        assert closed_view.cash_refunds_cents == 0
