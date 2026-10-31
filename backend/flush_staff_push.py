"""Send the staff Web Push deliveries that are still pending.

A notice writes one ``pending`` delivery per active browser and the pass travels
with the request that created it, so a process that dies before the response
leaves those rows waiting until someone presses «Enviar pendientes» in the
panel. This script drains that queue from the host's cron; ``failed`` rows are
left alone because retrying them is still an operator's decision (ADR-071).

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe flush_staff_push.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it, for example every fifteen minutes next to
``sync_push_receipts.py``:

    DATABASE_URL=postgresql+psycopg://... python flush_staff_push.py

``--preview`` uses ``gym_preview.db`` and simulates the deliveries, exactly like
the post-response pass does: nothing leaves the machine.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.modules import identity, memberships, notifications  # noqa: E402,F401
from app.modules.notifications import webpush  # noqa: E402

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Envía las entregas pendientes del push web del personal, sin "
            "reintentar las que fallaron."
        )
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="usa la base de vista previa (backend/gym_preview.db) y simula el envío",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL de SQLAlchemy; por defecto toma DATABASE_URL del entorno",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=webpush.DEFAULT_SEND_BATCH_LIMIT,
        help=(
            "entregas por corrida "
            f"(1 a {webpush.MAX_SEND_BATCH_LIMIT}; por defecto "
            f"{webpush.DEFAULT_SEND_BATCH_LIMIT})"
        ),
    )
    args = parser.parse_args(argv)
    if args.preview and args.database_url:
        parser.error("usa --preview o --database-url, no ambos.")
    if args.limit < 1 or args.limit > webpush.MAX_SEND_BATCH_LIMIT:
        parser.error(
            f"--limit debe estar entre 1 y {webpush.MAX_SEND_BATCH_LIMIT}."
        )
    return args


def _resolve_database_url(args: argparse.Namespace) -> tuple[str, bool] | None:
    if args.database_url:
        return args.database_url, False
    if args.preview:
        return PREVIEW_DATABASE_URL, True
    url = os.getenv("DATABASE_URL")
    if not url:
        print(
            "Error: configura DATABASE_URL o usa --preview para la base de "
            "vista previa.",
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
        result = webpush.send_pending_staff_push_deliveries_from_engine(
            engine, limit=args.limit
        )
    except SQLAlchemyError as error:
        print(
            f"Error al enviar la cola del push del personal: {error}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    print(
        f"Cola del push web del personal: {result.attempted} intentos — "
        f"enviados {result.sent}, simulados {result.simulated}, "
        f"fallidos {result.failed}, navegadores dados de baja {result.deactivated}."
    )
    print(f"Entregas pendientes que quedan: {result.remaining}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
