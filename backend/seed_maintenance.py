"""Seed the preview database with a realistic maintenance demo.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_maintenance.py

The script is idempotent: it does nothing when the ``equipment`` table already
has rows. It goes through the module service so the blocking/resolution rules,
the append-only history and the preventive scheduling behave exactly as they do
in production.
"""

import sys

sys.path.insert(0, r".\src")

from datetime import date, datetime, timedelta, timezone  # noqa: E402

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import (  # noqa: E402,F401
    access,
    classes,
    identity,
    inventory,
    maintenance,
    memberships,
    routines,
    staffing,
)
from app.modules.identity.models import AppUser, Employee  # noqa: E402
from app.modules.identity.service import ensure_default_access_control  # noqa: E402
from app.modules.maintenance import service as maintenance_service  # noqa: E402
from app.modules.maintenance.models import Equipment  # noqa: E402
from app.modules.routines import service as routines_service  # noqa: E402
from app.modules.routines.models import Exercise, Routine, RoutineItem  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"

# name, category, location, brand, model, serial, acquired days ago,
# useful_life_months, purchase cost cents, next preventive in days (None = unset)
EQUIPMENT = [
    ("Caminadora", "Cardio", "Cardio", "Life Fitness", "T5", "LF-T5-001", 900, 84, 4200000, -6),
    ("Bicicleta", "Cardio", "Cardio", "Precor", "SBK-885", "PR-SBK-014", 700, 96, 2800000, 22),
    ("Elíptica", "Cardio", "Cardio", "Octane", "Q47", "OC-Q47-003", 500, 96, 3100000, 45),
    ("Rack", "Fuerza", "Piso de pesas", "Hammer Strength", "HR-2000", "HS-HR-007", 1200, 180, 5600000, -20),
    ("Prensa", "Fuerza", "Piso de pesas", "Cybex", "Leg Press 45", "CY-LP-011", 800, 180, 4900000, 60),
    ("Polea alta", "Fuerza", "Piso de pesas", "Life Fitness", "Cable Motion", "LF-CM-020", 640, 150, 5200000, 30),
    ("Polea", "Fuerza", "Piso de pesas", "Life Fitness", "Cable Motion", "LF-CM-021", 640, 150, 5200000, 90),
    ("Banco plano", "Fuerza", "Piso de pesas", "Hammer Strength", "FB-110", "HS-FB-032", 1000, 240, 900000, 120),
    ("Hack squat", "Fuerza", "Piso de pesas", "Cybex", "HS-400", "CY-HS-004", 380, 180, 6100000, 15),
    ("Mancuernas", "Fuerza", "Área funcional", None, "Serie 2-40 kg", "MN-SET-01", 1400, 300, 3400000, None),
    ("Banda de correr curva", "Cardio", "Cardio", "Assault", "Runner", "AS-RN-002", 210, 72, 3600000, -3),
    ("Báscula de bioimpedancia", "Accesorio", "Recepción", "Tanita", "MC-780", "TN-MC-001", 300, 60, 1800000, 40),
]

# exercise equipment_name (from seed_routines) -> equipment name
EXERCISE_LINKS = {
    "rack": "Rack",
    "prensa": "Prensa",
    "barra": "Rack",
    "banco plano": "Banco plano",
    "mancuernas": "Mancuernas",
    "polea alta": "Polea alta",
    "polea": "Polea",
    "caminadora": "Caminadora",
    "bicicleta": "Bicicleta",
}

# Preventive history: equipment name, summary, days ago, cost cents, next due in days
PREVENTIVE_RECORDS = [
    ("Prensa", "Lubricación de guías y ajuste de cable", 20, 45000, 70),
    ("Polea alta", "Cambio de cable y polea móvil", 12, 128000, 180),
    ("Banco plano", "Revisión de estructura y tornillería", 33, 18000, 150),
    ("Báscula de bioimpedancia", "Calibración anual de báscula", 8, 26000, 357),
    ("Mancuernas", "Reapriete de discos y engrasado", 45, 30000, None),
]

