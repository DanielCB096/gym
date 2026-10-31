"""Retention for the member push receipts and the finished deliveries.

``member_push_delivery_receipts`` keeps what Expo said about a push after taking
it, and ``member_push_deliveries`` keeps one row per notice and device. Both grow
with every notice: the panel reads the latest receipt and the open queue, but an
answered send is history after a while.

The purge is two passes with their own window. Receipts go first by
``received_at`` —the club's clock, not the ticket's— because a late answer is
still stored when it arrives. Then deliveries in a terminal state
(``sent``/``simulated``/``failed``) go by ``created_at``. A delivery still
referenced by a receipt is kept even if it is past its window: the foreign key
is ``RESTRICT`` and the receipt's answer must not vanish under it. ``pending``
rows are never touched, because they are still the queue.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import os

from sqlalchemy import and_, delete, func
from sqlmodel import Session, select

from app.modules.notifications.models import (
    MemberPushDelivery,
    MemberPushDeliveryReceipt,
    utc_now,
)

RECEIPT_RETENTION_ENV = "PUSH_RECEIPT_RETENTION_DAYS"
DELIVERY_RETENTION_ENV = "PUSH_DELIVERY_RETENTION_DAYS"
DEFAULT_RECEIPT_RETENTION_DAYS = 90
DEFAULT_DELIVERY_RETENTION_DAYS = 365
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650
TERMINAL_DELIVERY_STATUSES = ("sent", "simulated", "failed")


@dataclass(frozen=True)
class PushRetentionPolicy:
    receipt_days: int
    delivery_days: int


@dataclass(frozen=True)
class PushPurgeResult:
    receipt_days: int
    delivery_days: int
    receipt_cutoff: datetime
    delivery_cutoff: datetime
    receipts_deleted: int
    deliveries_deleted: int
    dry_run: bool


def push_retention_policy_from_env() -> PushRetentionPolicy:
    return PushRetentionPolicy(
        receipt_days=_env_days(RECEIPT_RETENTION_ENV, DEFAULT_RECEIPT_RETENTION_DAYS),
        delivery_days=_env_days(
            DELIVERY_RETENTION_ENV, DEFAULT_DELIVERY_RETENTION_DAYS
        ),
    )


def purge_push_data(
    session: Session,
    *,
    now: datetime | None = None,
    receipt_days: int | None = None,
    delivery_days: int | None = None,
    dry_run: bool = False,
) -> PushPurgeResult:
    """Delete old receipts and finished deliveries, returning what was removed."""

    moment = _as_utc(now or utc_now())
    receipts_window = (
        _validated_days(receipt_days, name=RECEIPT_RETENTION_ENV)
        if receipt_days is not None
        else _env_days(RECEIPT_RETENTION_ENV, DEFAULT_RECEIPT_RETENTION_DAYS)
    )
    deliveries_window = (
        _validated_days(delivery_days, name=DELIVERY_RETENTION_ENV)
        if delivery_days is not None
        else _env_days(DELIVERY_RETENTION_ENV, DEFAULT_DELIVERY_RETENTION_DAYS)
    )
    receipt_cutoff = moment - timedelta(days=receipts_window)
    delivery_cutoff = moment - timedelta(days=deliveries_window)

    receipt_condition = MemberPushDeliveryReceipt.received_at < receipt_cutoff
    receipt_exists = (
        select(MemberPushDeliveryReceipt.id)
        .where(MemberPushDeliveryReceipt.delivery_id == MemberPushDelivery.id)
        .exists()
    )
    delivery_condition = and_(
        MemberPushDelivery.status.in_(TERMINAL_DELIVERY_STATUSES),
        MemberPushDelivery.created_at < delivery_cutoff,
        ~receipt_exists,
    )

    if dry_run:
        receipts_deleted = _count(session, MemberPushDeliveryReceipt, receipt_condition)
        deliveries_deleted = _count(session, MemberPushDelivery, delivery_condition)
    else:
        receipts_deleted = _delete(session, MemberPushDeliveryReceipt, receipt_condition)
        deliveries_deleted = _delete(session, MemberPushDelivery, delivery_condition)
        session.commit()

    return PushPurgeResult(
        receipt_days=receipts_window,
        delivery_days=deliveries_window,
        receipt_cutoff=receipt_cutoff,
        delivery_cutoff=delivery_cutoff,
        receipts_deleted=receipts_deleted,
        deliveries_deleted=deliveries_deleted,
        dry_run=dry_run,
    )


def _count(session: Session, model, condition) -> int:
    return int(
        session.exec(select(func.count(model.id)).where(condition)).one() or 0
    )


def _delete(session: Session, model, condition) -> int:
    result = session.exec(delete(model).where(condition))
    return int(getattr(result, "rowcount", 0) or 0)


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
            f"{name} debe estar entre {MIN_RETENTION_DAYS} y {MAX_RETENTION_DAYS} días."
        )
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)
