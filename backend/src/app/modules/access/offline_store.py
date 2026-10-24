from __future__ import annotations

from datetime import datetime, time
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import UUID

from app.modules.access.models import (
    AccessDecision,
    AccessDirection,
    AccessReason,
    AccessRequest,
    AccessSnapshot,
    AccessWindow,
    DuplicateAccessEventConflict,
)
from app.modules.access.service import evaluate_access


class SQLiteAccessStore:
    """Device-local cache and durable outbox for access decisions."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS access_snapshots (
                    member_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    valid_until TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_outbox (
                    event_id TEXT PRIMARY KEY,
                    member_id TEXT NOT NULL,
                    reader_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    authorized INTEGER NOT NULL CHECK (authorized IN (0, 1)),
                    reason TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    offline INTEGER NOT NULL CHECK (offline IN (0, 1)),
                    request_sha256 TEXT NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (sync_status IN ('pending', 'synced')),
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_access_outbox_pending_time
                    ON access_outbox(sync_status, occurred_at);
                CREATE INDEX IF NOT EXISTS ix_access_outbox_member_entry
                    ON access_outbox(member_id, direction, authorized, occurred_at);
                """
            )

    def put_snapshot(self, snapshot: AccessSnapshot) -> None:
        payload = _snapshot_to_dict(snapshot)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO access_snapshots(member_id, payload_json, cached_at, valid_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(member_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    cached_at = excluded.cached_at,
                    valid_until = excluded.valid_until
                """,
                (
                    str(snapshot.member_id),
                    _json(payload),
                    snapshot.cached_at.isoformat(),
                    snapshot.valid_until.isoformat(),
                ),
            )

    def get_snapshot(self, member_id: UUID) -> AccessSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM access_snapshots WHERE member_id = ?",
                (str(member_id),),
            ).fetchone()
        if row is None:
            return None
        return _snapshot_from_dict(json.loads(row["payload_json"]))

    def decide_and_enqueue(self, request: AccessRequest, *, timezone_name: str) -> AccessDecision:
        request_payload = {
            "event_id": str(request.event_id),
            "member_id": str(request.member_id),
            "reader_id": request.reader_id,
            "direction": request.direction.value,
            "occurred_at": request.occurred_at.isoformat(),
            "current_occupancy": request.current_occupancy,
            "max_occupancy": request.max_occupancy,
            "offline": request.offline,
            "timezone_name": timezone_name,
        }
        request_sha256 = sha256(_json(request_payload).encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT payload_json, request_sha256 FROM access_outbox WHERE event_id = ?",
                (str(request.event_id),),
            ).fetchone()
            if existing is not None:
                if existing["request_sha256"] != request_sha256:
                    raise DuplicateAccessEventConflict("Access event ID was reused with a different payload")
                return _decision_from_dict(json.loads(existing["payload_json"]))

            snapshot_row = connection.execute(
                "SELECT payload_json FROM access_snapshots WHERE member_id = ?",
                (str(request.member_id),),
            ).fetchone()
            snapshot = (
                _snapshot_from_dict(json.loads(snapshot_row["payload_json"]))
                if snapshot_row is not None
                else None
            )
            last_entry_row = None
            if request.direction == AccessDirection.ENTRY:
                last_entry_row = connection.execute(
                    """
                    SELECT occurred_at FROM access_outbox
                    WHERE member_id = ? AND direction = 'entry' AND authorized = 1
                    ORDER BY occurred_at DESC LIMIT 1
                    """,
                    (str(request.member_id),),
                ).fetchone()
            last_entry = (
                datetime.fromisoformat(last_entry_row["occurred_at"])
                if last_entry_row is not None
                else None
            )
            decision = evaluate_access(
                snapshot,
                request,
                timezone_name=timezone_name,
                last_successful_entry_at=last_entry,
            )
            event = {
                "event_id": str(decision.event_id),
                "member_id": str(decision.member_id),
                "reader_id": request.reader_id,
                "direction": decision.direction.value,
                "authorized": decision.authorized,
                "reason": decision.reason.value,
                "occurred_at": decision.occurred_at.isoformat(),
                "offline": decision.offline,
            }
            payload = _json(event)
            connection.execute(
                """
                INSERT INTO access_outbox(
                    event_id, member_id, reader_id, direction, authorized,
                    reason, occurred_at, offline, request_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(decision.event_id),
                    str(decision.member_id),
                    request.reader_id,
                    decision.direction.value,
                    int(decision.authorized),
                    decision.reason.value,
                    decision.occurred_at.isoformat(),
                    int(decision.offline),
                    request_sha256,
                    payload,
                ),
            )
        return decision

    def pending_events(self, limit: int = 100) -> list[dict[str, object]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM access_outbox
                WHERE sync_status = 'pending'
                ORDER BY occurred_at, event_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def mark_synchronized(self, event_ids: list[UUID]) -> int:
        if not event_ids:
            return 0
        with self._connect() as connection:
            cursor = connection.executemany(
                "UPDATE access_outbox SET sync_status = 'synced' WHERE event_id = ? AND sync_status = 'pending'",
                [(str(event_id),) for event_id in event_ids],
            )
        return cursor.rowcount

    def _last_successful_entry(self, member_id: UUID) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT occurred_at FROM access_outbox
                WHERE member_id = ? AND direction = 'entry' AND authorized = 1
                ORDER BY occurred_at DESC LIMIT 1
                """,
                (str(member_id),),
            ).fetchone()
        return datetime.fromisoformat(row["occurred_at"]) if row is not None else None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


def _snapshot_to_dict(snapshot: AccessSnapshot) -> dict[str, object]:
    return {
        "member_id": str(snapshot.member_id),
        "membership_status": snapshot.membership_status,
        "membership_starts_at": snapshot.membership_starts_at.isoformat(),
        "membership_ends_at": snapshot.membership_ends_at.isoformat(),
        "blocking_debt": snapshot.blocking_debt,
        "cached_at": snapshot.cached_at.isoformat(),
        "valid_until": snapshot.valid_until.isoformat(),
        "allowed_windows": (
            [
                {
                    "weekday": window.weekday,
                    "starts_at": window.starts_at.isoformat(),
                    "ends_at": window.ends_at.isoformat(),
                }
                for window in snapshot.allowed_windows
            ]
            if snapshot.allowed_windows is not None
            else None
        ),
        "daily_entry_limit": snapshot.daily_entry_limit,
        "entries_today": snapshot.entries_today,
        "antipassback_seconds": snapshot.antipassback_seconds,
    }


def _snapshot_from_dict(payload: dict[str, object]) -> AccessSnapshot:
    windows_payload = payload["allowed_windows"]
    windows = (
        tuple(
            AccessWindow(
                weekday=int(window["weekday"]),
                starts_at=time.fromisoformat(str(window["starts_at"])),
                ends_at=time.fromisoformat(str(window["ends_at"])),
            )
            for window in windows_payload
        )
        if windows_payload is not None
        else None
    )
    return AccessSnapshot(
        member_id=UUID(str(payload["member_id"])),
        membership_status=str(payload["membership_status"]),
        membership_starts_at=datetime.fromisoformat(str(payload["membership_starts_at"])),
        membership_ends_at=datetime.fromisoformat(str(payload["membership_ends_at"])),
        blocking_debt=bool(payload["blocking_debt"]),
        cached_at=datetime.fromisoformat(str(payload["cached_at"])),
        valid_until=datetime.fromisoformat(str(payload["valid_until"])),
        allowed_windows=windows,
        daily_entry_limit=(
            int(payload["daily_entry_limit"])
            if payload["daily_entry_limit"] is not None
            else None
        ),
        entries_today=int(payload["entries_today"]),
        antipassback_seconds=int(payload["antipassback_seconds"]),
    )


def _decision_from_dict(payload: dict[str, object]) -> AccessDecision:
    return AccessDecision(
        event_id=UUID(str(payload["event_id"])),
        member_id=UUID(str(payload["member_id"])),
        authorized=bool(payload["authorized"]),
        reason=AccessReason(str(payload["reason"])),
        direction=AccessDirection(str(payload["direction"])),
        occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
        offline=bool(payload["offline"]),
    )


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))