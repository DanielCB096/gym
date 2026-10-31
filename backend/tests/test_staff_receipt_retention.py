"""Retention for the provider receipts of the staff emails.

An acknowledgement is kept for a configurable number of days counted from the
moment the club stored it; the purge never touches a recent receipt, never
deletes a delivery, and refuses a retention shorter than the webhook's own
window.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications.models import (
    StaffNotificationDelivery,
    StaffNotificationDeliveryReceipt,
)
from app.modules.notifications.receipts import RECEIPT_MAX_AGE
from app.modules.notifications.retention import (
    DEFAULT_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    MIN_RETENTION_DAYS,
    purge_expired_receipts,
    receipt_retention_policy_from_env,
)
from app.modules.notifications.service import create_staff_notification
from app.modules.staffing import models as staffing_models  # noqa: F401

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)


def _delivery(session: Session) -> StaffNotificationDelivery:
    ensure_default_access_control(session)
    account = register_user(
        session,
        email=f"recepcion-{uuid4().hex[:8]}@example.test",
        password="strong-password-for-tests",
        role_codes=("reception",),
    )
    create_staff_notification(
        session,
        user_id=account.id,
        kind="attendance_corrected",
        title="Se corrigió tu marca",
        body="Recepción corrigió tu entrada de las 19:30 a las 19:15.",
        now=NOW,
    )
    session.commit()
    delivery = session.exec(select(StaffNotificationDelivery)).one()
    delivery.status = "sent"
    delivery.attempts = 1
    delivery.sent_at = NOW
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


def _receipt(
    session: Session,
    delivery: StaffNotificationDelivery,
    *,
    name: str,
    received_days_ago: int,
    occurred_days_ago: int | None = None,
) -> StaffNotificationDeliveryReceipt:
    receipt = StaffNotificationDeliveryReceipt(
        delivery_id=delivery.id,
        provider_event_id=f"evt-{name}-{uuid4().hex}",
        event_type="delivered",
        occurred_at=NOW - timedelta(
            days=received_days_ago if occurred_days_ago is None else occurred_days_ago
        ),
        received_at=NOW - timedelta(days=received_days_ago),
        detail="250 2.0.0 Ok",
    )
    session.add(receipt)
    session.commit()
    return receipt


def _seed(session: Session) -> dict[str, UUID]:
    delivery = _delivery(session)
    rows = {
        "ancient": _receipt(session, delivery, name="ancient", received_days_ago=400),
        "old": _receipt(
            session, delivery, name="old", received_days_ago=DEFAULT_RETENTION_DAYS + 1
        ),
        "mid": _receipt(session, delivery, name="mid", received_days_ago=60),
        "edge": _receipt(
            session, delivery, name="edge", received_days_ago=DEFAULT_RETENTION_DAYS - 1
        ),
        "fresh": _receipt(session, delivery, name="fresh", received_days_ago=1),
    }
    return {name: receipt.id for name, receipt in rows.items()}


def _remaining(session: Session) -> set[UUID]:
    return set(
        session.exec(select(StaffNotificationDeliveryReceipt.id)).all()
    )


def test_purge_removes_only_receipts_past_the_default_retention(
    session: Session,
) -> None:
    ids = _seed(session)

    result = purge_expired_receipts(session, now=NOW)

    assert result.retention_days == DEFAULT_RETENTION_DAYS
    assert result.cutoff == NOW - timedelta(days=DEFAULT_RETENTION_DAYS)
    assert result.receipts_deleted == 2
    assert result.dry_run is False
    assert _remaining(session) == {ids["mid"], ids["edge"], ids["fresh"]}


def test_the_purge_keeps_the_deliveries_and_the_inbox(session: Session) -> None:
    _seed(session)

    purge_expired_receipts(session, now=NOW)

    assert session.exec(select(StaffNotificationDelivery)).one() is not None


def test_purge_is_idempotent(session: Session) -> None:
    _seed(session)

    purge_expired_receipts(session, now=NOW)
    second = purge_expired_receipts(session, now=NOW)

    assert second.receipts_deleted == 0


def test_dry_run_counts_without_deleting(session: Session) -> None:
    ids = _seed(session)

    result = purge_expired_receipts(session, now=NOW, dry_run=True)

    assert result.dry_run is True
    assert result.receipts_deleted == 2
    assert _remaining(session) == set(ids.values())


def test_a_shorter_retention_reaches_more_receipts(session: Session) -> None:
    ids = _seed(session)

    result = purge_expired_receipts(session, now=NOW, retention_days=30)

    assert result.retention_days == 30
    assert result.receipts_deleted == 4
    assert _remaining(session) == {ids["fresh"]}


def test_a_longer_retention_keeps_more_receipts(session: Session) -> None:
    ids = _seed(session)

    result = purge_expired_receipts(session, now=NOW, retention_days=120)

    assert result.receipts_deleted == 1
    assert _remaining(session) == {
        ids["old"],
        ids["mid"],
        ids["edge"],
        ids["fresh"],
    }


def test_the_cutoff_uses_the_reception_date_not_the_provider_date(
    session: Session,
) -> None:
    delivery = _delivery(session)
    stale_report_just_stored = _receipt(
        session,
        delivery,
        name="stale-report",
        received_days_ago=1,
        occurred_days_ago=400,
    )
    fresh_report_stored_long_ago = _receipt(
        session,
        delivery,
        name="fresh-report",
        received_days_ago=DEFAULT_RETENTION_DAYS + 1,
        occurred_days_ago=1,
    )

    purge_expired_receipts(session, now=NOW)

    assert _remaining(session) == {stale_report_just_stored.id}
    assert fresh_report_stored_long_ago.id not in _remaining(session)


def test_the_minimum_retention_matches_the_webhook_window() -> None:
    assert MIN_RETENTION_DAYS == RECEIPT_MAX_AGE.days
    assert MIN_RETENTION_DAYS < DEFAULT_RETENTION_DAYS <= MAX_RETENTION_DAYS


@pytest.mark.parametrize(
    "value", [0, -1, MIN_RETENTION_DAYS - 1, MAX_RETENTION_DAYS + 1]
)
def test_retention_days_are_validated(session: Session, value: int) -> None:
    _seed(session)

    with pytest.raises(ValueError):
        purge_expired_receipts(session, now=NOW, retention_days=value)


def test_environment_policy_is_read_and_validated(monkeypatch) -> None:
    monkeypatch.delenv("STAFF_RECEIPT_RETENTION_DAYS", raising=False)
    policy = receipt_retention_policy_from_env()
    assert policy.retention_days == DEFAULT_RETENTION_DAYS

    monkeypatch.setenv("STAFF_RECEIPT_RETENTION_DAYS", "365")
    policy = receipt_retention_policy_from_env()
    assert policy.retention_days == 365

    monkeypatch.setenv("STAFF_RECEIPT_RETENTION_DAYS", "cero")
    with pytest.raises(ValueError):
        receipt_retention_policy_from_env()

    monkeypatch.setenv("STAFF_RECEIPT_RETENTION_DAYS", str(MIN_RETENTION_DAYS - 1))
    with pytest.raises(ValueError):
        receipt_retention_policy_from_env()

    monkeypatch.setenv("STAFF_RECEIPT_RETENTION_DAYS", str(MAX_RETENTION_DAYS + 1))
    with pytest.raises(ValueError):
        receipt_retention_policy_from_env()
