"""Panel-managed recipients for scheduled financial reports."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Iterable
from uuid import UUID

from sqlmodel import Session, select

from app.modules.identity.models import AppUser
from app.modules.reports.models import (
    REPORT_NAMES,
    ScheduledReportConfiguration,
    ScheduledReportConfigurationEvent,
    ScheduledReportRecipient,
)
from app.modules.reports.scheduled import (
    DEFAULT_RECIPIENT_LIMIT,
    REPORT_RECIPIENTS_ENV,
    ScheduledReportConfigurationError,
    configured_allowed_domains,
    configured_recipients,
)

# One boolean column per report name, so a seventh report is a new column plus
# the tuple entry — never a fourth copy of the list.
_REPORT_FIELDS = {report_name: f"{report_name}_enabled" for report_name in REPORT_NAMES}


@dataclass(frozen=True)
class ReportRecipientSetting:
    email: str
    reports: tuple[str, ...]
    allowed: bool = True


@dataclass(frozen=True)
class ScheduledReportConfigurationView:
    source: str
    allowed_domains: tuple[str, ...]
    recipients: tuple[ReportRecipientSetting, ...]
    updated_at: datetime | None


@dataclass(frozen=True)
class ScheduledReportConfigurationAudit:
    changed_at: datetime
    actor_email: str | None
    previous_recipient_count: int
    recipient_count: int
    previous_report_counts: dict[str, int]
    report_counts: dict[str, int]


def _reports_for_row(row: ScheduledReportRecipient) -> tuple[str, ...]:
    return tuple(
        report_name
        for report_name, field_name in _REPORT_FIELDS.items()
        if getattr(row, field_name)
    )


def _snapshot(recipients: Iterable[ReportRecipientSetting]) -> str:
    items = [
        {
            "recipient_hash": hashlib.sha256(
                item.email.casefold().encode("utf-8")
            ).hexdigest(),
            "reports": sorted(item.reports),
        }
        for item in recipients
    ]
    return json.dumps(
        sorted(items, key=lambda item: item["recipient_hash"]),
        separators=(",", ":"),
        sort_keys=True,
    )


def _settings_rows(session: Session) -> list[ScheduledReportRecipient]:
    return session.exec(
        select(ScheduledReportRecipient).order_by(
            ScheduledReportRecipient.email_key
        )
    ).all()


def _environment_configuration(
    allowed_domains: tuple[str, ...],
) -> tuple[ReportRecipientSetting, ...]:
    if not os.getenv(REPORT_RECIPIENTS_ENV, "").strip():
        return ()
    recipients = configured_recipients(domains_value=",".join(allowed_domains))
    return tuple(
        ReportRecipientSetting(email, tuple(REPORT_NAMES))
        for email in recipients
    )


def _validate_address(
    email: str, allowed_domains: tuple[str, ...]
) -> str:
    return configured_recipients(
        recipients_value=email,
        domains_value=",".join(allowed_domains),
        limit=1,
    )[0]


def get_scheduled_report_configuration(
    session: Session,
) -> ScheduledReportConfigurationView:
    allowed_domains = configured_allowed_domains()
    configuration = session.get(ScheduledReportConfiguration, 1)
    if configuration is None:
        return ScheduledReportConfigurationView(
            source="environment",
            allowed_domains=allowed_domains,
            recipients=_environment_configuration(allowed_domains),
            updated_at=None,
        )

    recipients = tuple(
        ReportRecipientSetting(
            email=row.email,
            reports=_reports_for_row(row),
            allowed=_is_allowed(row.email, allowed_domains),
        )
        for row in _settings_rows(session)
    )
    return ScheduledReportConfigurationView(
        source="panel",
        allowed_domains=allowed_domains,
        recipients=recipients,
        updated_at=configuration.updated_at,
    )


def get_scheduled_report_subscriptions(
    session: Session,
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Resolve the live configuration and re-check its domain allow-list."""

    view = get_scheduled_report_configuration(session)
    if view.source == "environment":
        if not view.recipients:
            raise ScheduledReportConfigurationError(
                f"Configura {REPORT_RECIPIENTS_ENV} o guarda destinatarios desde el panel."
            )
        return (
            tuple(item.email for item in view.recipients),
            {
                item.email: item.reports
                for item in view.recipients
            },
        )
    invalid = [item.email for item in view.recipients if not item.allowed]
    if invalid:
        raise ScheduledReportConfigurationError(
            "Hay destinatarios guardados fuera de los dominios internos permitidos; "
            "corrige la configuración desde el panel."
        )
    if len(view.recipients) > DEFAULT_RECIPIENT_LIMIT:
        raise ScheduledReportConfigurationError(
            f"La configuración guardada supera el límite de {DEFAULT_RECIPIENT_LIMIT} destinatarios."
        )
    recipients = tuple(item.email for item in view.recipients)
    return (
        recipients,
        {item.email: item.reports for item in view.recipients},
    )


