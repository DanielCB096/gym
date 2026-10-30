"""Class notices: reminders, held seats, freed seats and changes to the class.

The reminder has no scheduler: it is materialised when the member reads the
inbox or the badge, once per window. The waitlist likewise only advances by
itself when the freed seat is still useful, so a queue is never seated into a
class that already began. A cancellation or a moved slot reaches every live
reservation, held or queued, because both would otherwise show up at the wrong
time.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules import physio  # noqa: F401  (registers the table ``sales`` points at)
from app.modules.classes import (
    ClassReservation,
    InvalidSessionState,
    cancel_class_session,
    cancel_reservation,
    create_class_room,
    create_class_session,
    create_class_type,
    mark_attendance,
    reserve_seat,
    update_class_session,
)
from app.modules.memberships.models import Member
from app.modules.notifications import (
    MemberNotificationItem,
    list_member_notifications,
    unread_notification_count,
)
from app.timezone import to_club_timezone

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def _build_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _member(session: Session, first_name: str) -> UUID:
    member = Member(
        first_name=first_name,
        last_name="Demo",
        email=f"{first_name.lower()}@example.com",
        status="active",
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member.id


def _catalog(session: Session) -> tuple[UUID, UUID]:
    class_type = create_class_type(session, name="Spinning")
    room = create_class_room(session, name="Salón A", capacity=10)
    return class_type.id, room.id


def _class_session(
    session: Session,
    class_type_id: UUID,
    room_id: UUID,
    *,
    starts_in: timedelta,
    capacity: int = 1,
) -> UUID:
    starts_at = NOW + starts_in
    item = create_class_session(
        session,
        title="Spinning 6am",
        class_type_id=class_type_id,
        room_id=room_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        capacity=capacity,
        now=NOW,
    )
    return item.id


def _reserve(
    session: Session,
    session_id: UUID,
    member_id: UUID,
    *,
    origin: str = "app",
    now: datetime = NOW,
) -> UUID:
    return reserve_seat(
        session, session_id, member_id=member_id, origin=origin, now=now
    ).id


def _reservation(session: Session, reservation_id: UUID) -> ClassReservation:
    row = session.get(ClassReservation, reservation_id)
    assert row is not None
    return row


def _kinds(session: Session, member_id: UUID) -> list[str]:
    # Pinned to NOW: the reminder window depends on the wall clock, and this
    # file asserts exact inbox contents.
    page = list_member_notifications(session, member_id, now=NOW)
    return [item.kind for item in page.items]


def _notices(session: Session, member_id: UUID) -> list[MemberNotificationItem]:
    return list_member_notifications(session, member_id, now=NOW).items


def test_reminder_is_written_once_per_window_and_never_for_past_or_cancelled() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ana = _member(session, "Ana")
        type_id, room_id = _catalog(session)
        soon = _class_session(session, type_id, room_id, starts_in=timedelta(hours=20))
        imminent = _class_session(session, type_id, room_id, starts_in=timedelta(hours=1))
        far = _class_session(session, type_id, room_id, starts_in=timedelta(days=3))
        started = _class_session(session, type_id, room_id, starts_in=timedelta(hours=-1))
        other = _class_session(session, type_id, room_id, starts_in=timedelta(hours=10))

        seat_soon = _reserve(session, soon, ana)
        seat_imminent = _reserve(session, imminent, ana)
        _reserve(session, far, ana)
        _reserve(session, started, ana)
        cancelled_seat = _reserve(session, other, ana)
        cancel_reservation(session, cancelled_seat, now=NOW)

        # The badge counts the reminders before the inbox was ever opened.
        assert unread_notification_count(session, ana, now=NOW) == 7

        first = list_member_notifications(session, ana, now=NOW)
        reminders = [item for item in first.items if item.kind == "class_reminder"]
        assert len(reminders) == 2
        by_ref = {item.ref_id: item for item in reminders}
        assert set(by_ref) == {seat_soon, seat_imminent}
        assert "Spinning 6am" in by_ref[seat_soon].body
        assert "menos de 24 horas" in by_ref[seat_soon].body
        assert "menos de 2 horas" in by_ref[seat_imminent].body
        assert all(item.read_at is None for item in first.items)

        # Reopening inside the same window changes nothing.
        assert list_member_notifications(session, ana, now=NOW).total == 7

        # Closer to the class, the same seat warns again in the tighter window.
        later = NOW + timedelta(hours=19)
        page = list_member_notifications(session, ana, now=later)
        assert page.total == 8
        assert sum("menos de 2 horas" in item.body for item in page.items) == 2
        assert list_member_notifications(session, ana, now=later).total == 8

        # A cancelled reservation is not reminded later either, though its
        # confirmation stays in the inbox as history.
        reminder_refs = {item.ref_id for item in page.items if item.kind == "class_reminder"}
        assert cancelled_seat not in reminder_refs


def test_free_seats_seat_the_queue_only_while_the_class_can_be_attended() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ana = _member(session, "Ana")
        beto = _member(session, "Beto")
        caro = _member(session, "Caro")
        type_id, room_id = _catalog(session)

        # Raising the capacity is a seat that appears without a cancellation.
        class_id = _class_session(
            session, type_id, room_id, starts_in=timedelta(days=2), capacity=1
        )
        _reserve(session, class_id, ana)
        beto_seat = _reserve(session, class_id, beto)
        caro_seat = _reserve(session, class_id, caro)

        updated = update_class_session(session, class_id, capacity=2, now=NOW)
        assert updated.reserved_count == 2
        assert updated.waitlist_count == 1
        assert _reservation(session, beto_seat).status == "reserved"
        assert _reservation(session, caro_seat).status == "waitlist"
        assert _reservation(session, caro_seat).waitlist_position == 1
        assert _kinds(session, beto) == ["class_waitlist_promoted"]

        # A capacity that covers the rest of the queue seats all of it and stops.
        updated = update_class_session(session, class_id, capacity=5, now=NOW)
        assert updated.reserved_count == 3
        assert updated.waitlist_count == 0
        assert _reservation(session, caro_seat).status == "reserved"
        assert _kinds(session, caro) == ["class_waitlist_promoted"]

        # A no-show before the class frees a seat worth filling too.
        early_id = _class_session(
            session, type_id, room_id, starts_in=timedelta(days=3), capacity=1
        )
        early_seat = _reserve(session, early_id, ana)
        waiting_seat = _reserve(session, early_id, beto)
        mark_attendance(session, early_seat, attended=False, now=NOW)
        assert _reservation(session, waiting_seat).status == "reserved"
        assert _kinds(session, beto) == [
            "class_waitlist_promoted",
            "class_waitlist_promoted",
        ]

        # Once the class began, the freed seat is not offered to anybody.
        past_id = _class_session(
            session, type_id, room_id, starts_in=timedelta(hours=-1), capacity=1
        )
        past_seat = _reserve(session, past_id, ana)
        late_seat = _reserve(session, past_id, beto)
        cancel_reservation(session, past_seat, now=NOW)
        assert _reservation(session, late_seat).status == "waitlist"
        assert _reservation(session, late_seat).waitlist_position == 1
        assert _kinds(session, beto) == [
            "class_waitlist_promoted",
            "class_waitlist_promoted",
        ]


def test_reservation_confirms_the_seat_only_when_it_is_held() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ana = _member(session, "Ana")
        beto = _member(session, "Beto")
        type_id, room_id = _catalog(session)
        class_id = _class_session(
            session, type_id, room_id, starts_in=timedelta(days=2), capacity=1
        )

        ana_seat = _reserve(session, class_id, ana)
        ana_notices = _notices(session, ana)
        assert [item.kind for item in ana_notices] == ["class_reserved"]
        assert ana_notices[0].ref_id == ana_seat
        assert ana_notices[0].title == "Tu lugar en la clase está confirmado"
        assert "Ya tienes tu lugar reservado" in ana_notices[0].body
        assert "Spinning 6am" in ana_notices[0].body

        # Joining the queue is not holding a seat: the position is visible in
        # the app and the promotion will be announced when the seat opens.
        beto_seat = _reserve(session, class_id, beto, origin="reception")
        assert _reservation(session, beto_seat).status == "waitlist"
        assert _notices(session, beto) == []

        # Promotion is announced once and is not a confirmation of a new seat.
        cancel_reservation(session, ana_seat, now=NOW)
        assert _reservation(session, beto_seat).status == "reserved"
        assert [item.kind for item in _notices(session, beto)] == ["class_waitlist_promoted"]

        # A cancelled seat can be booked again: it is another reservation, so
        # it earns its own notice, and the desk says it was the desk.
        cancel_reservation(session, beto_seat, now=NOW)
        ana_again = _reserve(
            session, class_id, ana, origin="reception", now=NOW + timedelta(hours=1)
        )
        assert _reservation(session, ana_again).status == "reserved"
        ana_notices = _notices(session, ana)
        assert len(ana_notices) == 2
        assert ana_notices[0].ref_id == ana_again
        assert "Recepción reservó tu lugar" in ana_notices[0].body
        assert ana_notices[1].ref_id == ana_seat


def test_cancellation_reaches_every_live_reservation_and_announces_once() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ana = _member(session, "Ana")
        beto = _member(session, "Beto")
        caro = _member(session, "Caro")
        type_id, room_id = _catalog(session)
        class_id = _class_session(
            session, type_id, room_id, starts_in=timedelta(days=2), capacity=1
        )

        ana_seat = _reserve(session, class_id, ana)
        beto_seat = _reserve(session, class_id, beto)
        caro_seat = _reserve(session, class_id, caro)
        cancel_reservation(session, caro_seat, now=NOW)

        cancel_class_session(session, class_id, now=NOW)

        starts_local = to_club_timezone(NOW + timedelta(days=2))
        # Both the held seat and the queue are told: neither has to show up.
        for member, seat in ((ana, ana_seat), (beto, beto_seat)):
            assert _reservation(session, seat).status == "cancelled"
            notices = [item for item in _notices(session, member) if item.kind == "class_cancelled"]
            assert len(notices) == 1
            notice = notices[0]
            assert notice.ref_id == class_id
            assert notice.title == "Se canceló tu clase"
            assert "Spinning 6am" in notice.body
            assert f"{starts_local:%d/%m/%Y}" in notice.body
            assert f"{starts_local:%H:%M}" in notice.body
            assert "cancelada" in notice.body
            assert notice.read_at is None

        # A seat cancelled before the class was never at risk.
        assert _notices(session, caro) == []
        assert len(_notices(session, ana)) == 2
        assert len(_notices(session, beto)) == 1
        assert unread_notification_count(session, beto, now=NOW) == 1

        # Cancelling twice changes nothing and adds no second notice.
        with pytest.raises(InvalidSessionState):
            cancel_class_session(session, class_id, now=NOW)
        assert len(_notices(session, ana)) == 2
        assert len(_notices(session, beto)) == 1


def test_reschedule_announces_both_slots_and_ignores_other_edits() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ana = _member(session, "Ana")
        beto = _member(session, "Beto")
        caro = _member(session, "Caro")
        type_id, room_id = _catalog(session)
        class_id = _class_session(
            session, type_id, room_id, starts_in=timedelta(days=2), capacity=1
        )

        _reserve(session, class_id, ana)
        _reserve(session, class_id, beto)
        caro_seat = _reserve(session, class_id, caro)
        cancel_reservation(session, caro_seat, now=NOW)

        old_start = NOW + timedelta(days=2)
        new_start = NOW + timedelta(days=3)
        new_end = new_start + timedelta(hours=2)
        update_class_session(
            session, class_id, starts_at=new_start, ends_at=new_end, now=NOW
        )

        old_local = to_club_timezone(old_start)
        new_start_local = to_club_timezone(new_start)
        new_end_local = to_club_timezone(new_end)
        for member in (ana, beto):
            notices = [
                item for item in _notices(session, member) if item.kind == "class_rescheduled"
            ]
            assert len(notices) == 1
            notice = notices[0]
            assert notice.ref_id == class_id
            assert notice.title == "Cambió el horario de tu clase"
            assert f"{old_local:%d/%m/%Y}" in notice.body
            assert f"{old_local:%H:%M}" in notice.body
            assert f"{new_start_local:%d/%m/%Y}" in notice.body
            assert f"{new_start_local:%H:%M}" in notice.body
            assert f"{new_end_local:%H:%M}" in notice.body
            assert "Tu reserva sigue en pie" in notice.body
        assert all(item.kind != "class_rescheduled" for item in _notices(session, caro))

        # Capacity or title alone move nothing, so they stay silent.
        update_class_session(session, class_id, capacity=2, title="Spinning 7am", now=NOW)
        assert sum(
            item.kind == "class_rescheduled" for item in _notices(session, ana)
        ) == 1

        # A later move is its own news, even when only the end moves.
        moved_end = new_end + timedelta(minutes=30)
        update_class_session(
            session, class_id, ends_at=moved_end, now=NOW + timedelta(hours=1)
        )
        notices = [
            item for item in _notices(session, ana) if item.kind == "class_rescheduled"
        ]
        assert len(notices) == 2
        assert f"{to_club_timezone(moved_end):%H:%M}" in notices[0].body
        assert f"{new_end_local:%H:%M}" in notices[0].body
