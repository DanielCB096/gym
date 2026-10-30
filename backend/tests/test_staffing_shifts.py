from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.modules.identity.models import AppUser, Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.staffing.models import AttendanceEvent, StaffAttendance, StaffShift
from app.modules.staffing.service import (
    AttendanceAlreadyRecorded,
    AttendanceEventConflict,
    AttendanceNotAllowed,
    InvalidAttendanceTime,
    ManualAttendanceReasonRequired,
    ShiftOverlap,
    clock_in,
    clock_out,
    create_shift,
    list_shifts_with_attendance,
    record_manual_attendance,
)


START = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)


def seed_employee_and_manager(session: Session) -> tuple[Employee, AppUser]:
    ensure_default_access_control(session)
    employee = Employee(
        employee_number="EMP-100",
        first_name="Lucía",
        last_name="Mendoza",
        email="lucia@example.test",
        job_title="Recepción",
    )
    session.add(employee)
    session.commit()
    manager = register_user(
        session,
        email="manager@example.test",
        password="manager-password-long-enough",
        role_codes=("manager",),
    )
    return employee, manager


def test_create_shift_and_record_check_in_and_out(session: Session) -> None:
    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    attendance = clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=__import__("uuid").uuid4(),
        occurred_at=START + timedelta(minutes=7),
    )
    assert attendance.status == "late"
    assert attendance.check_in_source == "staff_app"

    clocked_out = clock_out(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=__import__("uuid").uuid4(),
        occurred_at=START + timedelta(hours=8, minutes=5),
    )
    assert clocked_out.check_out_at == START + timedelta(hours=8, minutes=5)
    assert len(session.exec(select(AttendanceEvent)).all()) == 2


def test_overlapping_shift_for_same_employee_is_rejected(session: Session) -> None:
    employee, manager = seed_employee_and_manager(session)
    create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    with pytest.raises(ShiftOverlap):
        create_shift(
            session,
            employee_id=employee.id,
            starts_at=START + timedelta(hours=7),
            ends_at=START + timedelta(hours=9),
            created_by=manager.id,
        )
    assert len(session.exec(select(StaffShift)).all()) == 1


def test_check_in_request_replay_is_idempotent(session: Session) -> None:
    from uuid import uuid4

    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )
    request_id = uuid4()
    first = clock_in(session, shift_id=shift.id, actor_id=manager.id, request_id=request_id, occurred_at=START)
    replay = clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=request_id,
        occurred_at=START + timedelta(minutes=1),
    )

    assert replay.id == first.id
    assert len(session.exec(select(AttendanceEvent)).all()) == 1


def test_duplicate_check_in_with_new_request_id_is_rejected(session: Session) -> None:
    from uuid import uuid4

    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )
    clock_in(session, shift_id=shift.id, actor_id=manager.id, request_id=uuid4(), occurred_at=START)

    with pytest.raises(AttendanceAlreadyRecorded):
        clock_in(session, shift_id=shift.id, actor_id=manager.id, request_id=uuid4(), occurred_at=START)


def test_check_out_requires_check_in_and_cannot_precede_it(session: Session) -> None:
    from uuid import uuid4

    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    with pytest.raises(InvalidAttendanceTime):
        clock_out(session, shift_id=shift.id, actor_id=manager.id, request_id=uuid4(), occurred_at=START)

    clock_in(session, shift_id=shift.id, actor_id=manager.id, request_id=uuid4(), occurred_at=START)
    with pytest.raises(InvalidAttendanceTime):
        clock_out(
            session,
            shift_id=shift.id,
            actor_id=manager.id,
            request_id=uuid4(),
            occurred_at=START - timedelta(seconds=1),
        )


def test_same_event_id_cannot_be_reused_for_another_shift_action(session: Session) -> None:
    from uuid import uuid4

    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )
    request_id = uuid4()
    clock_in(session, shift_id=shift.id, actor_id=manager.id, request_id=request_id, occurred_at=START)

    with pytest.raises(AttendanceEventConflict):
        clock_out(session, shift_id=shift.id, actor_id=manager.id, request_id=request_id, occurred_at=START)


