"""The club's silence window for member pushes.

The inbox keeps every notice the club wrote, but ringing a phone at 23:30 is a
different story: the window holds the automatic pass back without dropping
anything — the notice stays queued and the next pass after the window sends it,
together with any retries whose ``next_attempt_at`` fell due in the meantime.
A deliberate operator action from the panel is not the window's to defer, and
preview mode ignores it because a simulation never rings a phone.
"""

from datetime import datetime, timedelta, time, timezone

import pytest
from sqlmodel import Session, select

from app.modules.memberships.models import Member
from app.modules.notifications import push as push_module
from app.modules.notifications.models import MemberPushDelivery
from app.modules.notifications.push import (
    PushDeliveryFailed,
    parse_push_quiet_window,
    register_member_push_token,
    retry_member_push_delivery,
    send_pending_member_push_deliveries,
)
from app.modules.notifications.service import create_notification

# Mexico City is UTC-6 all year, so the local hour is the UTC hour minus six.
NOW = datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)  # 11:00 local
INSIDE = datetime(2026, 10, 31, 5, 30, tzinfo=timezone.utc)  # 23:30 local
AFTER = datetime(2026, 10, 31, 13, 30, tzinfo=timezone.utc)  # 07:30 local
TOKEN_A = "ExponentPushToken[aaaAAA111]"


def _quiet_window(
    monkeypatch, *, start: str | None = "22:00", end: str | None = "07:00"
) -> None:
    if start is None:
        monkeypatch.delenv("MEMBER_PUSH_QUIET_START", raising=False)
    else:
        monkeypatch.setenv("MEMBER_PUSH_QUIET_START", start)
    if end is None:
        monkeypatch.delenv("MEMBER_PUSH_QUIET_END", raising=False)
    else:
        monkeypatch.setenv("MEMBER_PUSH_QUIET_END", end)


def _queue_one_push(session: Session) -> MemberPushDelivery:
    member = Member(
        first_name="Ana", last_name="Demo", email="ana@example.test", status="active"
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    register_member_push_token(
        session, member.id, token=TOKEN_A, platform="ios", now=NOW
    )
    create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()
    return session.exec(select(MemberPushDelivery)).one()


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (None, None, None),
        ("22:00", "07:00", (time(22, 0), time(7, 0))),
        ("07:00", "22:00", (time(7, 0), time(22, 0))),
        ("22:00", "22:00", None),
    ],
)
def test_the_window_comes_as_a_pair_or_not_at_all(
    monkeypatch, start: str | None, end: str | None, expected
) -> None:
    _quiet_window(monkeypatch, start=start, end=end)
    assert parse_push_quiet_window() == expected


def test_a_half_configured_window_is_an_error(monkeypatch) -> None:
    _quiet_window(monkeypatch, start="22:00", end=None)
    with pytest.raises(ValueError) as error:
        parse_push_quiet_window()
    assert "MEMBER_PUSH_QUIET_START" in str(error.value)
    assert "MEMBER_PUSH_QUIET_END" in str(error.value)

    _quiet_window(monkeypatch, start=None, end="07:00")
    with pytest.raises(ValueError):
        parse_push_quiet_window()


def test_a_malformed_hour_names_its_variable(monkeypatch) -> None:
    _quiet_window(monkeypatch, start="7pm", end="07:00")
    with pytest.raises(ValueError) as error:
        parse_push_quiet_window()
    assert "MEMBER_PUSH_QUIET_START" in str(error.value)

    _quiet_window(monkeypatch, start="22:00", end="24:00")
    with pytest.raises(ValueError) as error:
        parse_push_quiet_window()
    assert "MEMBER_PUSH_QUIET_END" in str(error.value)


def test_the_pass_defers_inside_the_window(session: Session, monkeypatch) -> None:
    _quiet_window(monkeypatch)
    delivery = _queue_one_push(session)
    calls: list[dict[str, object]] = []

    def spy(**kwargs) -> str:
        calls.append(kwargs)
        return "sent"

    monkeypatch.setattr(push_module, "send_expo_push", spy)
    result = send_pending_member_push_deliveries(session, now=INSIDE)

    assert calls == []
    assert result.deferred is True
    assert (result.attempted, result.sent, result.failed) == (0, 0, 0)
    assert result.remaining == 1
    session.refresh(delivery)
    assert delivery.status == "pending"
    assert delivery.attempts == 0