# Check rounds: area, result, days ago, observation
CHECKLISTS = [
    ("Vestidores", "observation", 3, "Fuga leve en una regadera; se levantó reporte de plomería."),
    ("Piso de pesas", "ok", 2, None),
    ("Cardio", "ok", 1, None),
    ("Área funcional", "pending", 1, "Faltó pulido del piso; se reprograma para el lunes."),
    ("Recepción", "ok", 4, None),
    ("Vestidores", "ok", 0, None),
]


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        if session.exec(select(Equipment)).first() is not None:
            overview = maintenance_service.module_overview(session)
            print("Maintenance already seeded; skipping the demo fleet.")
            print(
                f"Equipos {overview.equipment_total} · operativos {overview.operational} · "
                f"fuera de servicio {overview.out_of_service} · tickets abiertos {overview.tickets_open}"
            )
            return

        today = date.today()
        now = datetime.now(timezone.utc)
        technicians = session.exec(
            select(Employee).where(Employee.status == "active").order_by(Employee.first_name)
        ).all()
        # Attribute the demo activity to a real user so the "Reportó" and
        # "Quién" columns of the panel are populated.
        admin = session.exec(select(AppUser).order_by(AppUser.email)).first()
        actor_id = admin.id if admin is not None else None

        def technician(index: int):
            return technicians[index % len(technicians)] if technicians else None

        # --- Fleet ---------------------------------------------------------
        fleet: dict[str, object] = {}
        for (
            name,
            category,
            location,
            brand,
            model,
            serial,
            acquired_days,
            useful_life,
            cost,
            next_due_days,
        ) in EQUIPMENT:
            item = maintenance_service.create_equipment(
                session,
                name=name,
                category=category,
                location=location,
                brand=brand,
                model=model,
                serial_number=serial,
                acquired_on=today - timedelta(days=acquired_days),
                useful_life_months=useful_life,
                purchase_cost_cents=cost,
                next_preventive_due=(today + timedelta(days=next_due_days))
                if next_due_days is not None
                else None,
                notes=None,
                actor_id=actor_id,
            )
            fleet[name.lower()] = item

        # --- Link the exercise library to the fleet ------------------------
        linked = 0
        for exercise in session.exec(select(Exercise)).all():
            if not exercise.equipment_name or exercise.equipment_id is not None:
                continue
            target = EXERCISE_LINKS.get(exercise.equipment_name.strip().lower())
            equipment = fleet.get(target.lower()) if target else None
            if equipment is not None:
                exercise.equipment_id = equipment.id
                session.add(exercise)
                linked += 1
        session.commit()

        # --- An exercise that depends on a machine under repair ------------
        # Linking it is what makes the routine plan show the availability
        # warning, so one cardio exercise is attached to the curve treadmill.
        curve_unit = fleet["banda de correr curva"]
        library = {item.name.lower(): item for item in session.exec(select(Exercise)).all()}
        curve_exercise = library.get("caminata en banda curva")
        if curve_exercise is None:
            curve_exercise = routines_service.create_exercise(
                session,
                name="Caminata en banda curva",
                muscle_group="Cardio",
                category="Cardio",
                equipment_id=curve_unit.id,
            )
        elif curve_exercise.equipment_id is None:
            curve_exercise.equipment_id = curve_unit.id
            session.add(curve_exercise)
            session.commit()
        linked += 1

        # Append it to a cardio routine so the plan itself carries the warning.
        cardio = session.exec(select(Routine).where(Routine.name == "Cardio y Movilidad")).first()
        if cardio is not None:
            lines = session.exec(
                select(RoutineItem)
                .where(
                    RoutineItem.routine_id == cardio.id,
                    RoutineItem.version == cardio.version,
                )
                .order_by(RoutineItem.position)
            ).all()
            if all(line.exercise_id != curve_exercise.id for line in lines):
                routines_service.replace_routine_items(
                    session,
                    cardio.id,
                    items=[
                        routines_service.RoutineItemInput(
                            exercise_id=line.exercise_id,
                            sets=line.sets,
                            reps=line.reps,
                            rest_seconds=line.rest_seconds,
                            load_note=line.load_note,
                            notes=line.notes,
                        )
                        for line in lines
                    ]
                    + [
                        routines_service.RoutineItemInput(
                            exercise_id=curve_exercise.id,
                            sets=1,
                            reps="12 min",
                            rest_seconds=0,
                            load_note="Zona 2",
                        )
                    ],
                    reason="Incluye banda curva (equipo en revisión)",
                )
                print("Rutina 'Cardio y Movilidad' actualizada con la banda curva.")

        # --- Preventive history -------------------------------------------
        records = 0
        for index, (name, summary, days_ago, cost, next_due) in enumerate(PREVENTIVE_RECORDS):
            equipment = fleet[name.lower()]
            maintenance_service.record_maintenance(
                session,
                equipment_id=equipment.id,
                kind="preventive",
                summary=summary,
                performed_at=now - timedelta(days=days_ago),
                cost_cents=cost,
                technician_id=technician(index).id if technician(index) else None,
                next_due_on=(today + timedelta(days=next_due)) if next_due is not None else None,
                notes="Trabajo realizado en sitio.",
                actor_id=actor_id,
            )
            records += 1

        # --- A resolved critical fault (blocks, then hands the unit back) ---
        treadmill = fleet["caminadora"]
        critical = maintenance_service.create_ticket(
            session,
            equipment_id=treadmill.id,
            title="Banda desgastada y motor con sobrecalentamiento",
            kind="corrective",
            severity="critical",
            description="La banda se desliza y el motor se calienta a los 20 minutos de uso.",
            actor_id=actor_id,
            now=now - timedelta(days=9),
        )
        maintenance_service.start_ticket(session, critical.id, now=now - timedelta(days=8))
        maintenance_service.resolve_ticket(
            session,
            critical.id,
            resolution_notes="Cambio de banda y limpieza del sistema de ventilación del motor.",
            cost_cents=320000,
            next_due_on=today + timedelta(days=100),
            technician_id=technician(0).id if technician(0) else None,
            now=now - timedelta(days=7),
        )

        # --- One live preventive, assigned and scheduled -------------------
        rack = fleet["rack"]
        preventive = maintenance_service.create_ticket(
            session,
            equipment_id=rack.id,
            title="Preventivo trimestral del rack",
            kind="preventive",
            severity="low",
            description="Reapriete de tornillería y revisión de anclajes.",
            assigned_to=technician(1).id if technician(1) else None,
            scheduled_for=today + timedelta(days=5),
            actor_id=actor_id,
            now=now - timedelta(days=2),
        )

        # --- A fault in progress that keeps the unit out of service --------
        curve = fleet["banda de correr curva"]
        in_progress = maintenance_service.create_ticket(
            session,
            equipment_id=curve.id,
            title="Rodamiento central con ruido",
            kind="corrective",
            severity="high",
            description="Chirrido constante durante el entrenamiento de intervalos.",
            assigned_to=technician(2).id if technician(2) else None,
            actor_id=actor_id,
            now=now - timedelta(days=3),
        )
        maintenance_service.start_ticket(session, in_progress.id, now=now - timedelta(days=2))

        # --- A critical fault left open keeps a unit out of service ---------
        maintenance_service.create_ticket(
            session,
            equipment_id=fleet["hack squat"].id,
            title="Fuga de aceite hidráulico",
            kind="corrective",
            severity="critical",
            description="Charco de aceite bajo la plataforma; se retiró de servicio.",
            actor_id=actor_id,
            now=now - timedelta(hours=6),
        )

        # --- A cancelled duplicate -----------------------------------------
        duplicate = maintenance_service.create_ticket(
            session,
            equipment_id=fleet["elíptica"].id,
            title="Reporte duplicado: pantalla sin respuesta",
            kind="corrective",
            severity="medium",
            actor_id=actor_id,
            now=now - timedelta(days=5),
        )
        maintenance_service.cancel_ticket(
            session,
            duplicate.id,
            reason="Duplicado del ticket reportado por recepción.",
            now=now - timedelta(days=4),
        )

        # --- Cleaning and inspection rounds --------------------------------
        checklists = 0
        for area, result, days_ago, observation in CHECKLISTS:
            maintenance_service.record_checklist(
                session,
                area=area,
                result=result,
                observations=observation,
                performed_at=now - timedelta(days=days_ago),
                actor_id=actor_id,
            )
            checklists += 1

        overview = maintenance_service.module_overview(session)
        print(f"Equipos creados: {len(fleet)} (operativos {overview.operational})")
        print(f"Ejercicios vinculados: {linked}")
        print(f"Registros técnicos: {records} (últimos 30 días {overview.records_last_30_days})")
        print(
            f"Tickets: 5 · abiertos {overview.tickets_open} · críticos abiertos "
            f"{overview.tickets_critical} · en mantenimiento {overview.maintenance} · "
            f"fuera de servicio {overview.out_of_service}"
        )
        print(f"Rondas registradas: {checklists}")
        print(f"Preventivos vencidos: {overview.preventives_due}")
        print("Done!")


if __name__ == "__main__":
    main()
