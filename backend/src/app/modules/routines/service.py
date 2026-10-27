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
  replaces an earlier measurement;
* a goal freezes its starting measurement as the baseline and is closed
  automatically when a later measurement meets the target. Achieving a goal
  never reopens it, even if the member later moves away from the target;
* a progress photo is validated by its actual bytes (not by the declared
  content type or filename) and stored outside the database under a random
  key. The row keeps only metadata.

No money is involved in this module. Per-set workout detail and trainer-member
messaging are out of scope (see ``docs/deuda-tecnica.md``).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.identity.models import Employee
from app.modules.memberships.models import Member
from app.modules.notifications import (
    notify_goal_achieved,
    notify_goal_cancelled_by_staff,
    notify_goal_updated_by_staff,
    notify_trainer_pending_workout,
    notify_workout_reviewed,
)
from app.modules.routines.models import (
    ASSIGNMENT_STATUSES,
    GOAL_DIRECTIONS,
    GOAL_METRICS,
    GOAL_STATUSES,
    MAX_EFFORT,
    MAX_SET_NUMBER,
    MAX_SET_REPS,
    MAX_SET_WEIGHT_KG,
    MAX_WEEKLY_FREQUENCY,
    MAX_WORKOUT_SETS,
    MIN_EFFORT,
    MIN_SET_NUMBER,
    MIN_SET_REPS,
    MIN_WEEKLY_FREQUENCY,
    PROGRESS_PHOTO_ANGLES,
    PROGRESS_PHOTO_CONTENT_TYPES,
    ROUTINE_STATUSES,
    BodyMeasurement,
    Exercise,
    MemberGoal,
    ProgressPhoto,
    Routine,
    RoutineAssignment,
    RoutineItem,
    RoutineRevision,
    WorkoutLog,
    WorkoutSet,
    utc_now,
)
from app.modules.routines.photo_storage import (
    MAX_PROGRESS_PHOTO_BYTES,
    delete_photo,
    photo_path,
    save_photo,
)
from app.timezone import club_date

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_MEASUREMENT_HISTORY = 36
MAX_GOAL_NOTES = 300
MAX_PROGRESS_PHOTO_NOTES = 300
MAX_PROGRESS_PHOTO_HISTORY = 100

_GOAL_METRIC_COLUMNS = {
    "weight_kg": BodyMeasurement.weight_kg,
    "waist_cm": BodyMeasurement.waist_cm,
    "chest_cm": BodyMeasurement.chest_cm,
    "body_fat_percent": BodyMeasurement.body_fat_percent,
}
_GOAL_METRIC_LABELS = {
    "weight_kg": "peso",
    "waist_cm": "cintura",
    "chest_cm": "pecho",
    "body_fat_percent": "grasa corporal",
}
_GOAL_METRIC_UNITS = {
    "weight_kg": "kg",
    "waist_cm": "cm",
    "chest_cm": "cm",
    "body_fat_percent": "%",
}

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


class GoalNotFound(RoutinesError):
    pass


class InvalidGoalData(RoutinesError):
    pass


class DuplicateActiveGoal(RoutinesError):
    pass


class InvalidGoalState(RoutinesError):
    pass


class InvalidProgressPhoto(RoutinesError):
    pass


class ProgressPhotoTooLarge(InvalidProgressPhoto):
    pass


class ProgressPhotoNotFound(RoutinesError):
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
class WorkoutSetInput:
    exercise_id: UUID
    set_number: int
    reps: int
    weight_kg: float | None = None


@dataclass(frozen=True)
class WorkoutSetItem:
    exercise_id: UUID
    exercise_name: str
    position: int
    set_number: int
    reps: int
    weight_kg: float | None


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
    origin: str
    reviewed_at: datetime | None
    created_at: datetime
    sets: list[WorkoutSetItem]


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
    origin: str
    created_at: datetime


@dataclass(frozen=True)
class ProgressPhotoItem:
    id: UUID
    member_id: UUID
    angle: str
    captured_at: datetime
    notes: str | None
    content_type: str
    byte_size: int
    created_at: datetime


@dataclass(frozen=True)
class ProgressPhotoFile:
    photo: ProgressPhotoItem
    path: Path


