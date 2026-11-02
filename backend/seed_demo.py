"""Prepare the disposable database used by the commercial demo.

The demo runs against a *copy* of the curated preview database so the original
``gym_preview.db`` is never touched. This script finalises that copy:

* applies the preview schema patches and creates any missing tables;
* leaves five staff accounts with known passwords and one role each, so the
  demo can switch between «dueño», «gerente», «recepción», «entrenador» and
  «mantenimiento» to show RBAC;
* refreshes the demo memberships so nobody is expired by accident: Ana is left
  three days from expiry (the «por vencer» case), Sofía is frozen and Raúl is
  past his end date (the «acceso denegado» case);
* seeds a physiotherapy agenda with a therapist, two packs and three upcoming
  appointments, so the module is not empty;
* revokes the old kiosk devices and creates «Recepción demo», writing its token
  to ``backend/.secrets/demo-kiosk-token.txt`` (ignored by git).

Run it from ``backend/`` after copying the preview database, or let
``demo/start-demo.ps1`` do both:

    .\\.venv\\Scripts\\python.exe seed_demo.py --db .demo_runtime/gym_preview.db

The credentials are for a local, disposable demo only. Do not reuse them in
production or against real member data.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import pkgutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

import app.modules  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

DEMO_PASSWORD = "DemoGimnasio2026!"
DEFAULT_DB = BACKEND_DIR / ".demo_runtime" / "gym_preview.db"
TOKEN_FILE = BACKEND_DIR / ".secrets" / "demo-kiosk-token.txt"

# One account per role. ``employee_number=None`` means the account is not tied
# to a staff file; the rest reuse the curated preview staff.
PERSONAS = (
    {
        "email": "owner@centrofit.mx",
        "role": "owner",
        "employee_number": "DEMO-001",
        "first_name": "Daniel",
        "last_name": "Ortega",
        "job_title": "Dueño",
    },
    {
        "email": "gerente@centrofit.mx",
        "role": "manager",
        "employee_number": "EMP-001",
        "first_name": "Laura",
        "last_name": "Sánchez",
        "job_title": "Gerente",
    },
    {
        "email": "recepcion@centrofit.mx",
        "role": "reception",
        "employee_number": "EMP-003",
        "first_name": "Paola",
        "last_name": "Ríos",
        "job_title": "Recepción",
    },
    {
        "email": "carlos.ortiz@centrofit.mx",
        "role": "trainer",
        "employee_number": "EMP-002",
        "first_name": "Carlos",
        "last_name": "Ortiz",
        "job_title": "Entrenador",
    },
    {
        "email": "mantenimiento.preview@centrofit.mx",
        "role": "maintenance",
        "employee_number": "EMP-004",
        "first_name": "Miguel",
        "last_name": "Ramos",
        "job_title": "Mantenimiento",
    },
)

DISABLED_EMAILS = ("pruebas@centrofit.mx", "ver.jornada@centrofit.mx")
DISABLED_EMPLOYEE_NUMBERS = ("EMP-V01",)

# (email, membership status, days until it ends)
MEMBERSHIP_REFRESH = {
    "ana.lopez@example.com": ("active", 3),
    "raul.morales@example.com": ("active", -1),
    "sofia.martinez@example.com": ("frozen", 30),
}


def import_all_models() -> None:
    """Populate SQLModel.metadata with every module, like alembic/env.py does."""
    for package in pkgutil.iter_modules(app.modules.__path__):
        module_name = f"app.modules.{package.name}.models"
        if importlib.util.find_spec(module_name) is not None:
            importlib.import_module(module_name)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_employee(session: Session, persona: dict[str, object]):
    from app.modules.identity.models import Employee

    number = str(persona["employee_number"])
    employee = session.exec(
        select(Employee).where(Employee.employee_number == number)
    ).first()
    if employee is None:
        employee = Employee(
            employee_number=number,
            first_name=str(persona["first_name"]),
            last_name=str(persona["last_name"]),
            job_title=str(persona["job_title"]),
            status="active",
        )
        session.add(employee)
        session.commit()
        session.refresh(employee)
        print(f"  empleado {number}: creado ({persona['first_name']} {persona['last_name']})")
    else:
        employee.first_name = str(persona["first_name"])
        employee.last_name = str(persona["last_name"])
        employee.job_title = str(persona["job_title"])
        employee.status = "active"
        session.add(employee)
        session.commit()
        print(f"  empleado {number}: reutilizado")
    return employee


def get_or_create_user(session: Session, persona: dict[str, object], owner_id: UUID | None):
    from app.modules.identity.models import AppUser
    from app.modules.identity.service import PASSWORD_HASHER, register_user

    email = str(persona["email"])
    employee = get_or_create_employee(session, persona)

    user = session.exec(
        select(AppUser).where(AppUser.email == email)
    ).first()
    if user is None:
        # An existing account may already own this staff file (unique employee_id).
        user = session.exec(
            select(AppUser).where(AppUser.employee_id == employee.id)
        ).first()
    if user is None:
        user = register_user(
            session,
            email=email,
            password=DEMO_PASSWORD,
            employee_id=employee.id,
            role_codes=(),
            assigned_by=owner_id,
        )
        print(f"  cuenta {email}: creada")
    else:
        user.email = email
        user.employee_id = employee.id
        user.password_hash = PASSWORD_HASHER.hash(DEMO_PASSWORD)
        user.status = "active"
        session.add(user)
        session.commit()
        session.refresh(user)
        print(f"  cuenta {email}: contraseña restablecida")
    return user


def ensure_role(session: Session, user, role_code: str, owner_id: UUID):
    from app.modules.identity.models import Role, UserRoleAssignment
    from app.modules.identity.service import assign_role

    role = session.exec(select(Role).where(Role.code == role_code)).first()
    if role is None:
        raise SystemExit(
            f"No existe el rol {role_code!r}. La base de origen no tiene el seed de RBAC."
        )
    active = session.exec(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.role_id == role.id,
            UserRoleAssignment.revoked_at.is_(None),
        )
    ).first()
    if active is None:
        assign_role(
            session,
            user_id=user.id,
            role_code=role_code,
            assigned_by=owner_id,
        )
        print(f"  rol {role_code}: asignado a {user.email}")
    else:
        print(f"  rol {role_code}: ya presente en {user.email}")


def refresh_memberships(session: Session) -> None:
    from app.modules.memberships.models import Member, Membership

    now = utc_now()
    members = session.exec(select(Member)).all()
    if not members:
        raise SystemExit(
            "La base de origen no tiene socios. Usa una copia sembrada de gym_preview.db."
        )

    for member in members:
        if member.status != "active":
            member.status = "active"
            session.add(member)

        membership = session.exec(
            select(Membership)
            .where(Membership.member_id == member.id)
            .order_by(Membership.ends_at.desc())
        ).first()
        explicit = (member.email or "") in MEMBERSHIP_REFRESH
        if membership is None or (
            not explicit
            and membership.status in ("cancelled", "expired", "pending_payment")
        ):
            continue

        status, days = MEMBERSHIP_REFRESH.get(
            member.email or "", ("active", 30)
        )
        membership.status = status
        membership.starts_at = now - timedelta(days=20)
        membership.ends_at = now + timedelta(days=days)
        session.add(membership)
        print(
            f"  membresía {member.first_name} {member.last_name}: "
            f"{status}, vence {membership.ends_at:%Y-%m-%d}"
        )
    session.commit()


def seed_physio_demo(session: Session, actor_id: UUID) -> None:
    """Give the physiotherapy agenda and packs something to show."""

    from app.modules.identity.models import Employee
    from app.modules.inventory import service as inventory_service
    from app.modules.memberships.models import Member
    from app.modules.physio import service as physio_service
    from app.modules.physio.models import (
        PhysioAppointment,
        PhysioOffer,
        PhysioPack,
        PhysioRoom,
        PhysioService,
        PhysioSpecialty,
    )

    service = session.exec(
        select(PhysioService).where(PhysioService.code == "DESCARGA")
    ).first()
    offer = session.exec(
        select(PhysioOffer).where(PhysioOffer.name == "Paquete de 2 descargas")
    ).first()
    valoracion = session.exec(
        select(PhysioService).where(PhysioService.code == "VALORACION")
    ).first()
    room = session.exec(
        select(PhysioRoom).where(PhysioRoom.name == "Consultorio 1")
    ).first()
    specialty = session.exec(
        select(PhysioSpecialty).where(PhysioSpecialty.name == "Terapia deportiva")
    ).first()

    if service is None or offer is None:
        raise RuntimeError(
            "Falta el catálogo de fisioterapia; ejecuta los seeds de la demo antes de seed_demo.py."
        )

    therapist = session.exec(
        select(Employee).where(Employee.employee_number == "DEMO-FISIO")
    ).first()
    if therapist is None:
        therapist = Employee(
            employee_number="DEMO-FISIO",
            first_name="Lucía",
            last_name="Núñez",
            job_title="Fisioterapeuta",
            status="active",
        )
        session.add(therapist)
        session.commit()
        session.refresh(therapist)
        print("  fisioterapeuta Lucía Núñez: creado")
    if room is not None or specialty is not None:
        physio_service.update_physio_therapist_profile(
            session,
            therapist.id,
            specialty_id=specialty.id if specialty is not None else None,
            room_id=room.id if room is not None else None,
        )

    if inventory_service.current_cash_session(session) is None:
        inventory_service.open_cash_session(
            session, opening_cash_cents=0, actor_id=actor_id
        )
        print("  caja: turno abierto para la demo")

    now = datetime.now(ZoneInfo(os.getenv("APP_TIMEZONE", "America/Mexico_City")))
    members = {member.email or "": member for member in session.exec(select(Member))}

    for email in ("ana.lopez@example.com", "luis.hernandez@example.com"):
        member = members.get(email)
        if member is None:
            continue
        existing = session.exec(
            select(PhysioPack).where(
                PhysioPack.member_id == member.id,
                PhysioPack.offer_id == offer.id,
                PhysioPack.voided_at.is_(None),
                PhysioPack.sessions_used < PhysioPack.sessions_total,
                PhysioPack.valid_until >= now,
            )
        ).first()
        if existing is not None:
            print(f"  paquete de fisioterapia para {member.first_name}: ya existe")
            continue
        physio_service.sell_physio_pack(
            session,
            member_id=member.id,
            offer_id=offer.id,
            payment_method="card",
            actor_id=actor_id,
            now=now,
        )
        print(f"  paquete de fisioterapia para {member.first_name}: vendido")

    def at(day_offset: int, hour: int) -> datetime:
        slot = (now + timedelta(days=day_offset)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        if slot <= now:
            slot += timedelta(days=1)
        return slot

    slots = [
        ("ana.lopez@example.com", service, (now + timedelta(hours=2)).replace(
            minute=0, second=0, microsecond=0
        )),
        ("sofia.martinez@example.com", valoracion or service, at(1, 10)),
        ("luis.hernandez@example.com", service, at(2, 16)),
    ]
    for email, slot_service, start in slots:
        member = members.get(email)
        if member is None:
            continue
        start_utc = start.astimezone(timezone.utc)
        existing = session.exec(
            select(PhysioAppointment).where(
                PhysioAppointment.member_id == member.id,
                PhysioAppointment.service_id == slot_service.id,
                PhysioAppointment.starts_at >= start_utc - timedelta(minutes=1),
                PhysioAppointment.starts_at <= start_utc + timedelta(minutes=1),
            )
        ).first()
        if existing is not None:
            print(f"  cita de {member.first_name}: ya existe")
            continue
        physio_service.create_physio_appointment(
            session,
            member_id=member.id,
            service_id=slot_service.id,
            therapist_employee_id=therapist.id,
            starts_at=start,
            room_id=room.id if room is not None else None,
            notes="Cita de demostración",
            actor_id=actor_id,
        )
        print(
            f"  cita de {member.first_name}: {start:%Y-%m-%d %H:%M} "
            f"con {therapist.first_name} {therapist.last_name}"
        )


def reset_kiosk(
    session: Session,
    owner_id: UUID,
    *,
    token_file: Path = TOKEN_FILE,
    keep: bool = False,
) -> str:
    from app.modules.access.kiosk import create_kiosk_device, list_kiosk_devices, revoke_kiosk_device

    if keep:
        active = [
            device
            for device in list_kiosk_devices(session)
            if device.status == "active" and device.label == "Recepción demo"
        ]
        if active and token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
            if token:
                print(f"  kiosco {active[0].label!r}: token conservado")
                return token

    for device in list_kiosk_devices(session):
        if device.status == "active":
            revoke_kiosk_device(session, device.id)
    device, token = create_kiosk_device(
        session, label="Recepción demo", created_by=owner_id
    )
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    print(f"  kiosco {device.label!r}: token nuevo en {token_file}")
    return token


def disable_leftovers(session: Session, actor_id: UUID) -> None:
    from app.modules.identity.models import AppUser, Employee
    from app.modules.identity.service import set_user_status

    for email in DISABLED_EMAILS:
        user = session.exec(select(AppUser).where(AppUser.email == email)).first()
        if user is not None and user.status == "active":
            set_user_status(
                session, user_id=user.id, status="disabled", actor_id=actor_id
            )
            print(f"  cuenta {email}: deshabilitada")

    for number in DISABLED_EMPLOYEE_NUMBERS:
        employee = session.exec(
            select(Employee).where(Employee.employee_number == number)
        ).first()
        if employee is not None and employee.status == "active":
            employee.status = "inactive"
            session.add(employee)
            print(f"  colaborador {number}: dado de baja")
    session.commit()


def main() -> int:
    global DEMO_PASSWORD

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--password",
        default=DEMO_PASSWORD,
        help="Contraseña compartida por las cuentas de la demo (mínimo 12).",
    )
    parser.add_argument(
        "--keep-kiosk",
        action="store_true",
        help="Conserva el token del kiosco activo si ya existe (reinicios rápidos).",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=TOKEN_FILE,
        help="Ruta del archivo local donde guardar el token del kiosco.",
    )
    args = parser.parse_args()
    if len(args.password) < 12:
        parser.error("La contraseña de la demo debe tener al menos 12 caracteres.")
    DEMO_PASSWORD = args.password

    db_path = args.db
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    if not db_path.exists():
        raise SystemExit(
            f"No existe {db_path}. Copia primero gym_preview.db o usa demo/start-demo.ps1."
        )

    import preview_patch  # noqa: E402  (script next to this file)

    print(f"Base de demo: {db_path}")
    import_all_models()
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", echo=False)
    SQLModel.metadata.create_all(engine)

    preview_patch.DB = str(db_path)
    preview_patch.main(False)

    from app.modules.identity.models import AppUser
    from app.modules.identity.service import ensure_default_access_control

    with Session(engine) as session:
        ensure_default_access_control(session)

        owner = session.exec(
            select(AppUser).where(AppUser.email == "owner@centrofit.mx")
        ).first()
        owner_id = owner.id if owner is not None else None

        print("Cuentas de demostración:")
        users = {}
        for persona in PERSONAS:
            user = get_or_create_user(session, persona, owner_id)
            users[str(persona["email"])] = user
            if owner_id is None:
                owner_id = user.id

        for persona in PERSONAS:
            ensure_role(
                session,
                users[str(persona["email"])],
                str(persona["role"]),
                owner_id,
            )

        print("Membresías:")
        refresh_memberships(session)

        print("Fisioterapia:")
        seed_physio_demo(session, owner_id)

        print("Kiosco:")
        token = reset_kiosk(
            session,
            owner_id,
            token_file=args.token_file.resolve(),
            keep=args.keep_kiosk,
        )

        disable_leftovers(session, owner_id)

    print("\nListo. Credenciales (solo para la demo local):")
    for persona in PERSONAS:
        print(f"  {persona['role']:12} {persona['email']:38} {DEMO_PASSWORD}")
    print(f"\nToken del kiosco: {token}")
    print(f"Guardado en: {args.token_file.resolve()}")
    print(f"\nBackend: DATABASE_URL=sqlite:///{db_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
