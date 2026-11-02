from datetime import date, datetime, timedelta, timezone
import hashlib

from sqlmodel import Session, select

from app.mailer import MailDeliveryFailed
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.reports.models import REPORT_NAMES, ScheduledReportDelivery
from app.modules.reports.scheduled import (
    ScheduledReportConfigurationError,
    configured_recipients,
    report_schedules,
    send_due_reports,
)
from app.modules.reports.scheduled_configuration import (
    get_scheduled_report_subscriptions,
    save_scheduled_report_configuration,
)


def test_recipients_require_an_internal_domain_allow_list() -> None:
    recipients = configured_recipients(
        recipients_value="finance@gym.example, finance@gym.example, owner@gym.example",
        domains_value="gym.example",
    )
    assert recipients == ("finance@gym.example", "owner@gym.example")


def test_recipient_outside_allow_list_is_rejected() -> None:
    try:
        configured_recipients(
            recipients_value="member@external.example",
            domains_value="gym.example",
        )
    except ScheduledReportConfigurationError as error:
        assert "dominios internos" in str(error)
    else:
        raise AssertionError("An external report recipient must be rejected.")


def test_missing_recipients_and_invalid_allow_list_are_rejected() -> None:
    for recipients, domains in (("", "gym.example"), ("finance@gym.example", "@gym.example")):
        try:
            configured_recipients(
                recipients_value=recipients,
                domains_value=domains,
            )
        except ScheduledReportConfigurationError:
            continue
        raise AssertionError("Invalid scheduled-report configuration must be rejected.")


def test_daily_weekly_and_monthly_periods_are_complete() -> None:
    monday = report_schedules(today=date(2026, 11, 2))
    assert [(item.frequency, item.period.date_from, item.period.date_to) for item in monday] == [
        ("daily", date(2026, 11, 1), date(2026, 11, 1)),
        ("weekly", date(2026, 10, 26), date(2026, 11, 1)),
    ]

    month_start = report_schedules(today=date(2026, 12, 1))
    assert [
        (item.frequency, item.period.date_from, item.period.date_to)
        for item in month_start
    ] == [
        ("daily", date(2026, 11, 30), date(2026, 11, 30)),
        ("monthly", date(2026, 11, 1), date(2026, 11, 30)),
    ]


def test_due_daily_weekly_and_monthly_reports_are_sent(
    session: Session, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.modules.reports.scheduled.send_email",
        lambda **kwargs: calls.append(kwargs) or "sent",
    )

    result = send_due_reports(
        session.get_bind(),
        recipients=("finance@gym.example",),
        today=date(2027, 2, 1),
    )

    assert (result.attempted, result.sent) == (18, 18)
    filenames = {
        call["attachments"][0].filename
        for call in calls
    }
    assert len(filenames) == 18
    filename_labels = {
        "overview": "resumen",
        "revenue": "ingresos",
        "memberships": "socios",
        "operations": "operacion",
        "maintenance": "mantenimiento",
        "inventory": "inventario",
    }
    for label in filename_labels.values():
        assert sum(filename.startswith(f"{label}-") for filename in filenames) == 3
    assert "ingresos-daily-2027-01-31-2027-01-31.csv" in filenames
    assert "resumen-weekly-2027-01-25-2027-01-31.csv" in filenames
    assert "inventario-monthly-2027-01-01-2027-01-31.csv" in filenames


def test_due_reports_respect_recipient_report_selection(session: Session, monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.modules.reports.scheduled.send_email",
        lambda **kwargs: calls.append(kwargs) or "sent",
    )
    engine = session.get_bind()
    options = {
        "finance@gym.example": ("revenue",),
        "owner@gym.example": ("overview", "inventory"),
    }

    sent = send_due_reports(
        engine,
        recipients=tuple(options),
        reports_by_recipient=options,
        today=date(2027, 2, 2),
    )

    assert (sent.attempted, sent.sent) == (3, 3)
    assert {
        (call["recipient"], call["subject"].split()[2])
        for call in calls
    } == {
        ("finance@gym.example", "ingresos"),
        ("owner@gym.example", "resumen"),
        ("owner@gym.example", "inventario"),
    }
    repeated = send_due_reports(
        engine,
        recipients=tuple(options),
        reports_by_recipient=options,
        today=date(2027, 2, 2),
    )
    assert (repeated.attempted, repeated.skipped) == (0, 3)
    assert len(calls) == 3


def test_cron_reads_saved_subscriptions_and_rechecks_domain_allowlist(
    session: Session, monkeypatch
) -> None:
    monkeypatch.setenv("INCOME_REPORT_RECIPIENTS", "fallback@gym.example")
    monkeypatch.setenv("INCOME_REPORT_ALLOWED_DOMAINS", "gym.example")
    ensure_default_access_control(session)
    owner = register_user(
        session,
        email="owner@gym.example",
        password="owner-strong-password",
        role_codes=("owner",),
    )
    saved = save_scheduled_report_configuration(
        session,
        recipients=[
            ("finance@gym.example", ("revenue", "inventory")),
            ("OPS@gym.example", ("operations",)),
        ],
        actor_id=owner.id,
    )
    assert saved.source == "panel"
    recipients, subscriptions = get_scheduled_report_subscriptions(session)
    assert recipients == ("finance@gym.example", "ops@gym.example")
    assert subscriptions == {
        "finance@gym.example": ("revenue", "inventory"),
        "ops@gym.example": ("operations",),
    }

    monkeypatch.setenv("INCOME_REPORT_ALLOWED_DOMAINS", "other.example")
    try:
        get_scheduled_report_subscriptions(session)
    except ScheduledReportConfigurationError as error:
        assert "fuera de los dominios" in str(error)
    else:
        raise AssertionError("A changed allow-list must prevent sending to saved addresses.")


