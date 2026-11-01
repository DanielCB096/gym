"""The deferred-notices task that writes reminders without a reader (ADR-076).

The member reminders and the two staff notices used to exist only because a
read path looked for them. The task materialises the same producers from cron,
so a member who never opens the app still receives the expiring-membership, the
class and the physiotherapy reminders, and the owners still hear about an
overdue change request and an expiring kiosk token.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.access.kiosk import create_kiosk_device, warn_expiring_kiosk_tokens
from app.modules.classes.models import ClassReservation, ClassSession, ClassType
from app.modules.identity.models import Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan, utc_now
from app.modules.notifications.models import (
    MemberNotification,
    MemberNotificationPreference,
    MemberPushDelivery,
    StaffNotification,
)
from app.modules.notifications.push import register_member_push_token
from app.modules.notifications.service import (
    list_member_notifications,
    materialise_deferred_notices,
)
from app.modules.physio.models import PhysioAppointment, PhysioService
from app.modules.staffing.service import clock_in, create_shift, request_attendance_change

EMIT = Path(__file__).resolve().parents[1] / "emit_deferred_notices.py"

spec = importlib.util.spec_from_file_location("emit_deferred_notices", EMIT)
emit_deferred_notices = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(emit_deferred_notices)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
PREVIEW_URL = "sqlite:///./gym_preview.db"
TOKEN = "ExponentPushToken[deferred-reminder]"


@pytest.fixture(autouse=True)
def _restore_preview_env() -> Iterator[None]:
    before = os.environ.get("PREVIEW_MODE")
    yield
    if before is None:
        os.environ.pop("PREVIEW_MODE", None)
    else:
        os.environ["PREVIEW_MODE"] = before


def _member(
    session: Session, *, email: str, ends_in: timedelta, now: datetime = NOW
) -> Membership:
    member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
    session.add(member)
    session.flush()
    plan = Plan(
        code=f"PLAN-{uuid4().hex[:8].upper()}",
        name="Mensual",
        duration_days=30,
        price_cents=50000,
    )
    session.add(plan)
    session.flush()
    membership = Membership(
        member_id=member.id,
        plan_id=plan.id,
        status="active",
        starts_at=now - timedelta(days=5),
        ends_at=now + ends_in,
    )
    session.add(membership)
    session.commit()
    return membership


def _class_reservation(
    session: Session, member_id, *, starts_in: timedelta, now: datetime = NOW
) -> ClassReservation:
    class_type = ClassType(name=f"Spinning {uuid4().hex[:4]}")
    session.add(class_type)
    session.flush()
    class_session = ClassSession(
        title="Spinning 6am",
        class_type_id=class_type.id,
        starts_at=now + starts_in,
        ends_at=now + starts_in + timedelta(hours=1),
        capacity=10,
    )
    session.add(class_session)
    session.flush()
    reservation = ClassReservation(
        session_id=class_session.id,
        member_id=member_id,
        status="reserved",
    )
    session.add(reservation)
    session.commit()
    return reservation


def _physio_appointment(
    session: Session, member_id, *, starts_in: timedelta, now: datetime = NOW
) -> PhysioAppointment:
    service = PhysioService(
        code=f"FISIO-{uuid4().hex[:4].upper()}",
        name="Masaje",
        duration_minutes=60,
        price_cents=50000,
    )
    therapist = Employee(
        employee_number=f"EMP-{uuid4().hex[:6].upper()}",
        first_name="Tere",
        last_name="Fisio",
        job_title="Fisioterapeuta",
    )
    session.add_all([service, therapist])
    session.flush()
    appointment = PhysioAppointment(
        member_id=member_id,
        service_id=service.id,
        therapist_employee_id=therapist.id,
        starts_at=now + starts_in,
        ends_at=now + starts_in + timedelta(minutes=60),
        room="Sala 1",
    )
    session.add(appointment)
    session.commit()
    return appointment


def _overdue_request(session: Session) -> object:
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
    owner = register_user(
        session,
        email="owner@example.test",
        password="owner-strong-password",
        role_codes=("owner",),
    )
    account = register_user(
        session,
        email="lucia.account@example.test",
        password="lucia-password-long-enough",
        employee_id=employee.id,
        role_codes=("reception",),
    )
    starts_at = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)
    shift = create_shift(
        session,
        employee_id=employee.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=8),
        created_by=owner.id,
    )
    attendance = clock_in(
        session,
        shift_id=shift.id,
        actor_id=owner.id,
        request_id=uuid4(),
        occurred_at=starts_at,
    )
    request = request_attendance_change(
        session,
        attendance_id=attendance.id,
        actor_id=account.id,
        employee_id=employee.id,
        mark="check_in",
        action="correct",
        proposed_at=starts_at,
        justification="Marqué la entrada por error",
    )
    return request


def test_task_writes_member_and_staff_notices_without_reading_any_inbox(
    session: Session,
) -> None:
    request = _overdue_request(session)
    run_at = request.created_at + timedelta(hours=25)

    membership = _member(
        session, email="ana@example.test", ends_in=timedelta(days=3), now=run_at
    )
    reservation = _class_reservation(
        session, membership.member_id, starts_in=timedelta(hours=20), now=run_at
    )
    appointment = _physio_appointment(
        session, membership.member_id, starts_in=timedelta(hours=20), now=run_at
    )
    # A fresh token is not announced; one issued eighty days ago is ten days
    # from expiring and falls inside the warning window.
    create_kiosk_device(session, label="Recepción", now=run_at - timedelta(days=80))
    create_kiosk_device(session, label="Bodega", now=run_at)

    # Nobody has opened either inbox yet; booking the request itself already
    # wrote the notice that tells the supervisor there is work to do.
    baseline = {row.id for row in session.exec(select(StaffNotification)).all()}
    assert session.exec(select(MemberNotification)).all() == []

    result = materialise_deferred_notices(session, now=run_at)

    assert result.members_checked == 1
    assert result.member_notices_written == 3
    assert result.attendance_escalations_written == 1
    assert result.kiosk_token_notices_written == 1
    assert result.staff_notices_written == 2

    member_notices = session.exec(select(MemberNotification)).all()
    assert {row.kind for row in member_notices} == {
        "membership_expiring",
        "class_reminder",
        "physio_reminder",
    }
    assert all(row.read_at is None for row in member_notices)
    expected_keys = {
        f"membership_expiring:{membership.id}:3",
        f"class_reminder:{reservation.id}:24",
        f"physio_reminder:{appointment.id}:24",
    }
    assert {row.dedupe_key for row in member_notices} == expected_keys

    staff_notices = [
        row for row in session.exec(select(StaffNotification)).all() if row.id not in baseline
    ]
    assert {row.kind for row in staff_notices} == {
        "attendance_request_overdue",
        "kiosk_token_expiring",
    }
    assert all(row.read_at is None and row.resolved_at is None for row in staff_notices)

    # A second pass inside the same windows finds the sources again but writes
    # nothing: every producer deduplicates itself.
    again = materialise_deferred_notices(session, now=run_at + timedelta(minutes=30))
    assert again.members_checked == 1
    assert again.member_notices_written == 0
    assert again.attendance_escalations_written == 0
    assert again.kiosk_token_notices_written == 0
    assert len(session.exec(select(MemberNotification)).all()) == 3
    assert len(session.exec(select(StaffNotification)).all()) == len(baseline) + 2


def test_sources_outside_every_window_are_ignored(session: Session) -> None:
    membership = _member(session, email="beto@example.test", ends_in=timedelta(days=8))
    reservation = _class_reservation(
        session, membership.member_id, starts_in=timedelta(hours=25)
    )
    appointment = _physio_appointment(
        session, membership.member_id, starts_in=timedelta(hours=25)
    )

    empty = materialise_deferred_notices(session, now=NOW)
    assert empty.members_checked == 0
    assert empty.member_notices_written == 0
    assert session.exec(select(MemberNotification)).all() == []

    # Bringing each source to its tightest threshold produces the reminders.
    membership.ends_at = NOW + timedelta(days=7)
    class_session = session.get(ClassSession, reservation.session_id)
    class_session.starts_at = NOW + timedelta(hours=24)
    class_session.ends_at = NOW + timedelta(hours=25)
    appointment.starts_at = NOW + timedelta(hours=24)
    appointment.ends_at = NOW + timedelta(hours=25)
    session.add(membership)
    session.add(class_session)
    session.add(appointment)
    session.commit()

    due = materialise_deferred_notices(session, now=NOW)
    assert due.members_checked == 1
    assert due.member_notices_written == 3


def test_kiosk_warning_counts_only_rows_it_actually_writes(session: Session) -> None:
    ensure_default_access_control(session)
    register_user(
        session,
        email="owner@example.test",
        password="owner-strong-password",
        role_codes=("owner",),
    )
    # The role assignment takes effect when the account is created, so the
    # warning runs a minute later instead of at a fixed past instant.
    run_at = utc_now() + timedelta(minutes=1)
    create_kiosk_device(session, label="Tablet", now=run_at - timedelta(days=80))

    assert warn_expiring_kiosk_tokens(session, now=run_at) == 1
    assert warn_expiring_kiosk_tokens(session, now=run_at) == 0


def test_scheduler_queues_one_push_per_reminder_without_a_reader(
    session: Session,
) -> None:
    membership = _member(session, email="ana@example.test", ends_in=timedelta(days=3))
    _class_reservation(session, membership.member_id, starts_in=timedelta(hours=20))
    _physio_appointment(session, membership.member_id, starts_in=timedelta(hours=20))
    register_member_push_token(
        session, membership.member_id, token=TOKEN, platform="android", now=NOW
    )

    result = materialise_deferred_notices(session, now=NOW)

    assert result.member_notices_written == 3
    deliveries = session.exec(select(MemberPushDelivery)).all()
    assert len(deliveries) == 3
    assert all(row.status == "pending" for row in deliveries)
    notice_kinds = {
        session.get(MemberNotification, row.notification_id).kind
        for row in deliveries
    }
    assert notice_kinds == {
        "membership_expiring",
        "class_reminder",
        "physio_reminder",
    }


def test_read_path_materialises_the_reminder_without_ringing_the_phone(
    session: Session,
) -> None:
    membership = _member(session, email="ana@example.test", ends_in=timedelta(days=3))
    register_member_push_token(
        session, membership.member_id, token=TOKEN, platform="android", now=NOW
    )

    page = list_member_notifications(session, membership.member_id, now=NOW)

    assert [item.kind for item in page.items] == ["membership_expiring"]
    assert session.exec(select(MemberPushDelivery)).all() == []


def test_a_switched_off_category_writes_the_notice_without_push(
    session: Session,
) -> None:
    membership = _member(session, email="ana@example.test", ends_in=timedelta(days=3))
    register_member_push_token(
        session, membership.member_id, token=TOKEN, platform="android", now=NOW
    )
    session.add(
        MemberNotificationPreference(
            member_id=membership.member_id,
            category="membership",
            push_enabled=False,
            updated_at=NOW,
        )
    )
    session.commit()

    result = materialise_deferred_notices(session, now=NOW)

    assert result.member_notices_written == 1
    assert [row.kind for row in session.exec(select(MemberNotification)).all()] == [
        "membership_expiring"
    ]
    assert session.exec(select(MemberPushDelivery)).all() == []


def test_preview_script_writes_a_due_reminder_and_repeats_safely(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    engine = create_engine(PREVIEW_URL)
    SQLModel.metadata.create_all(engine)
    now = utc_now()
    with Session(engine) as session:
        member = Member(
            first_name="Ana", last_name="Demo", email="ana@example.test", status="active"
        )
        session.add(member)
        session.flush()
        plan = Plan(code="PLAN-PREVIEW", name="Mensual", duration_days=30, price_cents=50000)
        session.add(plan)
        session.flush()
        session.add(
            Membership(
                member_id=member.id,
                plan_id=plan.id,
                status="active",
                starts_at=now - timedelta(days=5),
                ends_at=now + timedelta(days=3),
            )
        )
        session.commit()
    engine.dispose()

    assert emit_deferred_notices.main(["--preview"]) == 0
    first = capsys.readouterr().out
    assert "Base de vista previa: sqlite:///./gym_preview.db" in first
    assert "Revisados 1 socios" in first
    assert "Escritos 1 avisos del socio y 0 del personal" in first

    assert emit_deferred_notices.main(["--preview"]) == 0
    second = capsys.readouterr().out
    assert "Escritos 0 avisos del socio y 0 del personal" in second

    engine = create_engine(PREVIEW_URL)
    with Session(engine) as session:
        rows = session.exec(select(MemberNotification)).all()
    engine.dispose()
    assert [row.kind for row in rows] == ["membership_expiring"]


def test_preview_script_drains_the_queued_push(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    engine = create_engine(PREVIEW_URL)
    SQLModel.metadata.create_all(engine)
    now = utc_now()
    with Session(engine) as session:
        member = Member(
            first_name="Ana", last_name="Demo", email="ana@example.test", status="active"
        )
        session.add(member)
        session.flush()
        plan = Plan(code="PLAN-PREVIEW", name="Mensual", duration_days=30, price_cents=50000)
        session.add(plan)
        session.flush()
        session.add(
            Membership(
                member_id=member.id,
                plan_id=plan.id,
                status="active",
                starts_at=now - timedelta(days=5),
                ends_at=now + timedelta(days=3),
            )
        )
        register_member_push_token(
            session, member.id, token=TOKEN, platform="android", now=now
        )
        session.commit()
    engine.dispose()

    assert emit_deferred_notices.main(["--preview"]) == 0
    first = capsys.readouterr().out
    assert "Push del socio: 1 intentos — enviados 0, simulados 1" in first
    assert "Entregas de push pendientes que quedan: 0." in first

    engine = create_engine(PREVIEW_URL)
    with Session(engine) as session:
        deliveries = session.exec(select(MemberPushDelivery)).all()
    engine.dispose()
    assert [row.status for row in deliveries] == ["simulated"]
    assert all(row.attempts == 1 for row in deliveries)

    assert emit_deferred_notices.main(["--preview"]) == 0
    second = capsys.readouterr().out
    assert "Escritos 0 avisos del socio" in second
    assert "Push del socio: 0 intentos" in second


def test_script_rejects_an_out_of_range_push_limit() -> None:
    for limit in ("0", "101"):
        with pytest.raises(SystemExit) as raised:
            emit_deferred_notices.main(["--preview", "--push-limit", limit])
        assert raised.value.code == 2


def test_script_requires_a_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert emit_deferred_notices.main([]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_script_rejects_preview_together_with_a_database_url() -> None:
    with pytest.raises(SystemExit) as raised:
        emit_deferred_notices.main(["--preview", "--database-url", "sqlite:///x.db"])
    assert raised.value.code == 2


def test_script_reports_an_unreachable_database(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    url = f"sqlite:///{(tmp_path / 'missing' / 'dir' / 'gym.db').as_posix()}"

    assert emit_deferred_notices.main(["--database-url", url]) == 1
    assert "Error al emitir los avisos diferidos" in capsys.readouterr().err
