from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import TypeVar
from uuid import UUID, uuid4

from sqlmodel import Session, SQLModel, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.identity.models import AppUser, Employee
from app.modules.identity.service import user_ids_with_permission, user_ids_with_role
from app.modules.notifications.models import StaffNotification
from app.modules.notifications.service import (
    create_staff_notification,
    resolve_staff_notifications,
    staff_user_for_employee,
)
from app.modules.staffing.models import (
    AttendanceEvent,
    StaffAttendance,
    StaffAttendanceRequest,
    StaffShift,
    StaffingSettings,
    StaffingSettingsEvent,
    utc_now,
)
from app.timezone import to_club_timezone


_RecordT = TypeVar("_RecordT", bound=SQLModel)

# People usually arrive a few minutes before their shift starts. Marking that
# early is not an error, so the check-in window opens before the scheduled
# start; the shift's end still bounds it. The club can change both values from
# the panel; these are only the defaults of a missing settings row.
DEFAULT_CHECK_IN_EARLY_GRACE_MINUTES = 15
DEFAULT_LATENESS_TOLERANCE_MINUTES = 0
MAX_ATTENDANCE_POLICY_MINUTES = 240
# How long a supervisor has to decide a change request before the owners hear
# that it expired. Zero disables the term; the panel edits both.
DEFAULT_ATTENDANCE_REQUEST_SLA_HOURS = 24
MAX_ATTENDANCE_REQUEST_SLA_HOURS = 720
VOIDABLE_MARKS = ("check_in", "check_out")


class StaffingError(Exception):
    pass


class ShiftNotAvailable(StaffingError):
    pass


class ShiftOverlap(StaffingError):
    pass


class AttendanceAlreadyRecorded(StaffingError):
    pass


class InvalidAttendanceTime(StaffingError):
    pass


class AttendanceEventConflict(StaffingError):
    pass


class AttendanceNotAllowed(StaffingError):
    pass


class ManualAttendanceReasonRequired(StaffingError):
    pass


class AttendanceNotFound(StaffingError):
    pass


class AttendanceMarkMissing(StaffingError):
    pass


class AttendanceRequestNotFound(StaffingError):
    pass


class AttendanceRequestConflict(StaffingError):
    pass


class AttendanceRequestNotAllowed(StaffingError):
    pass


ANNULMENT_EVENT_TYPES = ("attendance_voided", "check_out_voided")
MARK_LABELS = {"check_in": "entrada", "check_out": "salida"}
REQUEST_ACTIONS = ("correct", "void")
REQUEST_STATUSES = ("pending", "approved", "rejected")


@dataclass(frozen=True)
class AttendanceAnnulment:
    event_id: UUID
    event_type: str
    occurred_at: datetime
    reason: str | None
    attendance_id: UUID
    employee_id: UUID
    employee_name: str
    actor_id: UUID
    actor_email: str
    actor_name: str | None


@dataclass(frozen=True)
class AnnulmentOperatorSummary:
    actor_id: UUID
    actor_email: str
    actor_name: str | None
    check_ins: int
    check_outs: int
    total: int
    last_at: datetime


@dataclass(frozen=True)
class AttendanceAnnulmentReport:
    items: list[AttendanceAnnulment]
    by_operator: list[AnnulmentOperatorSummary]
    total: int


def read_attendance_policy(session: Session) -> tuple[int, int]:
    """Return the club's check-in grace and lateness tolerance, in minutes.

    The settings row is created lazily from the panel; reading never writes, so
    a database without it falls back to the defaults.
    """
    settings = session.get(StaffingSettings, 1)
    if settings is None:
        return DEFAULT_CHECK_IN_EARLY_GRACE_MINUTES, DEFAULT_LATENESS_TOLERANCE_MINUTES
    return settings.check_in_early_grace_minutes, settings.lateness_tolerance_minutes


def read_attendance_request_sla_hours(session: Session) -> int:
    """Return the club's term for deciding a request, in hours (zero = none)."""
    settings = session.get(StaffingSettings, 1)
    if settings is None:
        return DEFAULT_ATTENDANCE_REQUEST_SLA_HOURS
    return settings.attendance_request_sla_hours


def get_staffing_settings(session: Session) -> StaffingSettings:
    """Return the singleton settings row, creating it with defaults if needed."""
    settings = session.get(StaffingSettings, 1)
    if settings is None:
        settings = StaffingSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def update_staffing_settings(
    session: Session,
    *,
    check_in_early_grace_minutes: int,
    lateness_tolerance_minutes: int,
    attendance_request_sla_hours: int,
    actor_id: UUID | None = None,
) -> StaffingSettings:
    """Save the club policy, recording who changed what and the previous values.

    ``staffing_settings`` only carries ``updated_at``; the audit row is what lets
    the panel answer who moved the check-in window. A save that changes nothing
    writes no row, so the history only shows real changes. The request term is
    frozen on each pending request when it is created, so changing it here never
    re-times a request that is already waiting.
    """
    for value, label, limit in (
        (check_in_early_grace_minutes, "check_in_early_grace_minutes", MAX_ATTENDANCE_POLICY_MINUTES),
        (lateness_tolerance_minutes, "lateness_tolerance_minutes", MAX_ATTENDANCE_POLICY_MINUTES),
        (
            attendance_request_sla_hours,
            "attendance_request_sla_hours",
            MAX_ATTENDANCE_REQUEST_SLA_HOURS,
        ),
    ):
        if not 0 <= value <= limit:
            raise ValueError(f"{label} must be between 0 and {limit}")
    settings = get_staffing_settings(session)
    previous_grace = settings.check_in_early_grace_minutes
    previous_tolerance = settings.lateness_tolerance_minutes
    previous_sla = settings.attendance_request_sla_hours
    if (
        previous_grace == check_in_early_grace_minutes
        and previous_tolerance == lateness_tolerance_minutes
        and previous_sla == attendance_request_sla_hours
    ):
        return _normalize_datetimes(settings, ("updated_at",))
    now = utc_now()
    settings.check_in_early_grace_minutes = check_in_early_grace_minutes
    settings.lateness_tolerance_minutes = lateness_tolerance_minutes
    settings.attendance_request_sla_hours = attendance_request_sla_hours
    settings.updated_at = now
    session.add(settings)
    session.add(
        StaffingSettingsEvent(
            actor_id=actor_id,
            previous_check_in_early_grace_minutes=previous_grace,
            previous_lateness_tolerance_minutes=previous_tolerance,
            check_in_early_grace_minutes=check_in_early_grace_minutes,
            lateness_tolerance_minutes=lateness_tolerance_minutes,
            previous_attendance_request_sla_hours=previous_sla,
            attendance_request_sla_hours=attendance_request_sla_hours,
            changed_at=now,
        )
    )
    session.commit()
    session.refresh(settings)
    return _normalize_datetimes(settings, ("updated_at",))


