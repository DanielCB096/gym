"""Equipment and facility maintenance service.

The rules that keep the fleet trustworthy live here:

* equipment is never deleted. A unit that leaves service is *retired*, which
  keeps every ticket and record that mentions it readable;
* a reported fault with ``critical`` severity blocks the equipment at once
  (``out_of_service``) and remembers the previous status so resolving the
  ticket can hand the unit back exactly where it was;
* a ticket can only be resolved with an explanation, and resolving it appends a
  row to the append-only technical history (``maintenance_records``) instead of
  rewriting anything;
* a preventive record may schedule the next preventive due date, which is what
  the dashboard uses to flag overdue maintenance.

Suppliers, purchase orders and replacement budgeting are out of this increment
(see ``docs/deuda-tecnica.md``).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.identity.models import Employee
from app.modules.maintenance.models import (
    BLOCKING_SEVERITIES,
    CHECKLIST_RESULTS,
    LIVE_EQUIPMENT_STATUSES,
    OPEN_TICKET_STATUSES,
    RECORD_KINDS,
    TICKET_KINDS,
    TICKET_SEVERITIES,
    UNAVAILABLE_EQUIPMENT_STATUSES,
    Equipment,
    MaintenanceChecklist,
    MaintenanceRecord,
    MaintenanceTicket,
    utc_now,
)
from app.modules.notifications import (
    notify_equipment_out_of_service,
    notify_technician_ticket_assigned,
)
from app.timezone import club_date, club_day_stamp

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# Statuses a manual status change may set (retiring has its own action).
MANUAL_EQUIPMENT_STATUSES = ("operational", "maintenance", "out_of_service", "inspection")

UNSET: object = object()


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class MaintenanceError(Exception):
    pass


class InvalidEquipmentData(MaintenanceError):
    pass


class EquipmentNotFound(MaintenanceError):
    pass


class DuplicateSerial(MaintenanceError):
    pass


class InvalidEquipmentState(MaintenanceError):
    pass


class InvalidTicketData(MaintenanceError):
    pass


class TicketNotFound(MaintenanceError):
    pass


class InvalidTicketState(MaintenanceError):
    pass


class InvalidRecordData(MaintenanceError):
    pass


class RecordNotFound(MaintenanceError):
    pass


class InvalidChecklistData(MaintenanceError):
    pass


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EquipmentItem:
    id: UUID
    name: str
    category: str
    brand: str | None
    model: str | None
    serial_number: str | None
    location: str | None
    acquired_on: date | None
    useful_life_months: int | None
    purchase_cost_cents: int
    status: str
    next_preventive_due: date | None
    notes: str | None
    retired_at: datetime | None
    open_tickets: int
    last_maintenance_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EquipmentChoice:
    id: UUID
    name: str
    location: str | None
    status: str


@dataclass(frozen=True)
class EquipmentSummary:
    total: int
    operational: int
    maintenance: int
    out_of_service: int
    inspection: int
    retired: int


@dataclass(frozen=True)
class EquipmentPage:
    items: list[EquipmentItem]
    total: int
    page: int
    page_size: int
    pages: int
    summary: EquipmentSummary
    categories: list[str]
    locations: list[str]


@dataclass(frozen=True)
class LinkedExercise:
    id: UUID
    name: str
    muscle_group: str


@dataclass(frozen=True)
class TicketItem:
    id: UUID
    code: str
    equipment_id: UUID
    equipment_name: str
    equipment_status: str
    kind: str
    severity: str
    title: str
    description: str | None
    status: str
    reported_by: UUID | None
    reporter_email: str | None
    reported_at: datetime
    assigned_to: UUID | None
    assignee_name: str | None
    assigned_at: datetime | None
    scheduled_for: date | None
    started_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None
    cost_cents: int
    blocked_equipment: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TicketSummary:
    total: int
    open: int
    assigned: int
    in_progress: int
    resolved: int
    cancelled: int
    critical_open: int


@dataclass(frozen=True)
class TicketPage:
    items: list[TicketItem]
    total: int
    page: int
    page_size: int
    pages: int
    summary: TicketSummary


@dataclass(frozen=True)
class MaintenanceRecordItem:
    id: UUID
    equipment_id: UUID
    equipment_name: str
    ticket_id: UUID | None
    kind: str
    summary: str
    notes: str | None
    performed_at: datetime
    cost_cents: int
    technician_id: UUID | None
    technician_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class RecordPage:
    items: list[MaintenanceRecordItem]
    total: int
    page: int
    page_size: int
    pages: int
    total_cost_cents: int


@dataclass(frozen=True)
class TicketDetail:
    ticket: TicketItem
    record: MaintenanceRecordItem | None


@dataclass(frozen=True)
class EquipmentDetail:
    equipment: EquipmentItem
    tickets: list[TicketItem]
    records: list[MaintenanceRecordItem]
    exercises: list[LinkedExercise]


@dataclass(frozen=True)
class ChecklistItem:
    id: UUID
    area: str
    result: str
    observations: str | None
    performed_at: datetime
    performed_by: UUID | None
    performer_email: str | None
    created_at: datetime


@dataclass(frozen=True)
class ChecklistPage:
    items: list[ChecklistItem]
    total: int
    page: int
    page_size: int
    pages: int


@dataclass(frozen=True)
class AreaServiceStatus:
    area: str
    total: int
    operational: int
    maintenance: int
    out_of_service: int
    inspection: int
    retired: int
    availability: str


@dataclass(frozen=True)
class MaintenanceOverview:
    equipment_total: int
    operational: int
    maintenance: int
    out_of_service: int
    tickets_open: int
    tickets_critical: int
    preventives_due: int
    records_last_30_days: int


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clean_required(value: str, field: str, *, max_length: int = 200) -> str:
    clean = (value or "").strip()
    if not clean:
        raise InvalidEquipmentData(f"{field} es obligatorio")
    if len(clean) > max_length:
        raise InvalidEquipmentData(f"{field} es demasiado largo")
    return clean


def _optional(value: str | None, *, max_length: int = 200) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    if not clean:
        return None
    if len(clean) > max_length:
        raise InvalidEquipmentData("El texto es demasiado largo")
    return clean


def _employee_name(employee: Employee | None) -> str | None:
    if employee is None:
        return None
    return f"{employee.first_name} {employee.last_name}".strip()


def _user_label(session: Session, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    from app.modules.identity.models import AppUser

    user = session.get(AppUser, user_id)
    return user.email if user is not None else None


def _require_employee(session: Session, employee_id: UUID | None) -> None:
    if employee_id is None:
        return
    if session.get(Employee, employee_id) is None:
        raise InvalidTicketData("El técnico no existe")


def _require_equipment(session: Session, equipment_id: UUID) -> Equipment:
    equipment = session.get(Equipment, equipment_id)
    if equipment is None:
        raise EquipmentNotFound("El equipo no existe")
    return equipment


def _build_ticket_code(occurred_at: datetime) -> str:
    # The code carries the club's local day, not the UTC day: a ticket opened at
    # 20:00 in Mexico is already the next day in UTC.
    return f"MT-{club_day_stamp(occurred_at)}-{uuid4().hex[:6].upper()}"


def _open_ticket_counts(session: Session, equipment_ids: list[UUID]) -> dict[UUID, int]:
    if not equipment_ids:
        return {}
    rows = session.exec(
        select(MaintenanceTicket.equipment_id, func.count(MaintenanceTicket.id))
        .where(
            MaintenanceTicket.equipment_id.in_(equipment_ids),
            MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES),
        )
        .group_by(MaintenanceTicket.equipment_id)
    ).all()
    return {equipment_id: int(count) for equipment_id, count in rows}


def _last_maintenance_map(session: Session, equipment_ids: list[UUID]) -> dict[UUID, datetime]:
    if not equipment_ids:
        return {}
    rows = session.exec(
        select(MaintenanceRecord.equipment_id, func.max(MaintenanceRecord.performed_at))
        .where(MaintenanceRecord.equipment_id.in_(equipment_ids))
        .group_by(MaintenanceRecord.equipment_id)
    ).all()
    return {
        equipment_id: _as_utc(performed_at)
        for equipment_id, performed_at in rows
        if performed_at is not None
    }


def _equipment_item(
    equipment: Equipment,
    *,
    open_tickets: int = 0,
    last_maintenance_at: datetime | None = None,
) -> EquipmentItem:
    return EquipmentItem(
        id=equipment.id,
        name=equipment.name,
        category=equipment.category,
        brand=equipment.brand,
        model=equipment.model,
        serial_number=equipment.serial_number,
        location=equipment.location,
        acquired_on=equipment.acquired_on,
        useful_life_months=equipment.useful_life_months,
        purchase_cost_cents=equipment.purchase_cost_cents,
        status=equipment.status,
        next_preventive_due=equipment.next_preventive_due,
        notes=equipment.notes,
        retired_at=equipment.retired_at,
        open_tickets=open_tickets,
        last_maintenance_at=last_maintenance_at,
        created_at=equipment.created_at,
        updated_at=equipment.updated_at,
    )


def _ticket_item(
    ticket: MaintenanceTicket,
    equipment: Equipment | None,
    *,
    assignee_name: str | None = None,
    reporter_email: str | None = None,
) -> TicketItem:
    return TicketItem(
        id=ticket.id,
        code=ticket.code,
        equipment_id=ticket.equipment_id,
        equipment_name=equipment.name if equipment is not None else "Equipo eliminado",
        equipment_status=equipment.status if equipment is not None else "unknown",
        kind=ticket.kind,
        severity=ticket.severity,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        reported_by=ticket.reported_by,
        reporter_email=reporter_email,
        reported_at=_as_utc(ticket.reported_at),
        assigned_to=ticket.assigned_to,
        assignee_name=assignee_name,
        assigned_at=_as_utc(ticket.assigned_at) if ticket.assigned_at else None,
        scheduled_for=ticket.scheduled_for,
        started_at=_as_utc(ticket.started_at) if ticket.started_at else None,
        resolved_at=_as_utc(ticket.resolved_at) if ticket.resolved_at else None,
        resolution_notes=ticket.resolution_notes,
        cost_cents=ticket.cost_cents,
        blocked_equipment=bool(ticket.blocked_equipment),
        created_at=_as_utc(ticket.created_at),
        updated_at=_as_utc(ticket.updated_at),
    )


def _record_item(
    record: MaintenanceRecord,
    equipment: Equipment | None,
    *,
    technician_name: str | None = None,
) -> MaintenanceRecordItem:
    return MaintenanceRecordItem(
        id=record.id,
        equipment_id=record.equipment_id,
        equipment_name=equipment.name if equipment is not None else "Equipo eliminado",
        ticket_id=record.ticket_id,
        kind=record.kind,
        summary=record.summary,
        notes=record.notes,
        performed_at=_as_utc(record.performed_at),
        cost_cents=record.cost_cents,
        technician_id=record.technician_id,
        technician_name=technician_name,
        created_at=_as_utc(record.created_at),
    )


def _checklist_item(
    checklist: MaintenanceChecklist, *, performer_email: str | None = None
) -> ChecklistItem:
    return ChecklistItem(
        id=checklist.id,
        area=checklist.area,
        result=checklist.result,
        observations=checklist.observations,
        performed_at=_as_utc(checklist.performed_at),
        performed_by=checklist.performed_by,
        performer_email=performer_email,
        created_at=_as_utc(checklist.created_at),
    )


# --------------------------------------------------------------------------- #
# Equipment registry
# --------------------------------------------------------------------------- #


def create_equipment(
    session: Session,
    *,
    name: str,
    category: str,
    brand: str | None = None,
    model: str | None = None,
    serial_number: str | None = None,
    location: str | None = None,
    acquired_on: date | None = None,
    useful_life_months: int | None = None,
    purchase_cost_cents: int = 0,
    notes: str | None = None,
    next_preventive_due: date | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> EquipmentItem:
    clean_name = _clean_required(name, "El nombre del equipo", max_length=160)
    clean_category = _clean_required(category, "La categoría", max_length=60)
    serial = _optional(serial_number, max_length=80)
    if purchase_cost_cents < 0:
        raise InvalidEquipmentData("El costo no puede ser negativo")
    if useful_life_months is not None and useful_life_months <= 0:
        raise InvalidEquipmentData("La vida útil debe ser mayor a cero")
    occurred = _as_utc(now or utc_now())
    if serial is not None:
        clash = session.exec(
            select(Equipment).where(func.lower(Equipment.serial_number) == serial.lower())
        ).first()
        if clash is not None:
            raise DuplicateSerial("Ya existe un equipo con ese número de serie")

    equipment = Equipment(
        name=clean_name,
        category=clean_category,
        brand=_optional(brand, max_length=80),
        model=_optional(model, max_length=80),
        serial_number=serial,
        location=_optional(location, max_length=80),
        acquired_on=acquired_on,
        useful_life_months=useful_life_months,
        purchase_cost_cents=purchase_cost_cents,
        next_preventive_due=next_preventive_due,
        notes=_optional(notes, max_length=2000),
        created_by=actor_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(equipment)
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the unique serial
        session.rollback()
        raise DuplicateSerial("Ya existe un equipo con ese número de serie") from error
    session.refresh(equipment)
    return _equipment_item(equipment)


def update_equipment(
    session: Session,
    equipment_id: UUID,
    *,
    name: str | None = None,
    category: str | None = None,
    brand: str | None = UNSET,  # type: ignore[assignment]
    model: str | None = UNSET,  # type: ignore[assignment]
    serial_number: str | None = UNSET,  # type: ignore[assignment]
    location: str | None = UNSET,  # type: ignore[assignment]
    acquired_on: date | None = UNSET,  # type: ignore[assignment]
    useful_life_months: int | None = UNSET,  # type: ignore[assignment]
    purchase_cost_cents: int | None = None,
    notes: str | None = UNSET,  # type: ignore[assignment]
    next_preventive_due: date | None = UNSET,  # type: ignore[assignment]
    now: datetime | None = None,
) -> EquipmentItem:
    equipment = _require_equipment(session, equipment_id)
    if equipment.status == "retired":
        raise InvalidEquipmentState("Un equipo retirado ya no se edita")

    if name is not None:
        equipment.name = _clean_required(name, "El nombre del equipo", max_length=160)
    if category is not None:
        equipment.category = _clean_required(category, "La categoría", max_length=60)
    if brand is not UNSET:
        equipment.brand = _optional(brand, max_length=80)
    if model is not UNSET:
        equipment.model = _optional(model, max_length=80)
    if serial_number is not UNSET:
        serial = _optional(serial_number, max_length=80)
        if serial is not None and (equipment.serial_number or "").lower() != serial.lower():
            clash = session.exec(
                select(Equipment).where(
                    func.lower(Equipment.serial_number) == serial.lower(),
                    Equipment.id != equipment_id,
                )
            ).first()
            if clash is not None:
                raise DuplicateSerial("Ya existe un equipo con ese número de serie")
        equipment.serial_number = serial
    if location is not UNSET:
        equipment.location = _optional(location, max_length=80)
    if acquired_on is not UNSET:
        equipment.acquired_on = acquired_on
    if useful_life_months is not UNSET:
        if useful_life_months is not None and useful_life_months <= 0:
            raise InvalidEquipmentData("La vida útil debe ser mayor a cero")
        equipment.useful_life_months = useful_life_months
    if purchase_cost_cents is not None:
        if purchase_cost_cents < 0:
            raise InvalidEquipmentData("El costo no puede ser negativo")
        equipment.purchase_cost_cents = purchase_cost_cents
    if notes is not UNSET:
        equipment.notes = _optional(notes, max_length=2000)
    if next_preventive_due is not UNSET:
        equipment.next_preventive_due = next_preventive_due

    equipment.updated_at = _as_utc(now or utc_now())
    session.add(equipment)
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the unique serial
        session.rollback()
        raise DuplicateSerial("Ya existe un equipo con ese número de serie") from error
    session.refresh(equipment)
    return _equipment_item(equipment)


def _members_using_equipment(session: Session, equipment_id: UUID) -> list[UUID]:
    """Members whose live routine plan includes an exercise on this machine.

    The match has to honour the version the assignment froze: rewriting the
    template must not decide who gets told about a broken unit.
    """
    # Imported lazily so the maintenance module does not import routines at
    # module load time (the exercise table references the equipment table).
    from app.modules.routines.models import Exercise, RoutineAssignment, RoutineItem

    rows = session.exec(
        select(RoutineAssignment.member_id)
        .join(
            RoutineItem,
            (RoutineItem.routine_id == RoutineAssignment.routine_id)
            & (RoutineItem.version == RoutineAssignment.routine_version),
        )
        .join(Exercise, Exercise.id == RoutineItem.exercise_id)
        .where(
            Exercise.equipment_id == equipment_id,
            RoutineAssignment.status == "active",
        )
        .distinct()
    ).all()
    return list(rows)


def _announce_equipment_outage(
    session: Session, equipment: Equipment, occurred: datetime
) -> None:
    """Tell the members who just lost a machine from their plan.

    Only the transition into ``out_of_service`` announces, so a unit that was
    already stopped does not repeat itself, and a machine nothing in a live plan
    uses tells nobody.
    """
    member_ids = _members_using_equipment(session, equipment.id)
    if not member_ids:
        return
    notify_equipment_out_of_service(
        session,
        equipment_id=equipment.id,
        equipment_name=equipment.name,
        location=equipment.location,
        member_ids=member_ids,
        occurred_on=club_date(occurred),
        now=occurred,
    )


def set_equipment_status(
    session: Session,
    equipment_id: UUID,
    *,
    status: str,
    now: datetime | None = None,
) -> EquipmentItem:
    equipment = _require_equipment(session, equipment_id)
    if status not in MANUAL_EQUIPMENT_STATUSES:
        if status == "retired":
            raise InvalidEquipmentState("Usa la baja de equipo para retirarlo")
        raise InvalidEquipmentData("Estado de equipo inválido")
    if equipment.status == "retired":
        raise InvalidEquipmentState("Un equipo retirado ya no cambia de estado")
    if equipment.status == status:
        return _equipment_item(equipment)
    equipment.status = status
    equipment.updated_at = _as_utc(now or utc_now())
    session.add(equipment)
    if status == "out_of_service":
        _announce_equipment_outage(session, equipment, equipment.updated_at)
    session.commit()
    session.refresh(equipment)
    return _equipment_item(equipment)


def retire_equipment(
    session: Session,
    equipment_id: UUID,
    *,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> EquipmentItem:
    equipment = _require_equipment(session, equipment_id)
    if equipment.status == "retired":
        raise InvalidEquipmentState("El equipo ya está retirado")
    open_tickets = session.exec(
        select(func.count(MaintenanceTicket.id)).where(
            MaintenanceTicket.equipment_id == equipment_id,
            MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES),
        )
    ).one()
    if int(open_tickets or 0) > 0:
        raise InvalidEquipmentState(
            "No se puede dar de baja un equipo con tickets abiertos"
        )
    occurred = _as_utc(now or utc_now())
    equipment.status = "retired"
    equipment.retired_at = occurred
    equipment.updated_at = occurred
    session.add(equipment)
    session.commit()
    session.refresh(equipment)
    return _equipment_item(equipment)


def list_equipment(
    session: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    category: str | None = None,
    location: str | None = None,
    include_retired: bool = False,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> EquipmentPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    conditions: list = []
    if status and status.strip():
        conditions.append(func.lower(Equipment.status) == status.strip().lower())
    elif not include_retired:
        conditions.append(Equipment.status != "retired")
    if category and category.strip():
        conditions.append(func.lower(Equipment.category) == category.strip().lower())
    if location and location.strip():
        conditions.append(func.lower(Equipment.location) == location.strip().lower())
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Equipment.name).like(like),
                func.lower(Equipment.category).like(like),
                func.lower(func.coalesce(Equipment.brand, "")).like(like),
                func.lower(func.coalesce(Equipment.model, "")).like(like),
                func.lower(func.coalesce(Equipment.serial_number, "")).like(like),
                func.lower(func.coalesce(Equipment.location, "")).like(like),
            )
        )

    count_statement = select(func.count(Equipment.id))
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    statement = select(Equipment).order_by(Equipment.name)
    if conditions:
        statement = statement.where(*conditions)
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(statement).all()

    equipment_ids = [row.id for row in rows]
    open_counts = _open_ticket_counts(session, equipment_ids)
    last_map = _last_maintenance_map(session, equipment_ids)

    status_rows = session.exec(
        select(Equipment.status, func.count(Equipment.id)).group_by(Equipment.status)
    ).all()
    status_counts = {status_name: int(count) for status_name, count in status_rows}
    summary = EquipmentSummary(
        total=sum(status_counts.values()),
        operational=status_counts.get("operational", 0),
        maintenance=status_counts.get("maintenance", 0),
        out_of_service=status_counts.get("out_of_service", 0),
        inspection=status_counts.get("inspection", 0),
        retired=status_counts.get("retired", 0),
    )
    categories = [
        row
        for row in session.exec(
            select(Equipment.category).distinct().order_by(Equipment.category)
        ).all()
    ]
    locations = [
        row
        for row in session.exec(
            select(Equipment.location)
            .where(Equipment.location.is_not(None))
            .distinct()
            .order_by(Equipment.location)
        ).all()
    ]
    pages = (total + page_size - 1) // page_size if total else 1
    return EquipmentPage(
        items=[
            _equipment_item(
                row,
                open_tickets=open_counts.get(row.id, 0),
                last_maintenance_at=last_map.get(row.id),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=summary,
        categories=categories,
        locations=locations,
    )


def equipment_choices(
    session: Session, *, include_retired: bool = False
) -> list[EquipmentChoice]:
    statement = select(Equipment).order_by(Equipment.name)
    if not include_retired:
        statement = statement.where(Equipment.status != "retired")
    rows = session.exec(statement).all()
    return [
        EquipmentChoice(id=row.id, name=row.name, location=row.location, status=row.status)
        for row in rows
    ]


def get_equipment(session: Session, equipment_id: UUID) -> EquipmentDetail:
    equipment = _require_equipment(session, equipment_id)
    tickets = session.exec(
        select(MaintenanceTicket)
        .where(MaintenanceTicket.equipment_id == equipment_id)
        .order_by(MaintenanceTicket.reported_at.desc())
    ).all()
    records = session.exec(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.equipment_id == equipment_id)
        .order_by(MaintenanceRecord.performed_at.desc())
    ).all()
    exercises = _linked_exercises(session, equipment_id)
    open_counts = _open_ticket_counts(session, [equipment_id])
    last_map = _last_maintenance_map(session, [equipment_id])
    return EquipmentDetail(
        equipment=_equipment_item(
            equipment,
            open_tickets=open_counts.get(equipment_id, 0),
            last_maintenance_at=last_map.get(equipment_id),
        ),
        tickets=[
            _ticket_item(
                ticket,
                equipment,
                assignee_name=_employee_name(session.get(Employee, ticket.assigned_to))
                if ticket.assigned_to
                else None,
                reporter_email=_user_label(session, ticket.reported_by),
            )
            for ticket in tickets
        ],
        records=[
            _record_item(
                record,
                equipment,
                technician_name=_employee_name(session.get(Employee, record.technician_id))
                if record.technician_id
                else None,
            )
            for record in records
        ],
        exercises=exercises,
    )


def _linked_exercises(session: Session, equipment_id: UUID) -> list[LinkedExercise]:
    # Imported lazily so the maintenance module does not import routines at
    # module load time (the exercise table references the equipment table).
    from app.modules.routines.models import Exercise

    rows = session.exec(
        select(Exercise).where(Exercise.equipment_id == equipment_id).order_by(Exercise.name)
    ).all()
    return [
        LinkedExercise(id=row.id, name=row.name, muscle_group=row.muscle_group) for row in rows
    ]


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #


def create_ticket(
    session: Session,
    *,
    equipment_id: UUID,
    title: str,
    kind: str = "corrective",
    severity: str = "medium",
    description: str | None = None,
    assigned_to: UUID | None = None,
    scheduled_for: date | None = None,
    block_equipment: bool | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> TicketItem:
    equipment = _require_equipment(session, equipment_id)
    if equipment.status == "retired":
        raise InvalidEquipmentState("No se registran tickets de un equipo retirado")
    if kind not in TICKET_KINDS:
        raise InvalidTicketData("Tipo de ticket inválido")
    if severity not in TICKET_SEVERITIES:
        raise InvalidTicketData("Severidad inválida")
    clean_title = _clean_required(title, "El título del ticket", max_length=160)
    _require_employee(session, assigned_to)
    occurred = _as_utc(now or utc_now())

    should_block = bool(block_equipment) if block_equipment is not None else (
        severity in BLOCKING_SEVERITIES
    )
    ticket = MaintenanceTicket(
        code=_build_ticket_code(occurred),
        equipment_id=equipment_id,
        kind=kind,
        severity=severity,
        title=clean_title,
        description=_optional(description, max_length=2000),
        status="open",
        reported_by=actor_id,
        reported_at=occurred,
        assigned_to=assigned_to,
        assigned_at=occurred if assigned_to is not None else None,
        scheduled_for=scheduled_for,
        blocked_equipment=False,
        created_at=occurred,
        updated_at=occurred,
    )
    if assigned_to is not None:
        ticket.status = "assigned"
    if should_block:
        _block_equipment(session, ticket, equipment, occurred)

    session.add(ticket)
    try:
        session.flush()
        if assigned_to is not None:
            notify_technician_ticket_assigned(
                session,
                technician_employee_id=assigned_to,
                ticket_id=ticket.id,
                ticket_code=ticket.code,
                equipment_name=equipment.name,
                ticket_title=ticket.title,
                now=occurred,
            )
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the unique code
        session.rollback()
        raise InvalidTicketData("No se pudo generar el folio del ticket") from error
    session.refresh(ticket)
    return _ticket_item(ticket, equipment, assignee_name=_employee_name(session.get(Employee, assigned_to)) if assigned_to else None, reporter_email=_user_label(session, actor_id))


def update_ticket(
    session: Session,
    ticket_id: UUID,
    *,
    title: str | None = None,
    description: str | None = UNSET,  # type: ignore[assignment]
    kind: str | None = None,
    severity: str | None = None,
    assigned_to: UUID | None = UNSET,  # type: ignore[assignment]
    scheduled_for: date | None = UNSET,  # type: ignore[assignment]
    cost_cents: int | None = None,
    now: datetime | None = None,
) -> TicketItem:
    ticket = session.get(MaintenanceTicket, ticket_id)
    if ticket is None:
        raise TicketNotFound("El ticket no existe")
    if ticket.status in ("resolved", "cancelled"):
        raise InvalidTicketState("Un ticket cerrado ya no se edita")
    occurred = _as_utc(now or utc_now())

    if title is not None:
        ticket.title = _clean_required(title, "El título del ticket", max_length=160)
    if description is not UNSET:
        ticket.description = _optional(description, max_length=2000)
    if kind is not None:
        if kind not in TICKET_KINDS:
            raise InvalidTicketData("Tipo de ticket inválido")
        ticket.kind = kind
    if severity is not None:
        if severity not in TICKET_SEVERITIES:
            raise InvalidTicketData("Severidad inválida")
        if severity in BLOCKING_SEVERITIES and ticket.status in OPEN_TICKET_STATUSES:
            _block_equipment(
                session, ticket, session.get(Equipment, ticket.equipment_id), occurred
            )
        ticket.severity = severity
    if assigned_to is not UNSET:
        _require_employee(session, assigned_to)
        ticket.assigned_to = assigned_to
        if assigned_to is None:
            ticket.assigned_at = None
            if ticket.status == "assigned":
                ticket.status = "open"
        else:
            ticket.assigned_at = occurred
            if ticket.status == "open":
                ticket.status = "assigned"
    if scheduled_for is not UNSET:
        ticket.scheduled_for = scheduled_for
    if cost_cents is not None:
        if cost_cents < 0:
            raise InvalidTicketData("El costo no puede ser negativo")
        ticket.cost_cents = cost_cents

    ticket.updated_at = occurred
    session.add(ticket)
    if assigned_to is not UNSET and assigned_to is not None:
        # Re-saving the same assignee is not spam: the dedupe key of the notice
        # is the ticket plus the technician, so only a genuinely new pair adds a
        # row. The first notice of a ticket comes from create_ticket.
        assignee_equipment = session.get(Equipment, ticket.equipment_id)
        notify_technician_ticket_assigned(
            session,
            technician_employee_id=assigned_to,
            ticket_id=ticket.id,
            ticket_code=ticket.code,
            equipment_name=assignee_equipment.name if assignee_equipment is not None else "un equipo",
            ticket_title=ticket.title,
            now=occurred,
        )
    session.commit()
    session.refresh(ticket)
    equipment = session.get(Equipment, ticket.equipment_id)
    return _ticket_item(
        ticket,
        equipment,
        assignee_name=_employee_name(session.get(Employee, ticket.assigned_to))
        if ticket.assigned_to
        else None,
        reporter_email=_user_label(session, ticket.reported_by),
    )


def _block_equipment(
    session: Session,
    ticket: MaintenanceTicket,
    equipment: Equipment | None,
    occurred: datetime,
) -> None:
    """A critical fault takes the unit out of service right away.

    The status it had before is remembered on the ticket so resolving or
    cancelling it can hand the unit back exactly where it was.
    """

    if equipment is None or equipment.status in ("retired", "out_of_service"):
        return
    ticket.blocked_equipment = True
    if equipment.status != "maintenance" or not ticket.previous_status:
        ticket.previous_status = equipment.status
    equipment.status = "out_of_service"
    equipment.updated_at = occurred
    session.add(equipment)
    _announce_equipment_outage(session, equipment, occurred)


def _start_equipment(
    session: Session,
    ticket: MaintenanceTicket,
    equipment: Equipment | None,
    occurred: datetime,
) -> None:
    """Starting the repair parks an otherwise usable unit in maintenance."""

    if equipment is None or equipment.status not in ("operational", "inspection"):
        return
    ticket.blocked_equipment = True
    ticket.previous_status = equipment.status
    equipment.status = "maintenance"
    equipment.updated_at = occurred
    session.add(equipment)


def _release_equipment(
    session: Session,
    ticket: MaintenanceTicket,
    equipment: Equipment | None,
    occurred: datetime,
) -> None:
    """Returns the unit to its prior status when the holding ticket closes.

    Only a ticket that actually took the equipment out of availability hands it
    back: resolving an unrelated low-severity ticket must never change the
    status of a machine that was never touched.
    """

    if equipment is None or equipment.status == "retired" or not ticket.blocked_equipment:
        return
    if equipment.status not in ("maintenance", "out_of_service"):
        return
    restored = ticket.previous_status or "inspection"
    if restored not in MANUAL_EQUIPMENT_STATUSES:
        restored = "inspection"
    equipment.status = restored
    equipment.updated_at = occurred
    session.add(equipment)


def start_ticket(
    session: Session,
    ticket_id: UUID,
    *,
    now: datetime | None = None,
) -> TicketItem:
    ticket = session.get(MaintenanceTicket, ticket_id)
    if ticket is None:
        raise TicketNotFound("El ticket no existe")
    if ticket.status == "resolved":
        raise InvalidTicketState("El ticket ya está resuelto")
    if ticket.status == "cancelled":
        raise InvalidTicketState("No se puede iniciar un ticket cancelado")
    occurred = _as_utc(now or utc_now())
    ticket.status = "in_progress"
    ticket.started_at = occurred
    ticket.updated_at = occurred
    equipment = session.get(Equipment, ticket.equipment_id)
    _start_equipment(session, ticket, equipment, occurred)
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    equipment = session.get(Equipment, ticket.equipment_id)
    return _ticket_item(
        ticket,
        equipment,
        assignee_name=_employee_name(session.get(Employee, ticket.assigned_to))
        if ticket.assigned_to
        else None,
        reporter_email=_user_label(session, ticket.reported_by),
    )


def resolve_ticket(
    session: Session,
    ticket_id: UUID,
    *,
    resolution_notes: str,
    cost_cents: int | None = None,
    next_due_on: date | None = None,
    technician_id: UUID | None = None,
    performed_at: datetime | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> TicketDetail:
    ticket = session.get(MaintenanceTicket, ticket_id)
    if ticket is None:
        raise TicketNotFound("El ticket no existe")
    if ticket.status == "resolved":
        raise InvalidTicketState("El ticket ya está resuelto")
    if ticket.status == "cancelled":
        raise InvalidTicketState("No se puede resolver un ticket cancelado")
    clean_notes = _clean_required(resolution_notes, "La solución", max_length=2000)
    if cost_cents is not None and cost_cents < 0:
        raise InvalidTicketData("El costo no puede ser negativo")
    _require_employee(session, technician_id)
    occurred = _as_utc(now or utc_now())
    performed = _as_utc(performed_at or occurred)
    if performed > occurred:
        raise InvalidRecordData("La fecha de ejecución no puede ser futura")

    equipment = session.get(Equipment, ticket.equipment_id)
    ticket.status = "resolved"
    ticket.resolved_at = occurred
    ticket.resolution_notes = clean_notes
    ticket.cost_cents = cost_cents if cost_cents is not None else ticket.cost_cents
    ticket.updated_at = occurred
    session.add(ticket)

    record_kind = "preventive" if ticket.kind == "preventive" else "corrective"
    record = MaintenanceRecord(
        equipment_id=ticket.equipment_id,
        ticket_id=ticket.id,
        kind=record_kind,
        summary=ticket.title,
        notes=clean_notes,
        performed_at=performed,
        cost_cents=ticket.cost_cents,
        technician_id=technician_id if technician_id is not None else ticket.assigned_to,
        created_by=actor_id,
        created_at=occurred,
    )
    session.add(record)

    if equipment is not None and next_due_on is not None and equipment.status != "retired":
        equipment.next_preventive_due = next_due_on
        equipment.updated_at = occurred
        session.add(equipment)
    _release_equipment(session, ticket, equipment, occurred)

    session.commit()
    session.refresh(ticket)
    session.refresh(record)
    return TicketDetail(
        ticket=_ticket_item(
            ticket,
            equipment,
            assignee_name=_employee_name(session.get(Employee, ticket.assigned_to))
            if ticket.assigned_to
            else None,
            reporter_email=_user_label(session, ticket.reported_by),
        ),
        record=_record_item(record, equipment, technician_name=_employee_name(session.get(Employee, record.technician_id)) if record.technician_id else None),
    )


def cancel_ticket(
    session: Session,
    ticket_id: UUID,
    *,
    reason: str | None = None,
    now: datetime | None = None,
) -> TicketItem:
    ticket = session.get(MaintenanceTicket, ticket_id)
    if ticket is None:
        raise TicketNotFound("El ticket no existe")
    if ticket.status == "resolved":
        raise InvalidTicketState("No se puede cancelar un ticket resuelto")
    if ticket.status == "cancelled":
        raise InvalidTicketState("El ticket ya está cancelado")
    occurred = _as_utc(now or utc_now())
    ticket.status = "cancelled"
    if reason and reason.strip():
        ticket.resolution_notes = reason.strip()
    ticket.updated_at = occurred

    _release_equipment(session, ticket, session.get(Equipment, ticket.equipment_id), occurred)

    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    equipment = session.get(Equipment, ticket.equipment_id)
    return _ticket_item(
        ticket,
        equipment,
        assignee_name=_employee_name(session.get(Employee, ticket.assigned_to))
        if ticket.assigned_to
        else None,
        reporter_email=_user_label(session, ticket.reported_by),
    )


def list_tickets(
    session: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    kind: str | None = None,
    equipment_id: UUID | None = None,
    open_only: bool = False,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> TicketPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    conditions: list = []
    if status and status.strip():
        conditions.append(func.lower(MaintenanceTicket.status) == status.strip().lower())
    elif open_only:
        conditions.append(MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES))
    if severity and severity.strip():
        conditions.append(func.lower(MaintenanceTicket.severity) == severity.strip().lower())
    if kind and kind.strip():
        conditions.append(func.lower(MaintenanceTicket.kind) == kind.strip().lower())
    if equipment_id is not None:
        conditions.append(MaintenanceTicket.equipment_id == equipment_id)
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(MaintenanceTicket.code).like(like),
                func.lower(MaintenanceTicket.title).like(like),
                func.lower(func.coalesce(MaintenanceTicket.description, "")).like(like),
            )
        )

    count_statement = select(func.count(MaintenanceTicket.id))
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    statement = (
        select(MaintenanceTicket, Equipment)
        .join(Equipment, Equipment.id == MaintenanceTicket.equipment_id)
        .order_by(MaintenanceTicket.reported_at.desc())
    )
    if conditions:
        statement = statement.where(*conditions)
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(statement).all()

    status_rows = session.exec(
        select(MaintenanceTicket.status, func.count(MaintenanceTicket.id)).group_by(
            MaintenanceTicket.status
        )
    ).all()
    status_counts = {status_name: int(count) for status_name, count in status_rows}
    critical_open = int(
        session.exec(
            select(func.count(MaintenanceTicket.id)).where(
                MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES),
                MaintenanceTicket.severity == "critical",
            )
        ).one()
        or 0
    )
    summary = TicketSummary(
        total=sum(status_counts.values()),
        open=status_counts.get("open", 0),
        assigned=status_counts.get("assigned", 0),
        in_progress=status_counts.get("in_progress", 0),
        resolved=status_counts.get("resolved", 0),
        cancelled=status_counts.get("cancelled", 0),
        critical_open=critical_open,
    )
    pages = (total + page_size - 1) // page_size if total else 1
    return TicketPage(
        items=[
            _ticket_item(
                ticket,
                equipment,
                assignee_name=_employee_name(session.get(Employee, ticket.assigned_to))
                if ticket.assigned_to
                else None,
                reporter_email=_user_label(session, ticket.reported_by),
            )
            for ticket, equipment in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=summary,
    )


def get_ticket(session: Session, ticket_id: UUID) -> TicketDetail:
    ticket = session.get(MaintenanceTicket, ticket_id)
    if ticket is None:
        raise TicketNotFound("El ticket no existe")
    equipment = session.get(Equipment, ticket.equipment_id)
    record = session.exec(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.ticket_id == ticket_id)
        .order_by(MaintenanceRecord.performed_at.desc())
    ).first()
    return TicketDetail(
        ticket=_ticket_item(
            ticket,
            equipment,
            assignee_name=_employee_name(session.get(Employee, ticket.assigned_to))
            if ticket.assigned_to
            else None,
            reporter_email=_user_label(session, ticket.reported_by),
        ),
        record=_record_item(
            record,
            equipment,
            technician_name=_employee_name(session.get(Employee, record.technician_id))
            if record and record.technician_id
            else None,
        )
        if record is not None
        else None,
    )


# --------------------------------------------------------------------------- #
# Technical history
# --------------------------------------------------------------------------- #


def record_maintenance(
    session: Session,
    *,
    equipment_id: UUID,
    kind: str,
    summary: str,
    performed_at: datetime | None = None,
    notes: str | None = None,
    cost_cents: int = 0,
    technician_id: UUID | None = None,
    next_due_on: date | None = None,
    ticket_id: UUID | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MaintenanceRecordItem:
    equipment = _require_equipment(session, equipment_id)
    if kind not in RECORD_KINDS:
        raise InvalidRecordData("Tipo de registro inválido")
    clean_summary = _clean_required(summary, "El resumen", max_length=200)
    if cost_cents < 0:
        raise InvalidRecordData("El costo no puede ser negativo")
    _require_employee(session, technician_id)
    occurred = _as_utc(now or utc_now())
    performed = _as_utc(performed_at or occurred)
    if performed > occurred:
        raise InvalidRecordData("La fecha de ejecución no puede ser futura")
    if ticket_id is not None and session.get(MaintenanceTicket, ticket_id) is None:
        raise TicketNotFound("El ticket no existe")

    record = MaintenanceRecord(
        equipment_id=equipment_id,
        ticket_id=ticket_id,
        kind=kind,
        summary=clean_summary,
        notes=_optional(notes, max_length=2000),
        performed_at=performed,
        cost_cents=cost_cents,
        technician_id=technician_id,
        created_by=actor_id,
        created_at=occurred,
    )
    session.add(record)
    if next_due_on is not None and equipment.status != "retired":
        equipment.next_preventive_due = next_due_on
        equipment.updated_at = occurred
        session.add(equipment)
    session.commit()
    session.refresh(record)
    return _record_item(
        record,
        equipment,
        technician_name=_employee_name(session.get(Employee, technician_id))
        if technician_id
        else None,
    )


def list_records(
    session: Session,
    *,
    equipment_id: UUID | None = None,
    kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> RecordPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    conditions: list = []
    if equipment_id is not None:
        conditions.append(MaintenanceRecord.equipment_id == equipment_id)
    if kind and kind.strip():
        conditions.append(func.lower(MaintenanceRecord.kind) == kind.strip().lower())
    if date_from is not None:
        conditions.append(
            MaintenanceRecord.performed_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if date_to is not None:
        conditions.append(
            MaintenanceRecord.performed_at
            < datetime.combine(date_to, datetime.min.time(), tzinfo=timezone.utc)
        )

    count_statement = select(func.count(MaintenanceRecord.id))
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    total_cost = 0
    cost_statement = select(func.coalesce(func.sum(MaintenanceRecord.cost_cents), 0))
    if conditions:
        cost_statement = cost_statement.where(*conditions)
    total_cost = int(session.exec(cost_statement).one() or 0)

    statement = (
        select(MaintenanceRecord, Equipment)
        .join(Equipment, Equipment.id == MaintenanceRecord.equipment_id)
        .order_by(MaintenanceRecord.performed_at.desc())
    )
    if conditions:
        statement = statement.where(*conditions)
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(statement).all()

    pages = (total + page_size - 1) // page_size if total else 1
    return RecordPage(
        items=[
            _record_item(
                record,
                equipment,
                technician_name=_employee_name(session.get(Employee, record.technician_id))
                if record.technician_id
                else None,
            )
            for record, equipment in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_cost_cents=total_cost,
    )


# --------------------------------------------------------------------------- #
# Cleaning / inspection checklists
# --------------------------------------------------------------------------- #


def record_checklist(
    session: Session,
    *,
    area: str,
    result: str,
    observations: str | None = None,
    performed_at: datetime | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ChecklistItem:
    clean_area = _clean_required(area, "El área", max_length=80)
    if result not in CHECKLIST_RESULTS:
        raise InvalidChecklistData("Resultado inválido")
    clean_observations = _optional(observations, max_length=2000)
    if result == "observation" and not clean_observations:
        raise InvalidChecklistData("Una observación requiere describirse")
    occurred = _as_utc(now or utc_now())
    performed = _as_utc(performed_at or occurred)
    if performed > occurred:
        raise InvalidChecklistData("La fecha de la ronda no puede ser futura")

    checklist = MaintenanceChecklist(
        area=clean_area,
        result=result,
        observations=clean_observations,
        performed_at=performed,
        performed_by=actor_id,
        created_at=occurred,
    )
    session.add(checklist)
    session.commit()
    session.refresh(checklist)
    return _checklist_item(checklist, performer_email=_user_label(session, actor_id))


def list_checklists(
    session: Session,
    *,
    area: str | None = None,
    result: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ChecklistPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    conditions: list = []
    if area and area.strip():
        conditions.append(func.lower(MaintenanceChecklist.area) == area.strip().lower())
    if result and result.strip():
        conditions.append(func.lower(MaintenanceChecklist.result) == result.strip().lower())
    if date_from is not None:
        conditions.append(
            MaintenanceChecklist.performed_at
            >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if date_to is not None:
        conditions.append(
            MaintenanceChecklist.performed_at
            < datetime.combine(date_to, datetime.min.time(), tzinfo=timezone.utc)
        )

    count_statement = select(func.count(MaintenanceChecklist.id))
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    statement = select(MaintenanceChecklist).order_by(MaintenanceChecklist.performed_at.desc())
    if conditions:
        statement = statement.where(*conditions)
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(statement).all()

    pages = (total + page_size - 1) // page_size if total else 1
    return ChecklistPage(
        items=[
            _checklist_item(row, performer_email=_user_label(session, row.performed_by))
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# --------------------------------------------------------------------------- #
# Aggregates
# --------------------------------------------------------------------------- #


def service_status(session: Session) -> list[AreaServiceStatus]:
    rows = session.exec(
        select(
            func.coalesce(Equipment.location, "Sin ubicación"),
            Equipment.status,
            func.count(Equipment.id),
        ).group_by(func.coalesce(Equipment.location, "Sin ubicación"), Equipment.status)
    ).all()

    areas: dict[str, dict[str, int]] = {}
    for area, status, count in rows:
        bucket = areas.setdefault(
            area,
            {
                "operational": 0,
                "maintenance": 0,
                "out_of_service": 0,
                "inspection": 0,
                "retired": 0,
            },
        )
        bucket[status] = int(count)

    result: list[AreaServiceStatus] = []
    for area in sorted(areas):
        bucket = areas[area]
        total = sum(bucket.values())
        live = total - bucket["retired"]
        unavailable = bucket["maintenance"] + bucket["out_of_service"]
        if live == 0:
            availability = "closed"
        elif unavailable == 0:
            availability = "available"
        elif bucket["operational"] + bucket["inspection"] > 0:
            availability = "partial"
        else:
            availability = "closed"
        result.append(
            AreaServiceStatus(
                area=area,
                total=total,
                operational=bucket["operational"],
                maintenance=bucket["maintenance"],
                out_of_service=bucket["out_of_service"],
                inspection=bucket["inspection"],
                retired=bucket["retired"],
                availability=availability,
            )
        )
    return result


def module_overview(session: Session, *, now: datetime | None = None) -> MaintenanceOverview:
    occurred = _as_utc(now or utc_now())
    today = occurred.date()
    since = occurred - timedelta(days=30)

    def _count(statement) -> int:
        return int(session.exec(statement).one() or 0)

    return MaintenanceOverview(
        equipment_total=_count(
            select(func.count(Equipment.id)).where(Equipment.status.in_(LIVE_EQUIPMENT_STATUSES))
        ),
        operational=_count(
            select(func.count(Equipment.id)).where(Equipment.status == "operational")
        ),
        maintenance=_count(
            select(func.count(Equipment.id)).where(Equipment.status == "maintenance")
        ),
        out_of_service=_count(
            select(func.count(Equipment.id)).where(Equipment.status == "out_of_service")
        ),
        tickets_open=_count(
            select(func.count(MaintenanceTicket.id)).where(
                MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES)
            )
        ),
        tickets_critical=_count(
            select(func.count(MaintenanceTicket.id)).where(
                MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES),
                MaintenanceTicket.severity == "critical",
            )
        ),
        preventives_due=_count(
            select(func.count(Equipment.id)).where(
                Equipment.status != "retired",
                Equipment.next_preventive_due.is_not(None),
                Equipment.next_preventive_due <= today,
            )
        ),
        records_last_30_days=_count(
            select(func.count(MaintenanceRecord.id)).where(
                MaintenanceRecord.performed_at >= since
            )
        ),
    )
