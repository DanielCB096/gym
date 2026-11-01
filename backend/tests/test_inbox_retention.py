"""Retention for both inboxes and for the staff delivery queues.

A read member notice and a finished staff notice are kept for a configurable
number of days, and so are the terminal deliveries of the staff email and push
queues. Pending work, unread notices, the rows a receipt still points at and the
kiosk token warning are never touched.
"""

import importlib.util
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.identity.models import AppUser
from app.modules.memberships.models import Member
from app.modules.notifications.inbox_retention import (
    DEFAULT_INBOX_RETENTION_DAYS,
    DEFAULT_STAFF_DELIVERY_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    MIN_DELIVERY_RETENTION_DAYS,
    MIN_INBOX_RETENTION_DAYS,
    inbox_retention_policy_from_env,
    purge_inbox_history,
)
from app.modules.notifications.models import (
    MemberNotification,
    MemberNotificationEmailDelivery,
    MemberPushDelivery,
    StaffNotification,
    StaffNotificationDelivery,
    StaffNotificationDeliveryReceipt,
    StaffPushDelivery,
    StaffPushSubscription,
)

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)
PURGE = Path(__file__).resolve().parents[1] / "purge_inbox_data.py"

spec = importlib.util.spec_from_file_location("purge_inbox_data", PURGE)
purge_inbox_script = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(purge_inbox_script)


