from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.access.models import (
    AccessDirection,
    AccessReason,
    AccessRequest,
    AccessSnapshot,
    AccessWindow,
    DuplicateAccessEventConflict,
)
from app.modules.access.offline_store import SQLiteAccessStore
from app.modules.access.service import evaluate_access


MEMBER_ID = UUID("f39e7d56-47d8-499f-9895-38a6e32cb90e")
UTC = timezone.utc
NOW = datetime(2026, 10, 15, 17, 0, tzinfo=UTC)


def make_snapshot(**overrides: object) -> AccessSnapshot:
    values: dict[str, object] = {
        "member_id": MEMBER_ID,
        "membership_status": "active",
        "membership_starts_at": NOW - timedelta(days=1),
        "membership_ends_at": NOW + timedelta(days=30),
        "blocking_debt": False,
        "cached_at": NOW - timedelta(minutes=1),
        "valid_until": NOW + timedelta(minutes=10),
        "allowed_windows": None,
        "daily_entry_limit": None,
        "entries_today": 0,
        "antipassback_seconds": 60,
    }
    values.update(overrides)
    return AccessSnapshot(**values)  # type: ignore[arg-type]


def make_request(**overrides: object) -> AccessRequest:
    values: dict[str, object] = {
        "event_id": uuid4(),
        "member_id": MEMBER_ID,
        "reader_id": "reader-main-door",
        "direction": AccessDirection.ENTRY,
        "occurred_at": NOW,
        "current_occupancy": 12,
        "max_occupancy": 80,
        "offline": True,
    }
    values.update(overrides)
    return AccessRequest(**values)  # type: ignore[arg-type]


def test_valid_offline_entry_is_authorized_and_persisted(tmp_path) -> None:
    database_path = tmp_path / "access.sqlite3"
    store = SQLiteAccessStore(database_path)
    store.put_snapshot(make_snapshot())
    request = make_request()

    decision = store.decide_and_enqueue(request, timezone_name="America/Mexico_City")
    reopened_store = SQLiteAccessStore(database_path)

    assert decision.authorized is True
    assert decision.reason == AccessReason.ENTRY_ALLOWED
    assert len(reopened_store.pending_events()) == 1
    assert reopened_store.pending_events()[0]["event_id"] == str(request.event_id)


@pytest.mark.parametrize(
    ("snapshot_changes", "request_changes", "expected_reason"),
    [
        ({"valid_until": NOW}, {}, AccessReason.SNAPSHOT_EXPIRED),
        ({"membership_status": "frozen"}, {}, AccessReason.MEMBERSHIP_NOT_ACTIVE),
        ({"blocking_debt": True}, {}, AccessReason.BLOCKING_DEBT),
        ({}, {"current_occupancy": 80}, AccessReason.OCCUPANCY_FULL),
        (
            {"allowed_windows": (AccessWindow(3, time(9), time(10)),)},
            {},
            AccessReason.OUTSIDE_ALLOWED_HOURS,
        ),
    ],
)
def test_entry_denies_invalid_or_stale_conditions(
    snapshot_changes: dict[str, object],
    request_changes: dict[str, object],
    expected_reason: AccessReason,
) -> None:
    decision = evaluate_access(
        make_snapshot(**snapshot_changes),
        make_request(**request_changes),
        timezone_name="America/Mexico_City",
    )

    assert decision.authorized is False
    assert decision.reason == expected_reason


def test_zero_occupancy_cap_means_the_club_has_no_limit() -> None:
    decision = evaluate_access(
        make_snapshot(antipassback_seconds=0),
        make_request(current_occupancy=500, max_occupancy=0),
        timezone_name="America/Mexico_City",
    )

    assert decision.authorized is True
    assert decision.reason == AccessReason.ENTRY_ALLOWED


def test_schedule_uses_gym_local_timezone_and_supports_overnight_window() -> None:
    snapshot = make_snapshot(
        allowed_windows=(AccessWindow(2, time(22), time(2)),),
        antipassback_seconds=0,
    )
    request = make_request(occurred_at=datetime(2026, 10, 15, 7, 0, tzinfo=UTC))

    decision = evaluate_access(snapshot, request, timezone_name="America/Mexico_City")

    assert decision.authorized is True


def test_antipassback_blocks_a_second_entry_inside_window(tmp_path) -> None:
    store = SQLiteAccessStore(tmp_path / "access.sqlite3")
    store.put_snapshot(make_snapshot())
    first = make_request()
    second = make_request(
        event_id=uuid4(),
        occurred_at=NOW + timedelta(seconds=30),
    )

    store.decide_and_enqueue(first, timezone_name="America/Mexico_City")
    decision = store.decide_and_enqueue(second, timezone_name="America/Mexico_City")

    assert decision.authorized is False
    assert decision.reason == AccessReason.ANTIPASSBACK
    assert len(store.pending_events()) == 2


def test_exit_is_allowed_even_without_a_current_membership_snapshot() -> None:
    request = make_request(direction=AccessDirection.EXIT)

    decision = evaluate_access(None, request, timezone_name="America/Mexico_City")

    assert decision.authorized is True
    assert decision.reason == AccessReason.EXIT_ALLOWED


def test_event_replay_is_idempotent_and_conflicting_reuse_is_rejected(tmp_path) -> None:
    store = SQLiteAccessStore(tmp_path / "access.sqlite3")
    store.put_snapshot(make_snapshot())
    request = make_request()

    first = store.decide_and_enqueue(request, timezone_name="America/Mexico_City")
    replay = store.decide_and_enqueue(request, timezone_name="America/Mexico_City")
    assert replay == first
    assert len(store.pending_events()) == 1

    changed = make_request(event_id=request.event_id, reader_id="reader-side-door")
    with pytest.raises(DuplicateAccessEventConflict):
        store.decide_and_enqueue(changed, timezone_name="America/Mexico_City")


def test_synced_events_leave_the_pending_outbox(tmp_path) -> None:
    store = SQLiteAccessStore(tmp_path / "access.sqlite3")
    store.put_snapshot(make_snapshot())
    request = make_request()
    store.decide_and_enqueue(request, timezone_name="America/Mexico_City")

    assert store.mark_synchronized([request.event_id]) == 1
    assert store.pending_events() == []