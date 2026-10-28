"""Member self-service routines and progress.

The routines module owns authoring, assignment, measurements and goals. Here we
only expose what belongs to the authenticated member:

* the assignments (and the plan version frozen at assignment time) of that member;
* the workouts and measurements of that member;
* the member's progress and goals.

Members may log their own workouts, record their own measurements, create or
cancel the goals they created themselves and upload or delete their own
progress photos. All of it is marked with ``origin = "app"`` and goes through
the same rules as the staff panel; a member workout stays ``logged`` until a
trainer reviews it. Everything else (editing goals, closing assignments) stays
with the staff.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hmac
from hashlib import sha256
from uuid import UUID

from sqlmodel import Session, func, select

from app.modules.memberships.models import Member, MemberConsent
from app.modules.portal.service import MemberPortalError, signing_secret
from app.modules.routines import (
    AssignmentItem,
    AssignmentNotFound,
    GoalNotFound,
    InvalidGoalState,
    MeasurementItem,
    MemberGoal,
    MemberGoalItem,
    ProgressPhotoItem,
    Routine,
    RoutineAssignment,
    RoutineLine,
    WorkoutItem,
    WorkoutSetInput,
    cancel_member_goal,
    create_member_goal,
    delete_progress_photo,
    get_assignment,
    list_assignments,
    list_member_goals,
    list_progress_photos,
    list_workouts,
    log_workout,
    member_progress,
    record_measurement,
    record_progress_photo,
)

MAX_MEMBER_ASSIGNMENTS = 100
MAX_MEMBER_WORKOUTS = 10

PROGRESS_PHOTO_CONSENT_TYPE = "progress_photos"
PROGRESS_PHOTO_CONSENT_VERSION = "fotos-progreso-v1"
PHOTO_LINK_LIFETIME = timedelta(minutes=10)


class ProgressPhotoConsentRequired(MemberPortalError):
    """The member has not authorised storing their progress photos yet."""


class InvalidProgressPhotoLink(MemberPortalError):
    """The signed photo link is malformed, forged or expired."""


@dataclass(frozen=True)
class MemberAssignmentSummary:
    id: UUID
    routine_id: UUID
    routine_name: str
    routine_version: int
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
class MemberRoutineList:
    items: list[MemberAssignmentSummary]
    total: int
    active: int
    completed: int
    cancelled: int


@dataclass(frozen=True)
class MemberRoutineDetail:
    assignment: MemberAssignmentSummary
    objective: str | None
    plan: list[RoutineLine]
    workouts: list[WorkoutItem]


@dataclass(frozen=True)
class MemberProgressView:
    workouts_total: int
    workouts_last_30_days: int
    last_workout_at: date | None
    latest_measurement: MeasurementItem | None
    measurements: list[MeasurementItem]
    goals: list[MemberGoalItem]


@dataclass(frozen=True)
class MemberProgressPhotos:
    items: list[ProgressPhotoItem]
    consent_recorded: bool


def list_member_routines(session: Session, member_id: UUID) -> MemberRoutineList:
    _require_member(session, member_id)
    page = list_assignments(
        session,
        member_id=member_id,
        page=1,
        page_size=MAX_MEMBER_ASSIGNMENTS,
    )
    counts = _assignment_counts(session, member_id)
    items = sorted(
        (_assignment_summary(item) for item in page.items),
        key=lambda item: (item.status != "active", -item.created_at.timestamp()),
    )
    return MemberRoutineList(
        items=items,
        total=sum(counts.values()),
        active=counts.get("active", 0),
        completed=counts.get("completed", 0),
        cancelled=counts.get("cancelled", 0),
    )


def get_member_routine(
    session: Session,
    member_id: UUID,
    assignment_id: UUID,
) -> MemberRoutineDetail:
    assignment = session.get(RoutineAssignment, assignment_id)
    if assignment is None or assignment.member_id != member_id:
        raise AssignmentNotFound("La rutina asignada no existe")
    detail = get_assignment(session, assignment_id)
    routine = session.get(Routine, assignment.routine_id)
    return MemberRoutineDetail(
        assignment=_assignment_summary(detail.assignment),
        objective=routine.objective if routine is not None else None,
        plan=detail.plan,
        workouts=list_workouts(
            session,
            assignment_id=assignment_id,
            page=1,
            page_size=MAX_MEMBER_WORKOUTS,
        ),
    )


def get_member_progress(
    session: Session,
    member_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberProgressView:
    progress = member_progress(session, member_id, now=now)
    return MemberProgressView(
        workouts_total=progress.workouts_total,
        workouts_last_30_days=progress.workouts_last_30_days,
        last_workout_at=progress.last_workout_at,
        latest_measurement=progress.latest_measurement,
        measurements=progress.measurements,
        goals=list_member_goals(session, member_id),
    )


def log_member_workout(
    session: Session,
    member_id: UUID,
    assignment_id: UUID,
    *,
    performed_at: date,
    duration_minutes: int | None = None,
    perceived_effort: int | None = None,
    notes: str | None = None,
    sets: list[WorkoutSetInput] | None = None,
    now: datetime | None = None,
) -> WorkoutItem:
    assignment = session.get(RoutineAssignment, assignment_id)
    if assignment is None or assignment.member_id != member_id:
        raise AssignmentNotFound("La rutina asignada no existe")
    return log_workout(
        session,
        assignment_id,
        performed_at=performed_at,
        duration_minutes=duration_minutes,
        perceived_effort=perceived_effort,
        notes=notes,
        sets=sets,
        origin="app",
        now=now,
    )


def record_member_measurement(
    session: Session,
    member_id: UUID,
    *,
    measured_at: datetime | None = None,
    weight_kg: float | None = None,
    waist_cm: float | None = None,
    chest_cm: float | None = None,
    body_fat_percent: float | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> MeasurementItem:
    _require_member(session, member_id)
    return record_measurement(
        session,
        member_id,
        measured_at=measured_at,
        weight_kg=weight_kg,
        waist_cm=waist_cm,
        chest_cm=chest_cm,
        body_fat_percent=body_fat_percent,
        notes=notes,
        origin="app",
        now=now,
    )


def create_member_goal_from_app(
    session: Session,
    member_id: UUID,
    *,
    metric: str,
    direction: str,
    target_value: float,
    target_date: date | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> MemberGoalItem:
    return create_member_goal(
        session,
        member_id,
        metric=metric,
        direction=direction,
        target_value=target_value,
        target_date=target_date,
        notes=notes,
        origin="app",
        now=now,
    )


def cancel_member_goal_from_app(
    session: Session,
    member_id: UUID,
    goal_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberGoalItem:
    goal = session.get(MemberGoal, goal_id)
    if goal is None or goal.member_id != member_id:
        raise GoalNotFound("La meta no existe")
    if goal.origin != "app":
        raise InvalidGoalState("La meta la creó el personal; cancélala en recepción")
    return cancel_member_goal(session, goal_id, now=now)


def list_member_progress_photos(session: Session, member_id: UUID) -> MemberProgressPhotos:
    _require_member(session, member_id)
    return MemberProgressPhotos(
        items=list_progress_photos(session, member_id),
        consent_recorded=_has_progress_photo_consent(session, member_id),
    )


def record_member_progress_photo(
    session: Session,
    member_id: UUID,
    *,
    data: bytes,
    content_type: str | None,
    angle: str,
    captured_at: datetime | None = None,
    notes: str | None = None,
    consent: bool = False,
    now: datetime | None = None,
) -> ProgressPhotoItem:
    _require_member(session, member_id)
    if not _has_progress_photo_consent(session, member_id):
        if not consent:
            raise ProgressPhotoConsentRequired(
                "Autoriza el uso de tus fotos de progreso antes de subirlas."
            )
        session.add(
            MemberConsent(
                member_id=member_id,
                consent_type=PROGRESS_PHOTO_CONSENT_TYPE,
                document_version=PROGRESS_PHOTO_CONSENT_VERSION,
                accepted_at=now or datetime.now(timezone.utc),
            )
        )
    try:
        return record_progress_photo(
            session,
            member_id,
            data=data,
            content_type=content_type,
            angle=angle,
            captured_at=captured_at,
            notes=notes,
            origin="app",
            now=now,
        )
    except Exception:
        # Do not keep a consent for a photo that was never stored.
        session.rollback()
        raise


def progress_photo_link(photo_id: UUID, *, now: datetime | None = None) -> str:
    expires_at_epoch = int(
        ((now or datetime.now(timezone.utc)) + PHOTO_LINK_LIFETIME).timestamp()
    )
    signature = _sign_progress_photo(photo_id, expires_at_epoch)
    return (
        f"/member/progress/photos/{photo_id}/file"
        f"?exp={expires_at_epoch}&sig={signature}"
    )


def verify_progress_photo_link(
    photo_id: UUID,
    expires_at_epoch: int,
    signature: str,
    *,
    now: datetime | None = None,
) -> None:
    occurred_at = now or datetime.now(timezone.utc)
    if expires_at_epoch < int(occurred_at.timestamp()):
        raise InvalidProgressPhotoLink("El enlace de la foto no es válido o expiró")
    expected = _sign_progress_photo(photo_id, expires_at_epoch)
    if not hmac.compare_digest(expected, signature):
        raise InvalidProgressPhotoLink("El enlace de la foto no es válido o expiró")


def _sign_progress_photo(photo_id: UUID, expires_at_epoch: int) -> str:
    message = f"photo:{photo_id}:{expires_at_epoch}".encode("utf-8")
    return hmac.new(signing_secret(), message, sha256).hexdigest()


def delete_member_progress_photo(session: Session, member_id: UUID, photo_id: UUID) -> None:
    delete_progress_photo(session, photo_id, member_id=member_id)


def _has_progress_photo_consent(session: Session, member_id: UUID) -> bool:
    statement = (
        select(MemberConsent.id)
        .where(
            MemberConsent.member_id == member_id,
            MemberConsent.consent_type == PROGRESS_PHOTO_CONSENT_TYPE,
            MemberConsent.revoked_at.is_(None),
        )
        .limit(1)
    )
    return session.exec(statement).first() is not None


def _assignment_counts(session: Session, member_id: UUID) -> dict[str, int]:
    rows = session.exec(
        select(RoutineAssignment.status, func.count(RoutineAssignment.id))
        .where(RoutineAssignment.member_id == member_id)
        .group_by(RoutineAssignment.status)
    ).all()
    return {status: int(count) for status, count in rows}


def _assignment_summary(item: AssignmentItem) -> MemberAssignmentSummary:
    return MemberAssignmentSummary(
        id=item.id,
        routine_id=item.routine_id,
        routine_name=item.routine_name,
        routine_version=item.routine_version,
        trainer_name=item.trainer_name,
        start_date=item.start_date,
        end_date=item.end_date,
        frequency_per_week=item.frequency_per_week,
        status=item.status,
        notes=item.notes,
        workouts_logged=item.workouts_logged,
        last_workout_at=item.last_workout_at,
        created_at=item.created_at,
        ended_at=item.ended_at,
    )


def _require_member(session: Session, member_id: UUID) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise MemberPortalError("Socio no encontrado")
    return member
