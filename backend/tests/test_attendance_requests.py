from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.modules.identity.models import AppUser, Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications.models import StaffNotification
from app.modules.staffing.models import (
    AttendanceEvent,
    StaffAttendance,
    StaffAttendanceRequest,
    StaffingSettingsEvent,
)
from app.modules.staffing.service import (
    AttendanceMarkMissing,
    AttendanceRequestConflict,
    AttendanceRequestNotAllowed,
    AttendanceRequestNotFound,
    InvalidAttendanceTime,
    ManualAttendanceReasonRequired,
    attendance_request_is_overdue,
    clock_in,
    clock_out,
    correct_attendance,
    create_shift,
    decide_attendance_request,
    escalate_overdue_attendance_requests,
    list_attendance_annulments,
    list_attendance_requests,
    list_staffing_settings_events,
    request_attendance_change,
    update_staffing_settings,
    void_attendance_mark,
)


START = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)


def seed_employee_with_account(session: Session) -> tuple[Employee, AppUser, AppUser]:
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
    account = register_user(
        session,
        email="lucia.account@example.test",
        password="lucia-password-long-enough",
        employee_id=employee.id,
        role_codes=("reception",),
    )
    return employee, account, manager


def seed_attendance(
    session: Session,
    employee_id,
    manager_id,
    *,
    late_minutes: int = 0,
    day_offset: int = 0,
) -> StaffAttendance:
    starts_at = START + timedelta(days=day_offset)
    shift = create_shift(
        session,
        employee_id=employee_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=8),
        created_by=manager_id,
    )
    return clock_in(
        session,
        shift_id=shift.id,
        actor_id=manager_id,
        request_id=uuid4(),
        occurred_at=starts_at + timedelta(minutes=late_minutes),
    )


def test_policy_changes_are_audited_with_actor_and_previous_values(session: Session) -> None:
    employee, _, manager = seed_employee_with_account(session)

    # Saving the defaults that were never changed writes no history row.
    update_staffing_settings(
        session,
        check_in_early_grace_minutes=15,
        lateness_tolerance_minutes=0,
        attendance_request_sla_hours=24,
        actor_id=manager.id,
    )
    assert session.exec(select(StaffingSettingsEvent)).all() == []

    update_staffing_settings(
        session,
        check_in_early_grace_minutes=30,
        lateness_tolerance_minutes=10,
        attendance_request_sla_hours=48,
        actor_id=manager.id,
    )
    update_staffing_settings(
        session,
        check_in_early_grace_minutes=30,
        lateness_tolerance_minutes=10,
        attendance_request_sla_hours=48,
        actor_id=manager.id,
    )
    history = list_staffing_settings_events(session)
    assert len(history) == 1
    event, actor, actor_employee = history[0]
    assert actor is not None and actor.id == manager.id
    assert actor_employee is None
    assert (
        event.previous_check_in_early_grace_minutes,
        event.previous_lateness_tolerance_minutes,
        event.previous_attendance_request_sla_hours,
    ) == (15, 0, 24)
    assert (event.check_in_early_grace_minutes, event.lateness_tolerance_minutes) == (30, 10)
    assert event.attendance_request_sla_hours == 48
    assert event.changed_at == event.changed_at.astimezone(timezone.utc)


def test_correction_and_void_notify_the_employee(session: Session) -> None:
    employee, account, manager = seed_employee_with_account(session)
    attendance = seed_attendance(session, employee.id, manager.id, late_minutes=20)

    correct_attendance(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=uuid4(),
        event_type="check_in",
        occurred_at=START - timedelta(minutes=5),
        reason="Llegó antes y marcó tarde",
    )
    notices = session.exec(select(StaffNotification)).all()
    assert [(row.user_id, row.kind) for row in notices] == [(account.id, "attendance_corrected")]
    assert "Llegó antes y marcó tarde" in notices[0].body
    assert "se corrigió" in notices[0].body

    void_attendance_mark(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=uuid4(),
        mark="check_in",
        reason="Era el turno de otra persona",
    )
    kinds = sorted(row.kind for row in session.exec(select(StaffNotification)).all())
    assert kinds == ["attendance_corrected", "attendance_voided"]

    # The employee acting on their own mark is not notified about themselves.
    attendance = seed_attendance(session, employee.id, manager.id, late_minutes=3, day_offset=1)
    correct_attendance(
        session,
        attendance_id=attendance.id,
        actor_id=account.id,
        request_id=uuid4(),
        event_type="check_in",
        occurred_at=START + timedelta(days=1, minutes=1),
        reason="Se corrigió a sí misma",
    )
    assert len(session.exec(select(StaffNotification)).all()) == 2


