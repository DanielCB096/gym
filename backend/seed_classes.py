"""Seed the preview database with a realistic class schedule.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_classes.py

The script is idempotent: it only creates the catalogue on demand and skips the
schedule/roster once at least one session exists. It goes through the module
service so every invariant (capacity, waitlist, attendance) is honoured.
"""

import sys

sys.path.insert(0, r".\src")

from datetime import datetime, timedelta, timezone  # noqa: E402

from sqlalchemy import delete  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import access, classes, identity, inventory, memberships, staffing  # noqa: E402,F401
from app.modules.classes import service as classes_service  # noqa: E402
from app.modules.classes.models import ClassReservation, ClassRoom, ClassSession, ClassType  # noqa: E402
from app.modules.identity.models import Employee  # noqa: E402
from app.modules.identity.service import ensure_default_access_control  # noqa: E402
from app.modules.memberships.models import Member  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"

CLASS_TYPES = [
    ("Spinning", "Ciclismo indoor con música y luces"),
    ("Yoga", "Movilidad, respiración y estiramiento"),
    ("Funcional", "Circuito de fuerza y cardio"),
    ("Zumba", "Baile fitness para todo nivel"),
    ("Boxeo", "Técnica de golpeo y acondicionamiento"),
]

CLASS_ROOMS = [("Salón A", 20), ("Salón B", 15), ("Salón C", 12)]

# (day_offset, hour, type_idx, room_idx, access_type, extra_cents, capacity_override)
SLOTS = [
    (-2, 18, 2, 0, "included", 0, None),
    (-1, 7, 0, 1, "included", 0, None),
    (1, 7, 2, 0, "included", 0, None),
    (1, 9, 0, 1, "included", 0, None),
    (1, 18, 3, 2, "included", 0, 5),
    (1, 20, 4, 0, "premium", 5000, None),
    (2, 7, 1, 1, "included", 0, None),
    (2, 18, 0, 0, "included", 0, None),
    (2, 20, 2, 2, "included", 0, None),
    (3, 9, 4, 1, "premium", 5000, None),
    (3, 18, 1, 1, "included", 0, None),
    (3, 20, 3, 2, "included", 0, None),
    (4, 7, 0, 0, "included", 0, None),
    (4, 18, 2, 0, "included", 0, None),
    (5, 9, 3, 2, "included", 0, None),
    (5, 18, 4, 0, "premium", 5000, None),
    (6, 7, 1, 1, "included", 0, None),
    (6, 18, 0, 0, "included", 0, None),
    (7, 9, 2, 2, "included", 0, None),
]


def _vary(index: int, span: int) -> int:
    return int(index % span)


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        # --- Catalogue -----------------------------------------------------
        types = {row.name.lower(): row for row in session.exec(select(ClassType)).all()}
        created_types = 0
        for name, description in CLASS_TYPES:
            if name.lower() not in types:
                item = classes_service.create_class_type(session, name=name, description=description)
                types[name.lower()] = item
                created_types += 1

        rooms = {row.name.lower(): row for row in session.exec(select(ClassRoom)).all()}
        created_rooms = 0
        for name, capacity in CLASS_ROOMS:
            if name.lower() not in rooms:
                item = classes_service.create_class_room(session, name=name, capacity=capacity)
                rooms[name.lower()] = item
                created_rooms += 1

        type_rows = [types[name.lower()] for name, _ in CLASS_TYPES]
        room_rows = [rooms[name.lower()] for name, _ in CLASS_ROOMS]

        instructors = session.exec(
            select(Employee).where(Employee.status == "active").order_by(Employee.first_name)
        ).all()
        members = session.exec(
            select(Member).where(Member.status == "active").order_by(Member.first_name)
        ).all()

        if not instructors:
            print("No active employees found: sessions will be created without an instructor.")
        if not members:
            print("No active members found: the roster will stay empty.")

        # --- Schedule ------------------------------------------------------
        # The schedule is always rebuilt so the demo stays anchored to "today".
        session.exec(delete(ClassReservation))
        session.exec(delete(ClassSession))
        session.commit()

        today = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        created_sessions = []
        for index, (offset, hour, type_idx, room_idx, access_type, extra, capacity_override) in enumerate(SLOTS):
            class_type = type_rows[type_idx]
            room = room_rows[room_idx]
            instructor = instructors[_vary(index, len(instructors))] if instructors else None
            starts_at = (today + timedelta(days=offset)).replace(hour=hour)
            item = classes_service.create_class_session(
                session,
                title=f"{class_type.name} {hour:02d}:00",
                class_type_id=class_type.id,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=1),
                capacity=capacity_override or room.capacity,
                room_id=room.id,
                instructor_id=instructor.id if instructor else None,
                access_type=access_type,
                extra_price_cents=extra,
                waitlist_enabled=True,
                cancel_window_hours=4,
                notes="Llevar toalla y botella de agua." if index % 3 == 0 else None,
            )
            created_sessions.append((offset, item))

        # --- Roster --------------------------------------------------------
        reservations = 0
        waitlisted = 0
        for index, (offset, item) in enumerate(created_sessions):
            if not members:
                continue
            if offset <= 0:
                # Past classes: mostly attended, one no-show and one late cancellation.
                # The seed rebuilds the agenda on every run, so it would pile up
                # confirmations of classes that no longer exist; it stays silent.
                for member in members:
                    classes_service.reserve_seat(
                        session,
                        item.id,
                        member_id=member.id,
                        origin="reception",
                        notify_member=False,
                    )
                    reservations += 1
                confirmed = [
                    reservation
                    for reservation in classes_service.list_session_reservations(session, item.id).reservations
                    if reservation.status == "reserved"
                ]
                if len(confirmed) >= 2:
                    classes_service.mark_attendance(session, confirmed[0].id, attended=False)
                if len(confirmed) >= 3:
                    classes_service.cancel_reservation(session, confirmed[1].id)
                for reservation in confirmed[2:]:
                    classes_service.mark_attendance(session, reservation.id, attended=True)
                continue

            # Upcoming classes: fill a slice of the room, overflow to the waitlist.
            take = min(len(members), max(item.capacity // 2, 3))
            if item.capacity <= 6:
                take = len(members)  # deliberately overflow the small class
            for member in members[:take]:
                result = classes_service.reserve_seat(
                    session,
                    item.id,
                    member_id=member.id,
                    origin="reception" if index % 2 == 0 else "app",
                    notify_member=False,
                )
                reservations += 1
                if result.status == "waitlist":
                    waitlisted += 1

        print(f"Class types created: {created_types} (total {len(type_rows)})")
        print(f"Rooms created: {created_rooms} (total {len(room_rows)})")
        print(f"Sessions created: {len(created_sessions)}")
        print(f"Reservations created: {reservations} (waitlisted {waitlisted})")
        print("Done!")


if __name__ == "__main__":
    main()
