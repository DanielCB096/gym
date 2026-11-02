"""Send the daily, weekly and monthly report CSVs to internal recipients."""

import argparse
from datetime import date, datetime, timezone
import importlib
import importlib.util
import os
from pathlib import Path
import pkgutil
import sqlite3
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel

load_dotenv(Path(__file__).with_name(".env"), override=False)
sys.path.insert(0, str(Path(__file__).with_name("src")))

import app.modules  # noqa: E402
from app.modules.reports.scheduled import (  # noqa: E402
    ScheduledReportConfigurationError,
    configured_recipients,
    report_schedules,
    send_due_reports,
)
from app.modules.reports.scheduled_configuration import (  # noqa: E402
    get_scheduled_report_subscriptions,
)
from app.modules.reports.service import REPORT_NAMES  # noqa: E402
from app.timezone import club_date  # noqa: E402

PREVIEW_DATABASE_URL = "sqlite:///./gym_preview.db"


def _load_all_models() -> None:
    for package in pkgutil.iter_modules(app.modules.__path__):
        if not package.ispkg:
            continue
        module_name = f"app.modules.{package.name}.models"
        if importlib.util.find_spec(module_name) is not None:
            importlib.import_module(module_name)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Envía los seis reportes financieros diario y, cuando corresponde, "
            "semanal y mensual a destinatarios internos configurados."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview",
        action="store_true",
        help="usa gym_preview.db y simula el correo; no contacta SMTP",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="muestra periodos y cantidad de destinatarios sin abrir la base ni enviar",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL de SQLAlchemy; por defecto toma DATABASE_URL del entorno",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="fecha local del club que activa las cadencias (para recuperación manual)",
    )
    parser.add_argument(
        "--retry-exhausted",
        action="store_true",
        help="permite reintentar entregas que ya alcanzaron cinco intentos",
    )
    args = parser.parse_args(argv)
    if args.preview and args.database_url:
        parser.error("usa --preview o --database-url, no ambos.")
    if args.dry_run and args.database_url:
        parser.error("--dry-run no usa --database-url.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    today = args.today or club_date(datetime.now(timezone.utc))
    schedules = report_schedules(today=today)
    if args.dry_run:
        try:
            recipients = configured_recipients()
        except ScheduledReportConfigurationError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        print(
            f"Reportes financieros para {today}: "
            f"{', '.join(schedule.frequency for schedule in schedules)}; "
            f"{len(schedules) * 6 * len(recipients)} envío(s) a "
            f"{len(recipients)} destinatario(s) interno(s)."
        )
        for report_name in REPORT_NAMES:
            for schedule in schedules:
                print(
                    f"{report_name} {schedule.frequency}: "
                    f"{schedule.period.date_from} a {schedule.period.date_to}"
                )
        return 0

    database_url = (
        PREVIEW_DATABASE_URL
        if args.preview
        else (args.database_url or os.getenv("DATABASE_URL", "")).strip()
    )
    if not database_url:
        print(
            "Error: configura DATABASE_URL o usa --preview para la base de vista previa.",
            file=sys.stderr,
        )
        return 2

    if args.preview:
        os.environ["PREVIEW_MODE"] = "1"
    engine = create_engine(database_url)
    try:
        if args.preview:
            _load_all_models()
            SQLModel.metadata.create_all(engine)
            from preview_patch import ensure_scheduled_report_delivery_columns

            with sqlite3.connect("gym_preview.db") as preview_connection:
                ensure_scheduled_report_delivery_columns(preview_connection)
                preview_connection.commit()
            print(f"Base de vista previa: {PREVIEW_DATABASE_URL}")
        with Session(engine) as configuration_session:
            recipients, reports_by_recipient = get_scheduled_report_subscriptions(
                configuration_session
            )
        result = send_due_reports(
            engine,
            recipients=recipients,
            reports_by_recipient=reports_by_recipient,
            today=today,
            retry_exhausted=args.retry_exhausted,
        )
    except ScheduledReportConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except SQLAlchemyError as error:
        print(
            f"Error al generar o registrar reportes financieros: {error}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    print(
        f"Reportes financieros: {result.attempted} intento(s), "
        f"{result.sent} enviado(s), {result.simulated} simulado(s), "
        f"{result.failed} fallido(s), {result.skipped} omitido(s)."
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