def test_employee_request_is_approved_and_applies_the_change(session: Session) -> None:
    employee, account, manager = seed_employee_with_account(session)
    attendance = seed_attendance(session, employee.id, manager.id, late_minutes=20)

    request = request_attendance_change(
        session,
        attendance_id=attendance.id,
        actor_id=account.id,
        employee_id=employee.id,
        mark="check_in",
        action="correct",
        proposed_at=START - timedelta(minutes=4),
        justification="Entré a las 13:56, no a las 14:20",
    )
    assert request.status == "pending"
    assert request.proposed_at == START - timedelta(minutes=4)

    # The supervisors hear about it in their inbox, the requester does not.
    pending_notices = session.exec(
        select(StaffNotification).where(StaffNotification.kind == "attendance_request_pending")
    ).all()
    assert [row.user_id for row in pending_notices] == [manager.id]
    assert "Lucía Mendoza" in pending_notices[0].body

    with pytest.raises(AttendanceRequestConflict):
        request_attendance_change(
            session,
            attendance_id=attendance.id,
            actor_id=account.id,
            employee_id=employee.id,
            mark="check_in",
            action="correct",
            proposed_at=START,
            justification="Otra vez",
        )

    # Nobody decides their own request, even with attendance.manage.
    with pytest.raises(AttendanceRequestNotAllowed):
        decide_attendance_request(
            session,
            request_id=request.id,
            actor_id=account.id,
            decision="approved",
        )

    decided = decide_attendance_request(
        session,
        request_id=request.id,
        actor_id=manager.id,
        decision="approved",
        note="Confirmado con la cámara de recepción",
    )
    assert decided.status == "approved"
    assert decided.decided_by == manager.id
    assert decided.decision_note == "Confirmado con la cámara de recepción"

    stored = session.get(StaffAttendance, attendance.id)
    assert stored.check_in_at == START - timedelta(minutes=4)
    assert stored.check_in_source == "correction"
    events = session.exec(select(AttendanceEvent)).all()
    assert sorted(event.event_type for event in events) == ["check_in", "check_in_correction"]
    correction = next(event for event in events if event.event_type == "check_in_correction")
    assert "Entré a las 13:56" in (correction.reason or "")

    # The pending notice closes and the employee is told the outcome.
    session.refresh(pending_notices[0])
    assert pending_notices[0].resolved_at is not None
    approved = session.exec(
        select(StaffNotification).where(StaffNotification.kind == "attendance_request_approved")
    ).all()
    assert [row.user_id for row in approved] == [account.id]
    assert "Confirmado con la cámara" in approved[0].body

    assert [row[0].id for row in list_attendance_requests(session, status="approved")] == [request.id]
    assert list_attendance_requests(session, status="pending") == []


