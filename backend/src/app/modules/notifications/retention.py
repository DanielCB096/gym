"""Retention for the provider receipts of the staff emails.

``staff_notification_delivery_receipts`` keeps what the mail provider said about
a message that already left —the mailbox accepted it, the address bounced, the
recipient marked it as spam—. The table is append-only and grows with every
report, while the panel only reads the latest receipt of each delivery: an old
report is useful to answer a dispute for a while, not forever.

The retention is never shorter than the webhook window (``RECEIPT_MAX_AGE``):
an event older than that is rejected, so a purged receipt cannot come back
through a late retry of the same event. The delivery rows and the inbox are not
touched; those are the club's record of what was sent and what was notified.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import os

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.modules.notifications.models import StaffNotificationDeliveryReceipt, utc_now
from app.modules.notifications.receipts import RECEIPT_MAX_AGE

RETENTION_ENV = "STAFF_RECEIPT_RETENTION_DAYS"
DEFAULT_RETENTION_DAYS = 90
MIN_RETENTION_DAYS = RECEIPT_MAX_AGE.days
MAX_RETENTION_DAYS = 3650


@dataclass(frozen=True)
class ReceiptRetentionPolicy:
    retention_days: int


@dataclass(frozen=True)
class ReceiptPurgeResult:
    retention_days: int
    cutoff: datetime
    receipts_deleted: int
    dry_run: bool


def receipt_retention_policy_from_env() -> ReceiptRetentionPolicy:
    return ReceiptRetentionPolicy(
        retention_days=_env_days(RETENTION_ENV, DEFAULT_RETENTION_DAYS)
    )


def purge_expired_receipts(
    session: Session,
    *,
    now: datetime | None = None,
    retention_days: int | None = None,
    dry_run: bool = False,
) -> ReceiptPurgeResult:
    """Delete the receipts received before the cutoff, returning what was removed.

    The cutoff uses ``received_at``, the club's clock, not the ``occurred_at``
    the provider sends: a report is kept for the configured time from the moment
    it was stored, whatever date it claims for the event.
    """

    occurred_at = _as_utc(now or utc_now())
    days = (
        _validated_days(retention_days, name=RETENTION_ENV)
        if retention_days is not None
        else _env_days(RETENTION_ENV, DEFAULT_RETENTION_DAYS)
    )
    cutoff = occurred_at - timedelta(days=days)
    condition = StaffNotificationDeliveryReceipt.received_at < cutoff

    if dry_run:
        receipts_deleted = int(
            session.exec(
                select(func.count(StaffNotificationDeliveryReceipt.id)).where(
                    condition
                )
            ).one()
            or 0
        )
    else:
        result = session.exec(
            delete(StaffNotificationDeliveryReceipt).where(condition)
        )
        receipts_deleted = int(getattr(result, "rowcount", 0) or 0)
        session.commit()

    return ReceiptPurgeResult(
        retention_days=days,
        cutoff=cutoff,
        receipts_deleted=receipts_deleted,
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
    if value < MIN_RETENTION_DAYS or value > MAX_RETENTION_DAYS:
        raise ValueError(
            f"{name} debe estar entre {MIN_RETENTION_DAYS} y {MAX_RETENTION_DAYS} "
            "días: una retención menor que la ventana del webhook dejaría volver "
            "un acuse purgado por un reintento tardío."
        )
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)
