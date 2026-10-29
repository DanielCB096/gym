"""PostgreSQL-only checks for the per-member row lock (ADR-030).

Skipped unless ``TEST_POSTGRES_URL`` points at a disposable PostgreSQL
database. SQLite drops ``FOR UPDATE``, so the rest of the suite cannot
reproduce the race these tests cover.
"""

import os
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, func, select

from app.modules.access import kiosk
from app.modules.access.models import (
    AccessEvent,
    AccessSettings,
    KioskDevice,
    MemberAccessCode,
)
from app.modules.memberships.models import Member, Membership, Plan

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL no definido; apunta a una base PostgreSQL desechable",
)


@pytest.fixture(scope="module")
def engine():
    pg_engine = create_engine(POSTGRES_URL)
    SQLModel.metadata.create_all(pg_engine)
    with Session(pg_engine) as session:
        if session.get(AccessSettings, 1) is None:
            session.add(
                AccessSettings(
                    id=1,
                    antipassback_seconds=0,
                    max_occupancy=None,
                    occupancy_window_seconds=7200,
                )
            )
            session.commit()
    yield pg_engine
    pg_engine.dispose()


@pytest.fixture(autouse=True)
def access_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "postgres-lock-secret")
    monkeypatch.setenv("APP_TIMEZONE", "America/Mexico_City")


def _seed(engine, *, daily_entry_limit: int | None, codes: list[str]) -> tuple[uuid.UUID, uuid.UUID]:
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        plan = Plan(
            code="T" + uuid.uuid4().hex[:10],
            name="Prueba PostgreSQL",
            duration_days=30,
            price_cents=10000,
            daily_entry_limit=daily_entry_limit,
        )
        session.add(plan)
        session.commit()
        member = Member(
            first_name="Prueba",
            last_name="Pg" + uuid.uuid4().hex[:5],
            email=f"pg{uuid.uuid4().hex[:10]}@example.com",
            status="active",
        )
        session.add(member)
        session.commit()
        session.add(
            Membership(
                member_id=member.id,
                plan_id=plan.id,
                status="active",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
        )
        device = KioskDevice(
            label="PG " + uuid.uuid4().hex[:6],
            token_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        )
        session.add(device)
        session.commit()
        for code in codes:
            session.add(
                MemberAccessCode(
                    member_id=member.id,
                    code_hash=kiosk._access_code_hash(code),
                    created_at=now,
                    expires_at=now + timedelta(minutes=5),
                )
            )
        session.commit()
        return member.id, device.id


def _count_authorized_entries(engine, member_id: uuid.UUID) -> int:
    with Session(engine) as session:
        return session.exec(
            select(func.count(AccessEvent.id)).where(
                AccessEvent.member_id == member_id,
                AccessEvent.direction == "entry",
                AccessEvent.authorized.is_(True),
            )
        ).one()


def test_second_kiosk_waits_for_the_member_lock(engine) -> None:
    member_id, device_id = _seed(engine, daily_entry_limit=None, codes=["424242"])

    holder = Session(engine)
    kiosk._lock_member_row(holder, member_id)

    def release() -> None:
        time.sleep(1.0)
        holder.commit()
        holder.close()

    releaser = threading.Thread(target=release)
    releaser.start()
    time.sleep(0.2)

    started = time.monotonic()
    with Session(engine) as session:
        device = session.get(KioskDevice, device_id)
        result = kiosk.check_in_with_code(session, device=device, code="424242")
    elapsed = time.monotonic() - started
    releaser.join()

    assert result.authorized is True
    assert elapsed >= 0.5, f"el check-in no esperó al bloqueo: {elapsed:.2f} s"
    assert _count_authorized_entries(engine, member_id) == 1


def test_two_kiosks_never_authorize_two_entries_against_a_daily_limit_of_one(engine) -> None:
    for _ in range(8):
        codes = [f"{random.randint(0, 999999):06d}", f"{random.randint(0, 999999):06d}"]
        member_id, device_id = _seed(engine, daily_entry_limit=1, codes=codes)
        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, bool | None, str]] = []
        lock = threading.Lock()

        def decide(code: str) -> None:
            with Session(engine) as session:
                device = session.get(KioskDevice, device_id)
                barrier.wait()
                try:
                    result = kiosk.check_in_with_code(session, device=device, code=code)
                    outcome = (code, result.authorized, result.reason)
                except Exception as error:  # noqa: BLE001
                    outcome = (code, None, type(error).__name__)
                with lock:
                    outcomes.append(outcome)

        threads = [threading.Thread(target=decide, args=(code,)) for code in codes]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        authorized = [outcome for outcome in outcomes if outcome[1] is True]
        denied = [outcome for outcome in outcomes if outcome[1] is False]
        assert len(authorized) == 1, outcomes
        assert [outcome[2] for outcome in denied] == ["daily_limit"], outcomes
        assert _count_authorized_entries(engine, member_id) == 1