@dataclass(frozen=True)
class MemberGoalItem:
    id: UUID
    member_id: UUID
    metric: str
    direction: str
    target_value: float
    baseline_value: float | None
    baseline_measured_at: datetime | None
    target_date: date | None
    notes: str | None
    status: str
    origin: str
    current_value: float | None
    current_measured_at: datetime | None
    progress_percent: int | None
    achieved: bool
    achieved_value: float | None
    achieved_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


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


def _workout_sets_by_workout(
    session: Session, workout_ids: list[UUID]
) -> dict[UUID, list[WorkoutSetItem]]:
    if not workout_ids:
        return {}
    rows = session.exec(
        select(WorkoutSet, Exercise.name, RoutineItem.position)
        .join(WorkoutLog, WorkoutLog.id == WorkoutSet.workout_id)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .join(
            RoutineItem,
            (RoutineItem.routine_id == WorkoutLog.routine_id)
            & (RoutineItem.version == WorkoutLog.routine_version)
            & (RoutineItem.exercise_id == WorkoutSet.exercise_id),
        )
        .where(WorkoutSet.workout_id.in_(workout_ids))
        .order_by(WorkoutSet.workout_id, RoutineItem.position, WorkoutSet.set_number)
    ).all()
    grouped: dict[UUID, list[WorkoutSetItem]] = {}
    for workout_set, exercise_name, position in rows:
        grouped.setdefault(workout_set.workout_id, []).append(
            WorkoutSetItem(
                exercise_id=workout_set.exercise_id,
                exercise_name=exercise_name,
                position=position,
                set_number=workout_set.set_number,
                reps=workout_set.reps,
                weight_kg=(
                    float(workout_set.weight_kg) if workout_set.weight_kg is not None else None
                ),
            )
        )
    return grouped


def _workout_item(workout: WorkoutLog, sets: list[WorkoutSetItem] | None = None) -> WorkoutItem:
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
        origin=workout.origin,
        reviewed_at=workout.reviewed_at,
        created_at=workout.created_at,
        sets=list(sets or []),
    )


def _validate_workout_sets(
    session: Session, assignment: RoutineAssignment, sets: list[WorkoutSetInput] | None
) -> list[WorkoutSetInput]:
    if not sets:
        return []
    if len(sets) > MAX_WORKOUT_SETS:
        raise InvalidWorkoutData(
            f"Un entrenamiento admite como máximo {MAX_WORKOUT_SETS} series"
        )
    planned = set(
        session.exec(
            select(RoutineItem.exercise_id).where(
                RoutineItem.routine_id == assignment.routine_id,
                RoutineItem.version == assignment.routine_version,
            )
        ).all()
    )
    seen: set[tuple[UUID, int]] = set()
    for item in sets:
        if item.exercise_id not in planned:
            raise InvalidWorkoutData(
                "El ejercicio no pertenece a la versión de la rutina asignada"
            )
        if not (MIN_SET_NUMBER <= item.set_number <= MAX_SET_NUMBER):
            raise InvalidWorkoutData(
                f"El número de serie debe estar entre {MIN_SET_NUMBER} y {MAX_SET_NUMBER}"
            )
        if not (MIN_SET_REPS <= item.reps <= MAX_SET_REPS):
            raise InvalidWorkoutData(
                f"Las repeticiones deben estar entre {MIN_SET_REPS} y {MAX_SET_REPS}"
            )
        if item.weight_kg is not None and not (0 <= item.weight_kg <= MAX_SET_WEIGHT_KG):
            raise InvalidWorkoutData(
                f"El peso debe estar entre 0 y {MAX_SET_WEIGHT_KG} kg"
            )
        key = (item.exercise_id, item.set_number)
        if key in seen:
            raise InvalidWorkoutData("La serie está repetida para el mismo ejercicio")
        seen.add(key)
    return sets


