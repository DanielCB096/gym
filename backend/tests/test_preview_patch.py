import importlib.util
import sqlite3
from pathlib import Path

PREVIEW_PATCH = Path(__file__).resolve().parents[1] / "preview_patch.py"

spec = importlib.util.spec_from_file_location("preview_patch", PREVIEW_PATCH)
preview_patch = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(preview_patch)

PHYSIO_KINDS = (
    "physio_appointment_scheduled",
    "physio_appointment_cancelled",
    "physio_appointment_rescheduled",
    "physio_reminder",
)

# The CHECK the preview database carried before the physiotherapy increment.
PRE_PHYSIO_TABLE = (
    'CREATE TABLE "member_notifications" (\n'
    "\tid CHAR(32) NOT NULL, \n"
    "\tkind VARCHAR(40) NOT NULL, \n"
    "\tdedupe_key VARCHAR(160), \n"
    "\tPRIMARY KEY (id), \n"
    "\tCONSTRAINT ck_member_notifications_kind CHECK (kind IN "
    "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
    "'invoice_cancelled', 'class_reminder', 'class_reserved', "
    "'class_cancelled', 'class_rescheduled'))\n"
    ")"
)


def _table_sql(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='member_notifications'"
    ).fetchone()
    assert row is not None and row[0] is not None
    return row[0]


def _run_upgrade(connection: sqlite3.Connection) -> None:
    preview_patch.upgrade_checks(
        connection,
        "member_notifications",
        preview_patch.CHECK_UPGRADES["member_notifications"],
        preview_patch.ADDED_CONSTRAINTS.get("member_notifications", ()),
    )


def test_preview_upgrade_adds_every_notification_kind() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(PRE_PHYSIO_TABLE)
    connection.execute(
        "INSERT INTO member_notifications (id, kind, dedupe_key) "
        "VALUES ('n1', 'class_reserved', 'class_reserved:n1')"
    )
    connection.commit()

    _run_upgrade(connection)

    create_sql = _table_sql(connection)
    for kind in PHYSIO_KINDS:
        assert kind in create_sql
    assert connection.execute("SELECT COUNT(*) FROM member_notifications").fetchone()[0] == 1
    # The upgraded CHECK now accepts a physiotherapy notice.
    connection.execute(
        "INSERT INTO member_notifications (id, kind, dedupe_key) "
        "VALUES ('n2', 'physio_reminder', 'physio_reminder:a:24')"
    )


def test_preview_upgrade_is_idempotent() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(PRE_PHYSIO_TABLE)
    connection.execute(
        "INSERT INTO member_notifications (id, kind, dedupe_key) "
        "VALUES ('n1', 'membership_expiring', 'membership_expiring:m:7')"
    )
    connection.commit()

    _run_upgrade(connection)
    upgraded_sql = _table_sql(connection)
    _run_upgrade(connection)

    assert _table_sql(connection) == upgraded_sql
    assert connection.execute("SELECT COUNT(*) FROM member_notifications").fetchone()[0] == 1
