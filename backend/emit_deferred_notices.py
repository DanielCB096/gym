"""Write the notices that normally wait for someone to open the inbox.

Member reminders (expiring membership, class and physiotherapy reminders) and the
two staff notices that were only produced on a read path (the overdue attendance
escalation and the expiring kiosk token) are materialised here. The producers
deduplicate themselves, so running this every hour writes each notice once.

The member reminders queue their push because nobody is looking at the inbox;
the same run drains that queue, so the phone rings without waiting for the
member to open the app. The pass respects the club's and the member's silence
windows, simulates in ``--preview`` and leaves ``failed`` rows for the normal
retry (ADR-078).

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe emit_deferred_notices.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it, for example every hour next to the other
operational tasks:

    DATABASE_URL=postgresql+psycopg://... python emit_deferred_notices.py

``--preview`` uses ``gym_preview.db`` and only creates the tables it needs, so a
notice written there stays on this machine.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.modules import (  # noqa: E402,F401
    access,
    classes,
    identity,
    memberships,
    notifications,
    physio,
    staffing,
)
from app.modules.notifications import materialise_deferred_notices  # noqa: E402
from app.modules.notifications.push import (  # noqa: E402
    DEFAULT_SEND_BATCH_LIMIT,
    MAX_SEND_BATCH_LIMIT,
    send_pending_member_push_deliveries_from_engine,
)

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Escribe los avisos del socio y del personal que dependen del "
            "tiempo, sin esperar a que alguien abra la bandeja."
        )
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="usa la base de vista previa (backend/gym_preview.db)",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL de SQLAlchemy; por defecto toma DATABASE_URL del entorno",
    )
    parser.add_argument(
        "--push-limit",
        type=int,
        default=DEFAULT_SEND_BATCH_LIMIT,
        help=(
            "pushes por corrida "
            f"(1 a {MAX_SEND_BATCH_LIMIT}; por defecto "
            f"{DEFAULT_SEND_BATCH_LIMIT}); lo que sobre sale en la siguiente"
        ),
    )
    args = parser.parse_args(argv)
    if args.push_limit < 1 or args.push_limit > MAX_SEND_BATCH_LIMIT:
        parser.error(
            f"--push-limit debe estar entre 1 y {MAX_SEND_BATCH_LIMIT}."
        )
    if args.preview and args.database_url:
        parser.error("usa --preview o --database-url, no ambos.")
    return args


def _resolve_database_url(args: argparse.Namespace) -> tuple[str, bool] | None:
    if args.database_url:
        return args.database_url, False
    if args.preview:
        return PREVIEW_DATABASE_URL, True
    url = os.getenv("DATABASE_URL")
    if not url:
        print(
            "Configura DATABASE_URL o usa --preview para la base de vista previa.",
            file=sys.stderr,
        )
        return None
    return url, False


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    resolved = _resolve_database_url(args)
    if resolved is None:
        return 2
    database_url, is_preview = resolved

    if is_preview:
        os.environ["PREVIEW_MODE"] = "1"

    engine = create_engine(database_url)
    try:
        if is_preview:
            SQLModel.metadata.create_all(engine)
            print(f"Base de vista previa: {database_url}")
        with Session(engine) as session:
            result = materialise_deferred_notices(session)
        pushes = send_pending_member_push_deliveries_from_engine(
            engine, limit=args.push_limit
        )
    except SQLAlchemyError as error:
        print(f"Error al emitir los avisos diferidos: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(f"Revisados {result.members_checked} socios con recordatorios en ventana.")
    print(
        f"Escritos {result.member_notices_written} avisos del socio y "
        f"{result.staff_notices_written} del personal "
        f"({result.attendance_escalations_written} escalamientos de asistencia y "
        f"{result.kiosk_token_notices_written} del token del kiosco)."
    )
    print(
        f"Push del socio: {pushes.attempted} intentos — "
        f"enviados {pushes.sent}, simulados {pushes.simulated}, "
        f"fallidos {pushes.failed}, dispositivos retirados {pushes.deactivated}."
    )
    if pushes.deferred:
        print("La ventana de silencio del club retuvo los push; saldrán en la próxima pasada.")
    print(f"Entregas de push pendientes que quedan: {pushes.remaining}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
