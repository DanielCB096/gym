"""Notification inbox service.

Three producers feed the two inboxes:

* domain events for the member, raised by the routines, classes and maintenance
  services inside the same transaction that changes the member's record. The
  message is written from the values the event already has in hand, so no extra
  query is needed and the notification can never disagree with the change that
  caused it. The one exception is the equipment outage, whose audience is a set
  of members nobody has in hand: the caller looks it up and passes it in, because
  finding it means joining tables this module must not know about;
* domain events for the staff, raised by the routines and maintenance services
  when something a member does in the app or a dispatcher does at the desk turns
  into work for a named person. The audience is a panel account, so the employee
  behind the assignment or the ticket is resolved to its ``app_users`` row here
  and the notice is simply skipped when that employee has no active account;
* the time-based reminders —a membership about to expire, a class about to
  start— which have no scheduler to wake them up. They are materialised lazily
  when the member reads the inbox or the unread counter and are deduplicated by
  a key that names the threshold, so the same reminder is written at most once
  per window (7, then 3, then 1 day left; 24 then 2 hours before the class).

Readers can only ever see and acknowledge their own rows; there is no update or
delete path on either inbox. The one exception happens outside the reader: the
service that completes the work a staff notice announced closes it with
``resolved_at``, so the inbox stops reporting a pending item the panel handled.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Sequence, TypeVar
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.identity.models import AppUser
from app.modules.memberships.models import Member, Membership
from app.modules.notifications.models import (
    MAX_BODY_CHARS,
    MAX_DEDUPE_CHARS,
    MAX_TITLE_CHARS,
    NOTIFICATION_KINDS,
    STAFF_NOTIFICATION_KINDS,
    MemberNotification,
    StaffNotification,
    utc_now,
)
from app.timezone import to_club_timezone

MEMBERSHIP_EXPIRY_WINDOWS = (7, 3, 1)
# Ascending order: each read picks the tightest window the class is already
# inside, so opening the inbox twice within the same window writes one row.
CLASS_REMINDER_WINDOWS_HOURS = (2, 24)
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


@dataclass(frozen=True)
class StaffNotificationItem:
    id: UUID
    kind: str
    title: str
    body: str
    ref_id: UUID | None
    created_at: datetime
    read_at: datetime | None
    resolved_at: datetime | None


@dataclass(frozen=True)
class StaffNotificationPage:
    items: list[StaffNotificationItem]
    total: int
    page: int
    page_size: int
    pages: int
    unread_total: int


NotificationRow = TypeVar("NotificationRow", MemberNotification, StaffNotification)


def _validated_message(
    kind: str, title: str, body: str, allowed_kinds: tuple[str, ...]
) -> tuple[str, str]:
    if kind not in allowed_kinds:
        raise NotificationError(f"El tipo de aviso '{kind}' no es válido")
    clean_title = title.strip()
    if not clean_title or len(clean_title) > MAX_TITLE_CHARS:
        raise NotificationError(f"El título debe tener entre 1 y {MAX_TITLE_CHARS} caracteres")
    clean_body = body.strip()
    if not clean_body or len(clean_body) > MAX_BODY_CHARS:
        raise NotificationError(f"El mensaje debe tener entre 1 y {MAX_BODY_CHARS} caracteres")
    return clean_title, clean_body


def _clean_dedupe_key(dedupe_key: str | None) -> str | None:
    if dedupe_key is None:
        return None
    key = dedupe_key.strip()
    if len(key) > MAX_DEDUPE_CHARS:
        raise NotificationError("La clave de duplicidad es demasiado larga")
    return key or None


def _append(
    session: Session, notification: NotificationRow, model: type[NotificationRow]
) -> NotificationRow:
    """Insert a row, honouring the dedupe key if it carries one.

    With a ``dedupe_key`` an existing message with the same key is returned
    untouched instead of being duplicated. A deduplicated row can lose the race
    against an identical insert from another connection; the savepoint keeps the
    caller's transaction usable either way.
    """
    dedupe_key = notification.dedupe_key
    if dedupe_key is None:
        session.add(notification)
        return notification
    existing = session.exec(select(model).where(model.dedupe_key == dedupe_key)).first()
    if existing is not None:
        return existing
    # The caller's pending changes are written *before* the savepoint so a
    # collision rolls back this row alone and never the domain change the
    # emitters sit next to.
    session.flush()
    session.add(notification)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        session.expunge(notification)
        winner = session.exec(select(model).where(model.dedupe_key == dedupe_key)).first()
        if winner is None:
            raise
        return winner
    return notification


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
    """Append a message for a member."""
    clean_title, clean_body = _validated_message(kind, title, body, NOTIFICATION_KINDS)
    return _append(
        session,
        MemberNotification(
            member_id=member_id,
            kind=kind,
            title=clean_title,
            body=clean_body,
            ref_id=ref_id,
            dedupe_key=_clean_dedupe_key(dedupe_key),
            created_at=_as_utc(now or utc_now()),
        ),
        MemberNotification,
    )


def create_staff_notification(
    session: Session,
    *,
    user_id: UUID,
    kind: str,
    title: str,
    body: str,
    ref_id: UUID | None = None,
    dedupe_key: str | None = None,
    now: datetime | None = None,
) -> StaffNotification:
    """Append a message for a panel account."""
    clean_title, clean_body = _validated_message(kind, title, body, STAFF_NOTIFICATION_KINDS)
    return _append(
        session,
        StaffNotification(
            user_id=user_id,
            kind=kind,
            title=clean_title,
            body=clean_body,
            ref_id=ref_id,
            dedupe_key=_clean_dedupe_key(dedupe_key),
            created_at=_as_utc(now or utc_now()),
        ),
        StaffNotification,
    )


def staff_user_for_employee(session: Session, employee_id: UUID | None) -> UUID | None:
    """The panel account that should receive a notice for this employee.

    A notice addressed to an employee with no account, or whose account was
    disabled, has nowhere to land: the caller is expected to skip it rather than
    to guess another recipient.
    """
    if employee_id is None:
        return None
    user = session.exec(
        select(AppUser).where(AppUser.employee_id == employee_id, AppUser.status == "active")
    ).first()
    return None if user is None else user.id


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


def notify_class_reserved(
    session: Session,
    *,
    member_id: UUID,
    reservation_id: UUID,
    class_title: str,
    starts_at: datetime,
    booked_by_staff: bool = False,
    now: datetime | None = None,
) -> MemberNotification:
    """Confirm a seat the member now holds.

    Written for both doors: the member who books in the app sees the screen, but
    the inbox is the only record that survives it, and a seat booked at the
    counter would otherwise never be announced. The body says who booked so the
    member is not surprised by a reservation they did not make.
    """
    local = to_club_timezone(starts_at)
    lead = (
        "Recepción reservó tu lugar en"
        if booked_by_staff
        else "Ya tienes tu lugar reservado en"
    )
    return create_notification(
        session,
        member_id=member_id,
        kind="class_reserved",
        title="Tu lugar en la clase está confirmado",
        body=(
            f"{lead} {class_title} del {local:%d/%m/%Y} a las {local:%H:%M}. "
            "Llega unos minutos antes."
        ),
        ref_id=reservation_id,
        now=now,
    )


def notify_class_cancelled(
    session: Session,
    *,
    member_id: UUID,
    class_session_id: UUID,
    class_title: str,
    starts_at: datetime,
    now: datetime | None = None,
) -> MemberNotification:
    """Tell everyone who still had a live reservation that the class is off.

    Both the seated and the waitlisted are told: a queue waiting for a class
    that no longer exists would keep checking for a seat that will never open.
    The key is per class and member so a retried cancellation cannot duplicate
    the notice.
    """
    local = to_club_timezone(starts_at)
    return create_notification(
        session,
        member_id=member_id,
        kind="class_cancelled",
        title="Se canceló tu clase",
        body=(
            f"La clase {class_title} del {local:%d/%m/%Y} a las {local:%H:%M} "
            "fue cancelada por el gimnasio. Ya no necesitas presentarte."
        ),
        ref_id=class_session_id,
        dedupe_key=f"class_cancelled:{class_session_id}:{member_id}",
        now=now,
    )


def notify_class_rescheduled(
    session: Session,
    *,
    member_id: UUID,
    class_session_id: UUID,
    class_title: str,
    old_starts_at: datetime,
    old_ends_at: datetime,
    starts_at: datetime,
    ends_at: datetime,
    now: datetime | None = None,
) -> MemberNotification:
    """Announce a moved class with both the old and the new slot.

    The member should not have to remember where the class used to be; the body
    carries the previous window so the change reads as a change. The key names
    the moment of the move, so moving the class back and forth announces every
    move instead of being silenced by an earlier notice with the same target.
    """
    occurred = now or utc_now()
    old_start = to_club_timezone(old_starts_at)
    old_end = to_club_timezone(old_ends_at)
    new_start = to_club_timezone(starts_at)
    new_end = to_club_timezone(ends_at)
    return create_notification(
        session,
        member_id=member_id,
        kind="class_rescheduled",
        title="Cambió el horario de tu clase",
        body=(
            f"La clase {class_title} cambió de horario: era el "
            f"{old_start:%d/%m/%Y} de {old_start:%H:%M} a {old_end:%H:%M} y ahora es el "
            f"{new_start:%d/%m/%Y} de {new_start:%H:%M} a {new_end:%H:%M}. "
            "Tu reserva sigue en pie."
        ),
        ref_id=class_session_id,
        dedupe_key=(
            f"class_rescheduled:{class_session_id}:{member_id}:"
            f"{occurred:%Y%m%dT%H%M%S%f}"
        ),
        now=occurred,
    )


def notify_equipment_out_of_service(
    session: Session,
    *,
    equipment_id: UUID,
    equipment_name: str,
    location: str | None,
    member_ids: Sequence[UUID],
    occurred_on: date,
    now: datetime | None = None,
) -> int:
    """Tell every member whose plan uses a machine that just stopped working.

    The audience is handed in because finding it means joining the routine
    tables, which live in another module; this function only writes the
    messages. One row per member, deduplicated by equipment, member and club
    day, so a unit pushed back into ``out_of_service`` the same day does not
    repeat itself while a new outage on a later day does.
    """
    label = _clip(equipment_name.strip() or "Un equipo", 80)
    where = f" de {_clip(location.strip(), 40)}" if location and location.strip() else ""
    body = (
        f"El equipo {label}{where} quedó fuera de servicio el {occurred_on:%d/%m/%Y}. "
        "Si tu rutina usa un ejercicio con este equipo, pídele a tu entrenador "
        "que lo sustituya."
    )
    for member_id in member_ids:
        create_notification(
            session,
            member_id=member_id,
            kind="equipment_out_of_service",
            title="Un equipo está fuera de servicio",
            body=body,
            ref_id=equipment_id,
            dedupe_key=(
                f"equipment_out_of_service:{equipment_id}:{member_id}:{occurred_on:%Y%m%d}"
            ),
            now=now,
        )
    return len(member_ids)


def notify_invoice_stamped(
    session: Session,
    *,
    member_id: UUID,
    invoice_id: UUID,
    folio_label: str,
    total_cents: int,
    simulated: bool,
    now: datetime | None = None,
) -> MemberNotification:
    suffix = (
        " Es un comprobante de prueba sin validez fiscal."
        if simulated
        else ""
    )
    return create_notification(
        session,
        member_id=member_id,
        kind="invoice_stamped",
        title="Factura timbrada",
        body=(
            f"Tu factura {folio_label} por {_money_label(total_cents)} ya está lista. "
            f"Descarga el PDF o el XML desde Facturas.{suffix}"
        ),
        ref_id=invoice_id,
        dedupe_key=f"invoice_stamped:{invoice_id}",
        now=now,
    )


def notify_invoice_failed(
    session: Session,
    *,
    member_id: UUID,
    invoice_id: UUID,
    folio_label: str,
    total_cents: int,
    now: datetime | None = None,
) -> MemberNotification:
    return create_notification(
        session,
        member_id=member_id,
        kind="invoice_failed",
        title="No pudimos timbrar tu factura",
        body=(
            f"La factura {folio_label} por {_money_label(total_cents)} no se pudo "
            "timbrar. Revisa tus datos fiscales en Facturas o acércate a recepción."
        ),
        ref_id=invoice_id,
        dedupe_key=f"invoice_failed:{invoice_id}",
        now=now,
    )


def notify_invoice_cancelled(
    session: Session,
    *,
    member_id: UUID,
    invoice_id: UUID,
    folio_label: str,
    total_cents: int,
    now: datetime | None = None,
) -> MemberNotification:
    return create_notification(
        session,
        member_id=member_id,
        kind="invoice_cancelled",
        title="Factura cancelada",
        body=(
            f"La factura {folio_label} por {_money_label(total_cents)} fue cancelada. "
            "Si tienes dudas, acércate a recepción."
        ),
        ref_id=invoice_id,
        dedupe_key=f"invoice_cancelled:{invoice_id}",
        now=now,
    )


def notify_trainer_pending_workout(
    session: Session,
    *,
    trainer_employee_id: UUID | None,
    member_label: str,
    workout_id: UUID,
    performed_on: date,
    routine_name: str | None,
    now: datetime | None = None,
) -> StaffNotification | None:
    """Tell the trainer that a member logged a workout waiting to be reviewed.

    Returns ``None`` when the assignment has no trainer or that trainer has no
    active panel account: the workout is still logged, only the notice is lost.
    """
    user_id = staff_user_for_employee(session, trainer_employee_id)
    if user_id is None:
        return None
    label = _clip(routine_name or "", 60)
    who = _clip(member_label, 60) or "Un socio"
    head = (
        f"{who} registró la rutina {label} del {performed_on:%d/%m/%Y}"
        if label
        else f"{who} registró su entrenamiento del {performed_on:%d/%m/%Y}"
    )
    return create_staff_notification(
        session,
        user_id=user_id,
        kind="workout_pending_review",
        title="Entrenamiento pendiente de revisión",
        body=f"{head} desde la app. Queda pendiente de tu revisión.",
        ref_id=workout_id,
        now=now,
    )


def notify_technician_ticket_assigned(
    session: Session,
    *,
    technician_employee_id: UUID | None,
    ticket_id: UUID,
    ticket_code: str,
    equipment_name: str,
    ticket_title: str,
    now: datetime | None = None,
) -> StaffNotification | None:
    """Tell a technician that a maintenance ticket is now theirs.

    The dedupe key ties the notice to the ticket *and* the technician, so
    re-saving the same assignee through a PATCH does not spam the inbox; the
    trade-off is that reassigning a ticket back to the same person after handing
    it to someone else is not announced a second time.
    """
    user_id = staff_user_for_employee(session, technician_employee_id)
    if user_id is None:
        return None
    return create_staff_notification(
        session,
        user_id=user_id,
        kind="maintenance_ticket_assigned",
        title="Se te asignó un ticket",
        body=(
            f"El ticket {_clip(ticket_code, 20)} de {_clip(equipment_name, 60)} te fue asignado: "
            f"{_clip(ticket_title, 160)}. Atiéndelo desde la vista de Mantenimiento."
        ),
        ref_id=ticket_id,
        dedupe_key=f"maintenance_ticket_assigned:{ticket_id}:{technician_employee_id}",
        now=now,
    )


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    return max(page, 1), min(max(page_size, 1), MAX_PAGE_SIZE)


def _paginate_inbox(
    session: Session,
    model: type[NotificationRow],
    owner_column,
    owner_id: UUID,
    *,
    page: int,
    page_size: int,
    unread_predicates: tuple = (),
) -> tuple[int, int, list[NotificationRow], int, int, int]:
    """Count, unread-count and page one inbox.

    Both inboxes have the same shape once the owner column is given, so the
    paging rules stay in a single place and cannot drift apart. The staff inbox
    passes the extra condition that a resolved notice no longer counts as
    unread, because the badge is about work still owed.
    """
    page, page_size = _clamp_page(page, page_size)
    total = int(
        session.exec(select(func.count(model.id)).where(owner_column == owner_id)).one() or 0
    )
    unread_total = int(
        session.exec(
            select(func.count(model.id)).where(
                owner_column == owner_id,
                model.read_at.is_(None),
                *unread_predicates,
            )
        ).one()
        or 0
    )
    rows = list(
        session.exec(
            select(model)
            .where(owner_column == owner_id)
            .order_by(model.created_at.desc(), model.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return page, page_size, rows, total, pages, unread_total


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
    _materialise_deferred(session, member_id, now=now)

    page, page_size, rows, total, pages, unread_total = _paginate_inbox(
        session,
        MemberNotification,
        MemberNotification.member_id,
        member_id,
        page=page,
        page_size=page_size,
    )
    return MemberNotificationPage(
        items=[_notification_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        unread_total=unread_total,
    )


def unread_notification_count(
    session: Session, member_id: UUID, *, now: datetime | None = None
) -> int:
    """Unread rows for the badge.

    The deferred reminders are materialised here too: the badge is what makes
    the member open the inbox, so a reminder that only appeared after opening
    it would never be announced.
    """
    _materialise_deferred(session, member_id, now=now)
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


def list_staff_notifications(
    session: Session,
    user_id: UUID,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> StaffNotificationPage:
    page, page_size, rows, total, pages, unread_total = _paginate_inbox(
        session,
        StaffNotification,
        StaffNotification.user_id,
        user_id,
        page=page,
        page_size=page_size,
        unread_predicates=(StaffNotification.resolved_at.is_(None),),
    )
    return StaffNotificationPage(
        items=[_staff_notification_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        unread_total=unread_total,
    )


def unread_staff_notification_count(session: Session, user_id: UUID) -> int:
    """Unread notices still owed to the account.

    A resolved notice is gone from the badge even if the reader never opened it:
    the badge answers "what is left for me to do", and the service that closed
    the notice already did it.
    """
    return int(
        session.exec(
            select(func.count(StaffNotification.id)).where(
                StaffNotification.user_id == user_id,
                StaffNotification.read_at.is_(None),
                StaffNotification.resolved_at.is_(None),
            )
        ).one()
        or 0
    )


def mark_staff_notification_read(
    session: Session,
    user_id: UUID,
    notification_id: UUID,
    *,
    now: datetime | None = None,
) -> StaffNotificationItem:
    occurred = _as_utc(now or utc_now())
    row = session.get(StaffNotification, notification_id)
    if row is None or row.user_id != user_id:
        raise NotificationNotFound("El aviso no existe")
    if row.read_at is None:
        row.read_at = occurred
        session.add(row)
        session.commit()
        session.refresh(row)
    return _staff_notification_item(row)


def mark_all_staff_notifications_read(
    session: Session,
    user_id: UUID,
    *,
    now: datetime | None = None,
) -> int:
    occurred = _as_utc(now or utc_now())
    result = session.exec(
        update(StaffNotification)
        .where(
            StaffNotification.user_id == user_id,
            StaffNotification.read_at.is_(None),
        )
        .values(read_at=occurred)
    )
    session.commit()
    return int(result.rowcount or 0)


def resolve_staff_notifications(
    session: Session,
    *,
    kind: str,
    ref_id: UUID,
    now: datetime | None = None,
) -> int:
    """Close the notices a completed piece of work made obsolete.

    The caller is the service that finished the work —reviewing a workout— and
    it is already inside its own transaction, so this neither commits nor opens
    a savepoint: the resolution lands together with the change that justifies
    it or not at all. Every account that received the notice is closed, since
    the audience is resolved from who owns the work at emission time.

    Closing also marks the notice as read when nobody had opened it, so the
    list does not show a "new" dot next to an item that is already attended.
    """
    occurred = _as_utc(now or utc_now())
    rows = list(
        session.exec(
            select(StaffNotification).where(
                StaffNotification.kind == kind,
                StaffNotification.ref_id == ref_id,
                StaffNotification.resolved_at.is_(None),
            )
        ).all()
    )
    for row in rows:
        row.resolved_at = occurred
        if row.read_at is None:
            row.read_at = occurred
        session.add(row)
    return len(rows)


def _materialise_deferred(
    session: Session, member_id: UUID, *, now: datetime | None = None
) -> None:
    """Write every reminder that only exists because someone is looking.

    There is no scheduler, so the two time-based notices are produced by the
    read path instead of a worker. Each producer deduplicates itself, which
    makes this safe to call on every read of the inbox and of the badge.
    """
    occurred = _as_utc(now or utc_now())
    _ensure_membership_expiring(session, member_id, now=occurred)
    _ensure_class_reminders(session, member_id, now=occurred)


def _ensure_class_reminders(
    session: Session, member_id: UUID, *, now: datetime | None = None
) -> None:
    """Write the reminder of every class the member is about to attend.

    The window is part of the dedupe key, so a member who opens the app the day
    before and again shortly before the class gets one reminder per threshold,
    while opening it twice inside the same window changes nothing. A cancelled
    reservation stops matching the query, and the reminder it already received
    stays in the inbox as history.
    """
    # Imported here because the classes service imports this module for the
    # waitlist notice; a top-level import would close the cycle at startup.
    from app.modules.classes.models import ClassReservation, ClassSession

    occurred = _as_utc(now or utc_now())
    horizon = occurred + timedelta(hours=max(CLASS_REMINDER_WINDOWS_HOURS))
    rows = session.exec(
        select(ClassReservation, ClassSession)
        .join(ClassSession, ClassSession.id == ClassReservation.session_id)
        .where(
            ClassReservation.member_id == member_id,
            ClassReservation.status == "reserved",
            ClassSession.status == "scheduled",
            ClassSession.starts_at > occurred,
            ClassSession.starts_at <= horizon,
        )
        .order_by(ClassSession.starts_at)
    ).all()
    if not rows:
        return
    for reservation, class_session in rows:
        starts_at = _as_utc(class_session.starts_at)
        hours_left = (starts_at - occurred).total_seconds() / 3600
        window = next(
            (limit for limit in CLASS_REMINDER_WINDOWS_HOURS if hours_left <= limit),
            None,
        )
        if window is None:
            continue
        local = to_club_timezone(starts_at)
        create_notification(
            session,
            member_id=member_id,
            kind="class_reminder",
            title="Tu clase empieza pronto",
            body=(
                f"Tu clase {_clip(class_session.title, 80)} del {local:%d/%m/%Y} "
                f"a las {local:%H:%M} empieza en menos de {window} horas. "
                "Llega unos minutos antes."
            ),
            ref_id=reservation.id,
            dedupe_key=f"class_reminder:{reservation.id}:{window}",
            now=occurred,
        )
    session.commit()


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


def _staff_notification_item(row: StaffNotification) -> StaffNotificationItem:
    return StaffNotificationItem(
        id=row.id,
        kind=row.kind,
        title=row.title,
        body=row.body,
        ref_id=row.ref_id,
        created_at=_as_utc(row.created_at),
        read_at=_as_utc(row.read_at) if row.read_at is not None else None,
        resolved_at=_as_utc(row.resolved_at) if row.resolved_at is not None else None,
    )


def _clip(value: str, limit: int) -> str:
    """Shorten a volatile piece of an emitted message.

    Names come from records the club edits freely, and an over-long one must not
    make the domain operation fail on the message length check.
    """
    clean = (value or "").strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}…"


def _money_label(cents: int) -> str:
    return f"${abs(cents) / 100:,.2f} MXN"


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment
