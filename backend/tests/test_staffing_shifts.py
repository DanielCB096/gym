from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.modules.identity.models import AppUser, Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.staffing.models import (
    AttendanceEvent,
    StaffAttendance,
    StaffingSettings,
    StaffShift,
)
from app.modules.staffing.service import (
    AttendanceAlreadyRecorded,
    AttendanceEventConflict,
    AttendanceMarkMissing,
    AttendanceNotAllowed,
    AttendanceNotFound,
    InvalidAttendanceTime,
    ManualAttendanceReasonRequired,
    ShiftOverlap,
    clock_in,
    clock_out,
    correct_attendance,
    create_shift,
    get_staffing_settings,
    list_attendance_events,
    list_shifts_with_attendance,
    read_attendance_policy,
    record_manual_attendance,
    update_staffing_settings,
    void_attendance_mark,
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


def test_correction_rewrites_a_mark_and_keeps_the_history(session: Session) -> None:
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
        request_id=uuid4(),
        occurred_at=START + timedelta(minutes=20),
    )
    assert attendance.status == "late"

    corrected_at = START - timedelta(minutes=5)
    correction_id = uuid4()
    corrected = correct_attendance(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=correction_id,
        event_type="check_in",
        occurred_at=corrected_at,
        reason="Marcó tarde por error; llegó antes de las 14:00",
    )
    assert corrected.check_in_at == corrected_at
    assert corrected.check_in_source == "correction"
    assert corrected.status == "present"

    events = session.exec(select(AttendanceEvent)).all()
    assert sorted(event.event_type for event in events) == ["check_in", "check_in_correction"]
    correction_event = next(event for event in events if event.event_type == "check_in_correction")
    assert correction_event.reason == "Marcó tarde por error; llegó antes de las 14:00"
    assert correction_event.source == "manual"

    # Replaying the same correction does not append another event.
    replay = correct_attendance(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=correction_id,
        event_type="check_in",
        occurred_at=corrected_at,
        reason="Marcó tarde por error; llegó a las 14:05",
    )
    assert replay.check_in_at == corrected_at
    assert len(session.exec(select(AttendanceEvent)).all()) == 2

    # The same request id cannot be reused for a different correction.
    with pytest.raises(AttendanceEventConflict):
        correct_attendance(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=correction_id,
            event_type="check_in",
            occurred_at=START + timedelta(minutes=40),
            reason="Otra corrección",
        )

    # Rewriting the entry later than the shift start flips the status back.
    late_again = correct_attendance(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=uuid4(),
        event_type="check_in",
        occurred_at=START + timedelta(minutes=30),
        reason="La primera corrección quedó temprano",
    )
    assert late_again.status == "late"


def test_correction_respects_order_and_requires_the_mark(session: Session) -> None:
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
        request_id=uuid4(),
        occurred_at=START + timedelta(minutes=4),
    )

    with pytest.raises(ManualAttendanceReasonRequired):
        correct_attendance(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=uuid4(),
            event_type="check_in",
            occurred_at=START,
            reason="   ",
        )

    # A missing mark is filled from the manual path, not corrected.
    with pytest.raises(AttendanceMarkMissing):
        correct_attendance(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=uuid4(),
            event_type="check_out",
            occurred_at=START + timedelta(hours=8),
            reason="Salida sin marca",
        )

    clock_out(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START + timedelta(hours=7),
    )

    with pytest.raises(InvalidAttendanceTime):
        correct_attendance(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=uuid4(),
            event_type="check_in",
            occurred_at=START + timedelta(hours=8),
            reason="Entrada posterior a la salida",
        )

    corrected = correct_attendance(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=uuid4(),
        event_type="check_out",
        occurred_at=START + timedelta(hours=8),
        reason="Salió una hora después de lo marcado",
    )
    assert corrected.check_out_at == START + timedelta(hours=8)
    assert corrected.check_out_source == "correction"

    with pytest.raises(AttendanceNotFound):
        correct_attendance(
            session,
            attendance_id=uuid4(),
            actor_id=manager.id,
            request_id=uuid4(),
            event_type="check_in",
            occurred_at=START,
            reason="Registro inexistente",
        )


def test_attendance_policy_defaults_and_validation(session: Session) -> None:
    assert read_attendance_policy(session) == (15, 0)

    # Reading never writes the singleton row.
    assert session.get(StaffingSettings, 1) is None

    settings = get_staffing_settings(session)
    assert settings.check_in_early_grace_minutes == 15
    assert settings.lateness_tolerance_minutes == 0

    updated = update_staffing_settings(
        session, check_in_early_grace_minutes=30, lateness_tolerance_minutes=10
    )
    assert (updated.check_in_early_grace_minutes, updated.lateness_tolerance_minutes) == (30, 10)
    assert read_attendance_policy(session) == (30, 10)

    for invalid in (-1, 241):
        with pytest.raises(ValueError):
            update_staffing_settings(
                session, check_in_early_grace_minutes=invalid, lateness_tolerance_minutes=0
            )
        with pytest.raises(ValueError):
            update_staffing_settings(
                session, check_in_early_grace_minutes=0, lateness_tolerance_minutes=invalid
            )
    # A rejected update does not partially persist.
    assert read_attendance_policy(session) == (30, 10)


