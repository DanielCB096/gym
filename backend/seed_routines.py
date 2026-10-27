"""Seed the preview database with a realistic routines and progress demo.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_routines.py

The script is idempotent: the exercise library is created on demand (looked up
by name) and the routines, assignments, workouts and measurements are only
seeded once, when the routines table is still empty. Goals and progress photos
are seeded separately, so a preview database created before those features
existed still receives their demo data. It goes through the module service so
versioning, the pinned routine version and the workout/measurement/goal/photo
rules are all honoured.
"""

import struct
import sys
import zlib

sys.path.insert(0, r".\src")

from datetime import date, datetime, timedelta, timezone  # noqa: E402

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import access, classes, identity, inventory, maintenance, memberships, routines, staffing  # noqa: E402,F401
from app.modules.identity.models import Employee  # noqa: E402
from app.modules.identity.service import ensure_default_access_control  # noqa: E402
from app.modules.memberships.models import Member  # noqa: E402
from app.modules.routines import service as routines_service  # noqa: E402
from app.modules.routines.models import (  # noqa: E402
    BodyMeasurement,
    Exercise,
    MemberGoal,
    ProgressPhoto,
    Routine,
    RoutineAssignment,
)
from app.modules.routines.photo_storage import photos_root  # noqa: E402
from app.timezone import to_club_timezone  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"

# (name, muscle_group, category, equipment)
EXERCISES = [
    ("Sentadilla con barra", "Piernas", "Fuerza", "Rack"),
    ("Prensa de piernas", "Piernas", "Fuerza", "Prensa"),
    ("Peso muerto", "Espalda", "Fuerza", "Barra"),
    ("Press banca", "Pecho", "Fuerza", "Banco plano"),
    ("Remo con mancuerna", "Espalda", "Fuerza", "Mancuernas"),
    ("Jalón al pecho", "Espalda", "Fuerza", "Polea alta"),
    ("Press militar", "Hombros", "Fuerza", "Barra"),
    ("Curl de bíceps", "Brazos", "Fuerza", "Mancuernas"),
    ("Extensión de tríceps", "Brazos", "Fuerza", "Polea"),
    ("Plancha abdominal", "Core", "Movilidad", None),
    ("Caminadora intervalos", "Cardio", "Cardio", "Caminadora"),
    ("Bicicleta fija", "Cardio", "Cardio", "Bicicleta"),
]

# name, objective, [(exercise name, sets, reps, rest_seconds, load_note)]
ROUTINES = [
    (
        "Fuerza Full Body",
        "Fuerza general en tres sesiones por semana",
        [
            ("Sentadilla con barra", 4, "8", 120, "70 kg"),
            ("Press banca", 4, "8", 120, "50 kg"),
            ("Remo con mancuerna", 4, "10", 90, "22 kg"),
            ("Press militar", 3, "10", 90, "30 kg"),
            ("Plancha abdominal", 3, "45 s", 45, "Peso corporal"),
        ],
    ),
    (
        "Hipertrofia Tren Superior",
        "Volumen de tren superior",
        [
            ("Press banca", 4, "10", 90, "45 kg"),
            ("Jalón al pecho", 4, "10", 90, "45 kg"),
            ("Press militar", 4, "12", 75, "28 kg"),
            ("Curl de bíceps", 3, "12", 60, "12 kg"),
            ("Extensión de tríceps", 3, "12", 60, "25 kg"),
        ],
    ),
    (
        "Piernas y Core",
        "Fuerza de tren inferior y estabilidad",
        [
            ("Prensa de piernas", 4, "12", 90, "120 kg"),
            ("Peso muerto", 4, "6", 150, "80 kg"),
            ("Plancha abdominal", 3, "60 s", 45, "Peso corporal"),
        ],
    ),
    (
        "Cardio y Movilidad",
        "Acondicionamiento aeróbico ligero",
        [
            ("Caminadora intervalos", 1, "20 min", 0, "Zona 2"),
            ("Bicicleta fija", 1, "15 min", 0, "Zona 2"),
            ("Plancha abdominal", 3, "30 s", 30, "Peso corporal"),
        ],
    ),
]

# Publish a second version of the first routine so the change log has history.
FIRST_ROUTINE_VERSION_2 = [
    ("Sentadilla con barra", 5, "5", 150, "80 kg"),
    ("Press banca", 5, "5", 150, "55 kg"),
    ("Remo con mancuerna", 4, "8", 90, "24 kg"),
    ("Press militar", 4, "8", 90, "32 kg"),
    ("Plancha abdominal", 3, "60 s", 45, "Peso corporal"),
]


def _latest_measurement(session: Session, member_id, metric: str) -> BodyMeasurement | None:
    column = getattr(BodyMeasurement, metric)
    return session.exec(
        select(BodyMeasurement)
        .where(BodyMeasurement.member_id == member_id, column.is_not(None))
        .order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.created_at.desc())
    ).first()


