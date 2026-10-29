"""Class reminders and the seats that free without a cancellation.

The reminder has no scheduler: it is materialised when the member reads the
inbox or the badge, once per window. The waitlist likewise only advances by
itself when the freed seat is still useful, so a queue is never seated into a
class that already began.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.modules.classes import (
    ClassReservation,
    cancel_reservation,
    create_class_room,
    create_class_session,
    create_class_type,
    mark_attendance,
    reserve_seat,
    update_class_session,
)
from app.modules.memberships.models import Member
from app.modules.notifications import list_member_notifications, unread_notification_count

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


def _reserve(session: Session, session_id: UUID, member_id: UUID) -> UUID:
    return reserve_seat(session, session_id, member_id=member_id, origin="app").id


def _reservation(session: Session, reservation_id: UUID) -> ClassReservation:
    row = session.get(ClassReservation, reservation_id)
    assert row is not None
    return row


def _kinds(session: Session, member_id: UUID) -> list[str]:
    page = list_member_notifications(session, member_id)
    return [item.kind for item in page.items]


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
        assert unread_notification_count(session, ana, now=NOW) == 2

        first = list_member_notifications(session, ana, now=NOW)
        assert [item.kind for item in first.items] == ["class_reminder", "class_reminder"]
        by_ref = {item.ref_id: item for item in first.items}
        assert set(by_ref) == {seat_soon, seat_imminent}
        assert "Spinning 6am" in by_ref[seat_soon].body
        assert "menos de 24 horas" in by_ref[seat_soon].body
        assert "menos de 2 horas" in by_ref[seat_imminent].body
        assert all(item.read_at is None for item in first.items)

        # Reopening inside the same window changes nothing.
        assert list_member_notifications(session, ana, now=NOW).total == 2

        # Closer to the class, the same seat warns again in the tighter window.
        later = NOW + timedelta(hours=19)
        page = list_member_notifications(session, ana, now=later)
        assert page.total == 3
        assert sum("menos de 2 horas" in item.body for item in page.items) == 2
        assert list_member_notifications(session, ana, now=later).total == 3

        # A cancelled reservation is not reminded later either.
        assert cancelled_seat not in {item.ref_id for item in page.items}


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