def log_workout(
    session: Session,
    assignment_id: UUID,
    *,
    performed_at: date,
    duration_minutes: int | None = None,
    perceived_effort: int | None = None,
    notes: str | None = None,
    sets: list[WorkoutSetInput] | None = None,
    actor_id: UUID | None = None,
    origin: str = "staff",
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
    validated_sets = _validate_workout_sets(session, assignment, sets)

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
        origin=origin,
        logged_by=actor_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(workout)
    session.flush()
    for item in validated_sets:
        session.add(
            WorkoutSet(
                workout_id=workout.id,
                exercise_id=item.exercise_id,
                set_number=item.set_number,
                reps=item.reps,
                weight_kg=item.weight_kg,
                created_at=occurred,
            )
        )
    if origin == "app":
        # A workout the member logged themselves is work for the trainer named on
        # the assignment; a workout the staff logged is already being watched.
        member = session.get(Member, assignment.member_id)
        routine = session.get(Routine, assignment.routine_id)
        notify_trainer_pending_workout(
            session,
            trainer_employee_id=assignment.trainer_id,
            member_label=_member_name(member),
            workout_id=workout.id,
            performed_on=performed_at,
            routine_name=routine.name if routine is not None else None,
            now=occurred,
        )
    session.commit()
    session.refresh(workout)
    sets_by_workout = _workout_sets_by_workout(session, [workout.id])
    return _workout_item(workout, sets_by_workout.get(workout.id))


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
    workouts = session.exec(statement).all()
    sets_by_workout = _workout_sets_by_workout(session, [workout.id for workout in workouts])
    return [_workout_item(workout, sets_by_workout.get(workout.id)) for workout in workouts]


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
    routine = session.get(Routine, workout.routine_id)
    notify_workout_reviewed(
        session,
        member_id=workout.member_id,
        workout_id=workout.id,
        performed_on=workout.performed_at,
        routine_name=routine.name if routine is not None else None,
        now=occurred,
    )
    session.commit()
    session.refresh(workout)
    sets_by_workout = _workout_sets_by_workout(session, [workout.id])
    return _workout_item(workout, sets_by_workout.get(workout.id))


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
        origin=measurement.origin,
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
    origin: str = "staff",
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
        origin=origin,
        created_at=occurred,
    )
    session.add(measurement)
    session.flush()
    _apply_goal_updates(session, member_id, measurement=measurement, now=occurred)
    session.commit()
    session.refresh(measurement)
    return _measurement_item(measurement)


# --------------------------------------------------------------------------- #
# Goals
# --------------------------------------------------------------------------- #


def _latest_goal_measurement(
    session: Session, member_id: UUID, metric: str
) -> BodyMeasurement | None:
    column = _GOAL_METRIC_COLUMNS[metric]
    return session.exec(
        select(BodyMeasurement)
        .where(BodyMeasurement.member_id == member_id, column.is_not(None))
        .order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.created_at.desc())
    ).first()


def _goal_measurement_value(
    measurement: BodyMeasurement | None, metric: str
) -> float | None:
    if measurement is None:
        return None
    return _as_float(getattr(measurement, metric))


def _goal_target_reached(goal: MemberGoal, value: float) -> bool:
    target = _as_float(goal.target_value)
    if target is None:
        return False
    return _target_reached(goal.direction, target, value)


def _target_reached(direction: str, target: float, value: float) -> bool:
    if direction == "decrease":
        return value <= target
    return value >= target


def _goal_progress(goal: MemberGoal, current: float | None) -> tuple[bool, int | None]:
    if goal.status == "achieved":
        return True, 100
    baseline = _as_float(goal.baseline_value)
    target = _as_float(goal.target_value)
    if current is None or baseline is None or target is None:
        return False, None
    if goal.direction == "decrease":
        span = baseline - target
        percent = (
            100.0
            if _goal_target_reached(goal, current)
            else ((baseline - current) / span * 100 if span > 0 else 0.0)
        )
    else:
        span = target - baseline
        percent = (
            100.0
            if _goal_target_reached(goal, current)
            else ((current - baseline) / span * 100 if span > 0 else 0.0)
        )
    return False, max(0, min(100, round(percent)))


def _goal_item(goal: MemberGoal, latest: BodyMeasurement | None) -> MemberGoalItem:
    current = _goal_measurement_value(latest, goal.metric)
    _, progress = _goal_progress(goal, current)
    return MemberGoalItem(
        id=goal.id,
        member_id=goal.member_id,
        metric=goal.metric,
        direction=goal.direction,
        target_value=_as_float(goal.target_value) or 0.0,
        baseline_value=_as_float(goal.baseline_value),
        baseline_measured_at=(
            _as_utc(goal.baseline_measured_at)
            if goal.baseline_measured_at is not None
            else None
        ),
        target_date=goal.target_date,
        notes=goal.notes,
        status=goal.status,
        origin=goal.origin,
        current_value=current,
        current_measured_at=(
            _as_utc(latest.measured_at) if latest is not None else None
        ),
        progress_percent=progress,
        achieved=goal.status == "achieved",
        achieved_value=_as_float(goal.achieved_value),
        achieved_at=(
            _as_utc(goal.achieved_at) if goal.achieved_at is not None else None
        ),
        cancelled_at=(
            _as_utc(goal.cancelled_at) if goal.cancelled_at is not None else None
        ),
        created_at=_as_utc(goal.created_at),
        updated_at=_as_utc(goal.updated_at),
    )