def _seed_goals(session: Session) -> int:
    """Seed one active, one cancelled and one achieved goal for the demo."""
    if session.exec(select(MemberGoal)).first() is not None:
        return 0
    members = session.exec(
        select(Member)
        .where(Member.status == "active")
        .order_by(Member.first_name)
        .limit(3)
    ).all()
    today = date.today()
    created = 0

    if members:
        weight = _latest_measurement(session, members[0].id, "weight_kg")
        if weight is not None and weight.weight_kg is not None:
            current = float(weight.weight_kg)
            routines_service.create_member_goal(
                session,
                members[0].id,
                metric="weight_kg",
                direction="decrease",
                target_value=max(1.0, round(current - 2, 1)),
                target_date=today + timedelta(days=60),
                notes="Meta de composición corporal.",
            )
            created += 1

    if len(members) > 1:
        member = members[1]
        waist = _latest_measurement(session, member.id, "waist_cm")
        if waist is not None and waist.waist_cm is not None:
            current = float(waist.waist_cm)
            routines_service.create_member_goal(
                session,
                member.id,
                metric="waist_cm",
                direction="decrease",
                target_value=max(1.0, round(current - 2.5, 1)),
                target_date=today + timedelta(days=45),
                notes="Reducir cintura para el verano.",
            )
            created += 1
        chest = _latest_measurement(session, member.id, "chest_cm")
        if chest is not None and chest.chest_cm is not None:
            cancelled = routines_service.create_member_goal(
                session,
                member.id,
                metric="chest_cm",
                direction="increase",
                target_value=round(float(chest.chest_cm) + 2, 1),
                target_date=today + timedelta(days=90),
                notes="Ganar volumen en tren superior.",
            )
            routines_service.cancel_member_goal(session, cancelled.id)
            created += 1

    if len(members) > 2:
        member = members[2]
        fat = _latest_measurement(session, member.id, "body_fat_percent")
        if fat is not None and fat.body_fat_percent is not None:
            current = float(fat.body_fat_percent)
            goal = routines_service.create_member_goal(
                session,
                member.id,
                metric="body_fat_percent",
                direction="decrease",
                target_value=max(0.1, round(current - 1, 1)),
                target_date=today + timedelta(days=90),
                notes="Cierre de etapa de definición.",
            )
            created += 1
            if goal.status == "active":
                latest = session.exec(
                    select(BodyMeasurement)
                    .where(BodyMeasurement.member_id == member.id)
                    .order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.created_at.desc())
                ).first()
                routines_service.record_measurement(
                    session,
                    member.id,
                    weight_kg=float(latest.weight_kg) if latest and latest.weight_kg is not None else None,
                    waist_cm=float(latest.waist_cm) if latest and latest.waist_cm is not None else None,
                    chest_cm=float(latest.chest_cm) if latest and latest.chest_cm is not None else None,
                    body_fat_percent=max(0.1, round(current - 1.5, 1)),
                    notes="Cierre de meta de grasa corporal.",
                )
    return created


# (angle, days before today, top colour, bottom colour, note)
PHOTO_DEMOS = [
    ("front", 56, (30, 66, 52), (118, 158, 130), "Inicio del plan de fuerza."),
    ("side", 28, (42, 80, 108), (142, 174, 198), "Semana 4: mejora postural."),
    ("back", 0, (118, 82, 46), (198, 174, 140), "Semana 8: control de espalda."),
]


