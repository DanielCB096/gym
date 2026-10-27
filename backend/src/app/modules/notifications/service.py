"""Notification inbox service.

Two producers feed the inbox:

* domain events, raised by the routines and classes services inside the same
  transaction that changes the member's record. The message is written from the
  values the event already has in hand, so no extra query is needed and the
  notification can never disagree with the change that caused it;
* the membership window, which has no scheduler to wake it up. It is materialised
  lazily when the member opens the inbox and is deduplicated by
  ``membership_expiring:<membership>:<window>``, so the same reminder is written
  at most once per threshold (7, then 3, then 1 day left).

Members can only ever read and acknowledge their own rows; there is no update or
delete path, and no staff-facing audience yet (see ``docs/deuda-tecnica.md``).
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.memberships.models import Member, Membership
from app.modules.notifications.models import (
    MAX_BODY_CHARS,
    MAX_DEDUPE_CHARS,
    MAX_TITLE_CHARS,
    NOTIFICATION_KINDS,
    MemberNotification,
    utc_now,
)
from app.timezone import to_club_timezone

MEMBERSHIP_EXPIRY_WINDOWS = (7, 3, 1)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


class NotificationError(Exception):
    pass


class NotificationNotFound(NotificationError):
    pass


@dataclass(frozen=True)
class MemberNotificationItem:
    id: UUID
    kind: str
    title: str
    body: str
    ref_id: UUID | None
    created_at: datetime
    read_at: datetime | None


@dataclass(frozen=True)
class MemberNotificationPage:
    items: list[MemberNotificationItem]
    total: int
    page: int
    page_size: int
    pages: int
    unread_total: int


def create_notification(
    session: Session,
    *,
    member_id: UUID,
    kind: str,
    title: str,
    body: str,
    ref_id: UUID | None = None,
    dedupe_key: str | None = None,
    now: datetime | None = None,
) -> MemberNotification:
    """Append a message for a member.

    With a ``dedupe_key`` an existing message with the same key is returned
    untouched instead of being duplicated.
    """
    if kind not in NOTIFICATION_KINDS:
        raise NotificationError(f"El tipo de aviso '{kind}' no es válido")
    clean_title = title.strip()
    if not clean_title or len(clean_title) > MAX_TITLE_CHARS:
        raise NotificationError(f"El título debe tener entre 1 y {MAX_TITLE_CHARS} caracteres")
    clean_body = body.strip()
    if not clean_body or len(clean_body) > MAX_BODY_CHARS:
        raise NotificationError(f"El mensaje debe tener entre 1 y {MAX_BODY_CHARS} caracteres")
    if dedupe_key is not None:
        key = dedupe_key.strip()
        if len(key) > MAX_DEDUPE_CHARS:
            raise NotificationError("La clave de duplicidad es demasiado larga")
        if key:
            dedupe_key = key
        else:
            dedupe_key = None

    occurred = _as_utc(now or utc_now())
    if dedupe_key is not None:
        existing = session.exec(
            select(MemberNotification).where(MemberNotification.dedupe_key == dedupe_key)
        ).first()
        if existing is not None:
            return existing

    notification = MemberNotification(
        member_id=member_id,
        kind=kind,
        title=clean_title,
        body=clean_body,
        ref_id=ref_id,
        dedupe_key=dedupe_key,
        created_at=occurred,
    )
    session.add(notification)
    if dedupe_key is None:
        return notification
    # A deduplicated row can lose the race against an identical insert from another
    # connection; the savepoint keeps the caller's transaction usable either way.
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        winner = session.exec(
            select(MemberNotification).where(MemberNotification.dedupe_key == dedupe_key)
        ).first()
        if winner is None:
            raise
        return winner
    return notification


def notify_workout_reviewed(
    session: Session,
    *,
    member_id: UUID,
    workout_id: UUID,
    performed_on: date,
    routine_name: str | None,
    now: datetime | None = None,
) -> MemberNotification:
    label = (routine_name or "").strip()
    body = (
        f"Tu entrenador revisó la rutina {label} del {performed_on:%d/%m/%Y}."
        if label
        else f"Tu entrenador revisó tu entrenamiento del {performed_on:%d/%m/%Y}."
    )
    return create_notification(
        session,
        member_id=member_id,
        kind="workout_reviewed",
        title="Entrenamiento revisado",
        body=body,
        ref_id=workout_id,
        now=now,
    )


def notify_goal_achieved(
    session: Session,
    *,
    member_id: UUID,
    goal_id: UUID,
    metric_label: str,
    target_text: str,
    achieved_text: str,
    now: datetime | None = None,
) -> MemberNotification:
    return create_notification(
        session,
        member_id=member_id,
        kind="goal_achieved",
        title="¡Alcanzaste tu meta!",
        body=(
            f"Tu meta de {metric_label} quedó en {achieved_text} "
            f"y ya superó el objetivo de {target_text}. El personal puede verlo en tu ficha."
        ),
        ref_id=goal_id,
        now=now,
    )


def notify_goal_cancelled_by_staff(
    session: Session,
    *,
    member_id: UUID,
    goal_id: UUID,
    metric_label: str,
    now: datetime | None = None,
) -> MemberNotification:
    return create_notification(
        session,
        member_id=member_id,
        kind="goal_cancelled_by_staff",
        title="El personal canceló tu meta",
        body=(
            f"Recepción canceló tu meta de {metric_label}. "
            "Puedes crear una nueva desde la app cuando quieras."
        ),
        ref_id=goal_id,
        now=now,
    )


def notify_goal_updated_by_staff(
    session: Session,
    *,
    member_id: UUID,
    goal_id: UUID,
    metric_label: str,
    new_target_text: str | None,
    new_target_date: date | None,
    now: datetime | None = None,
) -> MemberNotification:
    changes = []
    if new_target_text:
        changes.append(f"el nuevo objetivo es {new_target_text}")
    if new_target_date is not None:
        changes.append(f"la fecha límite quedó el {new_target_date:%d/%m/%Y}")
    tail = f"; {' y '.join(changes)}." if changes else "."
    return create_notification(
        session,
        member_id=member_id,
        kind="goal_updated_by_staff",
        title="El personal ajustó tu meta",
        body=f"Se actualizó tu meta de {metric_label} desde recepción{tail}",
        ref_id=goal_id,
        now=now,
    )


def notify_waitlist_promoted(
    session: Session,
    *,
    member_id: UUID,
    reservation_id: UUID,
    class_title: str,
    starts_at: datetime,
    now: datetime | None = None,
) -> MemberNotification:
    local = to_club_timezone(starts_at)
    return create_notification(
        session,
        member_id=member_id,
        kind="class_waitlist_promoted",
        title="Tienes lugar en la clase",
        body=(
            f"Se liberó un cupo y tu lugar en la lista de espera de {class_title} "
            f"quedó confirmado para el {local:%d/%m/%Y} a las {local:%H:%M}."
        ),
        ref_id=reservation_id,
        now=now,
    )


def list_member_notifications(
    session: Session,
    member_id: UUID,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: datetime | None = None,
) -> MemberNotificationPage:
    member = session.get(Member, member_id)
    if member is None:
        raise NotificationError("El socio no existe")
    _ensure_membership_expiring(session, member_id, now=now)

    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)

    total = int(
        session.exec(
            select(func.count(MemberNotification.id)).where(
                MemberNotification.member_id == member_id
            )
        ).one()
        or 0
    )
    unread_total = int(
        session.exec(
            select(func.count(MemberNotification.id)).where(
                MemberNotification.member_id == member_id,
                MemberNotification.read_at.is_(None),
            )
        ).one()
        or 0
    )
    rows = session.exec(
        select(MemberNotification)
        .where(MemberNotification.member_id == member_id)
        .order_by(MemberNotification.created_at.desc(), MemberNotification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return MemberNotificationPage(
        items=[_notification_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        unread_total=unread_total,
    )


def unread_notification_count(session: Session, member_id: UUID) -> int:
    return int(
        session.exec(
            select(func.count(MemberNotification.id)).where(
                MemberNotification.member_id == member_id,
                MemberNotification.read_at.is_(None),
            )
        ).one()
        or 0
    )


def mark_notification_read(
    session: Session,
    member_id: UUID,
    notification_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberNotificationItem:
    occurred = _as_utc(now or utc_now())
    row = session.get(MemberNotification, notification_id)
    if row is None or row.member_id != member_id:
        raise NotificationNotFound("El aviso no existe")
    if row.read_at is None:
        row.read_at = occurred
        session.add(row)
        session.commit()
        session.refresh(row)
    return _notification_item(row)


def mark_all_notifications_read(
    session: Session,
    member_id: UUID,
    *,
    now: datetime | None = None,
) -> int:
    occurred = _as_utc(now or utc_now())
    result = session.exec(
        update(MemberNotification)
        .where(
            MemberNotification.member_id == member_id,
            MemberNotification.read_at.is_(None),
        )
        .values(read_at=occurred)
    )
    session.commit()
    return int(result.rowcount or 0)


def _ensure_membership_expiring(
    session: Session, member_id: UUID, *, now: datetime | None = None
) -> None:
    """Write the expiring-membership reminder the member is currently inside.

    There is no scheduler in this project, so the reminder is materialised when
    the inbox is read. The dedupe key is the window (7, 3 or 1 day) rather than
    the exact day count, which is what keeps one reminder per threshold instead
    of one per day.
    """
    occurred = _as_utc(now or utc_now())
    row = session.exec(
        select(Membership)
        .where(
            Membership.member_id == member_id,
            Membership.status == "active",
            Membership.ends_at > occurred,
        )
        .order_by(Membership.ends_at.asc())
    ).first()
    if row is None:
        return
    ends_at = _as_utc(row.ends_at)
    days_remaining = math.ceil((ends_at - occurred).total_seconds() / 86400)
    window = next((limit for limit in MEMBERSHIP_EXPIRY_WINDOWS if days_remaining <= limit), None)
    if window is None:
        return
    ends_local = to_club_timezone(ends_at)
    body = (
        f"Tu membresía vence el {ends_local:%d/%m/%Y} (faltan {days_remaining} "
        f"{'día' if days_remaining == 1 else 'días'}). "
        "Renóvala en recepción para no perder el acceso."
    )
    create_notification(
        session,
        member_id=member_id,
        kind="membership_expiring",
        title="Tu membresía está por vencer",
        body=body,
        ref_id=row.id,
        dedupe_key=f"membership_expiring:{row.id}:{window}",
        now=occurred,
    )
    session.commit()


def _notification_item(row: MemberNotification) -> MemberNotificationItem:
    return MemberNotificationItem(
        id=row.id,
        kind=row.kind,
        title=row.title,
        body=row.body,
        ref_id=row.ref_id,
        created_at=_as_utc(row.created_at),
        read_at=_as_utc(row.read_at) if row.read_at is not None else None,
    )


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment
