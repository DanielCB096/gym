"""Delete the staff email receipts that are past their retention.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe purge_email_receipts.py --preview --dry-run
    .\\.venv\\Scripts\\python.exe purge_email_receipts.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it, for example, once a day next to
``purge_access_data.py``:

    DATABASE_URL=postgresql+psycopg://... python purge_email_receipts.py

The retention is 90 days by default; override it with
``STAFF_RECEIPT_RETENTION_DAYS`` or the ``--days`` flag. It cannot be shorter than
the webhook window (7 days), because a purged receipt could then come back from a
late retry of the same provider event. The deliveries and the inbox are never
touched: only the provider's acknowledgements are deleted.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import SQLModel, Session  # noqa: E402

from app.modules import identity, memberships, notifications  # noqa: E402,F401
from app.modules.notifications.retention import (  # noqa: E402
    DEFAULT_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    MIN_RETENTION_DAYS,
    ReceiptRetentionPolicy,
    purge_expired_receipts,
    receipt_retention_policy_from_env,
)

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Borra los acuses del proveedor de correo anteriores a la retención "
            "configurada, sin tocar las entregas ni la bandeja."
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
        "--days",
        type=int,
        default=None,
        help=f"días que se conserva un acuse (por defecto {DEFAULT_RETENTION_DAYS})",
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
    try:
        policy = receipt_retention_policy_from_env()
    except ValueError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    policy = ReceiptRetentionPolicy(
        retention_days=args.days if args.days is not None else policy.retention_days
    )

    engine = create_engine(database_url)
    try:
        if is_preview:
            SQLModel.metadata.create_all(engine)
            print(f"Base de vista previa: {database_url}")
        with Session(engine) as session:
            try:
                result = purge_expired_receipts(
                    session,
                    retention_days=policy.retention_days,
                    dry_run=args.dry_run,
                )
            except ValueError as error:
                print(f"Error de configuración: {error}", file=sys.stderr)
                return 2
    finally:
        engine.dispose()

    mode = "Simulación (no se borró nada)" if result.dry_run else "Purga aplicada"
    print(
        f"{mode} — retención de {result.retention_days} días para los acuses "
        f"(mínimo {MIN_RETENTION_DAYS}, máximo {MAX_RETENTION_DAYS})."
    )
    print(
        f"Acuses recibidos antes de "
        f"{result.cutoff:%Y-%m-%d %H:%M} UTC: {result.receipts_deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
