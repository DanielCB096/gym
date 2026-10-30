"""Delete unusable rotating codes and old kiosk attempts.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe purge_access_data.py --preview --dry-run
    .\\.venv\\Scripts\\python.exe purge_access_data.py --preview

In production point it at the real database with ``DATABASE_URL`` (or
``--database-url``) and schedule it, for example, once a day from cron:

    DATABASE_URL=postgresql+psycopg://... python purge_access_data.py

The retention defaults are 7 days for codes and 30 days for attempts; override
them with ``KIOSK_CODE_RETENTION_DAYS`` / ``KIOSK_ATTEMPT_RETENTION_DAYS`` or the
``--codes-days`` / ``--attempts-days`` flags. The access log is never touched:
its retention belongs to the club's records policy.
"""

import argparse
import os
import sys

sys.path.insert(0, r".\src")

from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import SQLModel, Session  # noqa: E402

from app.modules import access, identity, memberships  # noqa: E402,F401
from app.modules.access.retention import (  # noqa: E402
    DEFAULT_ATTEMPT_RETENTION_DAYS,
    DEFAULT_CODE_RETENTION_DAYS,
    RetentionPolicy,
    purge_expired_access_data,
    retention_policy_from_env,
)

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Borra los códigos rotativos ya inutilizables y los intentos del "
            "kiosco anteriores a la retención configurada."
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
        "--codes-days",
        type=int,
        default=None,
        help=f"días que se conserva un código (por defecto {DEFAULT_CODE_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--attempts-days",
        type=int,
        default=None,
        help=(
            "días que se conserva un intento del kiosco "
            f"(por defecto {DEFAULT_ATTEMPT_RETENTION_DAYS})"
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
        policy = retention_policy_from_env()
    except ValueError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    policy = RetentionPolicy(
        code_days=args.codes_days if args.codes_days is not None else policy.code_days,
        attempt_days=(
            args.attempts_days
            if args.attempts_days is not None
            else policy.attempt_days
        ),
    )

    engine = create_engine(database_url)
    try:
        if is_preview:
            SQLModel.metadata.create_all(engine)
            print(f"Base de vista previa: {database_url}")
        with Session(engine) as session:
            try:
                result = purge_expired_access_data(
                    session,
                    code_days=policy.code_days,
                    attempt_days=policy.attempt_days,
                    dry_run=args.dry_run,
                )
            except ValueError as error:
                print(f"Error de configuración: {error}", file=sys.stderr)
                return 2
    finally:
        engine.dispose()

    mode = "Simulación (no se borró nada)" if result.dry_run else "Purga aplicada"
    print(f"{mode} — retención de {result.code_days} días para códigos y "
          f"{result.attempt_days} días para intentos.")
    print(
        f"Códigos inutilizables antes de "
        f"{result.code_cutoff:%Y-%m-%d %H:%M} UTC: {result.codes_deleted}"
    )
    print(
        f"Intentos anteriores a "
        f"{result.attempt_cutoff:%Y-%m-%d %H:%M} UTC: {result.attempts_deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