def test_employee_request_validation_and_rejection(session: Session) -> None:
    employee, account, manager = seed_employee_with_account(session)
    other = Employee(
        employee_number="EMP-300",
        first_name="Otro",
        last_name="Colaborador",
        email="otro3@example.test",
        job_title="Mantenimiento",
    )
    session.add(other)
    session.commit()
    attendance = seed_attendance(session, employee.id, manager.id, late_minutes=10)

    with pytest.raises(AttendanceRequestNotAllowed):
        request_attendance_change(
            session,
            attendance_id=attendance.id,
            actor_id=account.id,
            employee_id=other.id,
            mark="check_in",
            action="correct",
            proposed_at=START,
            justification="No es su marca",
        )
    with pytest.raises(AttendanceMarkMissing):
        request_attendance_change(
            session,
            attendance_id=attendance.id,
            actor_id=account.id,
            employee_id=employee.id,
            mark="check_out",
            action="void",
            proposed_at=None,
            justification="No hay salida que anular",
        )
    with pytest.raises(InvalidAttendanceTime):
        request_attendance_change(
            session,
            attendance_id=attendance.id,
            actor_id=account.id,
            employee_id=employee.id,
            mark="check_in",
            action="correct",
            proposed_at=None,
            justification="Falta la hora propuesta",
        )
    with pytest.raises(ManualAttendanceReasonRequired):
        request_attendance_change(
            session,
            attendance_id=attendance.id,
            actor_id=account.id,
            employee_id=employee.id,
            mark="check_in",
            action="correct",
            proposed_at=START,
            justification="   ",
        )

    # A proposed exit before the registered entry breaks the chronological order.
    clock_out(
        session,
        shift_id=attendance.shift_id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START + timedelta(hours=8),
    )
    with pytest.raises(InvalidAttendanceTime):
        request_attendance_change(
            session,
            attendance_id=attendance.id,
            actor_id=account.id,
            employee_id=employee.id,
            mark="check_out",
            action="correct",
            proposed_at=START,
            justification="Salida anterior a la entrada",
        )

    request = request_attendance_change(
        session,
        attendance_id=attendance.id,
        actor_id=account.id,
        employee_id=employee.id,
        mark="check_in",
        action="correct",
        proposed_at=START + timedelta(minutes=2),
        justification="Marqué diez minutos tarde sin querer",
    )
    with pytest.raises(ManualAttendanceReasonRequired):
        decide_attendance_request(
            session, request_id=request.id, actor_id=manager.id, decision="rejected"
        )
    rejected = decide_attendance_request(
        session,
        request_id=request.id,
        actor_id=manager.id,
        decision="rejected",
        note="La cámara muestra la hora original",
    )
    assert rejected.status == "rejected"
    assert session.get(StaffAttendance, attendance.id).check_in_at == START + timedelta(minutes=10)

    notice = session.exec(
        select(StaffNotification).where(StaffNotification.kind == "attendance_request_rejected")
    ).one()
    assert notice.user_id == account.id
    assert "La cámara muestra la hora original" in notice.body

    with pytest.raises(AttendanceRequestConflict):
        decide_attendance_request(
            session, request_id=request.id, actor_id=manager.id, decision="approved"
        )
    with pytest.raises(AttendanceRequestNotFound):
        decide_attendance_request(
            session, request_id=uuid4(), actor_id=manager.id, decision="approved"
        )


def test_overdue_request_escalates_once_to_the_owners(session: Session) -> None:
    employee, account, manager = seed_employee_with_account(session)
    owner = register_user(
        session,
        email="owner@example.test",
        password="owner-password-long-enough",
        role_codes=("owner",),
    )
    attendance = seed_attendance(session, employee.id, manager.id, late_minutes=12)
    request = request_attendance_change(
        session,
        attendance_id=attendance.id,
        actor_id=account.id,
        employee_id=employee.id,
        mark="check_in",
        action="correct",
        proposed_at=START,
        justification="Marqué doce minutos tarde por error",
    )

    # The term is frozen on the request, not read again when it is evaluated.
    assert request.due_at == request.created_at + timedelta(hours=24)
    assert attendance_request_is_overdue(request) is False

    before_due = request.created_at + timedelta(hours=23, minutes=59)
    assert escalate_overdue_attendance_requests(session, now=before_due) == 0
    overdue_query = select(StaffNotification).where(
        StaffNotification.kind == "attendance_request_overdue"
    )
    assert session.exec(overdue_query).all() == []

    # Past the term the owners hear it once; the requester never does.
    assert escalate_overdue_attendance_requests(session, now=before_due + timedelta(minutes=2)) == 1
    overdue = session.exec(overdue_query).one()
    assert overdue.user_id == owner.id
    assert "Lucía Mendoza" in overdue.body
    assert overdue.dedupe_key == f"attendance_request_overdue:{request.id}:{owner.id}"

    # Reopening the queue (a read path) does not repeat the notice.
    after = request.created_at + timedelta(days=3)
    assert escalate_overdue_attendance_requests(session, now=after) == 0
    list_attendance_requests(session, status="pending")
    assert len(session.exec(overdue_query).all()) == 1

    decide_attendance_request(
        session,
        request_id=request.id,
        actor_id=manager.id,
        decision="rejected",
        note="El reloj de recepción marca la hora original",
    )
    session.refresh(overdue)
    assert overdue.resolved_at is not None


