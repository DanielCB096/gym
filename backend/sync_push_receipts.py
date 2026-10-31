"""Ask Expo for the receipts of the member pushes already sent.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe sync_push_receipts.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it, for example every fifteen minutes next to
``purge_email_receipts.py``:

    DATABASE_URL=postgresql+psycopg://... python sync_push_receipts.py

Expo keeps a receipt for 24 hours; a ticket older than that without an answer is
recorded as ``expired``. The panel's «Consultar acuses» button runs the same pass
by hand. Preview mode never queues a real ticket, so the run reports
``deferred`` and touches nothing.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import SQLModel, Session  # noqa: E402

from app.modules import identity, memberships, notifications  # noqa: E402,F401
from app.modules.notifications.push_receipts import (  # noqa: E402
    DEFAULT_RECEIPT_BATCH,
    MAX_RECEIPT_BATCH,
    PushReceiptsFailed,
    sync_member_push_receipts,
)

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Consulta en Expo los acuses de los push enviados y guarda uno por "
            "entrega, sin tocar el estado de la cola."
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
        "--limit",
        type=int,
        default=DEFAULT_RECEIPT_BATCH,
        help=f"tickets por corrida (por defecto {DEFAULT_RECEIPT_BATCH})",
    )
    args = parser.parse_args(argv)
    if args.preview and args.database_url:
        parser.error("usa --preview o --database-url, no ambos.")
    if args.limit < 1 or args.limit > MAX_RECEIPT_BATCH:
        parser.error(f"--limit debe estar entre 1 y {MAX_RECEIPT_BATCH}.")
    return args


def _resolve_database_url(args: argparse.Namespace) -> tuple[str, bool]:
    if args.database_url:
        return args.database_url, False
    if args.preview:
        return PREVIEW_DATABASE_URL, True
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit(
            "Configura DATABASE_URL o usa --preview para la base de vista previa."
        )
    return url, False


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url, is_preview = _resolve_database_url(args)

    engine = create_engine(database_url)
    try:
        if is_preview:
            SQLModel.metadata.create_all(engine)
            print(f"Base de vista previa: {database_url}")
        with Session(engine) as session:
            try:
                result = sync_member_push_receipts(session, limit=args.limit)
            except PushReceiptsFailed as error:
                print(f"Error al consultar los acuses: {error}", file=sys.stderr)
                return 1
    finally:
        engine.dispose()

    if result.deferred:
        print("Vista previa: no hay tickets reales que consultar (simulación).")
        return 0
    print(
        f"Acuses consultados: {result.checked} — entregados {result.delivered}, "
        f"con error {result.errors}, vencidos {result.expired}."
    )
    if result.deactivated:
        print(f"Dispositivos retirados (DeviceNotRegistered): {result.deactivated}.")
    print(f"Entregas enviadas que siguen sin acuse: {result.pending}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
