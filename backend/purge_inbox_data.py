"""Delete the read notices and the finished staff deliveries past retention.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe purge_inbox_data.py --preview --dry-run
    .\\.venv\\Scripts\\python.exe purge_inbox_data.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it, for example, once a day after the other
purges:

    DATABASE_URL=postgresql+psycopg://... python purge_inbox_data.py

The inbox window is 365 days by default (``NOTIFICATION_INBOX_RETENTION_DAYS``
or ``--inbox-days``): a member notice is deleted only when it was read, and a
staff notice when its work is done — resolved if it was actionable, read if it
only informed. The terminal deliveries of the two staff queues are kept 365 days
(``STAFF_DELIVERY_RETENTION_DAYS`` or ``--delivery-days``). Unread notices, the
unresolved actionable notices, the pending deliveries and any row a surviving
receipt still points at are never touched. The member push queue and its
receipts have their own purge in ``purge_push_data.py``.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.modules import identity, memberships, notifications  # noqa: E402,F401
from app.modules.notifications.inbox_retention import (  # noqa: E402
    DEFAULT_INBOX_RETENTION_DAYS,
    DEFAULT_STAFF_DELIVERY_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    MIN_DELIVERY_RETENTION_DAYS,
    MIN_INBOX_RETENTION_DAYS,
    InboxRetentionPolicy,
    inbox_retention_policy_from_env,
    purge_inbox_history,
)

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Borra los avisos leídos o cerrados y las entregas terminadas del "
            "personal anteriores a la retención configurada."
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
        "--inbox-days",
        type=int,
        default=None,
        help=(
            "días que se conserva un aviso ya leído o cerrado "
            f"(por defecto {DEFAULT_INBOX_RETENTION_DAYS})"
        ),
    )
    parser.add_argument(
        "--delivery-days",
        type=int,
        default=None,
        help=(
            "días que se conserva una entrega terminada del personal "
            f"(por defecto {DEFAULT_STAFF_DELIVERY_RETENTION_DAYS})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="cuenta lo que se borraría sin tocar la base",
    )
    args = parser.parse_args(argv)
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

    try:
        policy = inbox_retention_policy_from_env()
    except ValueError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    policy = InboxRetentionPolicy(
        inbox_days=(
            args.inbox_days if args.inbox_days is not None else policy.inbox_days
        ),
        delivery_days=(
            args.delivery_days
            if args.delivery_days is not None
            else policy.delivery_days
        ),
    )

    engine = create_engine(database_url)
    try:
        if is_preview:
            SQLModel.metadata.create_all(engine)
            print(f"Base de vista previa: {database_url}")
        with Session(engine) as session:
            try:
                result = purge_inbox_history(
                    session,
                    inbox_days=policy.inbox_days,
                    delivery_days=policy.delivery_days,
                    dry_run=args.dry_run,
                )
            except ValueError as error:
                print(f"Error de configuración: {error}", file=sys.stderr)
                return 2
    except SQLAlchemyError as error:
        print(f"Error al purgar la bandeja: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    mode = "Simulación (no se borró nada)" if result.dry_run else "Purga aplicada"
    print(
        f"{mode} — avisos de {result.inbox_days} días (mínimo "
        f"{MIN_INBOX_RETENTION_DAYS}) y entregas del personal de "
        f"{result.delivery_days} días (mínimo {MIN_DELIVERY_RETENTION_DAYS}, "
        f"máximo {MAX_RETENTION_DAYS})."
    )
    print(
        f"Avisos creados antes de {result.inbox_cutoff:%Y-%m-%d %H:%M} UTC: "
        f"{result.member_notices_deleted} del socio y "
        f"{result.staff_notices_deleted} del personal"
    )
    print(
        f"Entregas terminadas creadas antes de "
        f"{result.delivery_cutoff:%Y-%m-%d %H:%M} UTC: "
        f"{result.staff_email_deliveries_deleted} de correo y "
        f"{result.staff_push_deliveries_deleted} de push del personal"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
