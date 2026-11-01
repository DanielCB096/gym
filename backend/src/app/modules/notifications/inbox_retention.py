"""Retention for both inboxes and for the staff delivery queues.

The member and the staff inboxes are append-only from the reader's point of
view: a notice is never edited and only the emitting service can close it. They
also grow forever, because every event of the club leaves a row, and the panel
and the app read a bounded page at a time anyway. The staff delivery queues
store email and browser push per notice; member email is covered here too, while
Expo receipts and member push have their own purge in ``push_retention`` and
``retention``.

This module deletes history that nobody reads anymore:

* a member notice that was read and is older than the inbox window;
* a staff notice from the same window whose work is finished —resolved when it
  was actionable, read when it only informed—;
* a terminal email or push delivery past the delivery window, once no provider
  receipt still points at it.

Three guards keep the deletion safe. A notice is never touched while any
delivery still points at it (the foreign keys are ``RESTRICT``, so deleting the
notice first would fail); a delivery is never touched while a receipt still
points at it, and receipts have their own window (ADR-058); and the kiosk token
warning is never deleted because it is materialised on read, so the dedupe key
is the only thing that keeps it from being written again while the device keeps
its expired token (ADR-028). The unread member notices and the unresolved
actionable staff notices are the pending work of both inboxes and are never
retention candidates, no matter their age.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import os

from sqlalchemy import and_, delete, func, or_
from sqlmodel import Session, select

from app.modules.notifications.models import (
    MemberNotification,
    MemberNotificationEmailDelivery,
    MemberPushDelivery,
    StaffNotification,
    StaffNotificationDelivery,
    StaffNotificationDeliveryReceipt,
    StaffPushDelivery,
    utc_now,
)
from app.modules.notifications.service import CLOSABLE_STAFF_KINDS

INBOX_RETENTION_ENV = "NOTIFICATION_INBOX_RETENTION_DAYS"
# Kept for compatibility; the setting now also governs member email deliveries.
STAFF_DELIVERY_RETENTION_ENV = "STAFF_DELIVERY_RETENTION_DAYS"
DEFAULT_INBOX_RETENTION_DAYS = 365
DEFAULT_STAFF_DELIVERY_RETENTION_DAYS = 365
MIN_INBOX_RETENTION_DAYS = 30
MIN_DELIVERY_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650
TERMINAL_DELIVERY_STATUSES = ("sent", "simulated", "failed")
TERMINAL_MEMBER_EMAIL_STATUSES = ("sent", "simulated", "failed", "cancelled")
# Materialised on read, so deleting it would let the same warning be written
# again while the device still carries that expiry date; it is one row per
# device, phase and account, tiny against the event notices.
KIOSK_TOKEN_NOTICE_KIND = "kiosk_token_expiring"


@dataclass(frozen=True)
class InboxRetentionPolicy:
    inbox_days: int
    delivery_days: int


@dataclass(frozen=True)
class InboxPurgeResult:
    inbox_days: int
    delivery_days: int
    inbox_cutoff: datetime
    delivery_cutoff: datetime
    member_notices_deleted: int
    staff_notices_deleted: int
    member_email_deliveries_deleted: int
    staff_email_deliveries_deleted: int
    staff_push_deliveries_deleted: int
    dry_run: bool


def inbox_retention_policy_from_env() -> InboxRetentionPolicy:
    return InboxRetentionPolicy(
        inbox_days=_env_days(
            INBOX_RETENTION_ENV,
            DEFAULT_INBOX_RETENTION_DAYS,
            minimum=MIN_INBOX_RETENTION_DAYS,
        ),
        delivery_days=_env_days(
            STAFF_DELIVERY_RETENTION_ENV,
            DEFAULT_STAFF_DELIVERY_RETENTION_DAYS,
            minimum=MIN_DELIVERY_RETENTION_DAYS,
        ),
    )


def purge_inbox_history(
    session: Session,
    *,
    now: datetime | None = None,
    inbox_days: int | None = None,
    delivery_days: int | None = None,
    dry_run: bool = False,
) -> InboxPurgeResult:
    """Delete eligible notices and terminal email/push deliveries past their window.

    The deliveries go first: the notices point at them through ``RESTRICT``
    foreign keys, so a notice whose email or push row is still inside the
    delivery window survives this run and the next one catches it.
    """

    occurred = _as_utc(now or utc_now())
    days = (
        _validated_days(inbox_days, name=INBOX_RETENTION_ENV, minimum=MIN_INBOX_RETENTION_DAYS)
        if inbox_days is not None
        else _env_days(
            INBOX_RETENTION_ENV, DEFAULT_INBOX_RETENTION_DAYS, minimum=MIN_INBOX_RETENTION_DAYS
        )
    )
    delivery_window = (
        _validated_days(
            delivery_days,
            name=STAFF_DELIVERY_RETENTION_ENV,
            minimum=MIN_DELIVERY_RETENTION_DAYS,
        )
        if delivery_days is not None
        else _env_days(
            STAFF_DELIVERY_RETENTION_ENV,
            DEFAULT_STAFF_DELIVERY_RETENTION_DAYS,
            minimum=MIN_DELIVERY_RETENTION_DAYS,
        )
    )
    inbox_cutoff = occurred - timedelta(days=days)
    delivery_cutoff = occurred - timedelta(days=delivery_window)

    member_notice_condition = and_(
        MemberNotification.read_at.is_not(None),
        MemberNotification.created_at < inbox_cutoff,
        ~select(MemberPushDelivery.id)
        .where(MemberPushDelivery.notification_id == MemberNotification.id)
        .exists(),
        ~select(MemberNotificationEmailDelivery.id)
        .where(
            MemberNotificationEmailDelivery.notification_id == MemberNotification.id
        )
        .exists(),
    )
    staff_notice_condition = and_(
        StaffNotification.kind != KIOSK_TOKEN_NOTICE_KIND,
        StaffNotification.created_at < inbox_cutoff,
        or_(
            StaffNotification.resolved_at.is_not(None),
            and_(
                StaffNotification.kind.not_in(CLOSABLE_STAFF_KINDS),
                StaffNotification.read_at.is_not(None),
            ),
        ),
        ~select(StaffNotificationDelivery.id)
        .where(StaffNotificationDelivery.notice_id == StaffNotification.id)
        .exists(),
        ~select(StaffPushDelivery.id)
        .where(StaffPushDelivery.notice_id == StaffNotification.id)
        .exists(),
    )
    email_delivery_condition = and_(
        StaffNotificationDelivery.status.in_(TERMINAL_DELIVERY_STATUSES),
        StaffNotificationDelivery.created_at < delivery_cutoff,
        ~select(StaffNotificationDeliveryReceipt.id)
        .where(
            StaffNotificationDeliveryReceipt.delivery_id
            == StaffNotificationDelivery.id
        )
        .exists(),
    )
    member_email_delivery_condition = and_(
        MemberNotificationEmailDelivery.status.in_(TERMINAL_MEMBER_EMAIL_STATUSES),
        MemberNotificationEmailDelivery.next_attempt_at.is_(None),
        MemberNotificationEmailDelivery.created_at < delivery_cutoff,
    )
    push_delivery_condition = and_(
        StaffPushDelivery.status.in_(TERMINAL_DELIVERY_STATUSES),
        StaffPushDelivery.created_at < delivery_cutoff,
    )

    if dry_run:
        push_deleted = _count(session, StaffPushDelivery, push_delivery_condition)
        email_deleted = _count(
            session, StaffNotificationDelivery, email_delivery_condition
        )
        member_email_deleted = _count(
            session,
            MemberNotificationEmailDelivery,
            member_email_delivery_condition,
        )
        staff_deleted = _count(session, StaffNotification, staff_notice_condition)
        member_deleted = _count(session, MemberNotification, member_notice_condition)
    else:
        push_deleted = _delete(session, StaffPushDelivery, push_delivery_condition)
        email_deleted = _delete(
            session, StaffNotificationDelivery, email_delivery_condition
        )
        member_email_deleted = _delete(
            session,
            MemberNotificationEmailDelivery,
            member_email_delivery_condition,
        )
        staff_deleted = _delete(session, StaffNotification, staff_notice_condition)
        member_deleted = _delete(session, MemberNotification, member_notice_condition)
        session.commit()

    return InboxPurgeResult(
        inbox_days=days,
        delivery_days=delivery_window,
        inbox_cutoff=inbox_cutoff,
        delivery_cutoff=delivery_cutoff,
        member_notices_deleted=member_deleted,
        staff_notices_deleted=staff_deleted,
        member_email_deliveries_deleted=member_email_deleted,
        staff_email_deliveries_deleted=email_deleted,
        staff_push_deliveries_deleted=push_deleted,
        dry_run=dry_run,
    )


def _count(session: Session, model: type, condition) -> int:
    return int(
        session.exec(select(func.count(model.id)).where(condition)).one() or 0
    )


def _delete(session: Session, model: type, condition) -> int:
    statement = delete(model).where(condition).execution_options(
        synchronize_session=False
    )
    result = session.exec(statement)
    return int(getattr(result, "rowcount", 0) or 0)


def _env_days(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} debe ser un número entero de días.") from None
    return _validated_days(value, name=name, minimum=minimum)


def _validated_days(value: int, *, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} debe ser un número entero de días.")
    if value < minimum or value > MAX_RETENTION_DAYS:
        raise ValueError(
            f"{name} debe estar entre {minimum} y {MAX_RETENTION_DAYS} días."
        )
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)