def test_income_csv_is_sent_once_per_period_and_recipient(
    session: Session, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_send_email(**kwargs: object) -> str:
        calls.append(kwargs)
        return "sent"

    monkeypatch.setattr(
        "app.modules.reports.scheduled.send_email", fake_send_email
    )
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    engine = session.get_bind()

    sent = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now,
        today=date(2026, 11, 3),
    )

    assert (sent.attempted, sent.sent, sent.failed) == (6, 6, 0)
    assert len(calls) == 6
    revenue_call = next(
        call for call in calls if call["subject"].startswith("Reporte de ingresos")
    )
    attachment = revenue_call["attachments"][0]
    csv_content = attachment.content.decode("utf-8-sig")
    assert attachment.filename == "ingresos-daily-2026-11-02-2026-11-02.csv"
    assert "Mostrador (MXN)" in csv_content
    assert revenue_call["recipient"] == "finance@gym.example"
    assert "no un cierre contable" in revenue_call["body"]

    repeated = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now + timedelta(minutes=1),
        today=date(2026, 11, 3),
    )
    assert (repeated.attempted, repeated.skipped) == (0, 6)
    assert len(calls) == 6

    rows = session.exec(select(ScheduledReportDelivery)).all()
    assert len(rows) == 6
    assert {row.report_name for row in rows} == set(REPORT_NAMES)
    revenue_row = next(row for row in rows if row.report_name == "revenue")
    assert revenue_row.frequency == "daily"
    assert revenue_row.date_from == date(2026, 11, 2)
    assert revenue_row.date_to == date(2026, 11, 2)
    assert revenue_row.status == "sent"
    assert revenue_row.recipient_hash
    expected_recipient_hash = hashlib.sha256(
        b"finance@gym.example"
    ).hexdigest()
    legacy_source = (
        f"revenue:daily:2026-11-02:2026-11-02:{expected_recipient_hash}"
    )
    assert revenue_row.idempotency_key == hashlib.sha256(
        legacy_source.encode("utf-8")
    ).hexdigest()


def test_failed_report_delivery_can_be_retried_without_duplicate_success(
    session: Session, monkeypatch
) -> None:
    attempts = 0

    def fail_then_send(**kwargs: object) -> str:
        nonlocal attempts
        if kwargs["subject"] == "Reporte de ingresos diario (2026-11-02 a 2026-11-02)":
            attempts += 1
            if attempts == 1:
                raise MailDeliveryFailed("SMTP temporalmente no disponible.")
        return "sent"

    monkeypatch.setattr(
        "app.modules.reports.scheduled.send_email", fail_then_send
    )
    engine = session.get_bind()
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

    failed = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now,
        today=date(2026, 11, 3),
    )
    retried = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now + timedelta(minutes=1),
        today=date(2026, 11, 3),
    )

    assert failed.failed == 1
    assert retried.sent == 1
    assert attempts == 2
    row = session.exec(
        select(ScheduledReportDelivery).where(
            ScheduledReportDelivery.report_name == "revenue"
        )
    ).one()
    assert row.attempts == 2
    assert row.status == "sent"
    assert row.error is None


def test_stale_sending_delivery_is_reclaimed(session: Session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.reports.scheduled.send_email",
        lambda **_: "sent",
    )
    engine = session.get_bind()
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    initial = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now,
        today=date(2026, 11, 3),
    )
    assert initial.sent == 6
    row = session.exec(
        select(ScheduledReportDelivery).where(
            ScheduledReportDelivery.report_name == "revenue"
        )
    ).one()
    row.status = "sending"
    row.sent_at = None
    row.claimed_at = now - timedelta(hours=1)
    session.add(row)
    session.commit()

    recovered = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now,
        today=date(2026, 11, 3),
    )

    session.refresh(row)
    assert recovered.sent == 1
    assert recovered.skipped == 5
    assert row.attempts == 2
    assert row.status == "sent"


def test_exhausted_delivery_requires_explicit_retry(session: Session, monkeypatch) -> None:
    attempts = 0

    def fail_five_times_then_send(**kwargs: object) -> str:
        nonlocal attempts
        if kwargs["subject"] == "Reporte de ingresos diario (2026-11-02 a 2026-11-02)":
            attempts += 1
            if attempts <= 5:
                raise MailDeliveryFailed("SMTP temporalmente no disponible.")
        return "sent"

    monkeypatch.setattr(
        "app.modules.reports.scheduled.send_email", fail_five_times_then_send
    )
    engine = session.get_bind()
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    for retry in range(5):
        result = send_due_reports(
            engine,
            recipients=("finance@gym.example",),
            now=now + timedelta(minutes=retry),
            today=date(2026, 11, 3),
        )
        assert result.failed == 1

    skipped = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now + timedelta(minutes=6),
        today=date(2026, 11, 3),
    )
    assert skipped.attempted == 0
    assert skipped.skipped == 6

    retried = send_due_reports(
        engine,
        recipients=("finance@gym.example",),
        now=now + timedelta(minutes=7),
        today=date(2026, 11, 3),
        retry_exhausted=True,
    )

    row = session.exec(
        select(ScheduledReportDelivery).where(
            ScheduledReportDelivery.report_name == "revenue"
        )
    ).one()
    assert retried.sent == 1
    assert attempts == 6
    assert row.attempts == 6
    assert row.status == "sent"