def test_self_service_can_only_mark_its_own_shift(session: Session) -> None:
    from uuid import uuid4

    employee, manager = seed_employee_and_manager(session)
    other = Employee(
        employee_number="EMP-200",
        first_name="Otro",
        last_name="Colaborador",
        email="otro@example.test",
        job_title="Mantenimiento",
    )
    session.add(other)
    session.commit()

    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    with pytest.raises(AttendanceNotAllowed):
        clock_in(
            session,
            shift_id=shift.id,
            actor_id=manager.id,
            request_id=uuid4(),
            occurred_at=START,
            enforce_employee_id=other.id,
        )

    attendance = clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START,
        enforce_employee_id=employee.id,
    )
    assert attendance.employee_id == employee.id


def test_list_shifts_with_attendance_filters_by_employee_and_window(session: Session) -> None:
    from uuid import uuid4

    employee, manager = seed_employee_and_manager(session)
    other = Employee(
        employee_number="EMP-201",
        first_name="Otra",
        last_name="Persona",
        email="otra@example.test",
        job_title="Recepción",
    )
    session.add(other)
    session.commit()

    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )
    create_shift(
        session,
        employee_id=other.id,
        starts_at=START + timedelta(days=1),
        ends_at=START + timedelta(days=1, hours=8),
        created_by=manager.id,
    )
    clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START,
        enforce_employee_id=employee.id,
    )

    mine = list_shifts_with_attendance(session, employee_id=employee.id)
    assert len(mine) == 1
    listed_shift, attendance = mine[0]
    assert listed_shift.id == shift.id
    assert attendance is not None
    assert attendance.check_in_at == START

    assert list_shifts_with_attendance(
        session, employee_id=employee.id, from_at=START + timedelta(days=30)
    ) == []
    assert list_shifts_with_attendance(
        session, employee_id=employee.id, to_at=START - timedelta(days=30)
    ) == []


def test_check_in_opens_fifteen_minutes_before_the_shift(session: Session) -> None:
    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    early = clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START - timedelta(minutes=15),
    )
    assert early.check_in_at == START - timedelta(minutes=15)
    assert early.status == "present"


def test_check_in_before_the_grace_window_is_rejected(session: Session) -> None:
    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    with pytest.raises(InvalidAttendanceTime):
        clock_in(
            session,
            shift_id=shift.id,
            actor_id=manager.id,
            request_id=uuid4(),
            occurred_at=START - timedelta(minutes=16),
        )


def test_manual_attendance_fills_only_missing_marks(session: Session) -> None:
    employee, manager = seed_employee_and_manager(session)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    # A forgotten entry is registered once the shift is over, so the window
    # does not apply to the operator.
    manual = record_manual_attendance(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        event_type="check_in",
        occurred_at=START + timedelta(hours=9),
        reason="No pudo marcar la entrada",
    )
    assert manual.check_in_source == "manual"
    assert manual.status == "late"
    events = session.exec(select(AttendanceEvent)).all()
    assert [(event.source, event.reason) for event in events] == [
        ("manual", "No pudo marcar la entrada")
    ]

    # A manual mark never rewrites one the employee already made.
    with pytest.raises(AttendanceAlreadyRecorded):
        record_manual_attendance(
            session,
            shift_id=shift.id,
            actor_id=manager.id,
            request_id=uuid4(),
            event_type="check_in",
            occurred_at=START + timedelta(hours=9, minutes=30),
            reason="Entrada repetida",
        )

    with pytest.raises(ManualAttendanceReasonRequired):
        record_manual_attendance(
            session,
            shift_id=shift.id,
            actor_id=manager.id,
            request_id=uuid4(),
            event_type="check_out",
            occurred_at=START + timedelta(hours=17),
            reason="   ",
        )

    closed = record_manual_attendance(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        event_type="check_out",
        occurred_at=START + timedelta(hours=17),
        reason="Olvidó marcar la salida",
    )
    assert closed.check_out_source == "manual"
    assert closed.check_out_at == START + timedelta(hours=17)