@pytest.fixture(autouse=True)
def _clear_retention_env(monkeypatch) -> Iterator[None]:
    monkeypatch.delenv("NOTIFICATION_INBOX_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("STAFF_DELIVERY_RETENTION_DAYS", raising=False)
    yield


def _member(session: Session) -> Member:
    member = Member(
        first_name="Ana",
        last_name="Demo",
        email=f"ana-{uuid4().hex[:8]}@example.test",
        status="active",
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def _member_notice(
    session: Session,
    *,
    created_days_ago: int,
    read: bool = True,
    kind: str = "class_reserved",
    member: Member | None = None,
    now: datetime = NOW,
) -> MemberNotification:
    member = member or _member(session)
    created_at = now - timedelta(days=created_days_ago)
    notice = MemberNotification(
        member_id=member.id,
        kind=kind,
        title="Aviso de prueba",
        body="Cuerpo del aviso de prueba.",
        created_at=created_at,
        read_at=created_at if read else None,
    )
    session.add(notice)
    session.commit()
    session.refresh(notice)
    return notice


def _member_push_delivery(
    session: Session, notice: MemberNotification, *, created_days_ago: int = 400
) -> MemberPushDelivery:
    created_at = NOW - timedelta(days=created_days_ago)
    delivery = MemberPushDelivery(
        notification_id=notice.id,
        member_id=notice.member_id,
        token=f"ExponentPushToken[{uuid4().hex[:12]}]",
        status="sent",
        attempts=1,
        sent_at=created_at,
        created_at=created_at,
    )
    session.add(delivery)
    session.commit()
    return delivery


def _member_email_delivery(
    session: Session,
    notice: MemberNotification,
    *,
    status: str = "sent",
    next_attempt_at: datetime | None = None,
    created_days_ago: int = 400,
) -> MemberNotificationEmailDelivery:
    created_at = NOW - timedelta(days=created_days_ago)
    delivery = MemberNotificationEmailDelivery(
        notification_id=notice.id,
        member_id=notice.member_id,
        recipient="ana@example.test",
        message_id=f"{uuid4().hex}@example.test",
        status=status,
        attempts=1,
        next_attempt_at=next_attempt_at,
        sent_at=created_at if status == "sent" else None,
        created_at=created_at,
    )
    session.add(delivery)
    session.commit()
    return delivery


def _user(session: Session) -> AppUser:
    user = AppUser(
        email=f"staff-{uuid4().hex[:8]}@example.test",
        password_hash="not-a-real-hash",
        status="active",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _staff_notice(
    session: Session,
    user: AppUser,
    *,
    created_days_ago: int,
    read: bool = True,
    resolved: bool = False,
    kind: str = "attendance_corrected",
    now: datetime = NOW,
) -> StaffNotification:
    created_at = now - timedelta(days=created_days_ago)
    notice = StaffNotification(
        user_id=user.id,
        kind=kind,
        title="Aviso de prueba",
        body="Cuerpo del aviso de prueba.",
        created_at=created_at,
        read_at=created_at if read else None,
        resolved_at=created_at if resolved else None,
    )
    session.add(notice)
    session.commit()
    session.refresh(notice)
    return notice


def _email_delivery(
    session: Session,
    notice: StaffNotification,
    *,
    created_days_ago: int = 400,
    status: str = "sent",
) -> StaffNotificationDelivery:
    created_at = NOW - timedelta(days=created_days_ago)
    delivery = StaffNotificationDelivery(
        notice_id=notice.id,
        recipient="staff@example.test",
        status=status,
        attempts=1,
        sent_at=created_at if status != "pending" else None,
        created_at=created_at,
    )
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


def _email_receipt(
    session: Session,
    delivery: StaffNotificationDelivery,
    *,
    received_days_ago: int = 1,
) -> StaffNotificationDeliveryReceipt:
    receipt = StaffNotificationDeliveryReceipt(
        delivery_id=delivery.id,
        provider_event_id=f"evt-{uuid4().hex}",
        event_type="delivered",
        occurred_at=NOW,
        received_at=NOW - timedelta(days=received_days_ago),
    )
    session.add(receipt)
    session.commit()
    return receipt


def _push_delivery(
    session: Session,
    notice: StaffNotification,
    *,
    created_days_ago: int = 400,
    status: str = "sent",
) -> StaffPushDelivery:
    subscription = StaffPushSubscription(
        user_id=notice.user_id,
        endpoint=f"https://push.example.test/{uuid4().hex}",
        p256dh="p256dh-key",
        auth="auth-secret",
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    created_at = NOW - timedelta(days=created_days_ago)
    delivery = StaffPushDelivery(
        notice_id=notice.id,
        user_id=notice.user_id,
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        status=status,
        attempts=1,
        sent_at=created_at if status != "pending" else None,
        created_at=created_at,
    )
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


def _ids(session: Session, model) -> set[UUID]:
    return set(session.exec(select(model.id)).all())


def test_only_read_member_notices_past_the_window_are_deleted(
    session: Session,
) -> None:
    old_read = _member_notice(session, created_days_ago=400)
    young_read = _member_notice(session, created_days_ago=10)
    old_unread = _member_notice(session, created_days_ago=400, read=False)

    result = purge_inbox_history(session, now=NOW)

    assert result.inbox_days == DEFAULT_INBOX_RETENTION_DAYS
    assert result.inbox_cutoff == NOW - timedelta(days=DEFAULT_INBOX_RETENTION_DAYS)
    assert result.member_notices_deleted == 1
    assert _ids(session, MemberNotification) == {young_read.id, old_unread.id}
    assert old_read.id not in _ids(session, MemberNotification)


def test_member_notice_with_a_push_delivery_is_kept(session: Session) -> None:
    notice = _member_notice(session, created_days_ago=400)
    _member_push_delivery(session, notice)

    result = purge_inbox_history(session, now=NOW)

    assert result.member_notices_deleted == 0


def test_terminal_member_email_delivery_and_old_notice_are_purged_together(
    session: Session,
) -> None:
    notice = _member_notice(session, created_days_ago=400)
    delivery = _member_email_delivery(session, notice, status="sent")

    result = purge_inbox_history(session, now=NOW)

    assert result.member_email_deliveries_deleted == 1
    assert result.member_notices_deleted == 1
    assert delivery.id not in _ids(session, MemberNotificationEmailDelivery)
    assert notice.id not in _ids(session, MemberNotification)


def test_pending_or_scheduled_member_email_keeps_the_old_notice(
    session: Session,
) -> None:
    notice = _member_notice(session, created_days_ago=400)
    delivery = _member_email_delivery(
        session,
        notice,
        status="failed",
        next_attempt_at=NOW + timedelta(minutes=5),
    )

    result = purge_inbox_history(session, now=NOW)

    assert result.member_email_deliveries_deleted == 0
    assert result.member_notices_deleted == 0
    assert session.get(MemberNotificationEmailDelivery, delivery.id) is not None
    assert session.get(MemberNotification, notice.id) is not None
    assert _ids(session, MemberNotification) == {notice.id}


def test_staff_informational_notice_is_deleted_once_read(session: Session) -> None:
    user = _user(session)
    old_read = _staff_notice(session, user, created_days_ago=400)
    young_read = _staff_notice(session, user, created_days_ago=10)
    old_unread = _staff_notice(session, user, created_days_ago=400, read=False)

    result = purge_inbox_history(session, now=NOW)

    assert result.staff_notices_deleted == 1
    assert _ids(session, StaffNotification) == {young_read.id, old_unread.id}
    assert old_read.id not in _ids(session, StaffNotification)


def test_actionable_notice_needs_to_be_resolved_not_just_read(
    session: Session,
) -> None:
    user = _user(session)
    read_pending = _staff_notice(
        session, user, created_days_ago=400, kind="workout_pending_review"
    )
    ticket_pending = _staff_notice(
        session, user, created_days_ago=400, kind="maintenance_ticket_assigned"
    )
    resolved_unread = _staff_notice(
        session,
        user,
        created_days_ago=400,
        read=False,
        resolved=True,
        kind="workout_pending_review",
    )

    result = purge_inbox_history(session, now=NOW)

    assert result.staff_notices_deleted == 1
    assert _ids(session, StaffNotification) == {read_pending.id, ticket_pending.id}
    assert resolved_unread.id not in _ids(session, StaffNotification)


def test_kiosk_token_warning_is_never_deleted(session: Session) -> None:
    user = _user(session)
    notice = _staff_notice(
        session,
        user,
        created_days_ago=MAX_RETENTION_DAYS,
        kind="kiosk_token_expiring",
    )

    result = purge_inbox_history(session, now=NOW)

    assert result.staff_notices_deleted == 0
    assert _ids(session, StaffNotification) == {notice.id}


def test_staff_notice_with_a_live_delivery_is_kept(session: Session) -> None:
    user = _user(session)
    email_notice = _staff_notice(session, user, created_days_ago=400)
    _email_delivery(session, email_notice, created_days_ago=10)
    push_notice = _staff_notice(session, user, created_days_ago=400)
    _push_delivery(session, push_notice, created_days_ago=10)

    result = purge_inbox_history(session, now=NOW)

    assert result.staff_notices_deleted == 0
    assert _ids(session, StaffNotification) == {email_notice.id, push_notice.id}


def test_terminal_staff_deliveries_past_the_window_are_deleted(
    session: Session,
) -> None:
    user = _user(session)
    notices = {
        status: _staff_notice(session, user, created_days_ago=1)
        for status in ("sent", "simulated", "failed", "pending")
    }
    deliveries = {
        status: _email_delivery(
            session, notices[status], created_days_ago=400, status=status
        )
        for status in ("sent", "simulated", "failed", "pending")
    }
    young = _email_delivery(
        session,
        _staff_notice(session, user, created_days_ago=1),
        created_days_ago=10,
    )

    result = purge_inbox_history(session, now=NOW)

    assert result.staff_email_deliveries_deleted == 3
    remaining = _ids(session, StaffNotificationDelivery)
    assert remaining == {deliveries["pending"].id, young.id}


def test_email_delivery_with_a_live_receipt_is_kept(session: Session) -> None:
    user = _user(session)
    delivery = _email_delivery(
        session,
        _staff_notice(session, user, created_days_ago=1),
        created_days_ago=400,
    )
    _email_receipt(session, delivery)

    result = purge_inbox_history(session, now=NOW)

    assert result.staff_email_deliveries_deleted == 0
    assert _ids(session, StaffNotificationDelivery) == {delivery.id}


def test_an_old_push_delivery_frees_its_notice_in_the_same_run(
    session: Session,
) -> None:
    user = _user(session)
    notice = _staff_notice(session, user, created_days_ago=400)
    delivery = _push_delivery(session, notice, created_days_ago=400)

    result = purge_inbox_history(session, now=NOW)

    assert result.staff_push_deliveries_deleted == 1
    assert result.staff_notices_deleted == 1
    assert _ids(session, StaffPushDelivery) == set()
    assert notice.id not in _ids(session, StaffNotification)
    assert delivery.id not in _ids(session, StaffPushDelivery)


def test_windows_are_independent(session: Session) -> None:
    user = _user(session)
    notice = _staff_notice(session, user, created_days_ago=60)
    delivery = _email_delivery(session, notice, created_days_ago=60)

    first = purge_inbox_history(session, now=NOW, inbox_days=30, delivery_days=400)

    assert first.staff_email_deliveries_deleted == 0
    assert first.staff_notices_deleted == 0
    assert _ids(session, StaffNotification) == {notice.id}

    second = purge_inbox_history(session, now=NOW, inbox_days=30, delivery_days=30)

    assert second.staff_email_deliveries_deleted == 1
    assert second.staff_notices_deleted == 1
    assert delivery.id not in _ids(session, StaffNotificationDelivery)


def test_dry_run_counts_without_deleting(session: Session) -> None:
    notice = _member_notice(session, created_days_ago=400)

    result = purge_inbox_history(session, now=NOW, dry_run=True)

    assert result.dry_run is True
    assert result.member_notices_deleted == 1
    assert _ids(session, MemberNotification) == {notice.id}


def test_second_run_deletes_nothing(session: Session) -> None:
    _member_notice(session, created_days_ago=400)
    user = _user(session)
    notice = _staff_notice(session, user, created_days_ago=400)
    _email_delivery(session, notice, created_days_ago=400)

    first = purge_inbox_history(session, now=NOW)
    second = purge_inbox_history(session, now=NOW)

    assert first.member_notices_deleted == 1
    assert first.staff_email_deliveries_deleted == 1
    assert first.staff_notices_deleted == 1
    assert second.member_notices_deleted == 0
    assert second.staff_email_deliveries_deleted == 0
    assert second.staff_push_deliveries_deleted == 0
    assert second.staff_notices_deleted == 0


@pytest.mark.parametrize(
    "value", [0, MIN_INBOX_RETENTION_DAYS - 1, MAX_RETENTION_DAYS + 1]
)
def test_inbox_window_is_validated(session: Session, value: int) -> None:
    with pytest.raises(ValueError):
        purge_inbox_history(session, now=NOW, inbox_days=value)


@pytest.mark.parametrize(
    "value", [0, MIN_DELIVERY_RETENTION_DAYS - 1, MAX_RETENTION_DAYS + 1]
)
def test_delivery_window_is_validated(session: Session, value: int) -> None:
    with pytest.raises(ValueError):
        purge_inbox_history(session, now=NOW, delivery_days=value)


def test_policy_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFICATION_INBOX_RETENTION_DAYS", "90")
    monkeypatch.setenv("STAFF_DELIVERY_RETENTION_DAYS", "180")

    policy = inbox_retention_policy_from_env()

    assert policy.inbox_days == 90
    assert policy.delivery_days == 180


def test_policy_rejects_an_invalid_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTIFICATION_INBOX_RETENTION_DAYS", "0")

    with pytest.raises(ValueError):
        inbox_retention_policy_from_env()


def _seed_database_file(db_path: Path) -> dict[str, UUID]:
    # El script de purga corre con el reloj de la sala, no con la `NOW` congelada
    # del resto del archivo: sembrar contra el mismo instante que él va a leer.
    # Con la fecha congelada, el aviso «joven» dejaba de serlo al vencer los 365
    # días y la prueba se ponía roja sin que la retención hubiera cambiado.
    real_now = datetime.now(timezone.utc)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            old_read = _member_notice(session, created_days_ago=400, now=real_now)
            young_unread = _member_notice(session, created_days_ago=1, read=False, now=real_now)
            user = _user(session)
            old_staff = _staff_notice(session, user, created_days_ago=400, now=real_now)
            return {
                "old_read": old_read.id,
                "young_unread": young_unread.id,
                "old_staff": old_staff.id,
            }
    finally:
        engine.dispose()


def _remaining(db_path: Path) -> tuple[set[UUID], set[UUID]]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with Session(engine) as session:
            return (
                _ids(session, MemberNotification),
                _ids(session, StaffNotification),
            )
    finally:
        engine.dispose()


def test_script_purges_the_file_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "inbox.db"
    ids = _seed_database_file(db_path)

    code = purge_inbox_script.main(["--database-url", f"sqlite:///{db_path.as_posix()}"])

    assert code == 0
    output = capsys.readouterr().out
    assert "Avisos creados antes de" in output
    assert "1 del socio y 1 del personal" in output
    members, staff = _remaining(db_path)
    assert members == {ids["young_unread"]}
    assert staff == set()


def test_script_preview_reports_an_empty_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    code = purge_inbox_script.main(["--preview"])

    assert code == 0
    output = capsys.readouterr().out
    assert "gym_preview.db" in output
    assert "0 del socio y 0 del personal" in output


def test_script_rejects_preview_and_database_url_together() -> None:
    with pytest.raises(SystemExit) as error:
        purge_inbox_script.main(["--preview", "--database-url", "sqlite:///other.db"])

    assert error.value.code == 2


def test_script_exits_with_two_without_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = purge_inbox_script.main([])

    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_script_rejects_an_invalid_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    code = purge_inbox_script.main(["--preview", "--inbox-days", "0"])

    assert code == 2
    assert "NOTIFICATION_INBOX_RETENTION_DAYS" in capsys.readouterr().err


def test_script_exits_with_one_on_an_unreachable_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    code = purge_inbox_script.main(
        ["--database-url", "sqlite:///missing-dir/inbox.db"]
    )

    assert code == 1
    assert "Error al purgar la bandeja" in capsys.readouterr().err
