"""Member self-service class schedule and reservations.

This is a thin, member-scoped layer over the classes module. The schedule rules
(capacity, row lock, waitlist promotion, cancellation window) stay in
``app.modules.classes``; here we only enforce what a member is allowed to do on
their own behalf:

* only an active membership can book;
* premium classes are not bookable from the app until the extra charge exists;
* a member never sees or touches another member's reservation.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.modules.classes import (
    ClassSession,
    ClassSessionItem,
    ClassSessionNotFound,
    ClassesError,
    DuplicateReservation,
    InvalidReservationState,
    InvalidSessionState,
    ReservationItem,
    ReservationNotFound,
    cancel_reservation,
    list_class_sessions,
    reserve_seat,
)
from app.modules.classes.models import (
    ACTIVE_RESERVATION_STATUSES,
    ClassReservation,
    utc_now,
)
from app.modules.memberships.models import Member, Membership
from app.modules.portal.service import MemberPortalError

DEFAULT_CLASS_DAYS = 14
MAX_CLASS_DAYS = 60
DEFAULT_CLASS_PAGE_SIZE = 25
MAX_CLASS_PAGE_SIZE = 50


class MemberClassNotAllowed(ClassesError):
    """The member cannot perform this booking action."""


@dataclass(frozen=True)
class MemberReservationSummary:
    id: UUID
    session_id: UUID
    status: str
    waitlist_position: int | None
    late_cancellation: bool
    created_at: datetime


@dataclass(frozen=True)
class MemberClassItem:
    id: UUID
    title: str
    class_type_name: str
    room_name: str | None
    instructor_name: str | None
    starts_at: datetime
    ends_at: datetime
    capacity: int
    access_type: str
    extra_price_cents: int
    waitlist_enabled: bool
    cancel_window_hours: int
    notes: str | None
    reserved_count: int
    waitlist_count: int
    spots_left: int
    can_reserve: bool
    blocked_reason: str | None
    reservation: MemberReservationSummary | None


@dataclass(frozen=True)
class MemberClassPage:
    items: list[MemberClassItem]
    total: int
    page: int
    page_size: int
    pages: int


def list_member_classes(
    session: Session,
    member_id: UUID,
    *,
    days: int = DEFAULT_CLASS_DAYS,
    page: int = 1,
    page_size: int = DEFAULT_CLASS_PAGE_SIZE,
    now: datetime | None = None,
) -> MemberClassPage:
    occurred = _as_utc(now or utc_now())
    days = min(max(days, 1), MAX_CLASS_DAYS)
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_CLASS_PAGE_SIZE)
    access_enabled = _membership_active(session, member_id, occurred)

    directory = list_class_sessions(
        session,
        date_from=occurred,
        date_to=occurred + timedelta(days=days),
        status="scheduled",
        page=page,
        page_size=page_size,
        now=occurred,
    )
    session_ids = [item.id for item in directory.items]
    reservations: dict[UUID, ClassReservation] = {}
    if session_ids:
        rows = session.exec(
            select(ClassReservation).where(
                ClassReservation.member_id == member_id,
                ClassReservation.session_id.in_(session_ids),
                ClassReservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            )
        ).all()
        reservations = {row.session_id: row for row in rows}

    items = [
        _member_class_item(
            item,
            reservation=reservations.get(item.id),
            access_enabled=access_enabled,
            now=occurred,
        )
        for item in directory.items
    ]
    return MemberClassPage(
        items=items,
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
    )


def reserve_member_class(
    session: Session,
    member_id: UUID,
    session_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberReservationSummary:
    occurred = _as_utc(now or utc_now())
    if not _membership_active(session, member_id, occurred):
        raise MemberClassNotAllowed(
            "Tu membresía no está activa; no puedes reservar clases."
        )

    class_session = session.get(ClassSession, session_id)
    if class_session is None:
        raise ClassSessionNotFound("La clase no existe")
    if class_session.status != "scheduled":
        raise InvalidSessionState("La clase está cancelada")
    if _as_utc(class_session.starts_at) <= occurred:
        raise MemberClassNotAllowed("La clase ya comenzó; no se puede reservar.")
    if class_session.access_type != "included":
        raise MemberClassNotAllowed(
            "Esta clase es premium y todavía no se puede reservar desde la app."
        )

    existing = session.exec(
        select(ClassReservation).where(
            ClassReservation.session_id == session_id,
            ClassReservation.member_id == member_id,
            ClassReservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        )
    ).first()
    if existing is not None:
        raise DuplicateReservation("Ya tienes una reserva en esta clase")

    reservation = reserve_seat(
        session,
        session_id,
        member_id=member_id,
        origin="app",
        now=occurred,
    )
    return _reservation_summary(reservation)


def cancel_member_reservation(
    session: Session,
    member_id: UUID,
    reservation_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberReservationSummary:
    occurred = _as_utc(now or utc_now())
    reservation = session.get(ClassReservation, reservation_id)
    if reservation is None or reservation.member_id != member_id:
        raise ReservationNotFound("La reserva no existe")
    if reservation.status not in ACTIVE_RESERVATION_STATUSES:
        raise InvalidReservationState("La reserva ya no se puede cancelar")

    class_session = session.get(ClassSession, reservation.session_id)
    if class_session is None:
        raise ClassSessionNotFound("La clase no existe")
    if _as_utc(class_session.starts_at) <= occurred:
        raise InvalidReservationState("La clase ya comenzó; no se puede cancelar")

    cancelled = cancel_reservation(
        session,
        reservation_id,
        now=occurred,
    )
    return _reservation_summary(cancelled)


def _membership_active(session: Session, member_id: UUID, occurred: datetime) -> bool:
    member = session.get(Member, member_id)
    if member is None:
        raise MemberPortalError("Socio no encontrado")
    membership = session.exec(
        select(Membership)
        .where(Membership.member_id == member_id)
        .order_by(Membership.ends_at.desc())
    ).first()
    if membership is None:
        return False
    starts_at = _as_utc(membership.starts_at)
    ends_at = _as_utc(membership.ends_at)
    return (
        member.status == "active"
        and membership.status == "active"
        and starts_at <= occurred < ends_at
    )


def _booking_state(
    item: ClassSessionItem,
    *,
    reservation: ClassReservation | None,
    access_enabled: bool,
    now: datetime,
) -> tuple[bool, str | None]:
    if reservation is not None:
        return False, "already_reserved"
    if not access_enabled:
        return False, "membership_inactive"
    if item.access_type != "included":
        return False, "premium_class"
    if _as_utc(item.starts_at) <= now:
        return False, "started"
    if item.spots_left <= 0 and not item.waitlist_enabled:
        return False, "full"
    return True, None


def _member_class_item(
    item: ClassSessionItem,
    *,
    reservation: ClassReservation | None,
    access_enabled: bool,
    now: datetime,
) -> MemberClassItem:
    can_reserve, blocked_reason = _booking_state(
        item,
        reservation=reservation,
        access_enabled=access_enabled,
        now=now,
    )
    return MemberClassItem(
        id=item.id,
        title=item.title,
        class_type_name=item.class_type_name,
        room_name=item.room_name,
        instructor_name=item.instructor_name,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        capacity=item.capacity,
        access_type=item.access_type,
        extra_price_cents=item.extra_price_cents,
        waitlist_enabled=item.waitlist_enabled,
        cancel_window_hours=item.cancel_window_hours,
        notes=item.notes,
        reserved_count=item.reserved_count,
        waitlist_count=item.waitlist_count,
        spots_left=item.spots_left,
        can_reserve=can_reserve,
        blocked_reason=blocked_reason,
        reservation=_reservation_summary(reservation) if reservation is not None else None,
    )


def _reservation_summary(
    reservation: ClassReservation | ReservationItem,
) -> MemberReservationSummary:
    return MemberReservationSummary(
        id=reservation.id,
        session_id=reservation.session_id,
        status=reservation.status,
        waitlist_position=reservation.waitlist_position,
        late_cancellation=reservation.late_cancellation,
        created_at=reservation.created_at,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