def test_configurable_grace_and_tolerance_change_the_window_and_status(session: Session) -> None:
    employee, manager = seed_employee_and_manager(session)
    update_staffing_settings(
        session, check_in_early_grace_minutes=30, lateness_tolerance_minutes=10
    )
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=START,
        ends_at=START + timedelta(hours=8),
        created_by=manager.id,
    )

    # 25 minutes early would be rejected under the old 15-minute default.
    early = clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START - timedelta(minutes=25),
    )
    assert early.status == "present"

    # The tolerance is inclusive: exactly ten minutes late is still present.
    on_time = correct_attendance(
        session,
        attendance_id=early.id,
        actor_id=manager.id,
        request_id=uuid4(),
        event_type="check_in",
        occurred_at=START + timedelta(minutes=10),
        reason="Llegó diez minutos tarde, dentro de la tolerancia",
    )
    assert on_time.status == "present"

    with pytest.raises(InvalidAttendanceTime):
        clock_in(
            session,
            shift_id=shift.id,
            actor_id=manager.id,
            request_id=uuid4(),
            occurred_at=START - timedelta(minutes=31),
        )


def test_status_uses_the_configured_tolerance_on_the_first_mark(session: Session) -> None:
    employee, manager = seed_employee_and_manager(session)
    update_staffing_settings(
        session, check_in_early_grace_minutes=15, lateness_tolerance_minutes=10
    )
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
        request_id=uuid4(),
        occurred_at=START + timedelta(minutes=11),
    )
    assert attendance.status == "late"


def test_voiding_the_check_out_keeps_the_entry(session: Session) -> None:
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
        request_id=uuid4(),
        occurred_at=START,
    )
    clock_out(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START + timedelta(hours=8),
    )

    request_id = uuid4()
    voided = void_attendance_mark(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=request_id,
        mark="check_out",
        reason="La salida se registró por error",
    )
    assert voided.check_out_at is None
    assert voided.check_out_source is None
    assert voided.voided_at is None
    assert voided.check_in_at == START

    log = list_attendance_events(session, attendance_id=attendance.id)
    assert [event.event_type for event, _, _ in log] == [
        "check_in",
        "check_out",
        "check_out_voided",
    ]
    last_event, actor, employee_row = log[-1]
    assert last_event.reason == "La salida se registró por error"
    assert last_event.source == "manual"
    assert actor.id == manager.id
    assert employee_row is None

    # The entry still occupies the shift, so the exit can be marked again.
    with pytest.raises(AttendanceAlreadyRecorded):
        clock_in(
            session,
            shift_id=shift.id,
            actor_id=manager.id,
            request_id=uuid4(),
            occurred_at=START,
        )
    again = clock_out(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START + timedelta(hours=7, minutes=30),
    )
    assert again.check_out_at == START + timedelta(hours=7, minutes=30)

    # Replaying the annulment neither duplicates the event nor reopens the
    # already restored exit.
    replay = void_attendance_mark(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=request_id,
        mark="check_out",
        reason="La salida se registró por error",
    )
    assert replay.id == attendance.id
    assert len(list_attendance_events(session, attendance_id=attendance.id)) == 4


def test_voiding_the_check_in_frees_the_shift(session: Session) -> None:
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
        request_id=uuid4(),
        occurred_at=START + timedelta(minutes=5),
    )

    voided = void_attendance_mark(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=uuid4(),
        mark="check_in",
        reason="Era el turno de otra persona",
    )
    assert voided.voided_at is not None
    assert voided.voided_by == manager.id
    assert voided.void_reason == "Era el turno de otra persona"

    # The shift is free again and the view no longer shows the voided row.
    rows = list_shifts_with_attendance(session, employee_id=employee.id)
    assert [(row_shift.id, row_attendance) for row_shift, row_attendance in rows] == [
        (shift.id, None)
    ]

    replacement = clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START + timedelta(minutes=2),
    )
    assert replacement.id != attendance.id
    assert replacement.voided_at is None

    # The voided row keeps its history with the annulment on top.
    assert [event.event_type for event, _, _ in list_attendance_events(
        session, attendance_id=attendance.id
    )] == ["check_in", "attendance_voided"]

    listed = list_shifts_with_attendance(session, employee_id=employee.id)
    assert listed[0][1] is not None
    assert listed[0][1].id == replacement.id


def test_void_rejections(session: Session) -> None:
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
        request_id=uuid4(),
        occurred_at=START,
    )

    with pytest.raises(ManualAttendanceReasonRequired):
        void_attendance_mark(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=uuid4(),
            mark="check_in",
            reason="   ",
        )
    with pytest.raises(AttendanceMarkMissing):
        void_attendance_mark(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=uuid4(),
            mark="check_out",
            reason="No hay salida que anular",
        )
    with pytest.raises(AttendanceNotFound):
        void_attendance_mark(
            session,
            attendance_id=uuid4(),
            actor_id=manager.id,
            request_id=uuid4(),
            mark="check_in",
            reason="Registro inexistente",
        )
    with pytest.raises(ValueError):
        void_attendance_mark(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=uuid4(),
            mark="check_out_correction",
            reason="Tipo no anulable",
        )

    request_id = uuid4()
    void_attendance_mark(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=request_id,
        mark="check_in",
        reason="Marca duplicada",
    )
    # The same request id cannot be reused for a different annulment.
    with pytest.raises(AttendanceEventConflict):
        void_attendance_mark(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=request_id,
            mark="check_out",
            reason="Otra anulación",
        )
    # A voided row can no longer be corrected.
    with pytest.raises(AttendanceNotFound):
        correct_attendance(
            session,
            attendance_id=attendance.id,
            actor_id=manager.id,
            request_id=uuid4(),
            event_type="check_in",
            occurred_at=START,
            reason="Corregir algo ya anulado",
        )
    with pytest.raises(AttendanceNotFound):
        list_attendance_events(session, attendance_id=uuid4())
