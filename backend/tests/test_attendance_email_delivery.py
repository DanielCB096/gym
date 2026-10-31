from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

from app.mailer import MailDeliveryFailed, MailNotConfigured
from app.modules.identity.models import AppUser, Employee
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications import delivery as delivery_module
from app.modules.notifications.delivery import (
    AttendanceEmailDisabled,
    NotificationDeliveryNotFound,
    NotificationDeliveryRetryNotAllowed,
    email_message_for_notice,
    list_staff_notification_deliveries,
    retry_staff_notification_delivery,
    send_pending_staff_notification_emails,
    staff_notification_delivery_counts,
)
from app.modules.notifications.models import (
    STAFF_NOTIFICATION_KINDS,
    StaffNotification,
    StaffNotificationDelivery,
)
from app.modules.notifications.service import create_staff_notification
from app.modules.staffing.service import update_staffing_settings

NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)


def seed_accounts(session: Session) -> tuple[Employee, AppUser, AppUser]:
    ensure_default_access_control(session)
    employee = Employee(
        employee_number="EMP-200",
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


def queue_notice(
    session: Session,
    user_id: UUID,
    *,
    title: str = "Se corrigió tu marca",
    body: str = "Recepción corrigió tu entrada de las 19:30 a las 19:15.",
    now: datetime | None = None,
) -> StaffNotification:
    return create_staff_notification(
        session,
        user_id=user_id,
        kind="attendance_corrected",
        title=title,
        body=body,
        now=now,
    )


def outgoing(monkeypatch) -> list[dict[str, str]]:
    sent: list[dict[str, str]] = []

    def fake_send_email(*, recipient: str, subject: str, body: str, **_kwargs) -> str:
        sent.append({"recipient": recipient, "subject": subject, "body": body})
        return "sent"

    monkeypatch.setattr(delivery_module, "send_email", fake_send_email)
    return sent


def test_pass_sends_each_pending_delivery_once(session: Session, monkeypatch) -> None:
    _, account, _ = seed_accounts(session)
    first = queue_notice(session, account.id, title="Se corrigió tu marca", now=NOW)
    second = queue_notice(
        session,
        account.id,
        title="Se anuló tu salida",
        body="La salida de las 03:00 quedó anulada: era de otro día.",
        now=NOW + timedelta(minutes=1),
    )
    sent = outgoing(monkeypatch)

    result = send_pending_staff_notification_emails(session, now=NOW + timedelta(minutes=5))

    assert result.enabled is True
    assert (result.attempted, result.sent, result.simulated, result.failed) == (2, 2, 0, 0)
    assert result.remaining == 0
    assert [item["recipient"] for item in sent] == [
        "lucia.account@example.test",
        "lucia.account@example.test",
    ]
    assert sent[0]["subject"] == "[Asistencia] Se corrigió tu marca"
    assert first.body in sent[0]["body"]
    assert "Personal" in sent[0]["body"]
    assert "automáticamente" in sent[0]["body"]
    assert sent[1]["subject"] == "[Asistencia] Se anuló tu salida"
    assert second.body in sent[1]["body"]

    rows = session.exec(select(StaffNotificationDelivery)).all()
    assert [(row.status, row.attempts) for row in rows] == [("sent", 1), ("sent", 1)]
    assert all(row.sent_at is not None for row in rows)
    assert all(row.last_attempt_at is not None for row in rows)
    assert all(row.error is None for row in rows)

    # A second pass finds nothing left and never resends the same notice.
    again = send_pending_staff_notification_emails(session, now=NOW + timedelta(minutes=6))
    assert (again.attempted, again.remaining) == (0, 0)
    assert len(sent) == 2


def test_preview_simulation_is_kept_as_its_own_status(session: Session, monkeypatch) -> None:
    _, account, _ = seed_accounts(session)
    queue_notice(session, account.id)
    monkeypatch.setattr(
        delivery_module,
        "send_email",
        lambda **_kwargs: "simulated",
    )

    result = send_pending_staff_notification_emails(session, now=NOW)

    assert (result.attempted, result.sent, result.simulated) == (1, 0, 1)
    row = session.exec(select(StaffNotificationDelivery)).one()
    assert row.status == "simulated"
    assert row.attempts == 1
    assert row.sent_at is not None


def test_transport_failure_marks_the_row_and_the_pass_keeps_going(
    session: Session, monkeypatch
) -> None:
    _, account, _ = seed_accounts(session)
    first = queue_notice(session, account.id, title="Primero", now=NOW)
    second = queue_notice(session, account.id, title="Segundo", now=NOW + timedelta(minutes=1))
    calls: list[str] = []

    def flaky_send_email(*, recipient: str, subject: str, body: str, **_kwargs) -> str:
        calls.append(subject)
        if len(calls) == 1:
            raise MailDeliveryFailed("No se pudo enviar el aviso de asistencia: timeout")
        return "sent"

    monkeypatch.setattr(delivery_module, "send_email", flaky_send_email)

    result = send_pending_staff_notification_emails(session, now=NOW + timedelta(minutes=5))

    assert (result.attempted, result.sent, result.failed) == (2, 1, 1)
    assert result.remaining == 0
    rows = {
        row.notice_id: row for row in session.exec(select(StaffNotificationDelivery)).all()
    }
    assert rows[first.id].status == "failed"
    assert "timeout" in (rows[first.id].error or "")
    assert rows[first.id].sent_at is None
    assert rows[second.id].status == "sent"

    # A failed row waits for an explicit retry: the pass never retries it alone.
    monkeypatch.setattr(
        delivery_module,
        "send_email",
        lambda **_kwargs: pytest.fail("a failed delivery must not be retried by a pass"),
    )
    again = send_pending_staff_notification_emails(session, now=NOW + timedelta(minutes=6))
    assert again.attempted == 0


def test_retry_only_accepts_a_failed_delivery(session: Session, monkeypatch) -> None:
    _, account, _ = seed_accounts(session)
    queue_notice(session, account.id)

    def broken(**_kwargs) -> str:
        raise MailNotConfigured("El correo de asistencia no está configurado (SMTP_HOST).")

    monkeypatch.setattr(delivery_module, "send_email", broken)
    send_pending_staff_notification_emails(session, now=NOW)
    row = session.exec(select(StaffNotificationDelivery)).one()
    assert row.status == "failed"
    assert "SMTP_HOST" in (row.error or "")

    sent = outgoing(monkeypatch)
    retried = retry_staff_notification_delivery(session, row.id, now=NOW + timedelta(minutes=2))

    assert retried.status == "sent"
    assert retried.attempts == 2
    assert retried.error is None
    assert retried.sent_at is not None
    assert len(sent) == 1

    # Sent and simulated rows are final; an unknown id is a 404 in the API.
    with pytest.raises(NotificationDeliveryRetryNotAllowed):
        retry_staff_notification_delivery(session, row.id, now=NOW + timedelta(minutes=3))
    with pytest.raises(NotificationDeliveryNotFound):
        retry_staff_notification_delivery(session, uuid4(), now=NOW)


def test_switch_off_holds_the_queue_and_retry_refuses(session: Session, monkeypatch) -> None:
    _, account, manager = seed_accounts(session)
    queue_notice(session, account.id)

    def broken(**_kwargs) -> str:
        raise MailDeliveryFailed("No se pudo enviar el aviso de asistencia: 550")

    monkeypatch.setattr(delivery_module, "send_email", broken)
    send_pending_staff_notification_emails(session, now=NOW)
    failed = session.exec(select(StaffNotificationDelivery)).one()
    assert failed.status == "failed"

    update_staffing_settings(
        session,
        check_in_early_grace_minutes=15,
        lateness_tolerance_minutes=0,
        attendance_request_sla_hours=24,
        attendance_email_enabled=False,
        actor_id=manager.id,
    )
    sent = outgoing(monkeypatch)

    result = send_pending_staff_notification_emails(session, now=NOW + timedelta(minutes=2))
    assert result.enabled is False
    assert (result.attempted, result.sent) == (0, 0)
    assert sent == []
    with pytest.raises(AttendanceEmailDisabled):
        retry_staff_notification_delivery(session, failed.id, now=NOW + timedelta(minutes=2))

    # Turning the channel back on drains the retry that was waiting.
    update_staffing_settings(
        session,
        check_in_early_grace_minutes=15,
        lateness_tolerance_minutes=0,
        attendance_request_sla_hours=24,
        attendance_email_enabled=True,
        actor_id=manager.id,
    )
    retried = retry_staff_notification_delivery(session, failed.id, now=NOW + timedelta(minutes=4))
    assert retried.status == "sent"
    assert len(sent) == 1


def test_batch_limit_takes_the_oldest_first(session: Session, monkeypatch) -> None:
    _, account, _ = seed_accounts(session)
    for index in range(3):
        queue_notice(
            session,
            account.id,
            title=f"Aviso {index}",
            now=NOW + timedelta(minutes=index),
        )
    sent = outgoing(monkeypatch)

    result = send_pending_staff_notification_emails(
        session, limit=2, now=NOW + timedelta(minutes=10)
    )

    assert (result.attempted, result.remaining) == (2, 1)
    assert [item["subject"] for item in sent] == ["[Asistencia] Aviso 0", "[Asistencia] Aviso 1"]


def test_counts_and_listing_expose_the_queue(session: Session, monkeypatch) -> None:
    _, account, _ = seed_accounts(session)
    for index in range(3):
        queue_notice(
            session,
            account.id,
            title=f"Aviso {index}",
            now=NOW + timedelta(minutes=index),
        )
    calls = {"count": 0}

    def mixed(**_kwargs) -> str:
        calls["count"] += 1
        if calls["count"] == 2:
            raise MailDeliveryFailed("No se pudo enviar el aviso de asistencia: 421")
        return "sent"

    monkeypatch.setattr(delivery_module, "send_email", mixed)
    send_pending_staff_notification_emails(session, limit=2, now=NOW + timedelta(minutes=5))

    counts = staff_notification_delivery_counts(session)
    assert (counts.pending, counts.sent, counts.failed, counts.simulated) == (1, 1, 1, 0)

    everything = list_staff_notification_deliveries(session)
    assert everything.total == 3
    assert [item.title for item in everything.items] == ["Aviso 2", "Aviso 1", "Aviso 0"]
    assert everything.items[0].status == "pending"
    assert everything.items[1].status == "failed"
    assert "421" in (everything.items[1].error or "")
    assert everything.items[2].status == "sent"

    failed_only = list_staff_notification_deliveries(session, status_filter="failed")
    assert failed_only.total == 1
    assert failed_only.items[0].title == "Aviso 1"

    paged = list_staff_notification_deliveries(session, page=2, page_size=2)
    assert (paged.total, paged.pages, len(paged.items)) == (3, 2, 1)
    assert paged.items[0].title == "Aviso 0"


def test_recipient_is_the_address_frozen_when_the_notice_was_written(
    session: Session, monkeypatch
) -> None:
    _, account, _ = seed_accounts(session)
    queue_notice(session, account.id)
    account.email = "nueva.direccion@example.test"
    session.add(account)
    session.commit()
    sent = outgoing(monkeypatch)

    send_pending_staff_notification_emails(session, now=NOW)

    assert [item["recipient"] for item in sent] == ["lucia.account@example.test"]


def test_message_carries_the_notice_text(session: Session) -> None:
    _, account, _ = seed_accounts(session)
    notice = queue_notice(session, account.id)

    subject, body = email_message_for_notice(notice)

    assert subject == "[Asistencia] Se corrigió tu marca"
    assert notice.body in body


def test_claim_is_a_compare_and_set_on_the_attempt_count(session: Session) -> None:
    _, account, _ = seed_accounts(session)
    queue_notice(session, account.id, now=NOW)
    delivery = session.exec(select(StaffNotificationDelivery)).one()
    session.commit()

    # Both passes read the row with attempts == 0 before either writes; the
    # second compare-and-set matches nothing, so only one takes the delivery.
    other = Session(session.get_bind())
    try:
        stale = other.get(StaffNotificationDelivery, delivery.id)
        assert stale is not None and stale.attempts == 0

        assert (
            delivery_module._claim(session, delivery, from_status="pending", now=NOW)
            is True
        )
        assert delivery.attempts == 1

        assert (
            delivery_module._claim(
                other, stale, from_status="pending", now=NOW + timedelta(seconds=1)
            )
            is False
        )
        assert stale.attempts == 1
        assert stale.last_attempt_at is not None
    finally:
        other.close()


def test_every_staff_kind_queues_one_email(session: Session) -> None:
    _, account, _ = seed_accounts(session)

    for index, kind in enumerate(STAFF_NOTIFICATION_KINDS):
        create_staff_notification(
            session,
            user_id=account.id,
            kind=kind,
            title=f"Aviso {index}",
            body=f"Cuerpo del aviso {index}.",
            now=NOW + timedelta(minutes=index),
        )

    queued = session.exec(select(StaffNotificationDelivery)).all()
    assert len(queued) == len(STAFF_NOTIFICATION_KINDS)
    assert {delivery.recipient for delivery in queued} == {"lucia.account@example.test"}
    assert all(delivery.status == "pending" for delivery in queued)


def test_subject_and_destination_follow_the_notice_kind(session: Session) -> None:
    _, account, _ = seed_accounts(session)
    cases = {
        "attendance_corrected": ("[Asistencia] ", "pestaña Personal"),
        "workout_pending_review": ("[Rutinas] ", "pestaña Rutinas"),
        "maintenance_ticket_assigned": ("[Mantenimiento] ", "pestaña Mantenimiento"),
        "kiosk_token_expiring": ("[Kiosco] ", "página Kiosco"),
        "member_push_failed": ("[Avisos] ", "«Push del socio»"),
    }

    for kind, (prefix, location) in cases.items():
        notice = create_staff_notification(
            session,
            user_id=account.id,
            kind=kind,
            title="Aviso",
            body="Cuerpo del aviso.",
            now=NOW,
        )
        subject, body = email_message_for_notice(notice)
        assert subject == f"{prefix}Aviso"
        assert location in body
