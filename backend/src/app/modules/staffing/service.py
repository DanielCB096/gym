from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import TypeVar
from uuid import UUID, uuid4

from sqlmodel import Session, SQLModel, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.identity.models import AppUser, Employee
from app.modules.staffing.models import AttendanceEvent, StaffAttendance, StaffShift, StaffingSettings, utc_now


_RecordT = TypeVar("_RecordT", bound=SQLModel)

# People usually arrive a few minutes before their shift starts. Marking that
# early is not an error, so the check-in window opens before the scheduled
# start; the shift's end still bounds it. The club can change both values from
# the panel; these are only the defaults of a missing settings row.
DEFAULT_CHECK_IN_EARLY_GRACE_MINUTES = 15
DEFAULT_LATENESS_TOLERANCE_MINUTES = 0
MAX_ATTENDANCE_POLICY_MINUTES = 240
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


def read_attendance_policy(session: Session) -> tuple[int, int]:
    """Return the club's check-in grace and lateness tolerance, in minutes.

    The settings row is created lazily from the panel; reading never writes, so
    a database without it falls back to the defaults.
    """
    settings = session.get(StaffingSettings, 1)
    if settings is None:
        return DEFAULT_CHECK_IN_EARLY_GRACE_MINUTES, DEFAULT_LATENESS_TOLERANCE_MINUTES
    return settings.check_in_early_grace_minutes, settings.lateness_tolerance_minutes


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
) -> StaffingSettings:
    for value, label in (
        (check_in_early_grace_minutes, "check_in_early_grace_minutes"),
        (lateness_tolerance_minutes, "lateness_tolerance_minutes"),
    ):
        if not 0 <= value <= MAX_ATTENDANCE_POLICY_MINUTES:
            raise ValueError(f"{label} must be between 0 and {MAX_ATTENDANCE_POLICY_MINUTES}")
    settings = get_staffing_settings(session)
    settings.check_in_early_grace_minutes = check_in_early_grace_minutes
    settings.lateness_tolerance_minutes = lateness_tolerance_minutes
    settings.updated_at = utc_now()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return _normalize_datetimes(settings, ("updated_at",))


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
) -> StaffAttendance:
    """Rewrite a mark the employee already registered.

    Employees never edit their own marks: this path belongs to whoever holds
    ``attendance.manage``. The attendance row keeps the current value while the
    append-only event log keeps the original punch and appends the correction
    with its reason, so the history survives the edit. The shift window is not
    re-checked — corrections usually happen once the shift is over — but the
    check-in/check-out order must stay valid.
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
        record.check_in_at = event_time
        record.check_in_source = "correction"
        record.check_in_actor_id = actor_id
        record.status = _status_for(shift, event_time, lateness_tolerance_minutes)
    else:
        if record.check_out_at is None:
            raise AttendanceMarkMissing("Attendance has no check-out to correct")
        if event_time < _as_utc(record.check_in_at):
            raise InvalidAttendanceTime("Check-out cannot precede check-in")
        record.check_out_at = event_time
        record.check_out_source = "correction"
        record.check_out_actor_id = actor_id
    record.updated_at = utc_now()

    session.add(
        AttendanceEvent(
            request_id=request_id,
            request_sha256=fingerprint,
            attendance_id=record.id,
            actor_id=actor_id,
            event_type=stored_type,
            source="manual",
            occurred_at=event_time,
            reason=notes,
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
) -> StaffAttendance:
    """Remove a mark that should never have been recorded.

    Voiding the check-in eliminates the attendance itself — the row stays for
    the audit log but stops occupying the shift, so it can be marked again —
    while voiding the check-out only clears the exit and keeps the entry. The
    log keeps every previous event and appends the annulment with its reason,
    its actor and the instant it was made.
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
        record.check_out_at = None
        record.check_out_source = None
        record.check_out_actor_id = None
    else:
        record.voided_at = now
        record.voided_by = actor_id
        record.void_reason = notes
    record.updated_at = now

    session.add(
        AttendanceEvent(
            request_id=request_id,
            request_sha256=fingerprint,
            attendance_id=record.id,
            actor_id=actor_id,
            event_type=stored_type,
            source="manual",
            occurred_at=now,
            reason=notes,
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