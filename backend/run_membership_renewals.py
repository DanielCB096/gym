"""Expire due memberships, process scheduled renewals, and reconcile Conekta orders."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine, select

load_dotenv(Path(__file__).with_name(".env"), override=False)
sys.path.insert(0, str(Path(__file__).with_name("src")))

from app.modules.memberships.conekta_payment_methods import (  # noqa: E402
    ConektaPaymentMethodConfigurationError,
    ConektaPaymentMethodSettings,
    ConektaPaymentMethods,
    ConektaRecurringPaymentGateway,
)
from app.modules.memberships.models import Membership, PaymentAttempt  # noqa: E402
from app.modules.memberships.payment_method_security import (  # noqa: E402
    PaymentMethodEncryptionConfigurationError,
    PaymentMethodEncryptionError,
    validate_payment_method_encryption_configuration,
)
from app.modules.memberships.service import run_auto_renewal_batch  # noqa: E402
from app.timezone import validate_club_timezone  # noqa: E402


DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Procesa vencimientos, cobros automáticos de membresía y conciliación "
            "de órdenes Conekta en sandbox."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL de SQLAlchemy; por defecto toma DATABASE_URL del entorno",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"máximo de filas por etapa (1 a {MAX_LIMIT}; por defecto {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="consulta pendientes y vencimientos sin escribir ni contactar a Conekta",
    )
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > MAX_LIMIT:
        parser.error(f"--limit debe estar entre 1 y {MAX_LIMIT}.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("Error: configura DATABASE_URL o pasa --database-url.", file=sys.stderr)
        return 2

    engine = create_engine(database_url)
    try:
        now = datetime.now(timezone.utc)
        if args.dry_run:
            with Session(engine) as session:
                due_memberships = session.exec(
                    select(func.count())
                    .select_from(Membership)
                    .where(
                        Membership.status == "active",
                        Membership.ends_at <= now,
                    )
                ).one()
                unresolved_attempts = session.exec(
                    select(func.count())
                    .select_from(PaymentAttempt)
                    .where(
                        PaymentAttempt.provider == "conekta",
                        PaymentAttempt.status.in_(("pending", "processing", "unknown")),
                    )
                ).one()
            print(
                f"Vista previa: {due_memberships} membresía(s) vencida(s), "
                f"{unresolved_attempts} intento(s) por conciliar; "
                "no se modificó la base ni se contactó a Conekta."
            )
            return 0

        validate_club_timezone()
        settings = ConektaPaymentMethodSettings.from_env()
        validate_payment_method_encryption_configuration()
        with Session(engine) as session:
            result = run_auto_renewal_batch(
                session,
                ConektaRecurringPaymentGateway(
                    session,
                    ConektaPaymentMethods(settings),
                ),
                now=now,
                limit=args.limit,
            )
    except (
        ConektaPaymentMethodConfigurationError,
        PaymentMethodEncryptionConfigurationError,
        PaymentMethodEncryptionError,
        ValueError,
    ) as error:
        print(f"Error de configuración de renovaciones: {error}", file=sys.stderr)
        return 2
    except SQLAlchemyError as error:
        print(f"Error de base de datos en renovaciones: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(
        "Pasada de renovaciones completada: "
        f"{result.expired_memberships} vencida(s), "
        f"{result.charges_started} cobro(s) inicial(es), "
        f"{result.retries_started} reintento(s), "
        f"{result.attempts_reconciled} intento(s) conciliado(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