def _goal_view(session: Session, goal: MemberGoal) -> MemberGoalItem:
    return _goal_item(
        goal, _latest_goal_measurement(session, goal.member_id, goal.metric)
    )


def _require_goal(session: Session, goal_id: UUID) -> MemberGoal:
    goal = session.get(MemberGoal, goal_id)
    if goal is None:
        raise GoalNotFound("La meta no existe")
    return goal


def _validate_goal_target(metric: str, target_value: float) -> float:
    target = float(target_value)
    if target <= 0:
        raise InvalidGoalData("El objetivo debe ser mayor que cero")
    if metric == "body_fat_percent" and target > 100:
        raise InvalidGoalData("La grasa corporal objetivo debe estar entre 0 y 100")
    if target > 1000:
        raise InvalidGoalData("El objetivo es demasiado alto")
    return target


def _clean_goal_notes(notes: str | None) -> str | None:
    clean = (notes or "").strip() or None
    if clean is not None and len(clean) > MAX_GOAL_NOTES:
        raise InvalidGoalData(
            f"La nota de la meta no puede exceder {MAX_GOAL_NOTES} caracteres"
        )
    return clean


def _goal_value_text(metric: str, value: object) -> str:
    """A goal number the way the member reads it: ``72.5 kg``, not ``Decimal``."""

    return f"{float(value):g} {_GOAL_METRIC_UNITS[metric]}"


def _apply_goal_updates(
    session: Session,
    member_id: UUID,
    *,
    measurement: BodyMeasurement,
    now: datetime,
) -> None:
    goals = session.exec(
        select(MemberGoal).where(
            MemberGoal.member_id == member_id,
            MemberGoal.status == "active",
        )
    ).all()
    for goal in goals:
        value = _goal_measurement_value(measurement, goal.metric)
        if value is None:
            continue
        if goal.baseline_value is None:
            goal.baseline_value = value
            goal.baseline_measured_at = _as_utc(measurement.measured_at)
        latest = _latest_goal_measurement(session, member_id, goal.metric)
        current = _goal_measurement_value(latest, goal.metric)
        if current is None or not _goal_target_reached(goal, current):
            continue
        goal.status = "achieved"
        goal.achieved_value = current
        goal.achieved_at = now
        goal.updated_at = now
        session.add(goal)
        notify_goal_achieved(
            session,
            member_id=member_id,
            goal_id=goal.id,
            metric_label=_GOAL_METRIC_LABELS[goal.metric],
            target_text=_goal_value_text(goal.metric, goal.target_value),
            achieved_text=_goal_value_text(goal.metric, current),
            now=now,
        )


