"""Scheduled, internal-only delivery of financial report CSVs."""

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr
import hashlib
import os
import re
from io import StringIO

from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.mailer import EmailAttachment, MailerError, send_email
from app.modules.reports.models import ScheduledReportDelivery
from app.modules.reports.service import (
    REPORT_NAMES,
    ReportPeriod,
    build_export,
    build_report,
    resolve_period,
)
from app.timezone import club_date

REPORT_RECIPIENTS_ENV = "INCOME_REPORT_RECIPIENTS"
REPORT_ALLOWED_DOMAINS_ENV = "INCOME_REPORT_ALLOWED_DOMAINS"
DEFAULT_RECIPIENT_LIMIT = 10
MAX_DELIVERY_ATTEMPTS = 5
STALE_CLAIM_AFTER = timedelta(minutes=30)
FREQUENCY_LABELS = {
    "daily": "diario",
    "weekly": "semanal",
    "monthly": "mensual",
}
REPORT_LABELS = {
    "overview": "resumen",
    "revenue": "ingresos",
    "memberships": "socios",
    "operations": "operación",
    "maintenance": "mantenimiento",
    "inventory": "inventario",
}
REPORT_FILENAME_LABELS = {
    "overview": "resumen",
    "revenue": "ingresos",
    "memberships": "socios",
    "operations": "operacion",
    "maintenance": "mantenimiento",
    "inventory": "inventario",
}
_EMAIL_PATTERN = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")
_DOMAIN_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


class ScheduledReportConfigurationError(ValueError):
    """Scheduled-report recipients are missing or unsafe."""


@dataclass(frozen=True)
class ReportSchedule:
    frequency: str
    period: ReportPeriod


@dataclass(frozen=True)
class ScheduledReportPass:
    attempted: int
    sent: int
    simulated: int
    failed: int
    skipped: int


