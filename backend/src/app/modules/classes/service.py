"""Class schedule and reservation service.

The rules that keep the schedule sane live here:

* a session is only bookable while it is ``scheduled``; cancelling a session
  cancels every live reservation on it;
* capacity is checked against the *seated* reservations (``reserved`` +
  ``attended``) and the row lock on the session serialises two receptionists
  booking the last spot at the same time;
* when the room is full the member falls back to an ordered waitlist, and
  cancelling a seat promotes the next member in line;
* a cancellation outside the configured window is still allowed but flagged
  ``late_cancellation`` so the penalty can be applied once billing exists.

Money stays in integer cents; a premium class carries ``extra_price_cents`` but
the first increment does **not** charge it (same deliberate shortcut as the
membership activation, which is audited and pending the real gateway).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.classes.models import (
    ACCESS_TYPES,
    ACTIVE_RESERVATION_STATUSES,
    DEFAULT_CANCEL_WINDOW_HOURS,
    RESERVATION_ORIGINS,
    SEATED_RESERVATION_STATUSES,
    SESSION_STATUSES,
    ClassReservation,
    ClassRoom,
    ClassSession,
    ClassType,
    utc_now,
)
from app.modules.identity.models import Employee
from app.modules.memberships.models import Member
from app.modules.notifications import notify_waitlist_promoted

DEFAULT_SESSION_PAGE_SIZE = 25
MAX_SESSION_PAGE_SIZE = 100

# Sentinel so a partial update can tell "leave unchanged" (absent) apart from
# "clear the value" (explicit ``None``).
UNSET: object = object()


class ClassesError(Exception):
    """Base class for every expected classes-module failure."""


class InvalidClassData(ClassesError):
    pass


class ClassTypeNotFound(ClassesError):
    pass


class DuplicateClassType(ClassesError):
    pass


class ClassRoomNotFound(ClassesError):
    pass


class DuplicateClassRoom(ClassesError):
    pass


class InstructorNotFound(ClassesError):
    pass


class ClassSessionNotFound(ClassesError):
    pass


class InvalidSessionState(ClassesError):
    pass


class SessionFull(ClassesError):
    pass


class DuplicateReservation(ClassesError):
    pass


class MemberNotAvailable(ClassesError):
    pass


class ReservationNotFound(ClassesError):
    pass


class InvalidReservationState(ClassesError):
    pass


@dataclass(frozen=True)
class ClassTypeItem:
    id: UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class ClassRoomItem:
    id: UUID
    name: str
    capacity: int
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class InstructorItem:
    id: UUID
    name: str
    job_title: str


@dataclass(frozen=True)
class ClassSessionItem:
    id: UUID
    title: str
    class_type_id: UUID
    class_type_name: str
    room_id: UUID | None
    room_name: str | None
    instructor_id: UUID | None
    instructor_name: str | None
    starts_at: datetime
    ends_at: datetime
    capacity: int
    status: str
    access_type: str
    extra_price_cents: int
    waitlist_enabled: bool
    cancel_window_hours: int
    notes: str | None
    reserved_count: int
    waitlist_count: int
    spots_left: int
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None


@dataclass(frozen=True)
class ClassSessionSummary:
    total: int
    scheduled: int
    cancelled: int
    upcoming: int
    reserved_total: int
    waitlist_total: int


@dataclass(frozen=True)
class ClassSessionPage:
    items: list[ClassSessionItem]
    total: int
    page: int
    page_size: int
    pages: int
    summary: ClassSessionSummary


@dataclass(frozen=True)
class ReservationItem:
    id: UUID
    session_id: UUID
    member_id: UUID
    member_name: str
    member_email: str | None
    status: str
    origin: str
    waitlist_position: int | None
    late_cancellation: bool
    note: str | None
    created_at: datetime
    cancelled_at: datetime | None
    marked_at: datetime | None


@dataclass(frozen=True)
class ClassRoster:
    session: ClassSessionItem
    reservations: list[ReservationItem]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _member_name(member: Member | None) -> str:
    if member is None:
        return "Socio eliminado"
    return f"{member.first_name} {member.last_name}".strip()


def _class_type_item(item: ClassType) -> ClassTypeItem:
    return ClassTypeItem(
        id=item.id,
        name=item.name,
        description=item.description,
        is_active=item.is_active,
        created_at=item.created_at,
    )


def _class_room_item(item: ClassRoom) -> ClassRoomItem:
    return ClassRoomItem(
        id=item.id,
        name=item.name,
        capacity=item.capacity,
        is_active=item.is_active,
        created_at=item.created_at,
    )


def _assert_time_window(starts_at: datetime, ends_at: datetime) -> None:
    if _as_utc(ends_at) <= _as_utc(starts_at):
        raise InvalidClassData("La hora de término debe ser posterior a la de inicio")


# --------------------------------------------------------------------------- #
# Catalog: class types and rooms
# --------------------------------------------------------------------------- #


def create_class_type(
    session: Session,
    *,
    name: str,
    description: str | None = None,
    now: datetime | None = None,
) -> ClassTypeItem:
    clean = name.strip()
    if not clean:
        raise InvalidClassData("El nombre del tipo de clase es obligatorio")
    existing = session.exec(select(ClassType).where(func.lower(ClassType.name) == clean.lower())).first()
    if existing is not None:
        raise DuplicateClassType("Ya existe un tipo de clase con ese nombre")
    occurred = _as_utc(now or utc_now())
    item = ClassType(
        name=clean,
        description=description or None,
        is_active=True,
        created_at=occurred,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the unique index
        session.rollback()
        raise DuplicateClassType("Ya existe un tipo de clase con ese nombre") from error
    session.refresh(item)
    return _class_type_item(item)


def list_class_types(session: Session, *, include_inactive: bool = True) -> list[ClassTypeItem]:
    statement = select(ClassType).order_by(ClassType.name)
    if not include_inactive:
        statement = statement.where(ClassType.is_active.is_(True))
    return [_class_type_item(item) for item in session.exec(statement).all()]


def create_class_room(
    session: Session,
    *,
    name: str,
    capacity: int,
    now: datetime | None = None,
) -> ClassRoomItem:
    clean = name.strip()
    if not clean:
        raise InvalidClassData("El nombre del salón es obligatorio")
    if capacity <= 0:
        raise InvalidClassData("La capacidad del salón debe ser mayor que cero")
    existing = session.exec(select(ClassRoom).where(func.lower(ClassRoom.name) == clean.lower())).first()
    if existing is not None:
        raise DuplicateClassRoom("Ya existe un salón con ese nombre")
    occurred = _as_utc(now or utc_now())
    item = ClassRoom(name=clean, capacity=capacity, is_active=True, created_at=occurred)
    session.add(item)
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the unique index
        session.rollback()
        raise DuplicateClassRoom("Ya existe un salón con ese nombre") from error
    session.refresh(item)
    return _class_room_item(item)


def list_class_rooms(session: Session, *, include_inactive: bool = True) -> list[ClassRoomItem]:
    statement = select(ClassRoom).order_by(ClassRoom.name)
    if not include_inactive:
        statement = statement.where(ClassRoom.is_active.is_(True))
    return [_class_room_item(item) for item in session.exec(statement).all()]


def list_instructors(session: Session) -> list[InstructorItem]:
    """Active employees, so the schedule can point at a real person."""

    statement = (
        select(Employee)
        .where(Employee.status == "active")
        .order_by(Employee.first_name, Employee.last_name)
    )
    return [
        InstructorItem(
            id=employee.id,
            name=f"{employee.first_name} {employee.last_name}".strip(),
            job_title=employee.job_title,
        )
        for employee in session.exec(statement).all()
    ]


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #


def _session_select():
    return (
        select(
            ClassSession,
            ClassType.name,
            ClassRoom.name,
            Employee.first_name,
            Employee.last_name,
        )
        .join(ClassType, ClassType.id == ClassSession.class_type_id)
        .outerjoin(ClassRoom, ClassRoom.id == ClassSession.room_id)
        .outerjoin(Employee, Employee.id == ClassSession.instructor_id)
    )


def _session_conditions(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    room_id: UUID | None,
    instructor_id: UUID | None,
    class_type_id: UUID | None,
    status: str | None,
    search: str | None,
) -> list:
    conditions: list = []
    if date_from is not None:
        conditions.append(ClassSession.starts_at >= _as_utc(date_from))
    if date_to is not None:
        conditions.append(ClassSession.starts_at < _as_utc(date_to))
    if room_id is not None:
        conditions.append(ClassSession.room_id == room_id)
    if instructor_id is not None:
        conditions.append(ClassSession.instructor_id == instructor_id)
    if class_type_id is not None:
        conditions.append(ClassSession.class_type_id == class_type_id)
    if status in SESSION_STATUSES:
        conditions.append(ClassSession.status == status)
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(ClassSession.title).like(like),
                func.lower(ClassType.name).like(like),
            )
        )
    return conditions


def _count_seated(session: Session, session_id: UUID) -> int:
    statement = select(func.count(ClassReservation.id)).where(
        ClassReservation.session_id == session_id,
        ClassReservation.status.in_(SEATED_RESERVATION_STATUSES),
    )
    return int(session.exec(statement).one() or 0)


def _session_metrics(session: Session, session_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
    metrics = {session_id: {"reserved": 0, "waitlist": 0} for session_id in session_ids}
    if not session_ids:
        return metrics
    statement = (
        select(ClassReservation.session_id, ClassReservation.status, func.count(ClassReservation.id))
        .where(ClassReservation.session_id.in_(session_ids))
        .group_by(ClassReservation.session_id, ClassReservation.status)
    )
    for session_id, status, count in session.exec(statement).all():
        if session_id not in metrics:
            continue
        if status in SEATED_RESERVATION_STATUSES:
            metrics[session_id]["reserved"] += int(count)
        elif status == "waitlist":
            metrics[session_id]["waitlist"] += int(count)
    return metrics


def _session_item(row, metrics: dict[UUID, dict[str, int]]) -> ClassSessionItem:
    class_session, type_name, room_name, first_name, last_name = row
    counts = metrics.get(class_session.id, {"reserved": 0, "waitlist": 0})
    instructor_name = f"{first_name or ''} {last_name or ''}".strip() or None
    return ClassSessionItem(
        id=class_session.id,
        title=class_session.title,
        class_type_id=class_session.class_type_id,
        class_type_name=type_name,
        room_id=class_session.room_id,
        room_name=room_name,
        instructor_id=class_session.instructor_id,
        instructor_name=instructor_name,
        starts_at=class_session.starts_at,
        ends_at=class_session.ends_at,
        capacity=class_session.capacity,
        status=class_session.status,
        access_type=class_session.access_type,
        extra_price_cents=class_session.extra_price_cents,
        waitlist_enabled=class_session.waitlist_enabled,
        cancel_window_hours=class_session.cancel_window_hours,
        notes=class_session.notes,
        reserved_count=counts["reserved"],
        waitlist_count=counts["waitlist"],
        spots_left=max(class_session.capacity - counts["reserved"], 0),
        created_at=class_session.created_at,
        updated_at=class_session.updated_at,
        cancelled_at=class_session.cancelled_at,
    )


def _session_item_by_id(session: Session, session_id: UUID) -> ClassSessionItem:
    row = session.exec(_session_select().where(ClassSession.id == session_id)).first()
    if row is None:
        raise ClassSessionNotFound("La clase no existe")
    return _session_item(row, _session_metrics(session, [session_id]))


def _filtered_count(statement):
    # Las condiciones de búsqueda leen ClassType.name: sin el join el WHERE
    # queda sin relacionar y produce un producto cartesiano con conteos inflados.
    return statement.select_from(ClassSession).join(
        ClassType, ClassType.id == ClassSession.class_type_id
    )


def _session_summary(session: Session, conditions: list, *, now: datetime | None = None) -> ClassSessionSummary:
    occurred = _as_utc(now or utc_now())
    statement = _filtered_count(
        select(
            func.count(ClassSession.id),
            func.coalesce(func.sum(case((ClassSession.status == "scheduled", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ClassSession.status == "cancelled", 1), else_=0)), 0),
            func.coalesce(
                func.sum(
                    case(
                        (and_(ClassSession.status == "scheduled", ClassSession.starts_at >= occurred), 1),
                        else_=0,
                    )
                ),
                0,
            ),
        )
    )
    if conditions:
        statement = statement.where(*conditions)
    total, scheduled, cancelled, upcoming = session.exec(statement).one()

    attendance = (
        select(
            func.coalesce(
                func.sum(case((ClassReservation.status.in_(SEATED_RESERVATION_STATUSES), 1), else_=0)), 0
            ),
            func.coalesce(func.sum(case((ClassReservation.status == "waitlist", 1), else_=0)), 0),
        )
        .select_from(ClassReservation)
        .join(ClassSession, ClassSession.id == ClassReservation.session_id)
        .join(ClassType, ClassType.id == ClassSession.class_type_id)
    )
    if conditions:
        attendance = attendance.where(*conditions)
    reserved_total, waitlist_total = session.exec(attendance).one()

    return ClassSessionSummary(
        total=int(total or 0),
        scheduled=int(scheduled or 0),
        cancelled=int(cancelled or 0),
        upcoming=int(upcoming or 0),
        reserved_total=int(reserved_total or 0),
        waitlist_total=int(waitlist_total or 0),
    )


def create_class_session(
    session: Session,
    *,
    title: str,
    class_type_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    capacity: int,
    room_id: UUID | None = None,
    instructor_id: UUID | None = None,
    access_type: str = "included",
    extra_price_cents: int = 0,
    waitlist_enabled: bool = True,
    cancel_window_hours: int = DEFAULT_CANCEL_WINDOW_HOURS,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ClassSessionItem:
    clean_title = title.strip()
    if not clean_title:
        raise InvalidClassData("El título de la clase es obligatorio")
    _assert_time_window(starts_at, ends_at)
    if capacity <= 0:
        raise InvalidClassData("La capacidad de la clase debe ser mayor que cero")
    if access_type not in ACCESS_TYPES:
        raise InvalidClassData("El tipo de acceso debe ser 'included' o 'premium'")
    if extra_price_cents < 0:
        raise InvalidClassData("El precio extra no puede ser negativo")
    if cancel_window_hours < 0:
        raise InvalidClassData("La ventana de cancelación no puede ser negativa")
    if session.get(ClassType, class_type_id) is None:
        raise ClassTypeNotFound("El tipo de clase no existe")
    if room_id is not None and session.get(ClassRoom, room_id) is None:
        raise ClassRoomNotFound("El salón no existe")
    if instructor_id is not None and session.get(Employee, instructor_id) is None:
        raise InstructorNotFound("El instructor no existe")

    occurred = _as_utc(now or utc_now())
    item = ClassSession(
        title=clean_title,
        class_type_id=class_type_id,
        room_id=room_id,
        instructor_id=instructor_id,
        starts_at=_as_utc(starts_at),
        ends_at=_as_utc(ends_at),
        capacity=capacity,
        status="scheduled",
        access_type=access_type,
        extra_price_cents=extra_price_cents,
        waitlist_enabled=waitlist_enabled,
        cancel_window_hours=cancel_window_hours,
        notes=notes or None,
        created_by=actor_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _session_item_by_id(session, item.id)


def update_class_session(
    session: Session,
    session_id: UUID,
    *,
    title: str | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    capacity: int | None = None,
    access_type: str | None = None,
    extra_price_cents: int | None = None,
    waitlist_enabled: bool | None = None,
    cancel_window_hours: int | None = None,
    room_id: UUID | None = UNSET,  # type: ignore[assignment]
    instructor_id: UUID | None = UNSET,  # type: ignore[assignment]
    notes: str | None = UNSET,  # type: ignore[assignment]
    now: datetime | None = None,
) -> ClassSessionItem:
    item = session.get(ClassSession, session_id)
    if item is None:
        raise ClassSessionNotFound("La clase no existe")
    if item.status != "scheduled":
        raise InvalidSessionState("No se puede editar una clase cancelada")

    if title is not None:
        clean_title = title.strip()
        if not clean_title:
            raise InvalidClassData("El título de la clase es obligatorio")
        item.title = clean_title
    if starts_at is not None:
        item.starts_at = _as_utc(starts_at)
    if ends_at is not None:
        item.ends_at = _as_utc(ends_at)
    _assert_time_window(item.starts_at, item.ends_at)
    if capacity is not None:
        if capacity <= 0:
            raise InvalidClassData("La capacidad de la clase debe ser mayor que cero")
        if capacity < _count_seated(session, session_id):
            raise InvalidClassData("La capacidad no puede ser menor que las reservas confirmadas")
        item.capacity = capacity
    if access_type is not None:
        if access_type not in ACCESS_TYPES:
            raise InvalidClassData("El tipo de acceso debe ser 'included' o 'premium'")
        item.access_type = access_type
    if extra_price_cents is not None:
        if extra_price_cents < 0:
            raise InvalidClassData("El precio extra no puede ser negativo")
        item.extra_price_cents = extra_price_cents
    if waitlist_enabled is not None:
        item.waitlist_enabled = bool(waitlist_enabled)
    if cancel_window_hours is not None:
        if cancel_window_hours < 0:
            raise InvalidClassData("La ventana de cancelación no puede ser negativa")
        item.cancel_window_hours = cancel_window_hours
    if room_id is not UNSET:
        if room_id is not None and session.get(ClassRoom, room_id) is None:
            raise ClassRoomNotFound("El salón no existe")
        item.room_id = room_id
    if instructor_id is not UNSET:
        if instructor_id is not None and session.get(Employee, instructor_id) is None:
            raise InstructorNotFound("El instructor no existe")
        item.instructor_id = instructor_id
    if notes is not UNSET:
        item.notes = notes or None

    item.updated_at = _as_utc(now or utc_now())
    session.add(item)
    session.commit()
    session.refresh(item)
    return _session_item_by_id(session, item.id)


def cancel_class_session(
    session: Session,
    session_id: UUID,
    *,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ClassSessionItem:
    item = session.get(ClassSession, session_id)
    if item is None:
        raise ClassSessionNotFound("La clase no existe")
    if item.status == "cancelled":
        raise InvalidSessionState("La clase ya está cancelada")

    occurred = _as_utc(now or utc_now())
    item.status = "cancelled"
    item.cancelled_at = occurred
    item.cancelled_by = actor_id
    item.updated_at = occurred
    session.add(item)
    session.flush()

    live = session.exec(
        select(ClassReservation).where(
            ClassReservation.session_id == session_id,
            ClassReservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        )
    ).all()
    for reservation in live:
        reservation.status = "cancelled"
        reservation.waitlist_position = None
        reservation.cancelled_at = occurred
        reservation.cancelled_by = actor_id
        reservation.updated_at = occurred
        session.add(reservation)

    session.commit()
    return _session_item_by_id(session, session_id)


def list_class_sessions(
    session: Session,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    room_id: UUID | None = None,
    instructor_id: UUID | None = None,
    class_type_id: UUID | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_SESSION_PAGE_SIZE,
    now: datetime | None = None,
) -> ClassSessionPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_SESSION_PAGE_SIZE)
    conditions = _session_conditions(
        date_from=date_from,
        date_to=date_to,
        room_id=room_id,
        instructor_id=instructor_id,
        class_type_id=class_type_id,
        status=status,
        search=search,
    )

    count_statement = _filtered_count(select(func.count(ClassSession.id)))
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    statement = _session_select().order_by(ClassSession.starts_at)
    if conditions:
        statement = statement.where(*conditions)
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(statement).all()

    session_ids = [row[0].id for row in rows]
    metrics = _session_metrics(session, session_ids)
    items = [_session_item(row, metrics) for row in rows]
    summary = _session_summary(session, conditions, now=now)
    pages = (total + page_size - 1) // page_size if total else 1

    return ClassSessionPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=summary,
    )


# --------------------------------------------------------------------------- #
# Reservations
# --------------------------------------------------------------------------- #


def _reservation_item(reservation: ClassReservation, *, member_name: str, member_email: str | None) -> ReservationItem:
    return ReservationItem(
        id=reservation.id,
        session_id=reservation.session_id,
        member_id=reservation.member_id,
        member_name=member_name,
        member_email=member_email,
        status=reservation.status,
        origin=reservation.origin,
        waitlist_position=reservation.waitlist_position,
        late_cancellation=reservation.late_cancellation,
        note=reservation.note,
        created_at=reservation.created_at,
        cancelled_at=reservation.cancelled_at,
        marked_at=reservation.marked_at,
    )


def list_session_reservations(session: Session, session_id: UUID) -> ClassRoster:
    session_item = _session_item_by_id(session, session_id)
    status_order = case(
        (ClassReservation.status == "reserved", 0),
        (ClassReservation.status == "attended", 1),
        (ClassReservation.status == "no_show", 2),
        (ClassReservation.status == "waitlist", 3),
        else_=4,
    )
    rows = session.exec(
        select(ClassReservation, Member)
        .outerjoin(Member, Member.id == ClassReservation.member_id)
        .where(
            ClassReservation.session_id == session_id,
            ClassReservation.status != "cancelled",
        )
        .order_by(status_order, ClassReservation.waitlist_position, ClassReservation.created_at)
    ).all()
    items = [
        _reservation_item(
            reservation,
            member_name=_member_name(member),
            member_email=member.email if member is not None else None,
        )
        for reservation, member in rows
    ]
    return ClassRoster(session=session_item, reservations=items)


def reserve_seat(
    session: Session,
    session_id: UUID,
    *,
    member_id: UUID,
    origin: str = "reception",
    note: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ReservationItem:
    if origin not in RESERVATION_ORIGINS:
        raise InvalidClassData("El origen de la reserva no es válido")

    class_session = session.exec(
        select(ClassSession).where(ClassSession.id == session_id).with_for_update()
    ).first()
    if class_session is None:
        raise ClassSessionNotFound("La clase no existe")
    if class_session.status != "scheduled":
        raise InvalidSessionState("La clase está cancelada")

    member = session.get(Member, member_id)
    if member is None:
        raise MemberNotAvailable("El socio no existe")
    if member.status == "inactive":
        raise MemberNotAvailable("El socio está inactivo")
    member_name = _member_name(member)
    member_email = member.email

    existing = session.exec(
        select(ClassReservation).where(
            ClassReservation.session_id == session_id,
            ClassReservation.member_id == member_id,
            ClassReservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        )
    ).first()
    if existing is not None:
        raise DuplicateReservation("El socio ya tiene una reserva en esta clase")

    occurred = _as_utc(now or utc_now())
    if _count_seated(session, session_id) < class_session.capacity:
        reservation = ClassReservation(
            session_id=session_id,
            member_id=member_id,
            status="reserved",
            origin=origin,
            note=note or None,
            created_by=actor_id,
            created_at=occurred,
            updated_at=occurred,
        )
    elif class_session.waitlist_enabled:
        max_position = session.exec(
            select(func.max(ClassReservation.waitlist_position)).where(
                ClassReservation.session_id == session_id,
                ClassReservation.status == "waitlist",
            )
        ).one()
        reservation = ClassReservation(
            session_id=session_id,
            member_id=member_id,
            status="waitlist",
            origin=origin,
            waitlist_position=int(max_position or 0) + 1,
            note=note or None,
            created_by=actor_id,
            created_at=occurred,
            updated_at=occurred,
        )
    else:
        raise SessionFull("La clase está llena y no admite lista de espera")

    session.add(reservation)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateReservation("El socio ya tiene una reserva activa en esta clase") from error
    session.refresh(reservation)
    return _reservation_item(reservation, member_name=member_name, member_email=member_email)


def cancel_reservation(
    session: Session,
    reservation_id: UUID,
    *,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ReservationItem:
    reservation = session.get(ClassReservation, reservation_id)
    if reservation is None:
        raise ReservationNotFound("La reserva no existe")
    if reservation.status not in SEATED_RESERVATION_STATUSES + ("waitlist",):
        raise InvalidReservationState("La reserva ya no se puede cancelar")

    class_session = session.get(ClassSession, reservation.session_id)
    occurred = _as_utc(now or utc_now())
    was_seated = reservation.status in SEATED_RESERVATION_STATUSES

    reservation.status = "cancelled"
    reservation.waitlist_position = None
    reservation.cancelled_at = occurred
    reservation.cancelled_by = actor_id
    reservation.updated_at = occurred
    if was_seated and class_session is not None:
        deadline = _as_utc(class_session.starts_at) - timedelta(hours=class_session.cancel_window_hours)
        reservation.late_cancellation = occurred > deadline
    session.add(reservation)
    session.flush()

    if (
        was_seated
        and class_session is not None
        and class_session.status == "scheduled"
    ):
        _promote_next_waitlist(session, reservation.session_id, now=occurred)

    member = session.get(Member, reservation.member_id)
    member_name = _member_name(member)
    member_email = member.email if member is not None else None
    session.commit()
    session.refresh(reservation)
    return _reservation_item(reservation, member_name=member_name, member_email=member_email)


def mark_attendance(
    session: Session,
    reservation_id: UUID,
    *,
    attended: bool,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ReservationItem:
    reservation = session.get(ClassReservation, reservation_id)
    if reservation is None:
        raise ReservationNotFound("La reserva no existe")
    if reservation.status not in SEATED_RESERVATION_STATUSES + ("no_show",):
        raise InvalidReservationState("Solo se puede marcar asistencia de una reserva confirmada")

    occurred = _as_utc(now or utc_now())
    reservation.status = "attended" if attended else "no_show"
    reservation.marked_by = actor_id
    reservation.marked_at = occurred
    reservation.updated_at = occurred
    session.add(reservation)

    member = session.get(Member, reservation.member_id)
    member_name = _member_name(member)
    member_email = member.email if member is not None else None
    session.commit()
    session.refresh(reservation)
    return _reservation_item(reservation, member_name=member_name, member_email=member_email)


def _promote_next_waitlist(
    session: Session, session_id: UUID, *, now: datetime | None = None
) -> ClassReservation | None:
    candidate = session.exec(
        select(ClassReservation)
        .where(
            ClassReservation.session_id == session_id,
            ClassReservation.status == "waitlist",
        )
        .order_by(ClassReservation.waitlist_position, ClassReservation.created_at)
    ).first()
    if candidate is None:
        return None
    candidate.status = "reserved"
    candidate.waitlist_position = None
    candidate.updated_at = _as_utc(now or utc_now())
    session.add(candidate)
    session.flush()
    _renumber_waitlist(session, session_id)
    class_session = session.get(ClassSession, session_id)
    if class_session is not None:
        notify_waitlist_promoted(
            session,
            member_id=candidate.member_id,
            reservation_id=candidate.id,
            class_title=class_session.title,
            starts_at=_as_utc(class_session.starts_at),
            now=candidate.updated_at,
        )
    return candidate


def _renumber_waitlist(session: Session, session_id: UUID) -> None:
    rows = session.exec(
        select(ClassReservation)
        .where(
            ClassReservation.session_id == session_id,
            ClassReservation.status == "waitlist",
        )
        .order_by(ClassReservation.waitlist_position, ClassReservation.created_at)
    ).all()
    for index, row in enumerate(rows, start=1):
        if row.waitlist_position != index:
            row.waitlist_position = index
            session.add(row)
