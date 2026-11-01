"""Queue and deliver consented email copies of member notifications."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os

from sqlalchemy import and_, func, or_, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.mailer import MailerError, send_email
from app.modules.memberships.models import Member
from app.modules.notifications.delivery import (
    DEFAULT_GYM_NAME,
    MAX_SUBJECT_CHARS,
    new_message_id,
)
from app.modules.notifications.models import (
    MemberNotification,
    MemberNotificationEmailDelivery,
    utc_now,
)
from app.modules.notifications.preferences import is_email_enabled

DEFAULT_SEND_BATCH_LIMIT = 20
MAX_SEND_BATCH_LIMIT = 100
MAX_ATTEMPTS = 5
RETRY_DELAYS_MINUTES = (5, 15, 60, 360)



@dataclass(frozen=True)
class MemberEmailPass:
    attempted: int
    sent: int
    simulated: int
    failed: int
    cancelled: int
    remaining: int


def enqueue_member_notification_email(
    session: Session, notice: MemberNotification
) -> MemberNotificationEmailDelivery | None:
    """Write one delivery with the notice only when the member opted in."""

    if not is_email_enabled(session, notice.member_id, notice.kind):
        return None
    member = session.get(Member, notice.member_id)
    recipient = (member.email or "").strip() if member is not None else ""
    if not recipient:
        return None
    delivery = MemberNotificationEmailDelivery(
        notification_id=notice.id,
        member_id=notice.member_id,
        recipient=recipient,
        message_id=new_message_id(),
    )
    session.add(delivery)
    return delivery


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _eligible_delivery(delivery: MemberNotificationEmailDelivery, now: datetime) -> bool:
    return delivery.status == "pending" or (
        delivery.status == "failed"
        and delivery.next_attempt_at is not None
        and _as_utc(delivery.next_attempt_at) <= now
    )


def _remaining_count(session: Session) -> int:
    return int(
        session.exec(
            select(func.count(MemberNotificationEmailDelivery.id)).where(
                or_(
                    MemberNotificationEmailDelivery.status == "pending",
                    and_(
                        MemberNotificationEmailDelivery.status == "failed",
                        MemberNotificationEmailDelivery.next_attempt_at.is_not(None),
                    ),
                )
            )
        ).one()
        or 0
    )


def _claim(
    session: Session,
    delivery: MemberNotificationEmailDelivery,
    *,
    now: datetime,
) -> bool:
    eligible = or_(
        MemberNotificationEmailDelivery.status == "pending",
        and_(
            MemberNotificationEmailDelivery.status == "failed",
            MemberNotificationEmailDelivery.next_attempt_at <= now,
        ),
    )
    result = session.exec(
        update(MemberNotificationEmailDelivery)
        .execution_options(synchronize_session=False)
        .where(
            MemberNotificationEmailDelivery.id == delivery.id,
            MemberNotificationEmailDelivery.attempts == delivery.attempts,
            eligible,
        )
        .values(
            attempts=MemberNotificationEmailDelivery.attempts + 1,
            last_attempt_at=now,
            next_attempt_at=None,
        )
    )
    session.commit()
    if not result.rowcount:
        session.refresh(delivery)
        return False
    session.refresh(delivery)
    return True


def _cancel(
    session: Session,
    delivery: MemberNotificationEmailDelivery,
    reason: str,
) -> None:
    delivery.status = "cancelled"
    delivery.error = reason[:500]
    delivery.next_attempt_at = None
    session.add(delivery)
    session.commit()


def _message_for_notice(notice: MemberNotification) -> tuple[str, str]:
    gym_name = os.getenv("GYM_NAME", DEFAULT_GYM_NAME).strip() or DEFAULT_GYM_NAME
    subject = f"{gym_name} · {notice.title}".strip()
    if len(subject) > MAX_SUBJECT_CHARS:
        subject = f"{subject[: MAX_SUBJECT_CHARS - 1].rstrip()}…"
    body = (
        f"Hola,\n\n{notice.body}\n\n"
        "Este aviso también está disponible en la bandeja de tu app.\n\n"
        f"{gym_name} · Este correo se envió automáticamente.\n"
    )
    return subject, body


def _retry_at(now: datetime, attempts: int) -> datetime | None:
    if attempts >= MAX_ATTEMPTS:
        return None
    delay = RETRY_DELAYS_MINUTES[min(attempts - 1, len(RETRY_DELAYS_MINUTES) - 1)]
    return now + timedelta(minutes=delay)


def _deliver(
    session: Session,
    delivery: MemberNotificationEmailDelivery,
    *,
    now: datetime,
) -> str:
    notice = session.get(MemberNotification, delivery.notification_id)
    member = session.get(Member, delivery.member_id)
    if notice is None or member is None:
        _cancel(session, delivery, "El socio o el aviso ya no existe.")
        return "cancelled"
    if not is_email_enabled(session, delivery.member_id, notice.kind):
        _cancel(session, delivery, "El socio desactivó los avisos por correo.")
        return "cancelled"
    current_email = (member.email or "").strip()
    if not current_email or current_email.casefold() != delivery.recipient.casefold():
        _cancel(session, delivery, "El correo del socio cambió antes del envío.")
        return "cancelled"

    subject, body = _message_for_notice(notice)
    try:
        outcome = send_email(
            recipient=delivery.recipient,
            subject=subject,
            body=body,
            message_id=delivery.message_id,
            not_configured_message=(
                "El correo de avisos del socio no está configurado (SMTP_HOST)."
            ),
            failure_label="No se pudo enviar el aviso al socio",
        )
    except MailerError as error:
        delivery.status = "failed"
        delivery.error = str(error)[:500]
        delivery.next_attempt_at = _retry_at(now, delivery.attempts)
        session.add(delivery)
        session.commit()
        return "failed"

    delivery.status = outcome
    delivery.error = None
    delivery.next_attempt_at = None
    delivery.sent_at = now if outcome == "sent" else None
    session.add(delivery)
    session.commit()
    return outcome


def send_pending_member_notification_emails(
    session: Session,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> MemberEmailPass:
    """Send queued messages and due retries, each claimed before SMTP."""

    if limit < 1 or limit > MAX_SEND_BATCH_LIMIT:
        raise ValueError(f"limit debe estar entre 1 y {MAX_SEND_BATCH_LIMIT}.")
    occurred = _as_utc(now or utc_now())
    eligible = or_(
        MemberNotificationEmailDelivery.status == "pending",
        and_(
            MemberNotificationEmailDelivery.status == "failed",
            MemberNotificationEmailDelivery.next_attempt_at <= occurred,
        ),
    )
    deliveries = session.exec(
        select(MemberNotificationEmailDelivery)
        .where(eligible)
        .order_by(
            MemberNotificationEmailDelivery.created_at,
            MemberNotificationEmailDelivery.id,
        )
        .limit(limit)
    ).all()
    sent = simulated = failed = cancelled = attempted = 0
    for delivery in deliveries:
        if not _eligible_delivery(delivery, occurred):
            continue
        if not _claim(session, delivery, now=occurred):
            continue
        attempted += 1
        outcome = _deliver(session, delivery, now=occurred)
        if outcome == "sent":
            sent += 1
        elif outcome == "simulated":
            simulated += 1
        elif outcome == "cancelled":
            cancelled += 1
        else:
            failed += 1
    return MemberEmailPass(
        attempted=attempted,
        sent=sent,
        simulated=simulated,
        failed=failed,
        cancelled=cancelled,
        remaining=_remaining_count(session),
    )


def send_pending_member_notification_emails_from_engine(
    engine: Engine,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> MemberEmailPass:
    """Run one pass in its own session for request hooks and cron."""

    with Session(engine) as session:
        return send_pending_member_notification_emails(session, limit=limit, now=now)


__all__ = [
    "DEFAULT_SEND_BATCH_LIMIT",
    "MAX_ATTEMPTS",
    "MAX_SEND_BATCH_LIMIT",
    "MemberEmailPass",
    "RETRY_DELAYS_MINUTES",
    "enqueue_member_notification_email",
    "send_pending_member_notification_emails",
    "send_pending_member_notification_emails_from_engine",
]
