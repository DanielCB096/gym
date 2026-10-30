"""Retention for the rotating codes and the kiosk attempt log.

``member_access_codes`` and ``kiosk_attempts`` are operational tables: a code
lives five minutes and an attempt is only needed for the one-minute device rate
limit. Keeping them forever adds nothing and leaves personal data on disk, so
this module deletes rows that have been useless for a configurable number of
days.

The access log (``access_events``) is *not* touched: it is the club's business
record and its retention is a policy decision with the club, not a cleanup job.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import os

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.modules.access.models import KioskAttempt, MemberAccessCode, utc_now

CODE_RETENTION_ENV = "KIOSK_CODE_RETENTION_DAYS"
ATTEMPT_RETENTION_ENV = "KIOSK_ATTEMPT_RETENTION_DAYS"
DEFAULT_CODE_RETENTION_DAYS = 7
DEFAULT_ATTEMPT_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 3650


@dataclass(frozen=True)
class RetentionPolicy:
    code_days: int
    attempt_days: int


@dataclass(frozen=True)
class PurgeResult:
    code_days: int
    attempt_days: int
    code_cutoff: datetime
    attempt_cutoff: datetime
    codes_deleted: int
    attempts_deleted: int
    dry_run: bool


def retention_policy_from_env() -> RetentionPolicy:
    return RetentionPolicy(
        code_days=_env_days(CODE_RETENTION_ENV, DEFAULT_CODE_RETENTION_DAYS),
        attempt_days=_env_days(ATTEMPT_RETENTION_ENV, DEFAULT_ATTEMPT_RETENTION_DAYS),
    )


def purge_expired_access_data(
    session: Session,
    *,
    now: datetime | None = None,
    code_days: int | None = None,
    attempt_days: int | None = None,
    dry_run: bool = False,
) -> PurgeResult:
    """Delete unusable codes and old attempts, returning what was removed.

    A code is removed once its ``expires_at`` is older than the cutoff: by then
    it is either expired and unusable or was consumed long before it expired.
    A code that is still valid is never deleted, even with a one-day retention.
    """

    occurred_at = _as_utc(now or utc_now())
    code_days = (
        _validated_days(code_days, name=CODE_RETENTION_ENV)
        if code_days is not None
        else _env_days(CODE_RETENTION_ENV, DEFAULT_CODE_RETENTION_DAYS)
    )
    attempt_days = (
        _validated_days(attempt_days, name=ATTEMPT_RETENTION_ENV)
        if attempt_days is not None
        else _env_days(ATTEMPT_RETENTION_ENV, DEFAULT_ATTEMPT_RETENTION_DAYS)
    )
    code_cutoff = occurred_at - timedelta(days=code_days)
    attempt_cutoff = occurred_at - timedelta(days=attempt_days)
    code_condition = MemberAccessCode.expires_at < code_cutoff
    attempt_condition = KioskAttempt.occurred_at < attempt_cutoff

    if dry_run:
        codes_deleted = int(
            session.exec(
                select(func.count(MemberAccessCode.id)).where(code_condition)
            ).one()
            or 0
        )
        attempts_deleted = int(
            session.exec(
                select(func.count(KioskAttempt.id)).where(attempt_condition)
            ).one()
            or 0
        )
    else:
        codes_result = session.exec(delete(MemberAccessCode).where(code_condition))
        attempts_result = session.exec(delete(KioskAttempt).where(attempt_condition))
        codes_deleted = int(getattr(codes_result, "rowcount", 0) or 0)
        attempts_deleted = int(getattr(attempts_result, "rowcount", 0) or 0)
        session.commit()

    return PurgeResult(
        code_days=code_days,
        attempt_days=attempt_days,
        code_cutoff=code_cutoff,
        attempt_cutoff=attempt_cutoff,
        codes_deleted=codes_deleted,
        attempts_deleted=attempts_deleted,
        dry_run=dry_run,
    )


def _env_days(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} debe ser un número entero de días.") from None
    return _validated_days(value, name=name)


def _validated_days(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} debe ser un número entero de días.")
    if value < 1 or value > MAX_RETENTION_DAYS:
        raise ValueError(
            f"{name} debe estar entre 1 y {MAX_RETENTION_DAYS} días."
        )
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)
