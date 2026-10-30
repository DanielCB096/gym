from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlmodel import Session, select

from app.main import app  # noqa: F401  # registers every table in SQLModel.metadata
from app.modules.access.models import (
    KioskAttempt,
    KioskDevice,
    MemberAccessCode,
)
from app.modules.access.retention import (
    DEFAULT_ATTEMPT_RETENTION_DAYS,
    DEFAULT_CODE_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    purge_expired_access_data,
    retention_policy_from_env,
)
from app.modules.memberships.models import Member

NOW = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)


def _seed_rows(session: Session) -> dict[str, UUID]:
    member = Member(first_name="Ana", last_name="Lopez", email="ana@example.test")
    device = KioskDevice(label="Recepción", token_sha256="a" * 64)
    session.add_all([member, device])
    session.flush()

    rows = {
        "old_consumed": MemberAccessCode(
            member_id=member.id,
            code_hash="1" * 64,
            created_at=NOW - timedelta(days=10),
            expires_at=NOW - timedelta(days=10) + timedelta(minutes=5),
            consumed_at=NOW - timedelta(days=10) + timedelta(minutes=2),
        ),
        "old_expired": MemberAccessCode(
            member_id=member.id,
            code_hash="2" * 64,
            created_at=NOW - timedelta(days=8),
            expires_at=NOW - timedelta(days=8) + timedelta(minutes=5),
        ),
        "recent_expired": MemberAccessCode(
            member_id=member.id,
            code_hash="3" * 64,
            created_at=NOW - timedelta(days=2),
            expires_at=NOW - timedelta(days=2) + timedelta(minutes=5),
        ),
        "active": MemberAccessCode(
            member_id=member.id,
            code_hash="4" * 64,
            created_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=4),
        ),
    }
    session.add_all(rows.values())
    attempts = {
        "old": KioskAttempt(
            device_id=device.id, result="invalid", occurred_at=NOW - timedelta(days=40)
        ),
        "medium": KioskAttempt(
            device_id=device.id, result="denied", occurred_at=NOW - timedelta(days=20)
        ),
        "recent": KioskAttempt(
            device_id=device.id, result="authorized", occurred_at=NOW - timedelta(hours=1)
        ),
    }
    session.add_all(attempts.values())
    session.commit()
    return {**{key: row.id for key, row in rows.items()},
            **{key: row.id for key, row in attempts.items()}}


def _remaining(session: Session, model) -> set[UUID]:
    session.expire_all()
    return {row.id for row in session.exec(select(model)).all()}


def test_purge_removes_only_rows_past_the_default_retention(session: Session) -> None:
    ids = _seed_rows(session)

    result = purge_expired_access_data(session, now=NOW)

    assert result.code_days == DEFAULT_CODE_RETENTION_DAYS
    assert result.attempt_days == DEFAULT_ATTEMPT_RETENTION_DAYS
    assert result.dry_run is False
    assert result.codes_deleted == 2
    assert result.attempts_deleted == 1
    assert result.code_cutoff == NOW - timedelta(days=DEFAULT_CODE_RETENTION_DAYS)
    assert result.attempt_cutoff == NOW - timedelta(
        days=DEFAULT_ATTEMPT_RETENTION_DAYS
    )
    assert _remaining(session, MemberAccessCode) == {
        ids["recent_expired"],
        ids["active"],
    }
    assert _remaining(session, KioskAttempt) == {ids["medium"], ids["recent"]}


def test_purge_is_idempotent(session: Session) -> None:
    _seed_rows(session)

    purge_expired_access_data(session, now=NOW)
    second = purge_expired_access_data(session, now=NOW)

    assert second.codes_deleted == 0
    assert second.attempts_deleted == 0


def test_dry_run_counts_without_deleting(session: Session) -> None:
    ids = _seed_rows(session)

    result = purge_expired_access_data(session, now=NOW, dry_run=True)

    assert result.dry_run is True
    assert result.codes_deleted == 2
    assert result.attempts_deleted == 1
    assert _remaining(session, MemberAccessCode) == {
        ids["old_consumed"],
        ids["old_expired"],
        ids["recent_expired"],
        ids["active"],
    }
    assert _remaining(session, KioskAttempt) == {
        ids["old"],
        ids["medium"],
        ids["recent"],
    }


def test_overrides_move_the_cutoff(session: Session) -> None:
    ids = _seed_rows(session)

    result = purge_expired_access_data(
        session, now=NOW, code_days=1, attempt_days=5
    )

    assert result.codes_deleted == 3
    assert result.attempts_deleted == 2
    assert _remaining(session, MemberAccessCode) == {ids["active"]}
    assert _remaining(session, KioskAttempt) == {ids["recent"]}


def test_an_active_code_survives_any_retention(session: Session) -> None:
    ids = _seed_rows(session)

    purge_expired_access_data(session, now=NOW, code_days=1, attempt_days=1)

    assert ids["active"] in _remaining(session, MemberAccessCode)


@pytest.mark.parametrize("value", [0, -1, MAX_RETENTION_DAYS + 1])
def test_retention_days_are_validated(session: Session, value: int) -> None:
    _seed_rows(session)

    with pytest.raises(ValueError):
        purge_expired_access_data(session, now=NOW, code_days=value)
    with pytest.raises(ValueError):
        purge_expired_access_data(session, now=NOW, attempt_days=value)


def test_environment_policy_is_read_and_validated(monkeypatch) -> None:
    monkeypatch.delenv("KIOSK_CODE_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("KIOSK_ATTEMPT_RETENTION_DAYS", raising=False)
    policy = retention_policy_from_env()
    assert policy.code_days == DEFAULT_CODE_RETENTION_DAYS
    assert policy.attempt_days == DEFAULT_ATTEMPT_RETENTION_DAYS

    monkeypatch.setenv("KIOSK_CODE_RETENTION_DAYS", "14")
    monkeypatch.setenv("KIOSK_ATTEMPT_RETENTION_DAYS", "60")
    policy = retention_policy_from_env()
    assert policy.code_days == 14
    assert policy.attempt_days == 60

    monkeypatch.setenv("KIOSK_CODE_RETENTION_DAYS", "cero")
    with pytest.raises(ValueError):
        retention_policy_from_env()

    monkeypatch.setenv("KIOSK_CODE_RETENTION_DAYS", "0")
    with pytest.raises(ValueError):
        retention_policy_from_env()
