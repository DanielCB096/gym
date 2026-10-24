"""Routines and progress service.

The rules that keep the training plan honest live here:

* a routine is a *template* owned by a trainer and versioned. Editing the plan
  never overwrites history: ``replace_routine_items`` publishes ``version + 1``
  with a fresh set of ``routine_items`` and records the motive in
  ``routine_revisions``, so an assignment (and every workout logged against it)
  stays pinned to the exact plan the member trained;
* an assignment freezes the routine version at creation time
  (``routine_version``) and a member can only follow one live assignment per
  routine at a time;
* a workout is only logged against an *active* assignment and never dated in the
  future;
* body measurements are append-only: recording a new one adds a row, it never
  replaces an earlier measurement.

No money is involved in this module. Per-set workout detail, goals, progress
photos and trainer-member messaging are out of this first increment (see
``docs/deuda-tecnica.md``).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.identity.models import Employee
from app.modules.memberships.models import Member
from app.modules.routines.models import (
    ASSIGNMENT_STATUSES,
    MAX_EFFORT,
    MAX_WEEKLY_FREQUENCY,
    MIN_EFFORT,
    MIN_WEEKLY_FREQUENCY,
    ROUTINE_STATUSES,
    BodyMeasurement,
    Exercise,
    Routine,
    RoutineAssignment,
    RoutineItem,
    RoutineRevision,
    WorkoutLog,
    utc_now,
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_MEASUREMENT_HISTORY = 36

# Sentinel so a partial update can tell "leave unchanged" (absent) apart from
# "clear the value" (explicit ``None``).
UNSET: object = object()


class RoutinesError(Exception):
    """Base class for every expected routines-module failure."""


class InvalidRoutineData(RoutinesError):
    pass


class DuplicateExercise(RoutinesError):
    pass


class ExerciseNotFound(RoutinesError):
    pass


class ExerciseUnavailable(RoutinesError):
    pass


class RoutineNotFound(RoutinesError):
    pass


class InvalidRoutineState(RoutinesError):
    pass


class EmptyRoutine(RoutinesError):
    pass


class DuplicateRoutineExercise(RoutinesError):
    pass


class AssignmentNotFound(RoutinesError):
    pass


class DuplicateAssignment(RoutinesError):
    pass


class MemberNotEligible(RoutinesError):
    pass


class InvalidAssignmentState(RoutinesError):
    pass


class WorkoutNotFound(RoutinesError):
    pass


class InvalidWorkoutData(RoutinesError):
    pass


class InvalidWorkoutState(RoutinesError):
    pass


class InvalidMeasurement(RoutinesError):
    pass


@dataclass(frozen=True)
class RoutineItemInput:
    """Validated input line for a routine version."""

    exercise_id: UUID
    sets: int
    reps: str
    rest_seconds: int | None = None
    load_note: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ExerciseItem:
    id: UUID
    name: str
    muscle_group: str
    category: str
    equipment_name: str | None
    equipment_id: UUID | None
    equipment_status: str | None
    description: str | None
    video_url: str | None
    image_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ExercisePage:
    items: list[ExerciseItem]
    total: int
    page: int
    page_size: int
    pages: int
    muscle_groups: list[str]
    categories: list[str]


@dataclass(frozen=True)
class RoutineLine:
    id: UUID
    exercise_id: UUID
    exercise_name: str
    muscle_group: str
    category: str
    equipment_status: str | None
    position: int
    sets: int
    reps: str
    rest_seconds: int | None
    load_note: str | None
    notes: str | None


@dataclass(frozen=True)
class RoutineRevisionItem:
    version: int
    reason: str | None
    item_count: int
    changed_by: UUID | None
    created_at: datetime


@dataclass(frozen=True)
class RoutineItemView:
    id: UUID
    name: str
    trainer_id: UUID | None
    trainer_name: str | None
    objective: str | None
    notes: str | None
    status: str
    version: int
    item_count: int
    active_assignments: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True)
class RoutineDetail:
    routine: RoutineItemView
    items: list[RoutineLine]
    revisions: list[RoutineRevisionItem]


@dataclass(frozen=True)
class RoutineSummary:
    total: int
    active: int
    draft: int
    archived: int


@dataclass(frozen=True)
class RoutinePage:
    items: list[RoutineItemView]
    total: int
    page: int
    page_size: int
    pages: int
    summary: RoutineSummary


@dataclass(frozen=True)
class AssignmentItem:
    id: UUID
    routine_id: UUID
    routine_name: str
    routine_version: int
    member_id: UUID
    member_name: str
    member_email: str | None
    trainer_id: UUID | None
    trainer_name: str | None
    start_date: date
    end_date: date | None
    frequency_per_week: int | None
    status: str
    notes: str | None
    workouts_logged: int
    last_workout_at: date | None
    created_at: datetime
    ended_at: datetime | None


@dataclass(frozen=True)
class AssignmentSummary:
    total: int
    active: int
    completed: int
    cancelled: int


@dataclass(frozen=True)
class AssignmentPage:
    items: list[AssignmentItem]
    total: int
    page: int
    page_size: int
    pages: int
    summary: AssignmentSummary


@dataclass(frozen=True)
class AssignmentDetail:
    assignment: AssignmentItem
    routine_version: int
    plan: list[RoutineLine]


@dataclass(frozen=True)
class WorkoutItem:
    id: UUID
    assignment_id: UUID
    member_id: UUID
    routine_id: UUID
    routine_version: int
    performed_at: date
    duration_minutes: int | None
    perceived_effort: int | None
    notes: str | None
    status: str
    reviewed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class MeasurementItem:
    id: UUID
    member_id: UUID
    measured_at: datetime
    weight_kg: float | None
    waist_cm: float | None
    chest_cm: float | None
    body_fat_percent: float | None
    notes: str | None
    created_at: datetime


@dataclass(frozen=True)
class MemberProgress:
    member_id: UUID
    member_name: str
    active_assignments: int
    workouts_total: int
    workouts_last_30_days: int
    last_workout_at: date | None
    latest_measurement: MeasurementItem | None
    measurements: list[MeasurementItem]


@dataclass(frozen=True)
class ModuleOverview:
    exercises: int
    routines_active: int
    routines_archived: int
    assignments_active: int
    workouts_last_7_days: int


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _member_name(member: Member | None) -> str:
    if member is None:
        return "Socio eliminado"
    return f"{member.first_name} {member.last_name}".strip()


def _employee_name(employee: Employee | None) -> str | None:
    if employee is None:
        return None
    return f"{employee.first_name} {employee.last_name}".strip()


def _require_member(session: Session, member_id: UUID) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise MemberNotEligible("El socio no existe")
    return member


def _require_employee(session: Session, employee_id: UUID) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise InvalidRoutineData("El entrenador no existe")
    return employee


def _exercise_item(
    exercise: Exercise, *, equipment_status: str | None = None
) -> ExerciseItem:
    return ExerciseItem(
        id=exercise.id,
        name=exercise.name,
        muscle_group=exercise.muscle_group,
        category=exercise.category,
        equipment_name=exercise.equipment_name,
        equipment_id=exercise.equipment_id,
        equipment_status=equipment_status,
        description=exercise.description,
        video_url=exercise.video_url,
        image_url=exercise.image_url,
        is_active=exercise.is_active,
        created_at=exercise.created_at,
        updated_at=exercise.updated_at,
    )


def _equipment_status_map(
    session: Session, equipment_ids: list[UUID | None]
) -> dict[UUID, str]:
    ids = [equipment_id for equipment_id in equipment_ids if equipment_id is not None]
    if not ids:
        return {}
    # Imported lazily to keep the routines module free of a hard dependency on
    # maintenance at import time.
    from app.modules.maintenance.models import Equipment

    rows = session.exec(
        select(Equipment.id, Equipment.status).where(Equipment.id.in_(ids))
    ).all()
    return {equipment_id: status for equipment_id, status in rows}


def _require_linked_equipment(session: Session, equipment_id: UUID) -> str:
    from app.modules.maintenance.models import Equipment

    equipment = session.get(Equipment, equipment_id)
    if equipment is None:
        raise InvalidRoutineData("El equipo no existe")
    if equipment.status == "retired":
        raise InvalidRoutineData("No se puede vincular un ejercicio a un equipo retirado")
    return equipment.status


# --------------------------------------------------------------------------- #
# Exercise library
# --------------------------------------------------------------------------- #


def _clean_required(value: str, field: str) -> str:
    clean = value.strip()
    if not clean:
        raise InvalidRoutineData(f"{field} es obligatorio")
    return clean


def create_exercise(
    session: Session,
    *,
    name: str,
    muscle_group: str,
    category: str,
    equipment_name: str | None = None,
    equipment_id: UUID | None = None,
    description: str | None = None,
    video_url: str | None = None,
    image_url: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ExerciseItem:
    clean_name = _clean_required(name, "El nombre del ejercicio")
    clean_muscle = _clean_required(muscle_group, "El grupo muscular")
    clean_category = _clean_required(category, "La categoría")
    existing = session.exec(select(Exercise).where(func.lower(Exercise.name) == clean_name.lower())).first()
    if existing is not None:
        raise DuplicateExercise("Ya existe un ejercicio con ese nombre")
    equipment_status = (
        _require_linked_equipment(session, equipment_id) if equipment_id is not None else None
    )
    occurred = _as_utc(now or utc_now())
    item = Exercise(
        name=clean_name,
        muscle_group=clean_muscle,
        category=clean_category,
        equipment_name=(equipment_name or "").strip() or None,
        equipment_id=equipment_id,
        description=(description or "").strip() or None,
        video_url=(video_url or "").strip() or None,
        image_url=(image_url or "").strip() or None,
        is_active=True,
        created_by=actor_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the unique index
        session.rollback()
        raise DuplicateExercise("Ya existe un ejercicio con ese nombre") from error
    session.refresh(item)
    return _exercise_item(item, equipment_status=equipment_status)


def update_exercise(
    session: Session,
    exercise_id: UUID,
    *,
    name: str | None = None,
    muscle_group: str | None = None,
    category: str | None = None,
    equipment_name: str | None = UNSET,  # type: ignore[assignment]
    equipment_id: UUID | None = UNSET,  # type: ignore[assignment]
    description: str | None = UNSET,  # type: ignore[assignment]
    video_url: str | None = UNSET,  # type: ignore[assignment]
    image_url: str | None = UNSET,  # type: ignore[assignment]
    is_active: bool | None = None,
    now: datetime | None = None,
) -> ExerciseItem:
    item = session.get(Exercise, exercise_id)
    if item is None:
        raise ExerciseNotFound("El ejercicio no existe")
    equipment_status: str | None = None

    if name is not None:
        clean_name = _clean_required(name, "El nombre del ejercicio")
        if clean_name.lower() != item.name.lower():
            clash = session.exec(
                select(Exercise).where(
                    func.lower(Exercise.name) == clean_name.lower(), Exercise.id != exercise_id
                )
            ).first()
            if clash is not None:
                raise DuplicateExercise("Ya existe un ejercicio con ese nombre")
        item.name = clean_name
    if muscle_group is not None:
        item.muscle_group = _clean_required(muscle_group, "El grupo muscular")
    if category is not None:
        item.category = _clean_required(category, "La categoría")
    if equipment_name is not UNSET:
        item.equipment_name = (equipment_name or "").strip() or None
    if equipment_id is not UNSET:
        item.equipment_id = equipment_id
        equipment_status = (
            _require_linked_equipment(session, equipment_id)
            if equipment_id is not None
            else None
        )
    if description is not UNSET:
        item.description = (description or "").strip() or None
    if video_url is not UNSET:
        item.video_url = (video_url or "").strip() or None
    if image_url is not UNSET:
        item.image_url = (image_url or "").strip() or None
    if is_active is not None:
        item.is_active = bool(is_active)

    item.updated_at = _as_utc(now or utc_now())
    session.add(item)
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the unique index
        session.rollback()
        raise DuplicateExercise("Ya existe un ejercicio con ese nombre") from error
    session.refresh(item)
    if equipment_status is None and item.equipment_id is not None:
        equipment_status = _equipment_status_map(session, [item.equipment_id]).get(
            item.equipment_id
        )
    return _exercise_item(item, equipment_status=equipment_status)


def list_exercises(
    session: Session,
    *,
    search: str | None = None,
    muscle_group: str | None = None,
    category: str | None = None,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ExercisePage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    conditions: list = []
    if not include_inactive:
        conditions.append(Exercise.is_active.is_(True))
    if muscle_group and muscle_group.strip():
        conditions.append(func.lower(Exercise.muscle_group) == muscle_group.strip().lower())
    if category and category.strip():
        conditions.append(func.lower(Exercise.category) == category.strip().lower())
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Exercise.name).like(like),
                func.lower(Exercise.muscle_group).like(like),
                func.lower(Exercise.category).like(like),
                func.lower(func.coalesce(Exercise.equipment_name, "")).like(like),
            )
        )

    count_statement = select(func.count(Exercise.id))
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    statement = select(Exercise).order_by(Exercise.name)
    if conditions:
        statement = statement.where(*conditions)
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(statement).all()
    equipment_statuses = _equipment_status_map(session, [row.equipment_id for row in rows])

    muscle_groups = [
        row
        for row in session.exec(
            select(Exercise.muscle_group).distinct().order_by(Exercise.muscle_group)
        ).all()
    ]
    categories = [
        row
        for row in session.exec(
            select(Exercise.category).distinct().order_by(Exercise.category)
        ).all()
    ]
    pages = (total + page_size - 1) // page_size if total else 1
    return ExercisePage(
        items=[
            _exercise_item(
                row,
                equipment_status=equipment_statuses.get(row.equipment_id)
                if row.equipment_id
                else None,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        muscle_groups=muscle_groups,
        categories=categories,
    )


# --------------------------------------------------------------------------- #
# Routines and versions
# --------------------------------------------------------------------------- #


def _validate_items(session: Session, items: list[RoutineItemInput]) -> list[RoutineItemInput]:
    if not items:
        raise EmptyRoutine("La rutina debe tener al menos un ejercicio")
    seen: set[UUID] = set()
    validated: list[RoutineItemInput] = []
    for line in items:
        if line.exercise_id in seen:
            raise DuplicateRoutineExercise("No se puede repetir el mismo ejercicio en la rutina")
        seen.add(line.exercise_id)
        exercise = session.get(Exercise, line.exercise_id)
        if exercise is None:
            raise ExerciseNotFound("Uno de los ejercicios no existe")
        if not exercise.is_active:
            raise ExerciseUnavailable(f"El ejercicio «{exercise.name}» está inactivo")
        if line.sets <= 0:
            raise InvalidRoutineData("Las series deben ser mayores que cero")
        reps = line.reps.strip()
        if not reps:
            raise InvalidRoutineData("Las repeticiones son obligatorias")
        if line.rest_seconds is not None and line.rest_seconds < 0:
            raise InvalidRoutineData("El descanso no puede ser negativo")
        validated.append(
            RoutineItemInput(
                exercise_id=line.exercise_id,
                sets=line.sets,
                reps=reps,
                rest_seconds=line.rest_seconds,
                load_note=(line.load_note or "").strip() or None,
                notes=(line.notes or "").strip() or None,
            )
        )
    return validated


def _insert_items(
    session: Session, routine_id: UUID, version: int, items: list[RoutineItemInput]
) -> None:
    for position, line in enumerate(items, start=1):
        session.add(
            RoutineItem(
                routine_id=routine_id,
                version=version,
                position=position,
                exercise_id=line.exercise_id,
                sets=line.sets,
                reps=line.reps,
                rest_seconds=line.rest_seconds,
                load_note=line.load_note,
                notes=line.notes,
            )
        )


def _active_assignments_count(session: Session, routine_id: UUID) -> int:
    statement = select(func.count(RoutineAssignment.id)).where(
        RoutineAssignment.routine_id == routine_id,
        RoutineAssignment.status == "active",
    )
    return int(session.exec(statement).one() or 0)


def _item_count(session: Session, routine: Routine, version: int | None = None) -> int:
    statement = select(func.count(RoutineItem.id)).where(
        RoutineItem.routine_id == routine.id,
        RoutineItem.version == (version if version is not None else routine.version),
    )
    return int(session.exec(statement).one() or 0)


def _routine_rows(session: Session, conditions: list):
    item_count = (
        select(func.count(RoutineItem.id))
        .where(RoutineItem.routine_id == Routine.id, RoutineItem.version == Routine.version)
        .scalar_subquery()
    )
    active_assignments = (
        select(func.count(RoutineAssignment.id))
        .where(
            RoutineAssignment.routine_id == Routine.id,
            RoutineAssignment.status == "active",
        )
        .scalar_subquery()
    )
    statement = (
        select(
            Routine,
            Employee.first_name,
            Employee.last_name,
            item_count,
            active_assignments,
        )
        .outerjoin(Employee, Employee.id == Routine.trainer_id)
    )
    if conditions:
        statement = statement.where(*conditions)
    return statement


def _routine_view(row) -> RoutineItemView:
    routine, first_name, last_name, item_count, active_assignments = row
    trainer_name = f"{first_name or ''} {last_name or ''}".strip() or None
    return RoutineItemView(
        id=routine.id,
        name=routine.name,
        trainer_id=routine.trainer_id,
        trainer_name=trainer_name,
        objective=routine.objective,
        notes=routine.notes,
        status=routine.status,
        version=routine.version,
        item_count=int(item_count or 0),
        active_assignments=int(active_assignments or 0),
        created_at=routine.created_at,
        updated_at=routine.updated_at,
        archived_at=routine.archived_at,
    )


def _routine_revision_item(revision: RoutineRevision) -> RoutineRevisionItem:
    return RoutineRevisionItem(
        version=revision.version,
        reason=revision.reason,
        item_count=revision.item_count,
        changed_by=revision.changed_by,
        created_at=revision.created_at,
    )


def _routine_lines(session: Session, routine_id: UUID, version: int) -> list[RoutineLine]:
    rows = session.exec(
        select(RoutineItem, Exercise)
        .join(Exercise, Exercise.id == RoutineItem.exercise_id)
        .where(RoutineItem.routine_id == routine_id, RoutineItem.version == version)
        .order_by(RoutineItem.position)
    ).all()
    equipment_statuses = _equipment_status_map(session, [exercise.equipment_id for _, exercise in rows])
    return [
        RoutineLine(
            id=line.id,
            exercise_id=line.exercise_id,
            exercise_name=exercise.name,
            muscle_group=exercise.muscle_group,
            category=exercise.category,
            equipment_status=equipment_statuses.get(exercise.equipment_id)
            if exercise.equipment_id
            else None,
            position=line.position,
            sets=line.sets,
            reps=line.reps,
            rest_seconds=line.rest_seconds,
            load_note=line.load_note,
            notes=line.notes,
        )
        for line, exercise in rows
    ]


def get_routine(session: Session, routine_id: UUID, *, version: int | None = None) -> RoutineDetail:
    routine = session.get(Routine, routine_id)
    if routine is None:
        raise RoutineNotFound("La rutina no existe")
    row = session.exec(_routine_rows(session, [Routine.id == routine_id])).first()
    if row is None:  # pragma: no cover - the routine was just fetched
        raise RoutineNotFound("La rutina no existe")
    requested_version = version if version is not None else routine.version
    revisions = session.exec(
        select(RoutineRevision)
        .where(RoutineRevision.routine_id == routine_id)
        .order_by(RoutineRevision.version.desc())
    ).all()
    return RoutineDetail(
        routine=_routine_view(row),
        items=_routine_lines(session, routine_id, requested_version),
        revisions=[_routine_revision_item(revision) for revision in revisions],
    )


def create_routine(
    session: Session,
    *,
    name: str,
    items: list[RoutineItemInput],
    trainer_id: UUID | None = None,
    objective: str | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> RoutineDetail:
    clean_name = _clean_required(name, "El nombre de la rutina")
    if trainer_id is not None:
        _require_employee(session, trainer_id)
    validated = _validate_items(session, items)
    occurred = _as_utc(now or utc_now())

    routine = Routine(
        name=clean_name,
        trainer_id=trainer_id,
        objective=(objective or "").strip() or None,
        notes=(notes or "").strip() or None,
        status="active",
        version=1,
        created_by=actor_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(routine)
    session.flush()
    _insert_items(session, routine.id, 1, validated)
    session.add(
        RoutineRevision(
            routine_id=routine.id,
            version=1,
            reason="Versión inicial",
            item_count=len(validated),
            changed_by=actor_id,
            created_at=occurred,
        )
    )
    session.commit()
    return get_routine(session, routine.id)


def replace_routine_items(
    session: Session,
    routine_id: UUID,
    *,
    items: list[RoutineItemInput],
    reason: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> RoutineDetail:
    routine = session.get(Routine, routine_id)
    if routine is None:
        raise RoutineNotFound("La rutina no existe")
    if routine.status == "archived":
        raise InvalidRoutineState("No se puede editar una rutina archivada")
    validated = _validate_items(session, items)
    occurred = _as_utc(now or utc_now())
    new_version = routine.version + 1

    _insert_items(session, routine_id, new_version, validated)
    routine.version = new_version
    routine.updated_at = occurred
    session.add(routine)
    session.add(
        RoutineRevision(
            routine_id=routine_id,
            version=new_version,
            reason=(reason or "").strip() or None,
            item_count=len(validated),
            changed_by=actor_id,
            created_at=occurred,
        )
    )
    session.commit()
    return get_routine(session, routine_id)


def update_routine(
    session: Session,
    routine_id: UUID,
    *,
    name: str | None = None,
    trainer_id: UUID | None = UNSET,  # type: ignore[assignment]
    objective: str | None = UNSET,  # type: ignore[assignment]
    notes: str | None = UNSET,  # type: ignore[assignment]
    status: str | None = None,
    now: datetime | None = None,
) -> RoutineDetail:
    routine = session.get(Routine, routine_id)
    if routine is None:
        raise RoutineNotFound("La rutina no existe")
    if routine.status == "archived" and status != "active":
        raise InvalidRoutineState("No se puede editar una rutina archivada")

    if name is not None:
        routine.name = _clean_required(name, "El nombre de la rutina")
    if trainer_id is not UNSET:
        if trainer_id is not None:
            _require_employee(session, trainer_id)
        routine.trainer_id = trainer_id
    if objective is not UNSET:
        routine.objective = (objective or "").strip() or None
    if notes is not UNSET:
        routine.notes = (notes or "").strip() or None
    if status is not None:
        if status not in ROUTINE_STATUSES:
            raise InvalidRoutineData("El estado de la rutina no es válido")
        routine.status = status
        routine.archived_at = _as_utc(now or utc_now()) if status == "archived" else None

    routine.updated_at = _as_utc(now or utc_now())
    session.add(routine)
    session.commit()
    return get_routine(session, routine_id)


def archive_routine(
    session: Session, routine_id: UUID, *, now: datetime | None = None
) -> RoutineDetail:
    routine = session.get(Routine, routine_id)
    if routine is None:
        raise RoutineNotFound("La rutina no existe")
    if routine.status == "archived":
        raise InvalidRoutineState("La rutina ya está archivada")
    routine.status = "archived"
    routine.archived_at = _as_utc(now or utc_now())
    routine.updated_at = routine.archived_at
    session.add(routine)
    session.commit()
    return get_routine(session, routine_id)


def list_routines(
    session: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    trainer_id: UUID | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> RoutinePage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    conditions: list = []
    if status in ROUTINE_STATUSES:
        conditions.append(Routine.status == status)
    if trainer_id is not None:
        conditions.append(Routine.trainer_id == trainer_id)
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Routine.name).like(like),
                func.lower(func.coalesce(Routine.objective, "")).like(like),
            )
        )

    count_statement = select(func.count(Routine.id))
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    statement = _routine_rows(session, conditions).order_by(Routine.name)
    rows = session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all()

    summary_active = int(
        session.exec(select(func.count(Routine.id)).where(Routine.status == "active")).one() or 0
    )
    draft_total = int(
        session.exec(select(func.count(Routine.id)).where(Routine.status == "draft")).one() or 0
    )
    archived_total = int(
        session.exec(select(func.count(Routine.id)).where(Routine.status == "archived")).one() or 0
    )
    pages = (total + page_size - 1) // page_size if total else 1
    return RoutinePage(
        items=[_routine_view(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=RoutineSummary(
            total=summary_active + draft_total + archived_total,
            active=summary_active,
            draft=draft_total,
            archived=archived_total,
        ),
    )


# --------------------------------------------------------------------------- #
# Assignments
# --------------------------------------------------------------------------- #


def _workouts_logged(session: Session, assignment_id: UUID) -> int:
    return int(
        session.exec(
            select(func.count(WorkoutLog.id)).where(WorkoutLog.assignment_id == assignment_id)
        ).one()
        or 0
    )


def _assignment_rows(session: Session, conditions: list):
    workouts_logged = (
        select(func.count(WorkoutLog.id))
        .where(WorkoutLog.assignment_id == RoutineAssignment.id)
        .scalar_subquery()
    )
    last_workout = (
        select(func.max(WorkoutLog.performed_at))
        .where(WorkoutLog.assignment_id == RoutineAssignment.id)
        .scalar_subquery()
    )
    statement = (
        select(
            RoutineAssignment,
            Routine.name,
            Member.first_name,
            Member.last_name,
            Member.email,
            Employee.first_name,
            Employee.last_name,
            workouts_logged,
            last_workout,
        )
        .join(Routine, Routine.id == RoutineAssignment.routine_id)
        .outerjoin(Member, Member.id == RoutineAssignment.member_id)
        .outerjoin(Employee, Employee.id == RoutineAssignment.trainer_id)
    )
    if conditions:
        statement = statement.where(*conditions)
    return statement


def _assignment_view(row) -> AssignmentItem:
    (
        assignment,
        routine_name,
        member_first,
        member_last,
        member_email,
        trainer_first,
        trainer_last,
        workouts_logged,
        last_workout,
    ) = row
    member_name = f"{member_first or ''} {member_last or ''}".strip() or "Socio eliminado"
    trainer_name = f"{trainer_first or ''} {trainer_last or ''}".strip() or None
    return AssignmentItem(
        id=assignment.id,
        routine_id=assignment.routine_id,
        routine_name=routine_name,
        routine_version=assignment.routine_version,
        member_id=assignment.member_id,
        member_name=member_name,
        member_email=member_email,
        trainer_id=assignment.trainer_id,
        trainer_name=trainer_name,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        frequency_per_week=assignment.frequency_per_week,
        status=assignment.status,
        notes=assignment.notes,
        workouts_logged=int(workouts_logged or 0),
        last_workout_at=last_workout,
        created_at=assignment.created_at,
        ended_at=assignment.ended_at,
    )


def create_assignment(
    session: Session,
    *,
    routine_id: UUID,
    member_id: UUID,
    start_date: date,
    end_date: date | None = None,
    frequency_per_week: int | None = None,
    trainer_id: UUID | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> AssignmentItem:
    routine = session.get(Routine, routine_id)
    if routine is None:
        raise RoutineNotFound("La rutina no existe")
    if routine.status == "archived":
        raise InvalidRoutineState("No se puede asignar una rutina archivada")
    if _item_count(session, routine) == 0:
        raise InvalidRoutineState("La rutina no tiene ejercicios configurados")
    member = _require_member(session, member_id)
    if member.status == "inactive":
        raise MemberNotEligible("El socio está inactivo")
    if trainer_id is not None:
        _require_employee(session, trainer_id)
    if end_date is not None and end_date < start_date:
        raise InvalidRoutineData("La fecha de fin no puede ser anterior a la de inicio")
    if frequency_per_week is not None and not (
        MIN_WEEKLY_FREQUENCY <= frequency_per_week <= MAX_WEEKLY_FREQUENCY
    ):
        raise InvalidRoutineData("La frecuencia semanal debe estar entre 1 y 7")

    existing = session.exec(
        select(RoutineAssignment).where(
            RoutineAssignment.member_id == member_id,
            RoutineAssignment.routine_id == routine_id,
            RoutineAssignment.status == "active",
        )
    ).first()
    if existing is not None:
        raise DuplicateAssignment("El socio ya tiene esta rutina asignada")

    occurred = _as_utc(now or utc_now())
    assignment = RoutineAssignment(
        routine_id=routine_id,
        routine_version=routine.version,
        member_id=member_id,
        trainer_id=trainer_id,
        assigned_by=actor_id,
        start_date=start_date,
        end_date=end_date,
        frequency_per_week=frequency_per_week,
        status="active",
        notes=(notes or "").strip() or None,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(assignment)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateAssignment("El socio ya tiene esta rutina asignada") from error
    session.refresh(assignment)
    return get_assignment(session, assignment.id).assignment


def get_assignment(session: Session, assignment_id: UUID) -> AssignmentDetail:
    row = session.exec(_assignment_rows(session, [RoutineAssignment.id == assignment_id])).first()
    if row is None:
        raise AssignmentNotFound("La asignación no existe")
    view = _assignment_view(row)
    return AssignmentDetail(
        assignment=view,
        routine_version=view.routine_version,
        plan=_routine_lines(session, view.routine_id, view.routine_version),
    )


def list_assignments(
    session: Session,
    *,
    member_id: UUID | None = None,
    routine_id: UUID | None = None,
    trainer_id: UUID | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> AssignmentPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    conditions: list = []
    if member_id is not None:
        conditions.append(RoutineAssignment.member_id == member_id)
    if routine_id is not None:
        conditions.append(RoutineAssignment.routine_id == routine_id)
    if trainer_id is not None:
        conditions.append(RoutineAssignment.trainer_id == trainer_id)
    if status in ASSIGNMENT_STATUSES:
        conditions.append(RoutineAssignment.status == status)
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Routine.name).like(like),
                func.lower(func.coalesce(Member.first_name, "")).like(like),
                func.lower(func.coalesce(Member.last_name, "")).like(like),
            )
        )

    count_statement = (
        select(func.count(RoutineAssignment.id))
        .select_from(RoutineAssignment)
        .join(Routine, Routine.id == RoutineAssignment.routine_id)
        .outerjoin(Member, Member.id == RoutineAssignment.member_id)
    )
    if conditions:
        count_statement = count_statement.where(*conditions)
    total = int(session.exec(count_statement).one() or 0)

    statement = _assignment_rows(session, conditions).order_by(
        RoutineAssignment.status, RoutineAssignment.created_at.desc()
    )
    rows = session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all()

    def _count(status: str) -> int:
        statement = (
            select(func.count(RoutineAssignment.id))
            .select_from(RoutineAssignment)
            .join(Routine, Routine.id == RoutineAssignment.routine_id)
            .outerjoin(Member, Member.id == RoutineAssignment.member_id)
            .where(RoutineAssignment.status == status)
        )
        return int(session.exec(statement).one() or 0)

    pages = (total + page_size - 1) // page_size if total else 1
    return AssignmentPage(
        items=[_assignment_view(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=AssignmentSummary(
            total=_count("active") + _count("completed") + _count("cancelled"),
            active=_count("active"),
            completed=_count("completed"),
            cancelled=_count("cancelled"),
        ),
    )


def _close_assignment(
    session: Session, assignment_id: UUID, *, status: str, now: datetime | None = None
) -> AssignmentItem:
    assignment = session.get(RoutineAssignment, assignment_id)
    if assignment is None:
        raise AssignmentNotFound("La asignación no existe")
    if assignment.status != "active":
        raise InvalidAssignmentState("La asignación ya está cerrada")
    occurred = _as_utc(now or utc_now())
    assignment.status = status
    assignment.ended_at = occurred
    assignment.updated_at = occurred
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return get_assignment(session, assignment_id).assignment


def complete_assignment(
    session: Session, assignment_id: UUID, *, now: datetime | None = None
) -> AssignmentItem:
    return _close_assignment(session, assignment_id, status="completed", now=now)


def cancel_assignment(
    session: Session, assignment_id: UUID, *, now: datetime | None = None
) -> AssignmentItem:
    return _close_assignment(session, assignment_id, status="cancelled", now=now)


# --------------------------------------------------------------------------- #
# Workouts
# --------------------------------------------------------------------------- #


def _workout_item(workout: WorkoutLog) -> WorkoutItem:
    return WorkoutItem(
        id=workout.id,
        assignment_id=workout.assignment_id,
        member_id=workout.member_id,
        routine_id=workout.routine_id,
        routine_version=workout.routine_version,
        performed_at=workout.performed_at,
        duration_minutes=workout.duration_minutes,
        perceived_effort=workout.perceived_effort,
        notes=workout.notes,
        status=workout.status,
        reviewed_at=workout.reviewed_at,
        created_at=workout.created_at,
    )


def log_workout(
    session: Session,
    assignment_id: UUID,
    *,
    performed_at: date,
    duration_minutes: int | None = None,
    perceived_effort: int | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> WorkoutItem:
    assignment = session.get(RoutineAssignment, assignment_id)
    if assignment is None:
        raise AssignmentNotFound("La asignación no existe")
    if assignment.status != "active":
        raise InvalidAssignmentState("Solo se registran entrenamientos de una asignación activa")
    occurred = _as_utc(now or utc_now())
    if performed_at > occurred.date():
        raise InvalidWorkoutData("No se puede registrar un entrenamiento en el futuro")
    if assignment.start_date is not None and performed_at < assignment.start_date:
        raise InvalidWorkoutData("El entrenamiento es anterior al inicio de la asignación")
    if duration_minutes is not None and duration_minutes < 0:
        raise InvalidWorkoutData("La duración no puede ser negativa")
    if perceived_effort is not None and not (MIN_EFFORT <= perceived_effort <= MAX_EFFORT):
        raise InvalidWorkoutData("El esfuerzo percibido debe estar entre 1 y 10")

    workout = WorkoutLog(
        assignment_id=assignment_id,
        member_id=assignment.member_id,
        routine_id=assignment.routine_id,
        routine_version=assignment.routine_version,
        performed_at=performed_at,
        duration_minutes=duration_minutes,
        perceived_effort=perceived_effort,
        notes=(notes or "").strip() or None,
        status="logged",
        logged_by=actor_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(workout)
    session.commit()
    session.refresh(workout)
    return _workout_item(workout)


def list_workouts(
    session: Session,
    *,
    assignment_id: UUID | None = None,
    member_id: UUID | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[WorkoutItem]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    statement = select(WorkoutLog)
    if assignment_id is not None:
        statement = statement.where(WorkoutLog.assignment_id == assignment_id)
    if member_id is not None:
        statement = statement.where(WorkoutLog.member_id == member_id)
    if status in ("logged", "reviewed"):
        statement = statement.where(WorkoutLog.status == status)
    statement = statement.order_by(WorkoutLog.performed_at.desc(), WorkoutLog.created_at.desc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    return [_workout_item(row) for row in session.exec(statement).all()]


def review_workout(
    session: Session, workout_id: UUID, *, actor_id: UUID | None = None, now: datetime | None = None
) -> WorkoutItem:
    workout = session.get(WorkoutLog, workout_id)
    if workout is None:
        raise WorkoutNotFound("El entrenamiento no existe")
    if workout.status == "reviewed":
        raise InvalidWorkoutState("El entrenamiento ya fue revisado")
    occurred = _as_utc(now or utc_now())
    workout.status = "reviewed"
    workout.reviewed_by = actor_id
    workout.reviewed_at = occurred
    workout.updated_at = occurred
    session.add(workout)
    session.commit()
    session.refresh(workout)
    return _workout_item(workout)


# --------------------------------------------------------------------------- #
# Body measurements and progress
# --------------------------------------------------------------------------- #


def _measurement_item(measurement: BodyMeasurement) -> MeasurementItem:
    return MeasurementItem(
        id=measurement.id,
        member_id=measurement.member_id,
        measured_at=_as_utc(measurement.measured_at),
        weight_kg=_as_float(measurement.weight_kg),
        waist_cm=_as_float(measurement.waist_cm),
        chest_cm=_as_float(measurement.chest_cm),
        body_fat_percent=_as_float(measurement.body_fat_percent),
        notes=measurement.notes,
        created_at=measurement.created_at,
    )


def record_measurement(
    session: Session,
    member_id: UUID,
    *,
    measured_at: datetime | None = None,
    weight_kg: float | None = None,
    waist_cm: float | None = None,
    chest_cm: float | None = None,
    body_fat_percent: float | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MeasurementItem:
    _require_member(session, member_id)
    if all(value is None for value in (weight_kg, waist_cm, chest_cm, body_fat_percent)):
        raise InvalidMeasurement("Registra al menos una medida (peso, cintura, pecho o grasa)")
    if weight_kg is not None and weight_kg <= 0:
        raise InvalidMeasurement("El peso debe ser mayor que cero")
    if waist_cm is not None and waist_cm <= 0:
        raise InvalidMeasurement("La cintura debe ser mayor que cero")
    if chest_cm is not None and chest_cm <= 0:
        raise InvalidMeasurement("El pecho debe ser mayor que cero")
    if body_fat_percent is not None and not (0 <= body_fat_percent <= 100):
        raise InvalidMeasurement("El porcentaje de grasa debe estar entre 0 y 100")

    occurred = _as_utc(now or utc_now())
    measured = _as_utc(measured_at) if measured_at is not None else occurred
    measurement = BodyMeasurement(
        member_id=member_id,
        measured_at=measured,
        weight_kg=weight_kg,
        waist_cm=waist_cm,
        chest_cm=chest_cm,
        body_fat_percent=body_fat_percent,
        notes=(notes or "").strip() or None,
        measured_by=actor_id,
        created_at=occurred,
    )
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return _measurement_item(measurement)


def list_measurements(
    session: Session,
    member_id: UUID,
    *,
    page: int = 1,
    page_size: int = MAX_MEASUREMENT_HISTORY,
) -> list[MeasurementItem]:
    _require_member(session, member_id)
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    statement = (
        select(BodyMeasurement)
        .where(BodyMeasurement.member_id == member_id)
        .order_by(BodyMeasurement.measured_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [_measurement_item(row) for row in session.exec(statement).all()]


def member_progress(
    session: Session,
    member_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberProgress:
    member = _require_member(session, member_id)
    occurred = _as_utc(now or utc_now())
    since = occurred - timedelta(days=30)

    active_assignments = int(
        session.exec(
            select(func.count(RoutineAssignment.id)).where(
                RoutineAssignment.member_id == member_id,
                RoutineAssignment.status == "active",
            )
        ).one()
        or 0
    )
    workouts_total = int(
        session.exec(
            select(func.count(WorkoutLog.id)).where(WorkoutLog.member_id == member_id)
        ).one()
        or 0
    )
    workouts_recent = int(
        session.exec(
            select(func.count(WorkoutLog.id)).where(
                WorkoutLog.member_id == member_id,
                WorkoutLog.performed_at >= since.date(),
            )
        ).one()
        or 0
    )
    last_workout_at = session.exec(
        select(func.max(WorkoutLog.performed_at)).where(WorkoutLog.member_id == member_id)
    ).one()
    measurements = list_measurements(session, member_id)
    return MemberProgress(
        member_id=member_id,
        member_name=_member_name(member),
        active_assignments=active_assignments,
        workouts_total=workouts_total,
        workouts_last_30_days=workouts_recent,
        last_workout_at=last_workout_at,
        latest_measurement=measurements[0] if measurements else None,
        measurements=measurements,
    )


def module_overview(session: Session, *, now: datetime | None = None) -> ModuleOverview:
    occurred = _as_utc(now or utc_now())
    since = (occurred - timedelta(days=7)).date()

    def _count(statement) -> int:
        return int(session.exec(statement).one() or 0)

    return ModuleOverview(
        exercises=_count(select(func.count(Exercise.id)).where(Exercise.is_active.is_(True))),
        routines_active=_count(
            select(func.count(Routine.id)).where(Routine.status == "active")
        ),
        routines_archived=_count(
            select(func.count(Routine.id)).where(Routine.status == "archived")
        ),
        assignments_active=_count(
            select(func.count(RoutineAssignment.id)).where(RoutineAssignment.status == "active")
        ),
        workouts_last_7_days=_count(
            select(func.count(WorkoutLog.id)).where(WorkoutLog.performed_at >= since)
        ),
    )
