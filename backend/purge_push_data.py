"""Delete the member push receipts and finished deliveries past their retention.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe purge_push_data.py --preview --dry-run
    .\\.venv\\Scripts\\python.exe purge_push_data.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it, for example, once a day next to the other
purges:

    DATABASE_URL=postgresql+psycopg://... python purge_push_data.py

Receipts are kept 90 days by default (``PUSH_RECEIPT_RETENTION_DAYS`` or
``--receipt-days``) and counted from ``received_at``, the moment the club stored
Expo's answer. Deliveries in a terminal state (``sent``, ``simulated`` or
``failed``) are kept 365 days (``PUSH_DELIVERY_RETENTION_DAYS`` or
``--delivery-days``) and counted from ``created_at``. A delivery still pointed at
by a receipt is never deleted, and a ``pending`` row is left alone: it is still
the queue.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlmodel import SQLModel, Session  # noqa: E402

from app.modules import identity, memberships, notifications  # noqa: E402,F401
from app.modules.notifications.push_retention import (  # noqa: E402
    DEFAULT_DELIVERY_RETENTION_DAYS,
    DEFAULT_RECEIPT_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    MIN_RETENTION_DAYS,
    PushRetentionPolicy,
    purge_push_data,
    push_retention_policy_from_env,
)

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Borra los acuses del push y las entregas terminadas anteriores a la "
            "retención configurada, sin tocar la cola pendiente."
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
        "--receipt-days",
        type=int,
        default=None,
        help=(
            "días que se conserva un acuse "
            f"(por defecto {DEFAULT_RECEIPT_RETENTION_DAYS})"
        ),
    )
    parser.add_argument(
        "--delivery-days",
        type=int,
        default=None,
        help=(
            "días que se conserva una entrega terminada "
            f"(por defecto {DEFAULT_DELIVERY_RETENTION_DAYS})"
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
        policy = push_retention_policy_from_env()
    except ValueError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    policy = PushRetentionPolicy(
        receipt_days=(
            args.receipt_days
            if args.receipt_days is not None
            else policy.receipt_days
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
                result = purge_push_data(
                    session,
                    receipt_days=policy.receipt_days,
                    delivery_days=policy.delivery_days,
                    dry_run=args.dry_run,
                )
            except ValueError as error:
                print(f"Error de configuración: {error}", file=sys.stderr)
                return 2
    except SQLAlchemyError as error:
        print(f"Error al purgar el push: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    mode = "Simulación (no se borró nada)" if result.dry_run else "Purga aplicada"
    print(
        f"{mode} — acuses de {result.receipt_days} días y entregas terminadas de "
        f"{result.delivery_days} días (mínimo {MIN_RETENTION_DAYS}, máximo "
        f"{MAX_RETENTION_DAYS})."
    )
    print(
        f"Acuses recibidos antes de "
        f"{result.receipt_cutoff:%Y-%m-%d %H:%M} UTC: {result.receipts_deleted}"
    )
    print(
        f"Entregas terminadas creadas antes de "
        f"{result.delivery_cutoff:%Y-%m-%d %H:%M} UTC: {result.deliveries_deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
