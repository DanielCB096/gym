"""Consent-gated email delivery for the member notification inbox."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.mailer import MailNotConfigured
from app.modules.memberships.models import Member
from app.modules.notifications.member_email import (
    _message_for_notice,
    send_pending_member_notification_emails,
)
from app.modules.notifications.models import (
    MemberNotification,
    MemberNotificationEmailDelivery,
)
from app.modules.notifications.preferences import update_member_preferences
from app.modules.notifications.service import create_notification

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)


def _member(session: Session, email: str = "ana@example.test") -> Member:
    member = Member(first_name="Ana", last_name="Demo", email=email, status="active")
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def _enable_email(session: Session, member: Member, category: str = "classes") -> None:
    update_member_preferences(
        session,
        member.id,
        {},
        email_changes={category: True},
        now=NOW,
    )


def _notice(session: Session, member: Member) -> MemberNotification:
    notice = create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Tu lugar en la clase está confirmado",
        body="Tu lugar en Spinning quedó reservado.",
        now=NOW,
    )
    session.commit()
    return notice


def test_notice_queues_mail_only_after_explicit_opt_in(session: Session) -> None:
    member = _member(session)

    notice = _notice(session, member)
    assert session.exec(select(MemberNotificationEmailDelivery)).all() == []

    _enable_email(session, member)
    notice = _notice(session, member)

    deliveries = session.exec(select(MemberNotificationEmailDelivery)).all()
    assert len(deliveries) == 1
    assert deliveries[0].notification_id == notice.id
    assert deliveries[0].member_id == member.id
    assert deliveries[0].recipient == member.email
    assert deliveries[0].status == "pending"
    assert deliveries[0].message_id


def test_email_uses_the_configured_gym_name(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _member(session)
    notice = _notice(session, member)
    monkeypatch.setenv("GYM_NAME", "Club Demo")

    subject, body = _message_for_notice(notice)

    assert subject.startswith("Club Demo · ")
    assert "Club Demo · Este correo se envió automáticamente." in body


def test_turning_email_off_cancels_pending_delivery(session: Session) -> None:
    member = _member(session)
    _enable_email(session, member)
    _notice(session, member)
    delivery = session.exec(select(MemberNotificationEmailDelivery)).one()

    update_member_preferences(
        session,
        member.id,
        {},
        email_changes={"classes": False},
        now=NOW,
    )

    session.refresh(delivery)
    assert delivery.status == "cancelled"
    assert delivery.next_attempt_at is None
    assert "desactivó" in (delivery.error or "")


def test_changed_member_address_cancels_the_queued_message(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _member(session)
    _enable_email(session, member)
    _notice(session, member)
    delivery = session.exec(select(MemberNotificationEmailDelivery)).one()
    member.email = "otra@example.test"
    session.add(member)
    session.commit()

    def unexpected_send(**_: object) -> str:
        pytest.fail("No debe enviarse al correo anterior.")

    monkeypatch.setattr(
        "app.modules.notifications.member_email.send_email", unexpected_send
    )
    result = send_pending_member_notification_emails(session, now=NOW)

    session.refresh(delivery)
    assert result.cancelled == 1
    assert delivery.status == "cancelled"
    assert "cambió" in (delivery.error or "")


def test_failed_mail_retries_after_backoff_and_keeps_attempt_history(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _member(session)
    _enable_email(session, member)
    _notice(session, member)
    delivery = session.exec(select(MemberNotificationEmailDelivery)).one()
    calls = 0

    def fail_then_send(**kwargs: object) -> str:
        nonlocal calls
        calls += 1
        assert kwargs["message_id"] == delivery.message_id
        if calls == 1:
            raise MailNotConfigured("SMTP no configurado.")
        return "sent"

    monkeypatch.setattr(
        "app.modules.notifications.member_email.send_email", fail_then_send
    )
    failed = send_pending_member_notification_emails(session, now=NOW)
    session.refresh(delivery)
    assert failed.failed == 1
    assert failed.remaining == 1
    assert delivery.status == "failed"
    assert delivery.attempts == 1
    assert delivery.next_attempt_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=5)

    too_soon = send_pending_member_notification_emails(
        session, now=NOW + timedelta(minutes=4)
    )
    assert too_soon.attempted == 0

    retried = send_pending_member_notification_emails(
        session, now=NOW + timedelta(minutes=5)
    )
    session.refresh(delivery)
    assert retried.sent == 1
    assert retried.remaining == 0
    assert delivery.status == "sent"
    assert delivery.attempts == 2
    assert delivery.next_attempt_at is None
    assert delivery.error is None
    assert delivery.sent_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=5)


def test_preview_outcome_is_audited_as_simulated(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _member(session)
    _enable_email(session, member)
    _notice(session, member)
    delivery = session.exec(select(MemberNotificationEmailDelivery)).one()
    monkeypatch.setattr(
        "app.modules.notifications.member_email.send_email",
        lambda **_: "simulated",
    )

    result = send_pending_member_notification_emails(session, now=NOW)

    session.refresh(delivery)
    assert result.simulated == 1
    assert delivery.status == "simulated"
    assert delivery.sent_at is None
