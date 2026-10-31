"""Send the queued staff-notification emails and keep their audit.

``create_staff_notification`` writes one ``pending`` delivery row in the same
transaction as the notice; nothing contacts a server there. This module is the
other half: it reads the queue **after** the domain transaction committed,
contacts SMTP once per row and records the outcome, so a slow or failing mail
server can never hold open — or roll back — the change that produced the
notice.

There is no worker in this project, so the pass runs in two ways: after the
response of the request that could have queued a notice (a FastAPI background
task), and on demand from the panel card. A delivery is claimed with a
compare-and-set on ``attempts`` before the message leaves, which keeps two
concurrent passes from sending the same row twice.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.mailer import MailerError, send_email
from app.modules.notifications.models import (
    StaffNotification,
    StaffNotificationDelivery,
    StaffNotificationDeliveryReceipt,
    utc_now,
)

DEFAULT_SEND_BATCH_LIMIT = 20
MAX_SEND_BATCH_LIMIT = 100
DEFAULT_DELIVERY_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DELIVERY_STATUSES = ("pending", "sent", "simulated", "failed")
# Only a failed attempt is retried: ``sent`` and ``simulated`` already left (or
# were deliberately not sent by the preview), and a pending row is picked up by
# the next pass on its own.
RETRYABLE_DELIVERY_STATUSES = ("failed",)
DEFAULT_GYM_NAME = "Centro Fit"
# The subject prefix and the closing line tell the reader which panel tab owns
# the notice; every kind the department mails has an entry here.
DEFAULT_SUBJECT_PREFIX = "[Asistencia] "
SUBJECT_PREFIXES = {
    "workout_pending_review": "[Rutinas] ",
    "maintenance_ticket_assigned": "[Mantenimiento] ",
    "kiosk_token_expiring": "[Kiosco] ",
    "member_push_failed": "[Avisos] ",
}
DEFAULT_NOTICE_LOCATION = "Puedes revisarlo en la pestaña Personal del panel del club."
NOTICE_LOCATIONS = {
    "workout_pending_review": "Puedes revisarlo en la pestaña Rutinas del panel del club.",
    "maintenance_ticket_assigned": "Puedes revisarlo en la pestaña Mantenimiento del panel del club.",
    "kiosk_token_expiring": "Puedes rotarlo en la página Kiosco del panel del club.",
    "member_push_failed": (
        "Puedes revisarlo en la tarjeta «Push del socio» de la pestaña Equipo "
        "del panel del club."
    ),
}
MAX_SUBJECT_CHARS = 180


class NotificationDeliveryError(Exception):
    pass


class NotificationDeliveryNotFound(NotificationDeliveryError):
    pass


class NotificationDeliveryRetryNotAllowed(NotificationDeliveryError):
    pass


class AttendanceEmailDisabled(NotificationDeliveryError):
    pass


@dataclass(frozen=True)
class AttendanceEmailPass:
    """What one send pass did to the queue."""

    enabled: bool
    attempted: int
    sent: int
    simulated: int
    failed: int
    remaining: int


@dataclass(frozen=True)
class StaffNotificationDeliveryItem:
    id: UUID
    notice_id: UUID
    kind: str
    title: str
    recipient: str
    status: str
    attempts: int
    error: str | None
    created_at: datetime
    last_attempt_at: datetime | None
    sent_at: datetime | None
    ack_status: str | None
    ack_at: datetime | None
    ack_detail: str | None


@dataclass(frozen=True)
class StaffNotificationDeliveryPage:
    items: list[StaffNotificationDeliveryItem]
    total: int
    page: int
    page_size: int
    pages: int


@dataclass(frozen=True)
class StaffNotificationDeliveryCounts:
    pending: int
    sent: int
    simulated: int
    failed: int


def email_message_for_notice(notice: StaffNotification) -> tuple[str, str]:
    """Subject and plain-text body of one staff notice.

    The body is the notice the panel already stores, plus where to look and a
    line that says the message is automatic. Nothing is recomputed from the
    domain: the email says exactly what the bell says.
    """

    gym_name = os.getenv("GYM_NAME", DEFAULT_GYM_NAME).strip() or DEFAULT_GYM_NAME
    prefix = SUBJECT_PREFIXES.get(notice.kind, DEFAULT_SUBJECT_PREFIX)
    subject = f"{prefix}{notice.title}".strip()
    if len(subject) > MAX_SUBJECT_CHARS:
        subject = f"{subject[: MAX_SUBJECT_CHARS - 1].rstrip()}…"
    location = NOTICE_LOCATIONS.get(notice.kind, DEFAULT_NOTICE_LOCATION)
    body = (
        f"Hola,\n\n{notice.body}\n\n"
        f"{location}\n\n"
        f"{gym_name} · Este correo se envió automáticamente.\n"
    )
    return subject, body


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _email_channel_enabled(session: Session) -> bool:
    """The club switch; late import because staffing imports this package."""

    from app.modules.staffing.service import read_attendance_email_enabled

    return read_attendance_email_enabled(session)


def _pending_count(session: Session) -> int:
    return int(
        session.exec(
            select(func.count(StaffNotificationDelivery.id)).where(
                StaffNotificationDelivery.status == "pending"
            )
        ).one()
        or 0
    )


def _claim(
    session: Session,
    delivery: StaffNotificationDelivery,
    *,
    from_status: str,
    now: datetime,
) -> bool:
    """Take exclusive ownership of one row before contacting SMTP.

    The attempt is counted and committed first, so a crash during the send
    still leaves a trace and never looks untouched. The compare-and-set on
    ``attempts`` makes a second concurrent pass lose the claim and skip the row
    instead of sending it twice.
    """

    result = session.exec(
        update(StaffNotificationDelivery)
        .where(
            StaffNotificationDelivery.id == delivery.id,
            StaffNotificationDelivery.status == from_status,
            StaffNotificationDelivery.attempts == delivery.attempts,
        )
        .values(
            attempts=StaffNotificationDelivery.attempts + 1,
            last_attempt_at=now,
        )
    )
    session.commit()
    if not result.rowcount:
        session.refresh(delivery)
        return False
    session.refresh(delivery)
    return True


def _deliver(session: Session, delivery: StaffNotificationDelivery, *, now: datetime) -> None:
    """Send one claimed delivery and record what the transport answered."""

    notice = session.get(StaffNotification, delivery.notice_id)
    if notice is None:
        # The foreign key makes this unreachable; if it ever happens the row
        # must not stay pending forever.
        delivery.status = "failed"
        delivery.error = "El aviso de la entrega ya no existe."
        session.add(delivery)
        session.commit()
        return
    subject, body = email_message_for_notice(notice)
    try:
        status = send_email(
            recipient=delivery.recipient,
            subject=subject,
            body=body,
            message_id=delivery.message_id,
            not_configured_message=(
                "El correo del personal no está configurado (SMTP_HOST)."
            ),
            failure_label="No se pudo enviar el aviso al personal",
        )
    except MailerError as error:
        delivery.status = "failed"
        delivery.error = str(error)[:500]
        session.add(delivery)
        session.commit()
        return
    except Exception as error:  # noqa: BLE001 - one bad message must not stop the pass
        delivery.status = "failed"
        delivery.error = (str(error).strip() or error.__class__.__name__)[:500]
        session.add(delivery)
        session.commit()
        return
    delivery.status = status
    delivery.error = None
    delivery.sent_at = now
    session.add(delivery)
    session.commit()


def send_pending_staff_notification_emails(
    session: Session,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> AttendanceEmailPass:
    """Send the oldest pending deliveries, at most ``limit`` per pass.

    The club switch is re-checked here, not only when the notice was written:
    turning the staff email off stops the queue instead of letting it drain.
    Rows skipped this way stay ``pending`` and go out on the next pass after
    the switch is turned back on.
    """

    occurred = _as_utc(now or utc_now())
    batch = max(1, min(limit, MAX_SEND_BATCH_LIMIT))
    if not _email_channel_enabled(session):
        return AttendanceEmailPass(
            enabled=False,
            attempted=0,
            sent=0,
            simulated=0,
            failed=0,
            remaining=_pending_count(session),
        )

    rows = list(
        session.exec(
            select(StaffNotificationDelivery)
            .where(StaffNotificationDelivery.status == "pending")
            .order_by(
                StaffNotificationDelivery.created_at,
                StaffNotificationDelivery.id,
            )
            .limit(batch)
        ).all()
    )
    sent = simulated = failed = attempted = 0
    for delivery in rows:
        if not _claim(session, delivery, from_status="pending", now=occurred):
            continue
        _deliver(session, delivery, now=occurred)
        attempted += 1
        if delivery.status == "sent":
            sent += 1
        elif delivery.status == "simulated":
            simulated += 1
        else:
            failed += 1
    return AttendanceEmailPass(
        enabled=True,
        attempted=attempted,
        sent=sent,
        simulated=simulated,
        failed=failed,
        remaining=_pending_count(session),
    )


def send_pending_staff_notification_emails_from_engine(
    engine: Engine,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> AttendanceEmailPass:
    """Run one pass in its own session, for the post-response hook."""

    with Session(engine) as session:
        return send_pending_staff_notification_emails(session, limit=limit, now=now)


def retry_staff_notification_delivery(
    session: Session,
    delivery_id: UUID,
    *,
    now: datetime | None = None,
) -> StaffNotificationDeliveryItem:
    """Attempt one failed delivery again, keeping its attempt history."""

    occurred = _as_utc(now or utc_now())
    delivery = session.get(StaffNotificationDelivery, delivery_id)
    if delivery is None:
        raise NotificationDeliveryNotFound("No se encontró la entrega del correo.")
    if delivery.status not in RETRYABLE_DELIVERY_STATUSES:
        raise NotificationDeliveryRetryNotAllowed(
            "Solo se puede reintentar una entrega que falló."
        )
    if not _email_channel_enabled(session):
        raise AttendanceEmailDisabled(
            "El correo del personal está apagado en la política del club."
        )
    if not _claim(session, delivery, from_status="failed", now=occurred):
        raise NotificationDeliveryRetryNotAllowed(
            "Otro intento tomó esta entrega; vuelve a consultar la cola."
        )
    _deliver(session, delivery, now=occurred)
    return _delivery_item(session, delivery)


def staff_notification_delivery_counts(session: Session) -> StaffNotificationDeliveryCounts:
    rows = session.exec(
        select(StaffNotificationDelivery.status, func.count())
        .group_by(StaffNotificationDelivery.status)
    ).all()
    by_status = {status: int(total) for status, total in rows}
    return StaffNotificationDeliveryCounts(
        pending=by_status.get("pending", 0),
        sent=by_status.get("sent", 0),
        simulated=by_status.get("simulated", 0),
        failed=by_status.get("failed", 0),
    )


def list_staff_notification_deliveries(
    session: Session,
    *,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_DELIVERY_PAGE_SIZE,
) -> StaffNotificationDeliveryPage:
    """Newest attempts first, optionally filtered by status."""

    if status_filter is not None and status_filter not in DELIVERY_STATUSES:
        raise NotificationDeliveryError("El estado de la entrega no es válido.")
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    condition = (
        StaffNotificationDelivery.status == status_filter
        if status_filter is not None
        else None
    )
    total_query = select(func.count(StaffNotificationDelivery.id))
    rows_query = select(StaffNotificationDelivery, StaffNotification).join(
        StaffNotification, StaffNotification.id == StaffNotificationDelivery.notice_id
    )
    if condition is not None:
        total_query = total_query.where(condition)
        rows_query = rows_query.where(condition)
    total = int(session.exec(total_query).one() or 0)
    rows = session.exec(
        rows_query.order_by(
            StaffNotificationDelivery.created_at.desc(),
            StaffNotificationDelivery.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    latest_receipts = _latest_receipts(
        session, [delivery.id for delivery, _ in rows]
    )
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return StaffNotificationDeliveryPage(
        items=[
            _delivery_item(
                session,
                delivery,
                notice=notice,
                receipt=latest_receipts.get(delivery.id),
            )
            for delivery, notice in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


def _latest_receipts(
    session: Session, delivery_ids: list[UUID]
) -> dict[UUID, StaffNotificationDeliveryReceipt]:
    """Newest acknowledgement per delivery, in one query for the whole page."""

    if not delivery_ids:
        return {}
    rows = session.exec(
        select(StaffNotificationDeliveryReceipt)
        .where(StaffNotificationDeliveryReceipt.delivery_id.in_(delivery_ids))
        .order_by(
            StaffNotificationDeliveryReceipt.received_at,
            StaffNotificationDeliveryReceipt.id,
        )
    ).all()
    return {receipt.delivery_id: receipt for receipt in rows}


def _delivery_item(
    session: Session,
    delivery: StaffNotificationDelivery,
    *,
    notice: StaffNotification | None = None,
    receipt: StaffNotificationDeliveryReceipt | None = None,
) -> StaffNotificationDeliveryItem:
    if notice is None:
        notice = session.get(StaffNotification, delivery.notice_id)
    if receipt is None:
        receipt = _latest_receipts(session, [delivery.id]).get(delivery.id)
    return StaffNotificationDeliveryItem(
        id=delivery.id,
        notice_id=delivery.notice_id,
        kind=notice.kind if notice is not None else "attendance_request_pending",
        title=notice.title if notice is not None else "Aviso de asistencia",
        recipient=delivery.recipient,
        status=delivery.status,
        attempts=delivery.attempts,
        error=delivery.error,
        created_at=_as_utc(delivery.created_at),
        last_attempt_at=(
            _as_utc(delivery.last_attempt_at)
            if delivery.last_attempt_at is not None
            else None
        ),
        sent_at=(
            _as_utc(delivery.sent_at) if delivery.sent_at is not None else None
        ),
        ack_status=receipt.event_type if receipt is not None else None,
        ack_at=(
            _as_utc(receipt.occurred_at) if receipt is not None else None
        ),
        ack_detail=receipt.detail if receipt is not None else None,
    )


__all__ = [
    "AttendanceEmailDisabled",
    "AttendanceEmailPass",
    "DEFAULT_SEND_BATCH_LIMIT",
    "DELIVERY_STATUSES",
    "NotificationDeliveryError",
    "NotificationDeliveryNotFound",
    "NotificationDeliveryRetryNotAllowed",
    "RETRYABLE_DELIVERY_STATUSES",
    "StaffNotificationDeliveryCounts",
    "StaffNotificationDeliveryItem",
    "StaffNotificationDeliveryPage",
    "email_message_for_notice",
    "list_staff_notification_deliveries",
    "retry_staff_notification_delivery",
    "send_pending_staff_notification_emails",
    "send_pending_staff_notification_emails_from_engine",
    "staff_notification_delivery_counts",
]