def _demo_png(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> bytes:
    """Build a small valid PNG gradient without adding an image dependency."""
    width, height = 240, 320

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = bytearray()
    for y in range(height):
        ratio = y / (height - 1)
        colour = bytes(round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        rows.append(0)
        rows.extend(colour * width)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def _seed_photos(session: Session) -> int:
    """Seed dated progress photos for the first one or two assigned members."""
    if session.exec(select(ProgressPhoto)).first() is not None:
        return 0
    member_ids: list = []
    assignments = session.exec(
        select(RoutineAssignment)
        .where(RoutineAssignment.status == "active")
        .order_by(RoutineAssignment.created_at)
        .limit(2)
    ).all()
    for assignment in assignments:
        if assignment.member_id not in member_ids:
            member_ids.append(assignment.member_id)
    if not member_ids:
        member = session.exec(
            select(Member).where(Member.status == "active").order_by(Member.first_name)
        ).first()
        if member is None:
            return 0
        member_ids.append(member.id)

    now = datetime.now(timezone.utc)
    local_day = to_club_timezone(now).replace(hour=12, minute=0, second=0, microsecond=0)
    created = 0
    for index, member_id in enumerate(member_ids):
        for angle, days_ago, top, bottom, notes in PHOTO_DEMOS[: 3 if index == 0 else 1]:
            captured_at = (local_day - timedelta(days=days_ago)).astimezone(timezone.utc)
            routines_service.record_progress_photo(
                session,
                member_id,
                data=_demo_png(top, bottom),
                content_type="image/png",
                angle=angle,
                captured_at=captured_at,
                notes=notes,
                now=now,
            )
            created += 1
    return created


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        # --- Exercise library ---------------------------------------------
        library = {row.name.lower(): row for row in session.exec(select(Exercise)).all()}
        created_exercises = 0
        for name, muscle, category, equipment in EXERCISES:
            if name.lower() not in library:
                item = routines_service.create_exercise(
                    session, name=name, muscle_group=muscle, category=category, equipment_name=equipment
                )
                library[name.lower()] = item
                created_exercises += 1

        def line(name: str, sets: int, reps: str, rest: int, load: str) -> routines_service.RoutineItemInput:
            return routines_service.RoutineItemInput(
                exercise_id=library[name.lower()].id,
                sets=sets,
                reps=reps,
                rest_seconds=rest,
                load_note=load,
            )

        members = session.exec(
            select(Member).where(Member.status == "active").order_by(Member.first_name)
        ).all()
        trainers = session.exec(
            select(Employee).where(Employee.status == "active").order_by(Employee.first_name)
        ).all()
        if not members:
            print("No active members found: assignments, workouts and measurements will stay empty.")

        if session.exec(select(Routine)).first() is not None:
            goals_created = _seed_goals(session)
            photos_created = _seed_photos(session)
            overview = routines_service.module_overview(session)
            print("Routines already seeded; skipping the demo plan.")
            if goals_created:
                total_goals = len(session.exec(select(MemberGoal)).all())
                print(f"Goals created: {goals_created} (total {total_goals})")
            if photos_created:
                total_photos = len(session.exec(select(ProgressPhoto)).all())
                print(
                    f"Progress photos created: {photos_created} "
                    f"(total {total_photos}, dir {photos_root()})"
                )
            print(
                f"Exercises {overview.exercises} · routines {overview.routines_active} activas · "
                f"asignaciones {overview.assignments_active} · entrenamientos (7d) {overview.workouts_last_7_days}"
            )
            return

        # --- Routines ------------------------------------------------------
        created_routines = []
        for index, (name, objective, items) in enumerate(ROUTINES):
            trainer = trainers[index % len(trainers)] if trainers else None
            detail = routines_service.create_routine(
                session,
                name=name,
                objective=objective,
                trainer_id=trainer.id if trainer else None,
                items=[line(*entry) for entry in items],
            )
            created_routines.append(detail)

        # History: publish version 2 of the flagship routine.
        flagship = created_routines[0]
        routines_service.replace_routine_items(
            session,
            flagship.routine.id,
            items=[line(*entry) for entry in FIRST_ROUTINE_VERSION_2],
            reason="Subir carga de fuerza tras cuatro semanas de adaptación",
        )

        # --- Assignments, workouts and measurements ------------------------
        today = date.today()
        now = datetime.now(timezone.utc)
        assignments = 0
        workouts = 0
        measurements = 0

        for index, member in enumerate(members[:6]):
            routine = created_routines[index % len(created_routines)]
            trainer = trainers[index % len(trainers)] if trainers else None
            assignment = routines_service.create_assignment(
                session,
                routine_id=routine.routine.id,
                member_id=member.id,
                start_date=today - timedelta(days=28),
                frequency_per_week=3 + (index % 2),
                trainer_id=trainer.id if trainer else None,
                notes="Revisión de técnica cada dos semanas." if index % 2 == 0 else None,
            )
            assignments += 1

            # Log a few workouts over the last three weeks.
            for week in range(3):
                performed = today - timedelta(days=week * 7 + (index % 3))
                if performed < assignment.start_date:
                    continue
                log = routines_service.log_workout(
                    session,
                    assignment.id,
                    performed_at=performed,
                    duration_minutes=45 + (index % 3) * 10,
                    perceived_effort=6 + (week % 3),
                    notes="Buena sesión." if week == 0 else None,
                )
                workouts += 1
                if week > 0:
                    routines_service.review_workout(session, log.id)

            # Measurements every two weeks with a gentle downward trend.
            base_weight = 68 + index * 3.5
            for step in range(3):
                measured = now - timedelta(days=56 - step * 28)
                routines_service.record_measurement(
                    session,
                    member.id,
                    measured_at=measured,
                    weight_kg=round(base_weight - step * 0.9, 1),
                    waist_cm=round(84 - step * 1.2, 1),
                    chest_cm=round(96 + index, 1),
                    body_fat_percent=round(24 - step * 0.8, 1),
                    notes="Medición de seguimiento." if step == 0 else None,
                )
                measurements += 1

        goals_created = _seed_goals(session)
        total_goals = len(session.exec(select(MemberGoal)).all())
        photos_created = _seed_photos(session)
        total_photos = len(session.exec(select(ProgressPhoto)).all())

        overview = routines_service.module_overview(session)
        print(f"Exercises created: {created_exercises} (total {overview.exercises})")
        print(f"Routines created: {len(created_routines)} (activas {overview.routines_active})")
        print(f"Assignments created: {assignments} (activas {overview.assignments_active})")
        print(f"Workouts created: {workouts} (últimos 7 días {overview.workouts_last_7_days})")
        print(f"Measurements created: {measurements}")
        print(f"Goals created: {goals_created} (total {total_goals})")
        print(
            f"Progress photos created: {photos_created} "
            f"(total {total_photos}, dir {photos_root()})"
        )
        print("Done!")


if __name__ == "__main__":
    main()