def test_the_pass_sends_after_the_window_ends(session: Session, monkeypatch) -> None:
    _quiet_window(monkeypatch)
    delivery = _queue_one_push(session)
    monkeypatch.setattr(push_module, "send_expo_push", lambda **_kwargs: "sent")

    deferred = send_pending_member_push_deliveries(session, now=INSIDE)
    assert deferred.deferred is True

    result = send_pending_member_push_deliveries(session, now=AFTER)
    assert result.deferred is False
    assert (result.attempted, result.sent) == (1, 1)
    assert result.remaining == 0
    session.refresh(delivery)
    assert delivery.status == "sent"
    assert delivery.sent_at.replace(tzinfo=timezone.utc) == AFTER


def test_a_retry_that_fell_due_waits_for_the_window_to_end(
    session: Session, monkeypatch
) -> None:
    _quiet_window(monkeypatch)
    delivery = _queue_one_push(session)

    def unreachable(**_kwargs) -> str:
        raise PushDeliveryFailed("El servicio de notificaciones respondió 503.")

    monkeypatch.setattr(push_module, "send_expo_push", unreachable)
    first = send_pending_member_push_deliveries(session, now=NOW)
    assert (first.attempted, first.failed) == (1, 1)
    session.refresh(delivery)
    assert delivery.next_attempt_at is not None

    inside = send_pending_member_push_deliveries(session, now=INSIDE)
    assert inside.deferred is True
    assert inside.remaining == 1
    session.refresh(delivery)
    assert delivery.attempts == 1

    monkeypatch.setattr(push_module, "send_expo_push", lambda **_kwargs: "sent")
    late = send_pending_member_push_deliveries(session, now=AFTER)
    assert (late.retried, late.sent) == (1, 1)
    session.refresh(delivery)
    assert delivery.status == "sent"
    assert delivery.next_attempt_at is None


def test_the_manual_send_bypasses_the_window(session: Session, monkeypatch) -> None:
    _quiet_window(monkeypatch)
    delivery = _queue_one_push(session)
    monkeypatch.setattr(push_module, "send_expo_push", lambda **_kwargs: "sent")

    result = send_pending_member_push_deliveries(
        session, override_quiet_hours=True, now=INSIDE
    )

    assert result.deferred is False
    assert (result.attempted, result.sent) == (1, 1)
    session.refresh(delivery)
    assert delivery.status == "sent"


def test_the_manual_retry_bypasses_the_window(session: Session, monkeypatch) -> None:
    _quiet_window(monkeypatch)
    delivery = _queue_one_push(session)

    def unreachable(**_kwargs) -> str:
        raise PushDeliveryFailed("El servicio de notificaciones respondió 503.")

    monkeypatch.setattr(push_module, "send_expo_push", unreachable)
    send_pending_member_push_deliveries(session, now=NOW)
    session.refresh(delivery)
    assert delivery.status == "failed"

    monkeypatch.setattr(push_module, "send_expo_push", lambda **_kwargs: "sent")
    retry_member_push_delivery(session, delivery.id, now=INSIDE)
    session.refresh(delivery)
    assert delivery.status == "sent"
    assert delivery.sent_at.replace(tzinfo=timezone.utc) == INSIDE


def test_preview_mode_ignores_the_window(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    _quiet_window(monkeypatch)
    delivery = _queue_one_push(session)

    result = send_pending_member_push_deliveries(session, now=INSIDE)

    assert result.deferred is False
    assert (result.simulated, result.remaining) == (1, 0)
    session.refresh(delivery)
    assert delivery.status == "simulated"


def test_without_a_window_the_pass_sends_as_before(
    session: Session, monkeypatch
) -> None:
    _quiet_window(monkeypatch, start=None, end=None)
    delivery = _queue_one_push(session)
    monkeypatch.setattr(push_module, "send_expo_push", lambda **_kwargs: "sent")

    result = send_pending_member_push_deliveries(session, now=INSIDE)

    assert result.deferred is False
    assert (result.sent, result.remaining) == (1, 0)
    session.refresh(delivery)
    assert delivery.status == "sent"


def test_silence_covers_the_hours_after_midnight(
    session: Session, monkeypatch
) -> None:
    """A window that starts at 22:00 covers 00:30 of the following night."""

    _quiet_window(monkeypatch, start="22:00", end="07:00")
    delivery = _queue_one_push(session)
    midnight = NOW + timedelta(hours=13, minutes=30)  # 00:30 local, Oct 31
    monkeypatch.setattr(push_module, "send_expo_push", lambda **_kwargs: "sent")

    deferred = send_pending_member_push_deliveries(session, now=midnight)
    assert deferred.deferred is True

    result = send_pending_member_push_deliveries(session, now=AFTER)
    assert result.sent == 1
    session.refresh(delivery)
    assert delivery.status == "sent"
