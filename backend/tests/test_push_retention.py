"""Retention for the member push receipts and finished deliveries.

Expo's answer about a sent push is kept for a configurable number of days, and a
terminal delivery for a longer one; neither the pending queue nor a delivery that
a receipt still points at is ever touched.
"""

import importlib.util
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.memberships.models import Member
from app.modules.notifications.models import (
    MemberPushDelivery,
    MemberPushDeliveryReceipt,
)
from app.modules.notifications.push import register_member_push_token
from app.modules.notifications.push_retention import (
    DEFAULT_DELIVERY_RETENTION_DAYS,
    DEFAULT_RECEIPT_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    purge_push_data,
    push_retention_policy_from_env,
)
from app.modules.notifications.service import create_notification

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)
PURGE = Path(__file__).resolve().parents[1] / "purge_push_data.py"

spec = importlib.util.spec_from_file_location("purge_push_data", PURGE)
purge_push_data_script = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(purge_push_data_script)


@pytest.fixture(autouse=True)
def _clear_retention_env(monkeypatch) -> Iterator[None]:
    monkeypatch.delenv("PUSH_RECEIPT_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("PUSH_DELIVERY_RETENTION_DAYS", raising=False)
    yield


def _member(session: Session) -> Member:
    member = Member(
        first_name="Ana",
        last_name="Demo",
        email=f"ana-{uuid4().hex[:8]}@example.test",
        status="active",
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def _delivery(
    session: Session,
    *,
    token: str,
    status: str = "sent",
    created_days_ago: int = 1,
) -> MemberPushDelivery:
    member = _member(session)
    register_member_push_token(session, member.id, token=token, platform="android", now=NOW)
    notice = create_notification(
        session,
        member_id=member.id,
        kind="class_reserved",
        title="Reserva confirmada",
        body="Tienes lugar en Spinning 6am.",
        now=NOW,
    )
    session.commit()
    delivery = session.exec(
        select(MemberPushDelivery).where(
            MemberPushDelivery.notification_id == notice.id,
            MemberPushDelivery.token == token,
        )
    ).one()
    delivery.status = status
    delivery.created_at = NOW - timedelta(days=created_days_ago)
    if status != "pending":
        delivery.attempts = 1
        delivery.sent_at = delivery.created_at
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


def _receipt(
    session: Session,
    delivery: MemberPushDelivery,
    *,
    received_days_ago: int,
) -> MemberPushDeliveryReceipt:
    receipt = MemberPushDeliveryReceipt(
        delivery_id=delivery.id,
        ticket_id=f"tkt-{uuid4().hex}",
        status="ok",
        received_at=NOW - timedelta(days=received_days_ago),
    )
    session.add(receipt)
    session.commit()
    return receipt


def _receipt_ids(session: Session) -> set[UUID]:
    return set(session.exec(select(MemberPushDeliveryReceipt.id)).all())


def _delivery_ids(session: Session) -> set[UUID]:
    return set(session.exec(select(MemberPushDelivery.id)).all())


def _seed_receipts(session: Session) -> dict[str, UUID]:
    rows = {}
    for name, days in (
        ("ancient", 400),
        ("old", DEFAULT_RECEIPT_RETENTION_DAYS + 1),
        ("mid", 60),
        ("edge", DEFAULT_RECEIPT_RETENTION_DAYS - 1),
        ("fresh", 1),
    ):
        delivery = _delivery(session, token=f"ExponentPushToken[{name}]")
        rows[name] = _receipt(session, delivery, received_days_ago=days).id
    return rows


def test_purge_removes_only_receipts_past_the_default_retention(
    session: Session,
) -> None:
    ids = _seed_receipts(session)

    result = purge_push_data(session, now=NOW)

    assert result.receipt_days == DEFAULT_RECEIPT_RETENTION_DAYS
    assert result.receipt_cutoff == NOW - timedelta(
        days=DEFAULT_RECEIPT_RETENTION_DAYS
    )
    assert result.receipts_deleted == 2
    assert result.deliveries_deleted == 0
    assert result.dry_run is False
    assert _receipt_ids(session) == {ids["mid"], ids["edge"], ids["fresh"]}


def test_finished_deliveries_are_removed_past_their_window(session: Session) -> None:
    old_sent = _delivery(
        session,
        token="ExponentPushToken[old-sent]",
        created_days_ago=DEFAULT_DELIVERY_RETENTION_DAYS + 1,
    )
    old_simulated = _delivery(
        session,
        token="ExponentPushToken[old-simulated]",
        status="simulated",
        created_days_ago=DEFAULT_DELIVERY_RETENTION_DAYS + 1,
    )
    old_failed = _delivery(
        session,
        token="ExponentPushToken[old-failed]",
        status="failed",
        created_days_ago=DEFAULT_DELIVERY_RETENTION_DAYS + 1,
    )
    young = _delivery(
        session,
        token="ExponentPushToken[young]",
        created_days_ago=DEFAULT_DELIVERY_RETENTION_DAYS - 1,
    )

    result = purge_push_data(session, now=NOW)

    assert result.delivery_days == DEFAULT_DELIVERY_RETENTION_DAYS
    assert result.deliveries_deleted == 3
    assert _delivery_ids(session) == {young.id}
    assert {old_sent.id, old_simulated.id, old_failed.id}.isdisjoint(
        _delivery_ids(session)
    )


def test_pending_deliveries_are_never_touched(session: Session) -> None:
    pending = _delivery(
        session,
        token="ExponentPushToken[pending]",
        status="pending",
        created_days_ago=MAX_RETENTION_DAYS,
    )

    result = purge_push_data(session, now=NOW)

    assert result.deliveries_deleted == 0
    assert _delivery_ids(session) == {pending.id}


def test_a_delivery_with_a_live_receipt_is_kept(session: Session) -> None:
    delivery = _delivery(
        session,
        token="ExponentPushToken[late-answer]",
        created_days_ago=DEFAULT_DELIVERY_RETENTION_DAYS + 10,
    )
    receipt = _receipt(session, delivery, received_days_ago=1)

    result = purge_push_data(session, now=NOW)

    assert result.receipts_deleted == 0
    assert result.deliveries_deleted == 0
    assert _receipt_ids(session) == {receipt.id}
    assert _delivery_ids(session) == {delivery.id}


def test_both_windows_honour_their_own_flag(session: Session) -> None:
    delivery = _delivery(
        session,
        token="ExponentPushToken[custom]",
        created_days_ago=60,
    )
    _receipt(session, delivery, received_days_ago=45)

    result = purge_push_data(
        session, now=NOW, receipt_days=30, delivery_days=90
    )

    assert result.receipt_days == 30
    assert result.delivery_days == 90
    assert result.receipts_deleted == 1
    assert result.deliveries_deleted == 0
    assert _receipt_ids(session) == set()
    assert _delivery_ids(session) == {delivery.id}


def test_purge_is_idempotent(session: Session) -> None:
    _seed_receipts(session)

    purge_push_data(session, now=NOW)
    second = purge_push_data(session, now=NOW)

    assert second.receipts_deleted == 0
    assert second.deliveries_deleted == 0


def test_dry_run_counts_without_deleting(session: Session) -> None:
    ids = _seed_receipts(session)
    old = _delivery(
        session,
        token="ExponentPushToken[old]",
        created_days_ago=DEFAULT_DELIVERY_RETENTION_DAYS + 1,
    )
    before = _delivery_ids(session)

    result = purge_push_data(session, now=NOW, dry_run=True)

    assert result.dry_run is True
    assert result.receipts_deleted == 2
    assert result.deliveries_deleted == 1
    assert _receipt_ids(session) == set(ids.values())
    assert _delivery_ids(session) == before
    assert old.id in before


@pytest.mark.parametrize("value", [0, -1, MAX_RETENTION_DAYS + 1])
def test_each_window_is_validated(session: Session, value: int) -> None:
    with pytest.raises(ValueError):
        purge_push_data(session, now=NOW, receipt_days=value)
    with pytest.raises(ValueError):
        purge_push_data(session, now=NOW, delivery_days=value)


def test_environment_policy_is_read_and_validated(monkeypatch) -> None:
    policy = push_retention_policy_from_env()
    assert policy.receipt_days == DEFAULT_RECEIPT_RETENTION_DAYS
    assert policy.delivery_days == DEFAULT_DELIVERY_RETENTION_DAYS

    monkeypatch.setenv("PUSH_RECEIPT_RETENTION_DAYS", "30")
    monkeypatch.setenv("PUSH_DELIVERY_RETENTION_DAYS", "730")
    policy = push_retention_policy_from_env()
    assert policy.receipt_days == 30
    assert policy.delivery_days == 730

    monkeypatch.setenv("PUSH_RECEIPT_RETENTION_DAYS", "cero")
    with pytest.raises(ValueError):
        push_retention_policy_from_env()

    monkeypatch.setenv("PUSH_RECEIPT_RETENTION_DAYS", "90")
    monkeypatch.setenv("PUSH_DELIVERY_RETENTION_DAYS", str(MAX_RETENTION_DAYS + 1))
    with pytest.raises(ValueError):
        push_retention_policy_from_env()


def _seed_database_file(db_path: Path) -> dict[str, UUID]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            with_receipt = _delivery(
                session,
                token="ExponentPushToken[file-receipt]",
                created_days_ago=100,
            )
            old_receipt = _receipt(session, with_receipt, received_days_ago=95)
            old_delivery = _delivery(
                session,
                token="ExponentPushToken[file-old]",
                created_days_ago=DEFAULT_DELIVERY_RETENTION_DAYS + 5,
            )
            fresh_delivery = _delivery(
                session,
                token="ExponentPushToken[file-fresh]",
                created_days_ago=5,
            )
            return {
                "delivery_with_receipt": with_receipt.id,
                "old_receipt": old_receipt.id,
                "old_delivery": old_delivery.id,
                "fresh_delivery": fresh_delivery.id,
            }
    finally:
        engine.dispose()


def _rows(db_path: Path) -> tuple[set[UUID], set[UUID]]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with Session(engine) as session:
            return _receipt_ids(session), _delivery_ids(session)
    finally:
        engine.dispose()


def test_script_purges_a_database_file(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "push.db"
    ids = _seed_database_file(db_path)

    code = purge_push_data_script.main(
        ["--database-url", f"sqlite:///{db_path.as_posix()}"]
    )

    assert code == 0
    output = capsys.readouterr().out
    assert f"Acuses recibidos antes de" in output
    assert ": 1" in output
    assert f"Entregas terminadas creadas antes de" in output
    receipts, deliveries = _rows(db_path)
    assert ids["old_receipt"] not in receipts
    assert receipts == set()
    assert ids["old_delivery"] not in deliveries
    assert deliveries == {ids["delivery_with_receipt"], ids["fresh_delivery"]}


def test_script_preview_reports_an_empty_database(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)

    code = purge_push_data_script.main(["--preview"])

    assert code == 0
    output = capsys.readouterr().out
    assert "gym_preview.db" in output
    assert ": 0" in output


def test_script_rejects_preview_and_database_url_together() -> None:
    with pytest.raises(SystemExit) as error:
        purge_push_data_script.main(
            ["--preview", "--database-url", "sqlite:///other.db"]
        )

    assert error.value.code == 2


def test_script_exits_with_two_without_database_url(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = purge_push_data_script.main([])

    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_script_rejects_an_invalid_window(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    code = purge_push_data_script.main(["--preview", "--receipt-days", "0"])

    assert code == 2
    assert "PUSH_RECEIPT_RETENTION_DAYS" in capsys.readouterr().err


def test_script_exits_with_one_on_an_unreachable_database(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)

    code = purge_push_data_script.main(
        ["--database-url", "sqlite:///missing-dir/push.db"]
    )

    assert code == 1
    assert "Error al purgar el push" in capsys.readouterr().err