def _is_allowed(email: str, allowed_domains: tuple[str, ...]) -> bool:
    try:
        _validate_address(email, allowed_domains)
    except ScheduledReportConfigurationError:
        return False
    return True


def save_scheduled_report_configuration(
    session: Session,
    *,
    recipients: list[tuple[str, tuple[str, ...]]],
    actor_id: UUID,
) -> ScheduledReportConfigurationView:
    allowed_domains = configured_allowed_domains()
    if len(recipients) > DEFAULT_RECIPIENT_LIMIT:
        raise ValueError(
            f"Se admiten como máximo {DEFAULT_RECIPIENT_LIMIT} destinatarios."
        )

    normalized: list[ReportRecipientSetting] = []
    seen: set[str] = set()
    for email, report_names in recipients:
        address = _validate_address(email, allowed_domains).casefold()
        key = address
        if key in seen:
            raise ValueError("No se permiten destinatarios duplicados.")
        seen.add(key)
        if len(set(report_names)) != len(report_names) or any(
            report_name not in REPORT_NAMES for report_name in report_names
        ):
            raise ValueError("La selección contiene un reporte inválido o repetido.")
        normalized.append(
            ReportRecipientSetting(
                email=address,
                reports=tuple(sorted(report_names)),
            )
        )

    configuration = session.exec(
        select(ScheduledReportConfiguration)
        .where(ScheduledReportConfiguration.id == 1)
        .with_for_update()
    ).first()
    if configuration is None:
        previous = _environment_configuration(allowed_domains)
        configuration = ScheduledReportConfiguration(
            id=1,
            updated_by=actor_id,
        )
        session.add(configuration)
        session.flush()
        is_first_save = True
    else:
        previous = tuple(
            ReportRecipientSetting(
                email=row.email,
                reports=_reports_for_row(row),
            )
            for row in _settings_rows(session)
        )
        is_first_save = False

    previous_snapshot = _snapshot(previous)
    next_snapshot = _snapshot(normalized)
    rows_by_key = {
        row.email_key: row
        for row in _settings_rows(session)
    }
    next_keys = {item.email.casefold() for item in normalized}
    for key, row in rows_by_key.items():
        if key not in next_keys:
            session.delete(row)

    for item in normalized:
        key = item.email.casefold()
        row = rows_by_key.get(key)
        if row is None:
            row = ScheduledReportRecipient(email=item.email, email_key=key)
        for report_name, field_name in _REPORT_FIELDS.items():
            setattr(row, field_name, report_name in item.reports)
        session.add(row)

    changed = is_first_save or previous_snapshot != next_snapshot
    if changed:
        now = datetime.now(timezone.utc)
        configuration.updated_by = actor_id
        configuration.updated_at = now
        session.add(
            ScheduledReportConfigurationEvent(
                actor_id=actor_id,
                previous_snapshot=previous_snapshot,
                next_snapshot=next_snapshot,
                changed_at=now,
            )
        )
    session.add(configuration)
    session.commit()
    return get_scheduled_report_configuration(session)


def list_scheduled_report_configuration_events(
    session: Session, *, limit: int = 20
) -> list[ScheduledReportConfigurationAudit]:
    rows = session.exec(
        select(ScheduledReportConfigurationEvent, AppUser)
        .join(
            AppUser,
            ScheduledReportConfigurationEvent.actor_id == AppUser.id,
            isouter=True,
        )
        .order_by(
            ScheduledReportConfigurationEvent.changed_at.desc(),
            ScheduledReportConfigurationEvent.id.desc(),
        )
        .limit(max(1, min(limit, 100)))
    ).all()
    result: list[ScheduledReportConfigurationAudit] = []
    for event, actor in rows:
        previous = json.loads(event.previous_snapshot)
        current = json.loads(event.next_snapshot)
        previous_counts = Counter(
            report_name
            for item in previous
            for report_name in item["reports"]
        )
        current_counts = Counter(
            report_name
            for item in current
            for report_name in item["reports"]
        )
        result.append(
            ScheduledReportConfigurationAudit(
                changed_at=event.changed_at,
                actor_email=actor.email if actor else None,
                previous_recipient_count=len(previous),
                recipient_count=len(current),
                previous_report_counts={
                    report_name: previous_counts[report_name]
                    for report_name in REPORT_NAMES
                },
                report_counts={
                    report_name: current_counts[report_name]
                    for report_name in REPORT_NAMES
                },
            )
        )
    return result