def test_zero_term_disables_the_deadline(session: Session) -> None:
    employee, account, manager = seed_employee_with_account(session)
    register_user(
        session,
        email="owner2@example.test",
        password="owner-password-long-enough",
        role_codes=("owner",),
    )
    update_staffing_settings(
        session,
        check_in_early_grace_minutes=15,
        lateness_tolerance_minutes=0,
        attendance_request_sla_hours=0,
        actor_id=manager.id,
    )
    attendance = seed_attendance(session, employee.id, manager.id, late_minutes=7)
    request = request_attendance_change(
        session,
        attendance_id=attendance.id,
        actor_id=account.id,
        employee_id=employee.id,
        mark="check_in",
        action="correct",
        proposed_at=START,
        justification="Llegué a la hora y marqué tarde",
    )
    assert request.due_at is None
    assert attendance_request_is_overdue(request, now=request.created_at + timedelta(days=30)) is False
    assert escalate_overdue_attendance_requests(session, now=request.created_at + timedelta(days=30)) == 0
    assert (
        session.exec(
            select(StaffNotification).where(StaffNotification.kind == "attendance_request_overdue")
        ).all()
        == []
    )

    # Raising the term again only affects requests created afterwards.
    update_staffing_settings(
        session,
        check_in_early_grace_minutes=15,
        lateness_tolerance_minutes=0,
        attendance_request_sla_hours=24,
        actor_id=manager.id,
    )
    assert session.get(StaffAttendanceRequest, request.id).due_at is None


def test_annulment_report_groups_by_operator(session: Session) -> None:
    employee, account, manager = seed_employee_with_account(session)
    first = seed_attendance(session, employee.id, manager.id, late_minutes=1)
    clock_out(
        session,
        shift_id=first.shift_id,
        actor_id=manager.id,
        request_id=uuid4(),
        occurred_at=START + timedelta(hours=8),
    )
    void_attendance_mark(
        session,
        attendance_id=first.id,
        actor_id=manager.id,
        request_id=uuid4(),
        mark="check_out",
        reason="La salida era de otro día",
    )

    second = seed_attendance(session, employee.id, manager.id, late_minutes=2, day_offset=1)
    void_attendance_mark(
        session,
        attendance_id=second.id,
        actor_id=account.id,
        request_id=uuid4(),
        mark="check_in",
        reason="Se marcó en el turno equivocado",
    )

    # The report filters by when the annulment was made, not by the shift date.
    now = datetime.now(timezone.utc)
    report = list_attendance_annulments(
        session, from_at=now - timedelta(hours=1), to_at=now + timedelta(hours=1)
    )
    assert report.total == 2
    summary = {row.actor_id: (row.check_ins, row.check_outs, row.total) for row in report.by_operator}
    assert summary == {manager.id: (0, 1, 1), account.id: (1, 0, 1)}
    assert {row.event_type for row in report.items} == {"attendance_voided", "check_out_voided"}
    assert {row.employee_name for row in report.items} == {"Lucía Mendoza"}
    assert all(row.reason for row in report.items)

    only_manager = list_attendance_annulments(
        session, from_at=now - timedelta(hours=1), actor_id=manager.id
    )
    assert only_manager.total == 1
    assert only_manager.items[0].event_type == "check_out_voided"

    outside = list_attendance_annulments(session, from_at=now + timedelta(days=3))
    assert outside.total == 0 and outside.by_operator == []


def test_employee_without_account_is_still_corrected(session: Session) -> None:
    ensure_default_access_control(session)
    employee = Employee(
        employee_number="EMP-400",
        first_name="Sin",
        last_name="Cuenta",
        email="sincuenta@example.test",
        job_title="Mantenimiento",
    )
    session.add(employee)
    session.commit()
    manager = register_user(
        session,
        email="manager2@example.test",
        password="manager-password-long-enough",
        role_codes=("manager",),
    )
    attendance = seed_attendance(session, employee.id, manager.id, late_minutes=6)

    correct_attendance(
        session,
        attendance_id=attendance.id,
        actor_id=manager.id,
        request_id=uuid4(),
        event_type="check_in",
        occurred_at=START,
        reason="Sin cuenta vinculada",
    )
    assert session.exec(select(StaffNotification)).all() == []