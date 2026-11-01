"""Drain member-notification emails and their scheduled retries.

The request that creates a notice sends the queue after its response. This
script recovers messages left pending by a crashed process and retries failures
whose backoff has elapsed.

    .\\.venv\\Scripts\\python.exe flush_member_email.py --preview

Use ``DATABASE_URL`` in the host's cron for the deployed database. Preview mode
uses ``gym_preview.db`` and simulates delivery without contacting SMTP.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.modules import identity, memberships, notifications  # noqa: E402,F401
from app.modules.notifications import member_email  # noqa: E402

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Envía avisos por correo a los socios que dieron su consentimiento."
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="usa la base de vista previa y simula el envío",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL de SQLAlchemy; por defecto toma DATABASE_URL del entorno",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=member_email.DEFAULT_SEND_BATCH_LIMIT,
        help=(
            "entregas por corrida "
            f"(1 a {member_email.MAX_SEND_BATCH_LIMIT}; por defecto "
            f"{member_email.DEFAULT_SEND_BATCH_LIMIT})"
        ),
    )
    args = parser.parse_args(argv)
    if args.preview and args.database_url:
        parser.error("usa --preview o --database-url, no ambos.")
    if args.limit < 1 or args.limit > member_email.MAX_SEND_BATCH_LIMIT:
        parser.error(
            f"--limit debe estar entre 1 y {member_email.MAX_SEND_BATCH_LIMIT}."
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
    previous_preview_mode = os.environ.get("PREVIEW_MODE")
    if is_preview:
        os.environ["PREVIEW_MODE"] = "1"

    engine = create_engine(database_url)
    try:
        if is_preview:
            SQLModel.metadata.create_all(engine)
            print(f"Base de vista previa: {database_url}")
        result = member_email.send_pending_member_notification_emails_from_engine(
            engine, limit=args.limit
        )
    except SQLAlchemyError as error:
        print(f"Error al drenar la cola de correo de socios: {error}", file=sys.stderr)
        return 1
    finally:
        try:
            engine.dispose()
        finally:
            if is_preview:
                if previous_preview_mode is None:
                    os.environ.pop("PREVIEW_MODE", None)
                else:
                    os.environ["PREVIEW_MODE"] = previous_preview_mode

    print(
        f"Cola de correo de socios: {result.attempted} intentos — "
        f"enviados {result.sent}, simulados {result.simulated}, "
        f"fallidos {result.failed}, cancelados {result.cancelled}."
    )
    print(f"Entregas pendientes o con reintento programado: {result.remaining}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