def list_staffing_settings_events(
    session: Session, *, limit: int = 20
) -> list[tuple[StaffingSettingsEvent, AppUser | None, Employee | None]]:
    """Return the policy history newest first, with the account that changed it."""
    rows = session.exec(
        select(StaffingSettingsEvent, AppUser, Employee)
        .join(AppUser, StaffingSettingsEvent.actor_id == AppUser.id, isouter=True)
        .join(Employee, AppUser.employee_id == Employee.id, isouter=True)
        .order_by(StaffingSettingsEvent.changed_at.desc(), StaffingSettingsEvent.id.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    return [
        (_normalize_datetimes(event, ("changed_at",)), user, employee)
        for event, user, employee in rows
    ]


def create_shift(
    session: Session,
    *,
    employee_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    created_by: UUID,
) -> StaffShift:
    _require_aware(starts_at)
    _require_aware(ends_at)
    _require_aware(created_at := utc_now())
    starts_at = _as_utc(starts_at)
    ends_at = _as_utc(ends_at)
    if ends_at <= starts_at:
        raise InvalidAttendanceTime("Shift end must be after its start")

    employee = session.get(Employee, employee_id)
    creator = session.get(AppUser, created_by)
    if employee is None or employee.status != "active" or creator is None or creator.status != "active":
        raise ShiftNotAvailable("Active employee and creator accounts are required")

    overlap = session.exec(
        select(StaffShift.id).where(
            StaffShift.employee_id == employee_id,
            StaffShift.status == "scheduled",
            StaffShift.starts_at < ends_at,
            StaffShift.ends_at > starts_at,
        )
    ).first()
    if overlap is not None:
        raise ShiftOverlap("Employee already has a scheduled shift during this period")

    shift = StaffShift(
        employee_id=employee_id,
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=created_by,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(shift)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ShiftOverlap("A conflicting shift was created concurrently") from error
    session.refresh(shift)
    return _normalize_datetimes(shift, ("starts_at", "ends_at", "created_at", "updated_at"))


def list_shifts_with_attendance(
    session: Session,
    *,
    employee_id: UUID | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> list[tuple[StaffShift, StaffAttendance | None]]:
    """List scheduled shifts with their attendance, newest first.

    ``from_at`` filters shifts that end at or after that instant and ``to_at``
    filters shifts that start at or before it, so a shift that straddles the
    window boundary is still returned.
    """
    query = (
        select(StaffShift, StaffAttendance)
        .join(
            StaffAttendance,
            (StaffAttendance.shift_id == StaffShift.id) & StaffAttendance.voided_at.is_(None),
            isouter=True,
        )
        .order_by(StaffShift.starts_at.desc())
    )
    if employee_id is not None:
        query = query.where(StaffShift.employee_id == employee_id)
    if from_at is not None:
        query = query.where(StaffShift.ends_at >= _as_utc(from_at))
    if to_at is not None:
        query = query.where(StaffShift.starts_at <= _as_utc(to_at))
    rows = session.exec(query).all()
    return [
        (
            _normalize_datetimes(shift, ("starts_at", "ends_at", "created_at", "updated_at")),
            _normalize_datetimes(attendance, ("check_in_at", "check_out_at", "created_at", "updated_at"))
            if attendance is not None
            else None,
        )
        for shift, attendance in rows
    ]


def clock_in(
    session: Session,
    *,
    shift_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    source: str = "staff_app",
    occurred_at: datetime | None = None,
    enforce_employee_id: UUID | None = None,
    reason: str | None = None,
    enforce_window: bool = True,
) -> StaffAttendance:
    event_time = _as_utc(occurred_at or utc_now())
    return _record_attendance_event(
        session,
        shift_id=shift_id,
        actor_id=actor_id,
        request_id=request_id,
        source=source,
        event_type="check_in",
        occurred_at=event_time,
        enforce_employee_id=enforce_employee_id,
        reason=reason,
        enforce_window=enforce_window,
    )


def clock_out(
    session: Session,
    *,
    shift_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    source: str = "staff_app",
    occurred_at: datetime | None = None,
    enforce_employee_id: UUID | None = None,
    reason: str | None = None,
) -> StaffAttendance:
    event_time = _as_utc(occurred_at or utc_now())
    return _record_attendance_event(
        session,
        shift_id=shift_id,
        actor_id=actor_id,
        request_id=request_id,
        source=source,
        event_type="check_out",
        occurred_at=event_time,
        enforce_employee_id=enforce_employee_id,
        reason=reason,
    )


def record_manual_attendance(
    session: Session,
    *,
    shift_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    event_type: str,
    occurred_at: datetime,
    reason: str,
) -> StaffAttendance:
    """Register a punch the employee could not mark, on their behalf.

    Only missing marks: an existing check-in or check-out is rejected by the
    shared recorder, so this path never rewrites a punch the employee already
    made. The operator writes the instant, which is why the shift window is
    not enforced — a forgotten entry is usually fixed once the shift is over —
    and a reason is required for the audit trail.
    """
    if event_type not in {"check_in", "check_out"}:
        raise ValueError("Unsupported attendance event")
    notes = reason.strip()
    if not notes:
        raise ManualAttendanceReasonRequired("Manual attendance requires a reason")

    if event_type == "check_in":
        return clock_in(
            session,
            shift_id=shift_id,
            actor_id=actor_id,
            request_id=request_id,
            source="manual",
            occurred_at=occurred_at,
            reason=notes,
            enforce_window=False,
        )
    return clock_out(
        session,
        shift_id=shift_id,
        actor_id=actor_id,
        request_id=request_id,
        source="manual",
        occurred_at=occurred_at,
        reason=notes,
    )


def correct_attendance(
    session: Session,
    *,
    attendance_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    event_type: str,
    occurred_at: datetime,
    reason: str,
    commit: bool = True,
    notify_employee: bool = True,
) -> StaffAttendance:
    """Rewrite a mark the employee already registered.

    Employees never edit their own marks: this path belongs to whoever holds
    ``attendance.manage``. The attendance row keeps the current value while the
    append-only event log keeps the original punch and appends the correction
    with its reason, so the history survives the edit. The shift window is not
    re-checked — corrections usually happen once the shift is over — but the
    check-in/check-out order must stay valid.

    ``commit=False`` lets the approval of an employee request apply the change in
    the same transaction that marks the request as decided; the caller commits.
    """
    if event_type not in {"check_in", "check_out"}:
        raise ValueError("Unsupported attendance event")
    notes = reason.strip()
    if not notes:
        raise ManualAttendanceReasonRequired("Manual attendance requires a reason")

    event_time = _as_utc(occurred_at)
    stored_type = f"{event_type}_correction"
    fingerprint = _fingerprint(
        {
            "attendance_id": str(attendance_id),
            "actor_id": str(actor_id),
            "event_type": stored_type,
            "occurred_at": event_time.isoformat(),
        }
    )
    prior_event = session.exec(
        select(AttendanceEvent).where(AttendanceEvent.request_id == request_id)
    ).first()
    if prior_event is not None:
        if prior_event.request_sha256 != fingerprint:
            raise AttendanceEventConflict("Request ID was reused for a different attendance correction")
        record = session.get(StaffAttendance, prior_event.attendance_id)
        if record is None:
            raise StaffingError("Attendance record for replayed event is missing")
        return _normalize_datetimes(record, ("check_in_at", "check_out_at", "created_at", "updated_at"))

    record = session.exec(
        select(StaffAttendance).where(StaffAttendance.id == attendance_id).with_for_update()
    ).first()
    if record is None or record.voided_at is not None:
        raise AttendanceNotFound("Attendance record was not found")
    shift = session.get(StaffShift, record.shift_id)
    actor = session.get(AppUser, actor_id)
    if shift is None or shift.status != "scheduled" or actor is None or actor.status != "active":
        raise ShiftNotAvailable("Scheduled shift and active user are required")

    if event_type == "check_in":
        _, lateness_tolerance_minutes = read_attendance_policy(session)
        if record.check_out_at is not None and event_time > _as_utc(record.check_out_at):
            raise InvalidAttendanceTime("Check-in cannot be after check-out")
        previous_at = record.check_in_at
        record.check_in_at = event_time
        record.check_in_source = "correction"
        record.check_in_actor_id = actor_id
        record.status = _status_for(shift, event_time, lateness_tolerance_minutes)
    else:
        if record.check_out_at is None:
            raise AttendanceMarkMissing("Attendance has no check-out to correct")
        if event_time < _as_utc(record.check_in_at):
            raise InvalidAttendanceTime("Check-out cannot precede check-in")
        previous_at = record.check_out_at
        record.check_out_at = event_time
        record.check_out_source = "correction"
        record.check_out_actor_id = actor_id
    record.updated_at = utc_now()

    event = AttendanceEvent(
        request_id=request_id,
        request_sha256=fingerprint,
        attendance_id=record.id,
        actor_id=actor_id,
        event_type=stored_type,
        source="manual",
        occurred_at=event_time,
        reason=notes,
    )
    session.add(event)
    if notify_employee:
        _notify_mark_changed(
            session,
            record=record,
            employee_id=record.employee_id,
            actor_id=actor_id,
            event_id=event.id,
            mark=event_type,
            action="correct",
            previous_at=previous_at,
            new_at=event_time,
            reason=notes,
        )
    try:
        if commit:
            session.commit()
        else:
            session.flush()
    except IntegrityError as error:
        session.rollback()
        prior_event = session.exec(
            select(AttendanceEvent).where(AttendanceEvent.request_id == request_id)
        ).first()
        if prior_event is None or prior_event.request_sha256 != fingerprint:
            raise AttendanceEventConflict("Attendance correction conflicted with another request") from error
        replay_record = session.get(StaffAttendance, prior_event.attendance_id)
        if replay_record is None:
            raise StaffingError("Attendance record for replayed event is missing") from error
        return _normalize_datetimes(replay_record, ("check_in_at", "check_out_at", "created_at", "updated_at"))
    session.refresh(record)
    return _normalize_datetimes(record, ("check_in_at", "check_out_at", "created_at", "updated_at"))


def void_attendance_mark(
    session: Session,
    *,
    attendance_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    mark: str,
    reason: str,
    commit: bool = True,
    notify_employee: bool = True,
) -> StaffAttendance:
    """Remove a mark that should never have been recorded.

    Voiding the check-in eliminates the attendance itself — the row stays for
    the audit log but stops occupying the shift, so it can be marked again —
    while voiding the check-out only clears the exit and keeps the entry. The
    log keeps every previous event and appends the annulment with its reason,
    its actor and the instant it was made.

    ``commit=False`` exists for the request approval, which records the decision
    in the same transaction.
    """
    if mark not in VOIDABLE_MARKS:
        raise ValueError("Unsupported attendance mark")
    notes = reason.strip()
    if not notes:
        raise ManualAttendanceReasonRequired("Voiding a mark requires a reason")

    stored_type = "attendance_voided" if mark == "check_in" else "check_out_voided"
    fingerprint = _fingerprint(
        {
            "attendance_id": str(attendance_id),
            "actor_id": str(actor_id),
            "event_type": stored_type,
        }
    )
    prior_event = session.exec(
        select(AttendanceEvent).where(AttendanceEvent.request_id == request_id)
    ).first()
    if prior_event is not None:
        if prior_event.request_sha256 != fingerprint:
            raise AttendanceEventConflict("Request ID was reused for a different attendance annulment")
        record = session.get(StaffAttendance, prior_event.attendance_id)
        if record is None:
            raise StaffingError("Attendance record for replayed event is missing")
        return _normalize_datetimes(record, _ATTENDANCE_DATETIME_FIELDS)

    record = session.exec(
        select(StaffAttendance).where(StaffAttendance.id == attendance_id).with_for_update()
    ).first()
    if record is None or record.voided_at is not None:
        raise AttendanceNotFound("Attendance record was not found")
    shift = session.get(StaffShift, record.shift_id)
    actor = session.get(AppUser, actor_id)
    if shift is None or shift.status != "scheduled" or actor is None or actor.status != "active":
        raise ShiftNotAvailable("Scheduled shift and active user are required")

    now = utc_now()
    if mark == "check_out":
        if record.check_out_at is None:
            raise AttendanceMarkMissing("Attendance has no check-out to void")
        previous_at = record.check_out_at
        record.check_out_at = None
        record.check_out_source = None
        record.check_out_actor_id = None
    else:
        previous_at = record.check_in_at
        record.voided_at = now
        record.voided_by = actor_id
        record.void_reason = notes
    record.updated_at = now

    event = AttendanceEvent(
        request_id=request_id,
        request_sha256=fingerprint,
        attendance_id=record.id,
        actor_id=actor_id,
        event_type=stored_type,
        source="manual",
        occurred_at=now,
        reason=notes,
    )
    session.add(event)
    if notify_employee:
        _notify_mark_changed(
            session,
            record=record,
            employee_id=record.employee_id,
            actor_id=actor_id,
            event_id=event.id,
            mark=mark,
            action="void",
            previous_at=previous_at,
            new_at=None,
            reason=notes,
        )
    try:
        if commit:
            session.commit()
        else:
            session.flush()
    except IntegrityError as error:
        session.rollback()
        prior_event = session.exec(
            select(AttendanceEvent).where(AttendanceEvent.request_id == request_id)
        ).first()
        if prior_event is None or prior_event.request_sha256 != fingerprint:
            raise AttendanceEventConflict("Attendance annulment conflicted with another request") from error
        replay_record = session.get(StaffAttendance, prior_event.attendance_id)
        if replay_record is None:
            raise StaffingError("Attendance record for replayed event is missing") from error
        return _normalize_datetimes(replay_record, _ATTENDANCE_DATETIME_FIELDS)
    session.refresh(record)
    return _normalize_datetimes(record, _ATTENDANCE_DATETIME_FIELDS)


def list_attendance_events(
    session: Session, *, attendance_id: UUID
) -> list[tuple[AttendanceEvent, AppUser, Employee | None]]:
    """Return the attendance log oldest first, with the account that acted."""
    record = session.get(StaffAttendance, attendance_id)
    if record is None:
        raise AttendanceNotFound("Attendance record was not found")
    rows = session.exec(
        select(AttendanceEvent, AppUser, Employee)
        .join(AppUser, AttendanceEvent.actor_id == AppUser.id)
        .join(Employee, AppUser.employee_id == Employee.id, isouter=True)
        .where(AttendanceEvent.attendance_id == attendance_id)
        .order_by(AttendanceEvent.occurred_at, AttendanceEvent.id)
    ).all()
    return [
        (_normalize_datetimes(event, ("occurred_at",)), actor, employee)
        for event, actor, employee in rows
    ]


def request_attendance_change(
    session: Session,
    *,
    attendance_id: UUID,
    actor_id: UUID,
    employee_id: UUID,
    mark: str,
    action: str,
    proposed_at: datetime | None,
    justification: str,
) -> StaffAttendanceRequest:
    """Let an employee ask a supervisor to correct or void one of their marks.

    The request does not touch the attendance; it only records what the employee
    wants and why. It is validated against the current row — the mark must exist
    and the proposed instant must keep the entry before the exit — so a
    supervisor never approves something the correction path would reject.
    """
    if mark not in VOIDABLE_MARKS:
        raise ValueError("Unsupported attendance mark")
    if action not in REQUEST_ACTIONS:
        raise ValueError("Unsupported attendance request action")
    notes = justification.strip()
    if not notes:
        raise ManualAttendanceReasonRequired("Attendance request requires a justification")

    record = session.exec(
        select(StaffAttendance).where(StaffAttendance.id == attendance_id).with_for_update()
    ).first()
    if record is None or record.voided_at is not None:
        raise AttendanceNotFound("Attendance record was not found")
    shift = session.get(StaffShift, record.shift_id)
    if shift is None or shift.status != "scheduled":
        raise ShiftNotAvailable("Scheduled shift is required")
    if record.employee_id != employee_id:
        raise AttendanceRequestNotAllowed("The attendance does not belong to the employee")
    if mark == "check_out" and record.check_out_at is None:
        raise AttendanceMarkMissing("Attendance has no check-out to request a change for")

    proposed: datetime | None = None
    if action == "correct":
        if proposed_at is None:
            raise InvalidAttendanceTime("A correction request needs the proposed instant")
        _require_aware(proposed_at)
        proposed = _as_utc(proposed_at)
        if mark == "check_in" and record.check_out_at is not None and proposed > _as_utc(record.check_out_at):
            raise InvalidAttendanceTime("Check-in cannot be after check-out")
        if mark == "check_out" and proposed < _as_utc(record.check_in_at):
            raise InvalidAttendanceTime("Check-out cannot precede check-in")

    pending = session.exec(
        select(StaffAttendanceRequest).where(
            StaffAttendanceRequest.attendance_id == attendance_id,
            StaffAttendanceRequest.mark == mark,
            StaffAttendanceRequest.action == action,
            StaffAttendanceRequest.status == "pending",
        )
    ).first()
    if pending is not None:
        raise AttendanceRequestConflict("There is already a pending request for that mark")

    now = utc_now()
    sla_hours = read_attendance_request_sla_hours(session)
    request = StaffAttendanceRequest(
        attendance_id=record.id,
        employee_id=employee_id,
        requested_by=actor_id,
        mark=mark,
        action=action,
        proposed_at=proposed,
        justification=notes,
        created_at=now,
        due_at=now + timedelta(hours=sla_hours) if sla_hours > 0 else None,
    )
    session.add(request)
    session.flush()
    _notify_request_pending(session, request=request, record=record, actor_id=actor_id)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise AttendanceRequestConflict("A conflicting request was created concurrently") from error
    session.refresh(request)
    return _normalize_datetimes(request, _REQUEST_DATETIME_FIELDS)


def attendance_request_is_overdue(
    request: StaffAttendanceRequest, *, now: datetime | None = None
) -> bool:
    """Whether a still-pending request already passed the club's term."""
    if request.status != "pending" or request.due_at is None:
        return False
    return _as_utc(request.due_at) <= _as_utc(now or utc_now())


def escalate_overdue_attendance_requests(
    session: Session, *, now: datetime | None = None
) -> int:
    """Tell the owners about every pending request whose term already passed.

    There is no scheduler, so this runs from the read paths that show requests
    (the employee's list, the supervisor queue and the staff inbox). The dedupe
    key keeps it to one notice per request and owner, so reopening the queue
    writes nothing; deciding the request resolves the notice.
    """
    occurred = _as_utc(now or utc_now())
    rows = session.exec(
        select(StaffAttendanceRequest, StaffAttendance)
        .join(StaffAttendance, StaffAttendance.id == StaffAttendanceRequest.attendance_id)
        .where(
            StaffAttendanceRequest.status == "pending",
            StaffAttendanceRequest.due_at.is_not(None),
            StaffAttendanceRequest.due_at <= occurred,
        )
    ).all()
    if not rows:
        return 0
    owners = user_ids_with_role(session, "owner", now=occurred)
    written = 0
    for request, record in rows:
        for user_id in owners:
            if user_id == request.requested_by:
                continue
            key = f"attendance_request_overdue:{request.id}:{user_id}"
            if session.exec(
                select(StaffNotification.id).where(StaffNotification.dedupe_key == key)
            ).first():
                continue
            _notify_request_overdue(
                session, request=request, record=record, user_id=user_id, now=occurred
            )
            written += 1
    if written:
        session.commit()
    return written


def list_attendance_requests(
    session: Session,
    *,
    employee_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[tuple[StaffAttendanceRequest, StaffAttendance, Employee]]:
    """List change requests newest first, optionally for one employee or state."""
    if status is not None and status not in REQUEST_STATUSES:
        raise ValueError("Unsupported attendance request status")
    escalate_overdue_attendance_requests(session)
    query = (
        select(StaffAttendanceRequest, StaffAttendance, Employee)
        .join(StaffAttendance, StaffAttendance.id == StaffAttendanceRequest.attendance_id)
        .join(Employee, Employee.id == StaffAttendanceRequest.employee_id)
        .order_by(StaffAttendanceRequest.created_at.desc(), StaffAttendanceRequest.id.desc())
        .limit(max(1, min(limit, 200)))
    )
    if employee_id is not None:
        query = query.where(StaffAttendanceRequest.employee_id == employee_id)
    if status is not None:
        query = query.where(StaffAttendanceRequest.status == status)
    rows = session.exec(query).all()
    return [
        (
            _normalize_datetimes(request, _REQUEST_DATETIME_FIELDS),
            _normalize_datetimes(record, _ATTENDANCE_DATETIME_FIELDS),
            employee,
        )
        for request, record, employee in rows
    ]


def decide_attendance_request(
    session: Session,
    *,
    request_id: UUID,
    actor_id: UUID,
    decision: str,
    note: str | None = None,
) -> StaffAttendanceRequest:
    """Approve or reject a request; approval applies the change in one transaction.

    Approving calls the regular correction/annulment path with ``commit=False``,
    so the mark's event log stays identical to a change made directly from the
    panel and the decision lands with it or not at all. The pending notices to
    the supervisors close here and the employee is told the outcome.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError("Unsupported attendance request decision")
    notes = (note or "").strip()
    if decision == "rejected" and not notes:
        raise ManualAttendanceReasonRequired("Rejecting a request requires a reason")

    request = session.exec(
        select(StaffAttendanceRequest)
        .where(StaffAttendanceRequest.id == request_id)
        .with_for_update()
    ).first()
    if request is None:
        raise AttendanceRequestNotFound("Attendance request was not found")
    if request.status != "pending":
        raise AttendanceRequestConflict("Attendance request was already decided")
    if request.requested_by == actor_id:
        # A supervisor who also marks their own attendance must not approve
        # themselves; that would turn the request into a self-service edit.
        raise AttendanceRequestNotAllowed("Nobody can decide their own attendance request")

    now = utc_now()
    if decision == "approved":
        reason = f"Solicitud del colaborador: {request.justification}"
        if notes:
            reason = f"{reason} · Nota del supervisor: {notes}"
        if request.action == "correct":
            correct_attendance(
                session,
                attendance_id=request.attendance_id,
                actor_id=actor_id,
                request_id=uuid4(),
                event_type=request.mark,
                occurred_at=request.proposed_at,
                reason=reason,
                commit=False,
                notify_employee=False,
            )
        else:
            void_attendance_mark(
                session,
                attendance_id=request.attendance_id,
                actor_id=actor_id,
                request_id=uuid4(),
                mark=request.mark,
                reason=reason,
                commit=False,
                notify_employee=False,
            )

    request.status = decision
    request.decided_by = actor_id
    request.decided_at = now
    request.decision_note = notes or None
    request.updated_at = now
    session.add(request)
    resolve_staff_notifications(
        session, kind="attendance_request_pending", ref_id=request.id, now=now
    )
    resolve_staff_notifications(
        session, kind="attendance_request_overdue", ref_id=request.id, now=now
    )
    record = session.get(StaffAttendance, request.attendance_id)
    if record is not None:
        _notify_request_decided(
            session,
            request=request,
            record=record,
            actor_id=actor_id,
            note=notes,
            now=now,
        )
    session.commit()
    session.refresh(request)
    return _normalize_datetimes(request, _REQUEST_DATETIME_FIELDS)


def list_attendance_annulments(
    session: Session,
    *,
    from_at: datetime,
    to_at: datetime | None = None,
    employee_id: UUID | None = None,
    actor_id: UUID | None = None,
    limit: int = 500,
) -> AttendanceAnnulmentReport:
    """Return the voided marks of a period and the count per operator.

    The summary is computed from the same rows the table shows, so the report
    and its totals can never disagree. ``from_at``/``to_at`` filter when the
    annulment was made, not when the mark happened.
    """
    target_employee = aliased(Employee)
    actor_employee = aliased(Employee)
    query = (
        select(
            AttendanceEvent,
            StaffAttendance,
            target_employee,
            AppUser,
            actor_employee,
        )
        .join(StaffAttendance, StaffAttendance.id == AttendanceEvent.attendance_id)
        .join(target_employee, target_employee.id == StaffAttendance.employee_id)
        .join(AppUser, AppUser.id == AttendanceEvent.actor_id)
        .join(actor_employee, actor_employee.id == AppUser.employee_id, isouter=True)
        .where(
            AttendanceEvent.event_type.in_(ANNULMENT_EVENT_TYPES),
            AttendanceEvent.occurred_at >= _as_utc(from_at),
        )
        .order_by(AttendanceEvent.occurred_at.desc(), AttendanceEvent.id.desc())
        .limit(max(1, min(limit, 1000)))
    )
    if to_at is not None:
        query = query.where(AttendanceEvent.occurred_at <= _as_utc(to_at))
    if employee_id is not None:
        query = query.where(StaffAttendance.employee_id == employee_id)
    if actor_id is not None:
        query = query.where(AttendanceEvent.actor_id == actor_id)
    rows = session.exec(query).all()

    items: list[AttendanceAnnulment] = []
    summaries: dict[UUID, AnnulmentOperatorSummary] = {}
    for event, record, employee, actor, actor_employee in rows:
        occurred = _as_utc(event.occurred_at)
        actor_name = (
            f"{actor_employee.first_name} {actor_employee.last_name}".strip()
            if actor_employee is not None
            else None
        )
        items.append(
            AttendanceAnnulment(
                event_id=event.id,
                event_type=event.event_type,
                occurred_at=occurred,
                reason=event.reason,
                attendance_id=record.id,
                employee_id=record.employee_id,
                employee_name=f"{employee.first_name} {employee.last_name}".strip(),
                actor_id=actor.id,
                actor_email=actor.email,
                actor_name=actor_name,
            )
        )
        summary = summaries.get(actor.id)
        entry_void = 1 if event.event_type == "attendance_voided" else 0
        exit_void = 1 if event.event_type == "check_out_voided" else 0
        if summary is None:
            summaries[actor.id] = AnnulmentOperatorSummary(
                actor_id=actor.id,
                actor_email=actor.email,
                actor_name=actor_name,
                check_ins=entry_void,
                check_outs=exit_void,
                total=1,
                last_at=occurred,
            )
        else:
            summaries[actor.id] = AnnulmentOperatorSummary(
                actor_id=summary.actor_id,
                actor_email=summary.actor_email,
                actor_name=summary.actor_name,
                check_ins=summary.check_ins + entry_void,
                check_outs=summary.check_outs + exit_void,
                total=summary.total + 1,
                last_at=max(summary.last_at, occurred),
            )
    by_operator = sorted(summaries.values(), key=lambda row: (-row.total, row.actor_email))
    return AttendanceAnnulmentReport(items=items, by_operator=by_operator, total=len(items))


def _notify_mark_changed(
    session: Session,
    *,
    record: StaffAttendance,
    employee_id: UUID,
    actor_id: UUID,
    event_id: UUID,
    mark: str,
    action: str,
    previous_at: datetime,
    new_at: datetime | None,
    reason: str,
) -> None:
    """Tell the employee that a mark of theirs changed and who changed it.

    Skipped when the employee has no active panel account and when they are the
    one who made the change, so nobody is notified about their own action. The
    event id is the dedupe key: one notice per applied change, replays included.
    """
    user_id = staff_user_for_employee(session, employee_id)
    if user_id is None or user_id == actor_id:
        return
    label = MARK_LABELS[mark]
    day = _day_label(record.check_in_at)
    actor = _actor_label(session, actor_id)
    if action == "correct":
        kind = "attendance_corrected"
        title = "Se corrigió tu marca de asistencia"
        body = (
            f"Tu {label} del {day} se corrigió: era {_time_label(previous_at)} "
            f"y ahora es {_time_label(new_at)}. Motivo: «{_clip(reason, 200)}». "
            f"Lo hizo {actor}."
        )
    else:
        kind = "attendance_voided"
        title = "Se anuló tu marca de asistencia"
        body = (
            f"Tu {label} del {day} ({_time_label(previous_at)}) se anuló. "
            f"Motivo: «{_clip(reason, 200)}». Lo hizo {actor}."
        )
    create_staff_notification(
        session,
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        ref_id=record.id,
        dedupe_key=f"{kind}:{event_id}",
    )


def _notify_request_pending(
    session: Session,
    *,
    request: StaffAttendanceRequest,
    record: StaffAttendance,
    actor_id: UUID,
) -> None:
    """Ask everyone who can decide the request to look at it."""
    label = MARK_LABELS[request.mark]
    day = _day_label(record.check_in_at)
    employee = session.get(Employee, request.employee_id)
    employee_name = (
        f"{employee.first_name} {employee.last_name}".strip() if employee is not None else "Un colaborador"
    )
    if request.action == "correct":
        head = (
            f"{employee_name} pidió corregir su {label} del {day}: de "
            f"{_time_label(record.check_out_at if request.mark == 'check_out' else record.check_in_at)} "
            f"a {_time_label(request.proposed_at)}."
        )
    else:
        head = (
            f"{employee_name} pidió anular su {label} del {day} "
            f"({_time_label(record.check_out_at if request.mark == 'check_out' else record.check_in_at)})."
        )
    body = (
        f"{head} Motivo: «{_clip(request.justification, 200)}». "
        "Apruébala o recházala en Personal › Equipo."
    )
    for user_id in user_ids_with_permission(session, "attendance.manage"):
        if user_id == actor_id:
            continue
        create_staff_notification(
            session,
            user_id=user_id,
            kind="attendance_request_pending",
            title="Solicitud de cambio de asistencia",
            body=body,
            ref_id=request.id,
            dedupe_key=f"attendance_request_pending:{request.id}:{user_id}",
        )


def _notify_request_overdue(
    session: Session,
    *,
    request: StaffAttendanceRequest,
    record: StaffAttendance,
    user_id: UUID,
    now: datetime,
) -> None:
    """Escalate an expired request to an owner who can push the decision."""
    label = MARK_LABELS[request.mark]
    day = _day_label(record.check_in_at)
    employee = session.get(Employee, request.employee_id)
    employee_name = (
        f"{employee.first_name} {employee.last_name}".strip()
        if employee is not None
        else "Un colaborador"
    )
    verb = "corregir" if request.action == "correct" else "anular"
    create_staff_notification(
        session,
        user_id=user_id,
        kind="attendance_request_overdue",
        title="Solicitud de asistencia vencida",
        body=(
            f"{employee_name} pidió {verb} su {label} del {day} el "
            f"{_day_label(request.created_at)} a las {_time_label(request.created_at)} "
            "y la solicitud sigue sin decisión. Ya pasó el plazo del club: "
            "revísala o pide a la supervisión que la atienda."
        ),
        ref_id=request.id,
        dedupe_key=f"attendance_request_overdue:{request.id}:{user_id}",
        now=now,
    )


def _notify_request_decided(
    session: Session,
    *,
    request: StaffAttendanceRequest,
    record: StaffAttendance,
    actor_id: UUID,
    note: str,
    now: datetime,
) -> None:
    """Tell the employee what a supervisor decided about their request."""
    user_id = request.requested_by
    if user_id == actor_id:
        return
    label = MARK_LABELS[request.mark]
    day = _day_label(record.check_in_at)
    actor = _actor_label(session, actor_id)
    if request.status == "approved":
        kind = "attendance_request_approved"
        title = "Se aprobó tu solicitud de asistencia"
        if request.action == "correct":
            head = (
                f"Tu solicitud se aprobó: tu {label} del {day} quedó en "
                f"{_time_label(request.proposed_at)}."
            )
        else:
            head = f"Tu solicitud se aprobó: tu {label} del {day} quedó anulada."
        tail = f" Nota: «{_clip(note, 120)}»." if note else ""
        body = f"{head}{tail} Lo hizo {actor}."
    else:
        kind = "attendance_request_rejected"
        title = "Se rechazó tu solicitud de asistencia"
        verb = "corregir" if request.action == "correct" else "anular"
        body = (
            f"Tu solicitud para {verb} tu {label} del {day} se rechazó. "
            f"Motivo: «{_clip(note, 200)}». Lo revisó {actor}."
        )
    create_staff_notification(
        session,
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        ref_id=request.id,
        dedupe_key=f"{kind}:{request.id}",
        now=now,
    )


def _actor_label(session: Session, user_id: UUID) -> str:
    user = session.get(AppUser, user_id)
    if user is None:
        return "El personal"
    if user.employee_id is not None:
        employee = session.get(Employee, user.employee_id)
        if employee is not None:
            name = f"{employee.first_name} {employee.last_name}".strip()
            if name:
                return name
    return user.email


def _day_label(moment: datetime) -> str:
    return to_club_timezone(_as_utc(moment)).strftime("%d/%m/%Y")


def _time_label(moment: datetime | None) -> str:
    return "--:--" if moment is None else to_club_timezone(_as_utc(moment)).strftime("%H:%M")


def _clip(value: str, limit: int) -> str:
    clean = (value or "").strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}…"


def _record_attendance_event(
    session: Session,
    *,
    shift_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    source: str,
    event_type: str,
    occurred_at: datetime,
    enforce_employee_id: UUID | None = None,
    reason: str | None = None,
    enforce_window: bool = True,
) -> StaffAttendance:
    if source not in {"staff_app", "manual", "access_reader"}:
        raise ValueError("Unsupported attendance source")

    fingerprint = _request_fingerprint(shift_id, actor_id, source, event_type)
    prior_event = session.exec(
        select(AttendanceEvent).where(AttendanceEvent.request_id == request_id)
    ).first()
    if prior_event is not None:
        if prior_event.request_sha256 != fingerprint:
            raise AttendanceEventConflict("Request ID was reused for a different attendance event")
        record = session.get(StaffAttendance, prior_event.attendance_id)
        if record is None:
            raise StaffingError("Attendance record for replayed event is missing")
        return _normalize_datetimes(record, ("check_in_at", "check_out_at", "created_at", "updated_at"))

    shift = session.exec(select(StaffShift).where(StaffShift.id == shift_id).with_for_update()).first()
    actor = session.get(AppUser, actor_id)
    if shift is None or shift.status != "scheduled" or actor is None or actor.status != "active":
        raise ShiftNotAvailable("Scheduled shift and active user are required")
    if enforce_employee_id is not None and shift.employee_id != enforce_employee_id:
        raise AttendanceNotAllowed("The shift does not belong to the acting employee")

    record = session.exec(
        select(StaffAttendance).where(
            StaffAttendance.shift_id == shift_id,
            StaffAttendance.voided_at.is_(None),
        )
    ).first()
    if event_type == "check_in":
        early_grace_minutes, lateness_tolerance_minutes = read_attendance_policy(session)
        if enforce_window and (
            occurred_at < _as_utc(shift.starts_at) - timedelta(minutes=early_grace_minutes)
            or occurred_at > _as_utc(shift.ends_at)
        ):
            raise InvalidAttendanceTime("Check-in must be within the scheduled shift")
        if record is not None:
            raise AttendanceAlreadyRecorded("Attendance already has a check-in for this shift")
        employee = session.get(Employee, shift.employee_id)
        if employee is None or employee.status != "active":
            raise ShiftNotAvailable("Employee is missing or inactive")
        record = StaffAttendance(
            shift_id=shift.id,
            employee_id=shift.employee_id,
            check_in_at=occurred_at,
            check_in_source=source,
            check_in_actor_id=actor_id,
            status=_status_for(shift, occurred_at, lateness_tolerance_minutes),
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        session.add(record)
        session.flush()
    else:
        if record is None:
            raise InvalidAttendanceTime("Check-in is required before check-out")
        if record.check_out_at is not None:
            raise AttendanceAlreadyRecorded("Attendance already has a check-out")
        if occurred_at < _as_utc(record.check_in_at):
            raise InvalidAttendanceTime("Check-out cannot precede check-in")
        record.check_out_at = occurred_at
        record.check_out_source = source
        record.check_out_actor_id = actor_id
        record.updated_at = occurred_at

    session.add(
        AttendanceEvent(
            request_id=request_id,
            request_sha256=fingerprint,
            attendance_id=record.id,
            actor_id=actor_id,
            event_type=event_type,
            source=source,
            occurred_at=occurred_at,
            reason=reason,
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        prior_event = session.exec(
            select(AttendanceEvent).where(AttendanceEvent.request_id == request_id)
        ).first()
        if prior_event is None or prior_event.request_sha256 != fingerprint:
            raise AttendanceEventConflict("Attendance event conflicted with another request") from error
        replay_record = session.get(StaffAttendance, prior_event.attendance_id)
        if replay_record is None:
            raise StaffingError("Attendance record for replayed event is missing") from error
        return _normalize_datetimes(replay_record, ("check_in_at", "check_out_at", "created_at", "updated_at"))
    session.refresh(record)
    return _normalize_datetimes(record, ("check_in_at", "check_out_at", "created_at", "updated_at"))


_ATTENDANCE_DATETIME_FIELDS = (
    "check_in_at",
    "check_out_at",
    "voided_at",
    "created_at",
    "updated_at",
)

_REQUEST_DATETIME_FIELDS = (
    "proposed_at",
    "due_at",
    "decided_at",
    "created_at",
    "updated_at",
)


def _status_for(shift: StaffShift, occurred_at: datetime, lateness_tolerance_minutes: int) -> str:
    """Classify an entry against the start plus the club's lateness tolerance."""
    limit = _as_utc(shift.starts_at) + timedelta(minutes=lateness_tolerance_minutes)
    return "late" if _as_utc(occurred_at) > limit else "present"


def _request_fingerprint(shift_id: UUID, actor_id: UUID, source: str, event_type: str) -> str:
    return _fingerprint(
        {"shift_id": str(shift_id), "actor_id": str(actor_id), "source": source, "event_type": event_type}
    )


def _fingerprint(payload: dict[str, str]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Shift timestamps must be timezone-aware")


def _as_utc(value: datetime) -> datetime:
    # Values read back from the database (notably SQLite) may lack tzinfo even
    # though the application always stores UTC. Treat naive values as UTC, the
    # same convention used by the identity and memberships modules.
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_datetimes(record: _RecordT, fields: tuple[str, ...]) -> _RecordT:
    """Return the reloaded record with timezone-aware UTC datetimes.

    SQLite (used in tests and preview) does not preserve ``tzinfo``, so a value
    reloaded after ``commit``/``refresh`` comes back naive even though the
    application stores UTC. Normalizing here keeps the service contract
    identical across database backends. ``set_committed_value`` updates the
    attribute without marking the instance dirty.
    """
    for field in fields:
        value = getattr(record, field)
        if value is not None:
            set_committed_value(record, field, _as_utc(value))
    return record