def _normalise_now(now: datetime | None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def configured_recipients(
    *,
    recipients_value: str | None = None,
    domains_value: str | None = None,
    limit: int = DEFAULT_RECIPIENT_LIMIT,
) -> tuple[str, ...]:
    """Load explicitly configured recipients and enforce an internal domain allow-list."""

    raw_recipients = (
        os.getenv(REPORT_RECIPIENTS_ENV, "")
        if recipients_value is None
        else recipients_value
    )
    raw_domains = (
        os.getenv(REPORT_ALLOWED_DOMAINS_ENV, "")
        if domains_value is None
        else domains_value
    )
    domains = set(configured_allowed_domains(domains_value=raw_domains))

    recipients: dict[str, str] = {}
    for candidate in raw_recipients.split(","):
        address = candidate.strip()
        if not address:
            continue
        parsed_name, parsed_address = parseaddr(address)
        if parsed_name or parsed_address != address or not _EMAIL_PATTERN.fullmatch(address):
            raise ScheduledReportConfigurationError(
                f"Hay una dirección inválida en {REPORT_RECIPIENTS_ENV}."
            )
        local_part, domain = address.rsplit("@", 1)
        if domain.lower() not in domains:
            raise ScheduledReportConfigurationError(
                f"Un destinatario de {REPORT_RECIPIENTS_ENV} no pertenece a "
                f"los dominios internos permitidos."
            )
        recipients.setdefault(f"{local_part}@{domain.lower()}".casefold(), address)
    if not recipients:
        raise ScheduledReportConfigurationError(
            f"Configura al menos un destinatario interno en {REPORT_RECIPIENTS_ENV}."
        )
    if len(recipients) > limit:
        raise ScheduledReportConfigurationError(
            f"{REPORT_RECIPIENTS_ENV} admite como máximo {limit} destinatarios."
        )
    return tuple(recipients.values())


def configured_allowed_domains(
    *, domains_value: str | None = None
) -> tuple[str, ...]:
    """Return the validated environment allow-list used by panel and cron."""

    raw_domains = (
        os.getenv(REPORT_ALLOWED_DOMAINS_ENV, "")
        if domains_value is None
        else domains_value
    )
    domains = tuple(
        dict.fromkeys(
            domain.strip().lower()
            for domain in raw_domains.split(",")
            if domain.strip()
        )
    )
    if not domains or any(not _DOMAIN_PATTERN.fullmatch(domain) for domain in domains):
        raise ScheduledReportConfigurationError(
            f"Configura {REPORT_ALLOWED_DOMAINS_ENV} con dominios internos válidos."
        )
    return domains


def report_schedules(
    *,
    today: date,
    timezone_name: str | None = None,
) -> tuple[ReportSchedule, ...]:
    """Return due cadences, each covering only a completed local period."""

    schedules = [
        ReportSchedule(
            "daily",
            resolve_period(
                date_from=today - timedelta(days=1),
                date_to=today - timedelta(days=1),
                timezone_name=timezone_name,
            ),
        )
    ]
    if today.weekday() == 0:
        schedules.append(
            ReportSchedule(
                "weekly",
                resolve_period(
                    today=today - timedelta(days=1),
                    date_from=today - timedelta(days=7),
                    timezone_name=timezone_name,
                ),
            )
        )
    if today.day == 1:
        previous_day = today - timedelta(days=1)
        schedules.append(
            ReportSchedule(
                "monthly",
                resolve_period(
                    today=previous_day,
                    date_from=previous_day.replace(day=1),
                    timezone_name=timezone_name,
                ),
            )
        )
    return tuple(schedules)


def _export_csv(report_name: str, period: ReportPeriod, session: Session) -> bytes:
    table = build_export(build_report(session, report_name, period), period)
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(table.headers)
    writer.writerows(table.rows)
    return buffer.getvalue().encode("utf-8-sig")


def _delivery_key(
    report_name: str, frequency: str, period: ReportPeriod, recipient: str
) -> tuple[str, str]:
    recipient_hash = hashlib.sha256(recipient.casefold().encode("utf-8")).hexdigest()
    source = (
        f"{report_name}:{frequency}:{period.date_from.isoformat()}:"
        f"{period.date_to.isoformat()}:{recipient_hash}"
    )
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return key, recipient_hash


def _claim_delivery(
    session: Session,
    *,
    report_name: str,
    frequency: str,
    period: ReportPeriod,
    recipient: str,
    now: datetime,
    retry_exhausted: bool = False,
) -> ScheduledReportDelivery | None:
    key, recipient_hash = _delivery_key(
        report_name, frequency, period, recipient
    )
    existing = session.exec(
        select(ScheduledReportDelivery).where(
            ScheduledReportDelivery.idempotency_key == key
        )
    ).first()
    if existing is None:
        existing = ScheduledReportDelivery(
            idempotency_key=key,
            report_name=report_name,
            frequency=frequency,
            date_from=period.date_from,
            date_to=period.date_to,
            recipient_hash=recipient_hash,
            status="sending",
            attempts=1,
            claimed_at=now,
        )
        session.add(existing)
        try:
            session.commit()
            session.refresh(existing)
            return existing
        except IntegrityError:
            session.rollback()
            existing = session.exec(
                select(ScheduledReportDelivery).where(
                    ScheduledReportDelivery.idempotency_key == key
                )
            ).first()
            if existing is None:
                raise

    if existing is None:
        raise RuntimeError("No se pudo recuperar el registro idempotente del reporte.")
    if existing.status in {"sent", "simulated"}:
        return None
    if (
        existing.status == "failed"
        and existing.attempts >= MAX_DELIVERY_ATTEMPTS
        and not retry_exhausted
    ):
        return None
    stale_before = now - STALE_CLAIM_AFTER
    claimable = (
        existing.status == "failed"
        or (
            existing.status == "sending"
            and _normalise_now(existing.claimed_at) <= stale_before
        )
    )
    if not claimable:
        return None
    result = session.exec(
        update(ScheduledReportDelivery)
        .where(
            ScheduledReportDelivery.id == existing.id,
            ScheduledReportDelivery.status == existing.status,
            ScheduledReportDelivery.claimed_at == existing.claimed_at,
        )
        .values(
            status="sending",
            attempts=ScheduledReportDelivery.attempts + 1,
            claimed_at=now,
            error=None,
        )
    )
    session.commit()
    if not result.rowcount:
        session.refresh(existing)
        return None
    session.refresh(existing)
    return existing


def _complete_delivery(
    session: Session,
    delivery: ScheduledReportDelivery,
    *,
    status: str,
    now: datetime,
    error: str | None = None,
) -> None:
    delivery.status = status
    delivery.error = error[:500] if error else None
    delivery.sent_at = now if status in {"sent", "simulated"} else None
    session.add(delivery)
    session.commit()


def send_due_reports(
    engine: Engine,
    *,
    recipients: tuple[str, ...],
    reports_by_recipient: dict[str, tuple[str, ...]] | None = None,
    now: datetime | None = None,
    today: date | None = None,
    retry_exhausted: bool = False,
) -> ScheduledReportPass:
    """Build and deliver due reports; database claims make retries idempotent."""

    occurred = _normalise_now(now)
    local_today = today or club_date(occurred)
    schedules = report_schedules(today=local_today)
    recipients_by_report = {
        report_name: (
            recipients
            if reports_by_recipient is None
            else tuple(
                recipient
                for recipient, report_names in reports_by_recipient.items()
                if report_name in report_names
            )
        )
        for report_name in REPORT_NAMES
    }
    recipient_by_hash = {
        hashlib.sha256(recipient.casefold().encode("utf-8")).hexdigest(): recipient
        for recipient in recipients
    }
    work: dict[
        tuple[str, str, date, date, str],
        tuple[str, ReportSchedule, str],
    ] = {}
    for report_name in REPORT_NAMES:
        for schedule in schedules:
            for recipient in recipients_by_report[report_name]:
                work[
                    (
                        report_name,
                        schedule.frequency,
                        schedule.period.date_from,
                        schedule.period.date_to,
                        recipient.casefold(),
                    )
                ] = (report_name, schedule, recipient)

    attempted = sent = simulated = failed = skipped = 0
    with Session(engine) as session:
        stale_before = occurred - STALE_CLAIM_AFTER
        retries = session.exec(
            select(ScheduledReportDelivery).where(
                (ScheduledReportDelivery.status == "failed")
                | (
                    (ScheduledReportDelivery.status == "sending")
                    & (ScheduledReportDelivery.claimed_at <= stale_before)
                )
            )
        ).all()
        for previous in retries:
            recipient = recipient_by_hash.get(previous.recipient_hash)
            if (
                recipient is None
                or previous.report_name not in recipients_by_report
                or recipient.casefold()
                not in {
                    item.casefold()
                    for item in recipients_by_report[previous.report_name]
                }
            ):
                continue
            if previous.attempts >= MAX_DELIVERY_ATTEMPTS and not retry_exhausted:
                continue
            period = resolve_period(previous.date_from, previous.date_to)
            schedule = ReportSchedule(previous.frequency, period)
            work.setdefault(
                (
                    previous.report_name,
                    schedule.frequency,
                    period.date_from,
                    period.date_to,
                    recipient.casefold(),
                ),
                (previous.report_name, schedule, recipient),
            )

        for report_name, schedule, recipient in work.values():
            content = _export_csv(report_name, schedule.period, session)
            start = schedule.period.date_from.isoformat()
            end = schedule.period.date_to.isoformat()
            attachment = EmailAttachment(
                content=content,
                filename=(
                    f"{REPORT_FILENAME_LABELS[report_name]}-{schedule.frequency}-"
                    f"{start}-{end}.csv"
                ),
                maintype="text",
                subtype="csv",
            )
            delivery = _claim_delivery(
                session,
                report_name=report_name,
                frequency=schedule.frequency,
                period=schedule.period,
                recipient=recipient,
                now=occurred,
                retry_exhausted=retry_exhausted,
            )
            if delivery is None:
                skipped += 1
                continue
            attempted += 1
            message_id = f"{delivery.idempotency_key}@reportes.centro-fit.local"
            try:
                outcome = send_email(
                    recipient=recipient,
                    subject=(
                        f"Reporte de {REPORT_LABELS[report_name]} "
                        f"{FREQUENCY_LABELS[schedule.frequency]} "
                        f"({start} a {end})"
                    ),
                    body=(
                        f"Adjuntamos el reporte de {REPORT_LABELS[report_name]} "
                        "solicitado para el periodo indicado. Es un reporte "
                        "operativo de consulta, no un cierre contable ni un "
                        "comprobante fiscal.\n"
                    ),
                    attachments=(attachment,),
                    message_id=message_id,
                    failure_label=f"No se pudo enviar el reporte de {REPORT_LABELS[report_name]}",
                )
            except MailerError as error:
                _complete_delivery(
                    session,
                    delivery,
                    status="failed",
                    now=occurred,
                    error=str(error),
                )
                failed += 1
                continue
            if outcome not in {"sent", "simulated"}:
                _complete_delivery(
                    session,
                    delivery,
                    status="failed",
                    now=occurred,
                    error=f"Resultado SMTP inesperado: {outcome}",
                )
                failed += 1
                continue
            _complete_delivery(session, delivery, status=outcome, now=occurred)
            if outcome == "sent":
                sent += 1
            else:
                simulated += 1
    return ScheduledReportPass(
        attempted=attempted,
        sent=sent,
        simulated=simulated,
        failed=failed,
        skipped=skipped,
    )
