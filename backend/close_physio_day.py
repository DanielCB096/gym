"""Close the physiotherapy agenda of a finished day.

The room has a manual «Cerrar día» that marks as ``no_show`` every pending
appointment that already ended, without charging nor consuming a credit
(ADR-039). Until now the day stayed open until someone pressed it, so a day
nobody reviewed kept its appointments ``scheduled`` forever. This script runs
that same service from the host's cron, one day behind the club's calendar.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe close_physio_day.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it daily after midnight; ``--date`` closes a
specific day when a run was missed:

    DATABASE_URL=postgresql+psycopg://... python close_physio_day.py --date 2026-10-30

``--preview`` uses ``gym_preview.db`` and writes there, exactly like pressing
«Cerrar día» in the panel. A no-show is still correctable inside the grace
window (24 hours after the appointment ends), so closing early never locks a
charge.
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.modules.physio import close_physio_day  # noqa: E402
from app.timezone import club_timezone  # noqa: E402

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cierra el día de la agenda de fisioterapia que ya terminó, sin "
            "cobrar ni descontar créditos."
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
        "--date",
        default=None,
        help=(
            "día del club a cerrar en formato AAAA-MM-DD (por defecto, el día "
            "anterior en APP_TIMEZONE)"
        ),
    )
    args = parser.parse_args(argv)
    if args.preview and args.database_url:
        parser.error("usa --preview o --database-url, no ambos.")
    if args.date is not None:
        try:
            args.date = date.fromisoformat(args.date)
        except ValueError:
            parser.error("--date debe tener la forma AAAA-MM-DD.")
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


def _default_day() -> date:
    return datetime.now(club_timezone()).date() - timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    resolved = _resolve_database_url(args)
    if resolved is None:
        return 2
    database_url, is_preview = resolved
    day = args.date or _default_day()

    if is_preview:
        os.environ["PREVIEW_MODE"] = "1"

    engine = create_engine(database_url)
    try:
        if is_preview:
            SQLModel.metadata.create_all(engine)
            print(f"Base de vista previa: {database_url}")
        with Session(engine) as session:
            closed = close_physio_day(session, day=day)
    except SQLAlchemyError as error:
        print(
            f"Error al cerrar el día de fisioterapia: {error}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    if closed:
        noun = "cita marcada" if len(closed) == 1 else "citas marcadas"
        print(
            f"Día de fisioterapia cerrado: {day.isoformat()} — {len(closed)} "
            f"{noun} como inasistencia."
        )
    else:
        print(f"Día de fisioterapia cerrado: {day.isoformat()} — sin citas pendientes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
