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


PRE_CORRECTION_TABLE = (
    'CREATE TABLE "staff_attendance_events" (\n'
    "\tid CHAR(32) NOT NULL, \n"
    "\tevent_type VARCHAR(16) NOT NULL, \n"
    "\tPRIMARY KEY (id), \n"
    "\tCONSTRAINT ck_staff_attendance_events_type CHECK "
    "(event_type IN ('check_in', 'check_out'))\n"
    ")"
)


def test_preview_upgrade_accepts_attendance_corrections() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(PRE_CORRECTION_TABLE)
    connection.execute(
        "INSERT INTO staff_attendance_events (id, event_type) VALUES ('e1', 'check_in')"
    )
    connection.commit()

    preview_patch.upgrade_checks(
        connection,
        "staff_attendance_events",
        preview_patch.CHECK_UPGRADES["staff_attendance_events"],
        preview_patch.ADDED_CONSTRAINTS.get("staff_attendance_events", ()),
    )

    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='staff_attendance_events'"
    ).fetchone()
    create_sql = row[0]
    assert "check_in_correction" in create_sql
    assert connection.execute("SELECT COUNT(*) FROM staff_attendance_events").fetchone()[0] == 1
    # The upgraded CHECK now accepts a correction event.
    connection.execute(
        "INSERT INTO staff_attendance_events (id, event_type) VALUES ('e2', 'check_out_correction')"
    )


def test_preview_upgrade_accepts_void_events() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(PRE_CORRECTION_TABLE)
    connection.execute(
        "INSERT INTO staff_attendance_events (id, event_type) VALUES ('e1', 'check_out')"
    )
    connection.commit()

    preview_patch.upgrade_checks(
        connection,
        "staff_attendance_events",
        preview_patch.CHECK_UPGRADES["staff_attendance_events"],
        preview_patch.ADDED_CONSTRAINTS.get("staff_attendance_events", ()),
    )

    create_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='staff_attendance_events'"
    ).fetchone()[0]
    assert "check_out_voided" in create_sql
    assert "attendance_voided" in create_sql
    connection.execute(
        "INSERT INTO staff_attendance_events (id, event_type) VALUES ('e2', 'attendance_voided')"
    )
    connection.execute(
        "INSERT INTO staff_attendance_events (id, event_type) VALUES ('e3', 'check_out_voided')"
    )
    assert connection.execute("SELECT COUNT(*) FROM staff_attendance_events").fetchone()[0] == 3


# The table constraint the preview database carried before voiding was added.
PRE_VOID_ATTENDANCE_TABLE = (
    'CREATE TABLE "staff_attendance" (\n'
    "\tid CHAR(32) NOT NULL, \n"
    "\tshift_id CHAR(32) NOT NULL, \n"
    "\tstatus VARCHAR(16) NOT NULL, \n"
    "\tvoided_at DATETIME, \n"
    "\tPRIMARY KEY (id), \n"
    "\tCONSTRAINT uq_staff_attendance_shift UNIQUE (shift_id), \n"
    "\tCONSTRAINT ck_staff_attendance_status CHECK (status IN ('present', 'late'))\n"
    ")"
)


def test_preview_voiding_frees_the_shift_only_for_voided_rows() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(PRE_VOID_ATTENDANCE_TABLE)
    connection.execute(
        "INSERT INTO staff_attendance (id, shift_id, status) VALUES ('a1', 's1', 'present')"
    )
    connection.commit()

    preview_patch.relax_attendance_shift_uniqueness(connection)

    create_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='staff_attendance'"
    ).fetchone()[0]
    assert "uq_staff_attendance_shift" not in create_sql
    index_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_staff_attendance_shift'"
    ).fetchone()[0]
    assert "WHERE voided_at IS NULL" in index_sql
    assert connection.execute("SELECT COUNT(*) FROM staff_attendance").fetchone()[0] == 1

    # Two live marks for the same shift remain impossible.
    try:
        connection.execute(
            "INSERT INTO staff_attendance (id, shift_id, status) VALUES ('a2', 's1', 'present')"
        )
    except sqlite3.IntegrityError:
        pass
    else:  # pragma: no cover - the unique index must reject the duplicate
        raise AssertionError("a second live attendance for the shift was accepted")

    connection.execute(
        "UPDATE staff_attendance SET voided_at = '2026-10-30 12:00:00' WHERE id = 'a1'"
    )
    connection.execute(
        "INSERT INTO staff_attendance (id, shift_id, status) VALUES ('a3', 's1', 'present')"
    )
    assert connection.execute("SELECT COUNT(*) FROM staff_attendance").fetchone()[0] == 2

    # Running it again keeps the freed-shift semantics.
    preview_patch.relax_attendance_shift_uniqueness(connection)
    assert connection.execute("SELECT COUNT(*) FROM staff_attendance").fetchone()[0] == 2


def test_preview_upgrade_registers_the_attendance_request_link() -> None:
    assert preview_patch.ADDED_COLUMNS["staff_attendance_events"] == {
        "attendance_request_id": "CHAR(32)"
    }

    connection = sqlite3.connect(":memory:")
    connection.execute(
        'CREATE TABLE "staff_attendance_events" (\n'
        "\tid CHAR(32) NOT NULL, \n"
        "\tevent_type VARCHAR(32) NOT NULL, \n"
        "\toccurred_at DATETIME NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    connection.execute("ALTER TABLE staff_attendance_events ADD COLUMN attendance_request_id CHAR(32)")

    # Running it twice keeps the patch idempotent.
    preview_patch.ensure_attendance_event_indexes(connection)
    preview_patch.ensure_attendance_event_indexes(connection)
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='staff_attendance_events'"
        )
    }
    assert {
        "ix_staff_attendance_events_type_time",
        "ix_staff_attendance_events_request_link",
    } <= indexes