def create_member_goal(
    session: Session,
    member_id: UUID,
    *,
    metric: str,
    direction: str,
    target_value: float,
    target_date: date | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    origin: str = "staff",
    now: datetime | None = None,
) -> MemberGoalItem:
    member = _require_member(session, member_id)
    if member.status == "inactive":
        raise MemberNotEligible("El socio está inactivo")
    if metric not in GOAL_METRICS:
        raise InvalidGoalData("La medida de la meta no es válida")
    if direction not in GOAL_DIRECTIONS:
        raise InvalidGoalData("La dirección de la meta no es válida")
    target = _validate_goal_target(metric, target_value)
    occurred = _as_utc(now or utc_now())
    if target_date is not None and target_date < club_date(occurred):
        raise InvalidGoalData("La fecha objetivo no puede ser anterior a hoy")
    existing = session.exec(
        select(MemberGoal).where(
            MemberGoal.member_id == member_id,
            MemberGoal.metric == metric,
            MemberGoal.status == "active",
        )
    ).first()
    if existing is not None:
        label = _GOAL_METRIC_LABELS[metric]
        raise DuplicateActiveGoal(f"Ya hay una meta activa de {label}")

    latest = _latest_goal_measurement(session, member_id, metric)
    baseline = _goal_measurement_value(latest, metric)
    if baseline is not None and _target_reached(direction, target, baseline):
        label = _GOAL_METRIC_LABELS[metric]
        raise InvalidGoalData(
            f"La meta ya se cumple con la última medición de {label}; elige un objetivo más exigente"
        )

    goal = MemberGoal(
        member_id=member_id,
        metric=metric,
        direction=direction,
        target_value=target,
        baseline_value=baseline,
        baseline_measured_at=(
            _as_utc(latest.measured_at) if latest is not None else None
        ),
        target_date=target_date,
        notes=_clean_goal_notes(notes),
        status="active",
        origin=origin,
        created_by=actor_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(goal)
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - race on the partial unique index
        session.rollback()
        raise DuplicateActiveGoal("Ya hay una meta activa de esa medida") from error
    session.refresh(goal)
    return _goal_view(session, goal)


def update_member_goal(
    session: Session,
    goal_id: UUID,
    *,
    target_value: float | None = None,
    target_date: date | None = UNSET,  # type: ignore[assignment]
    notes: str | None = UNSET,  # type: ignore[assignment]
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MemberGoalItem:
    goal = _require_goal(session, goal_id)
    if goal.status != "active":
        raise InvalidGoalState("Solo se puede editar una meta activa")

    occurred = _as_utc(now or utc_now())
    previous_target = float(goal.target_value)
    previous_date = goal.target_date
    changed_target_text: str | None = None
    if target_value is not None:
        target = _validate_goal_target(goal.metric, target_value)
        latest = _latest_goal_measurement(session, goal.member_id, goal.metric)
        current = _goal_measurement_value(latest, goal.metric)
        if current is not None and _target_reached(goal.direction, target, current):
            label = _GOAL_METRIC_LABELS[goal.metric]
            raise InvalidGoalData(
                f"La meta ya se cumple con la última medición de {label}; elige un objetivo más exigente"
            )
        goal.target_value = target
        if target != previous_target:
            changed_target_text = _goal_value_text(goal.metric, target)
    if target_date is not UNSET:
        if target_date is not None and target_date < club_date(occurred):
            raise InvalidGoalData("La fecha objetivo no puede ser anterior a hoy")
        goal.target_date = target_date
    if notes is not UNSET:
        goal.notes = _clean_goal_notes(notes)

    changed_date = goal.target_date if goal.target_date != previous_date else None
    goal.updated_at = occurred
    session.add(goal)
    if actor_id is not None and (changed_target_text or changed_date):
        notify_goal_updated_by_staff(
            session,
            member_id=goal.member_id,
            goal_id=goal.id,
            metric_label=_GOAL_METRIC_LABELS[goal.metric],
            new_target_text=changed_target_text,
            new_target_date=changed_date,
            now=occurred,
        )
    session.commit()
    session.refresh(goal)
    return _goal_view(session, goal)


def cancel_member_goal(
    session: Session,
    goal_id: UUID,
    *,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MemberGoalItem:
    goal = _require_goal(session, goal_id)
    if goal.status != "active":
        raise InvalidGoalState("Solo se puede cancelar una meta activa")
    occurred = _as_utc(now or utc_now())
    goal.status = "cancelled"
    goal.cancelled_at = occurred
    goal.cancelled_by = actor_id
    goal.updated_at = occurred
    session.add(goal)
    if actor_id is not None:
        notify_goal_cancelled_by_staff(
            session,
            member_id=goal.member_id,
            goal_id=goal.id,
            metric_label=_GOAL_METRIC_LABELS[goal.metric],
            now=occurred,
        )
    session.commit()
    session.refresh(goal)
    return _goal_view(session, goal)


def list_member_goals(
    session: Session,
    member_id: UUID,
    *,
    status: str | None = None,
) -> list[MemberGoalItem]:
    _require_member(session, member_id)
    if status is not None and status not in GOAL_STATUSES:
        raise InvalidGoalData("El estado de la meta no es válido")
    statement = select(MemberGoal).where(MemberGoal.member_id == member_id)
    if status is not None:
        statement = statement.where(MemberGoal.status == status)
    order = case(
        (MemberGoal.status == "active", 0),
        (MemberGoal.status == "achieved", 1),
        else_=2,
    )
    goals = session.exec(
        statement.order_by(order, MemberGoal.created_at.desc())
    ).all()
    return [
        _goal_item(goal, _latest_goal_measurement(session, member_id, goal.metric))
        for goal in goals
    ]


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


# --------------------------------------------------------------------------- #
# Progress photos
# --------------------------------------------------------------------------- #


def _progress_photo_item(photo: ProgressPhoto) -> ProgressPhotoItem:
    return ProgressPhotoItem(
        id=photo.id,
        member_id=photo.member_id,
        angle=photo.angle,
        captured_at=_as_utc(photo.captured_at),
        notes=photo.notes,
        content_type=photo.content_type,
        byte_size=photo.byte_size,
        created_at=_as_utc(photo.created_at),
    )


def _clean_progress_photo_notes(notes: str | None) -> str | None:
    clean = (notes or "").strip() or None
    if clean is not None and len(clean) > MAX_PROGRESS_PHOTO_NOTES:
        raise InvalidProgressPhoto(
            f"La nota de la foto no puede exceder {MAX_PROGRESS_PHOTO_NOTES} caracteres"
        )
    return clean


def _require_progress_photo(session: Session, photo_id: UUID) -> ProgressPhoto:
    photo = session.get(ProgressPhoto, photo_id)
    if photo is None:
        raise ProgressPhotoNotFound("La foto no existe")
    return photo


def record_progress_photo(
    session: Session,
    member_id: UUID,
    *,
    data: bytes,
    content_type: str | None,
    angle: str,
    captured_at: datetime | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ProgressPhotoItem:
    _require_member(session, member_id)
    if angle not in PROGRESS_PHOTO_ANGLES:
        raise InvalidProgressPhoto("El ángulo de la foto no es válido")
    declared_type = (content_type or "").split(";", 1)[0].strip().lower()
    if declared_type not in PROGRESS_PHOTO_CONTENT_TYPES:
        raise InvalidProgressPhoto("La foto debe ser JPEG, PNG o WebP")
    if not data:
        raise InvalidProgressPhoto("La imagen está vacía")
    if len(data) > MAX_PROGRESS_PHOTO_BYTES:
        limit_mb = MAX_PROGRESS_PHOTO_BYTES // (1024 * 1024)
        raise ProgressPhotoTooLarge(f"La imagen no puede superar {limit_mb} MB")
    clean_notes = _clean_progress_photo_notes(notes)
    occurred = _as_utc(now or utc_now())
    captured = _as_utc(captured_at) if captured_at is not None else occurred

    try:
        stored = save_photo(data, declared_type)
    except ValueError as error:
        raise InvalidProgressPhoto(str(error)) from error

    photo = ProgressPhoto(
        member_id=member_id,
        angle=angle,
        captured_at=captured,
        notes=clean_notes,
        content_type=stored.content_type,
        byte_size=stored.byte_size,
        storage_key=stored.key,
        uploaded_by=actor_id,
        created_at=occurred,
    )
    session.add(photo)
    try:
        session.commit()
    except Exception:
        session.rollback()
        delete_photo(stored.key)
        raise
    session.refresh(photo)
    return _progress_photo_item(photo)


def list_progress_photos(session: Session, member_id: UUID) -> list[ProgressPhotoItem]:
    _require_member(session, member_id)
    photos = session.exec(
        select(ProgressPhoto)
        .where(ProgressPhoto.member_id == member_id)
        .order_by(ProgressPhoto.captured_at.desc(), ProgressPhoto.created_at.desc())
        .limit(MAX_PROGRESS_PHOTO_HISTORY)
    ).all()
    return [_progress_photo_item(photo) for photo in photos]


def progress_photo_file(session: Session, photo_id: UUID) -> ProgressPhotoFile:
    photo = _require_progress_photo(session, photo_id)
    try:
        path = photo_path(photo.storage_key)
    except ValueError as error:
        raise ProgressPhotoNotFound("El archivo de la foto no está disponible") from error
    if not path.is_file():
        raise ProgressPhotoNotFound("El archivo de la foto no está disponible")
    return ProgressPhotoFile(photo=_progress_photo_item(photo), path=path)


def delete_progress_photo(session: Session, photo_id: UUID) -> None:
    photo = _require_progress_photo(session, photo_id)
    storage_key = photo.storage_key
    session.delete(photo)
    session.commit()
    try:
        delete_photo(storage_key)
    except (OSError, ValueError):
        # The row is already gone; an orphaned file is preferable to failing a
        # deletion the caller can no longer retry.
        pass


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
