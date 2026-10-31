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


LEGACY_REQUESTS_TABLE = (
    'CREATE TABLE "staff_attendance_requests" (\n'
    "\tid CHAR(32) NOT NULL, \n"
    "\tattendance_id CHAR(32) NOT NULL, \n"
    "\tmark VARCHAR(16) NOT NULL, \n"
    "\taction VARCHAR(16) NOT NULL, \n"
    "\tjustification VARCHAR(500) NOT NULL, \n"
    "\tstatus VARCHAR(16) NOT NULL, \n"
    "\tdecided_by CHAR(32), \n"
    "\tdecided_at DATETIME, \n"
    "\tPRIMARY KEY (id)\n"
    ")"
)

LEGACY_EVENTS_TABLE = (
    'CREATE TABLE "staff_attendance_events" (\n'
    "\tid CHAR(32) NOT NULL, \n"
    "\tattendance_id CHAR(32) NOT NULL, \n"
    "\tactor_id CHAR(32) NOT NULL, \n"
    "\tevent_type VARCHAR(32) NOT NULL, \n"
    "\tsource VARCHAR(20) NOT NULL, \n"
    "\treason TEXT, \n"
    "\toccurred_at DATETIME NOT NULL, \n"
    "\tattendance_request_id CHAR(32), \n"
    "\tPRIMARY KEY (id)\n"
    ")"
)


def _legacy_request(
    connection: sqlite3.Connection,
    request_id: str,
    *,
    attendance: str,
    mark: str,
    action: str,
    justification: str,
    status: str = "approved",
    decided_by: str | None = "s1",
) -> None:
    connection.execute(
        "INSERT INTO staff_attendance_requests (id, attendance_id, mark, action, "
        "justification, status, decided_by, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            request_id,
            attendance,
            mark,
            action,
            justification,
            status,
            decided_by,
            "2026-10-30 20:00:00" if decided_by else None,
        ),
    )


def _legacy_event(
    connection: sqlite3.Connection,
    event_id: str,
    *,
    attendance: str,
    actor: str = "s1",
    event_type: str,
    reason: str | None,
    source: str = "manual",
    linked_to: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO staff_attendance_events (id, attendance_id, actor_id, event_type, "
        "source, reason, occurred_at, attendance_request_id) "
        "VALUES (?, ?, ?, ?, ?, ?, '2026-10-30 20:00:01', ?)",
        (event_id, attendance, actor, event_type, source, reason, linked_to),
    )


def test_preview_backfills_the_request_link_on_older_events() -> None:
    assert preview_patch.ADDED_COLUMNS["staff_attendance_events"] == {
        "attendance_request_id": "CHAR(32)"
    }

    connection = sqlite3.connect(":memory:")
    connection.execute(LEGACY_REQUESTS_TABLE)
    connection.execute(LEGACY_EVENTS_TABLE)

    # A correction approved before the column existed.
    _legacy_request(
        connection,
        "r1",
        attendance="a1",
        mark="check_in",
        action="correct",
        justification="Entré a las 19:15 y la marca quedó a las 19:30",
    )
    _legacy_event(
        connection,
        "e1",
        attendance="a1",
        event_type="check_in_correction",
        reason="Solicitud del colaborador: Entré a las 19:15 y la marca quedó a las 19:30",
    )
    # A panel correction on the same mark stays unlinked.
    _legacy_event(
        connection,
        "e2",
        attendance="a1",
        event_type="check_in_correction",
        reason="Entrada corregida a la hora del turno",
    )
    # An annulment approved with a supervisor's note.
    _legacy_request(
        connection,
        "r2",
        attendance="a2",
        mark="check_out",
        action="void",
        justification="Salí a las 21:00 y la salida quedó en cero",
    )
    _legacy_event(
        connection,
        "e3",
        attendance="a2",
        event_type="check_out_voided",
        reason="Solicitud del colaborador: Salí a las 21:00 y la salida quedó en cero"
        " · Nota del supervisor: Revisado",
    )
    # Voiding the whole attendance.
    _legacy_request(
        connection,
        "r3",
        attendance="a3",
        mark="check_in",
        action="void",
        justification="Ese turno no era mío",
    )
    _legacy_event(
        connection,
        "e4",
        attendance="a3",
        event_type="attendance_voided",
        reason="Solicitud del colaborador: Ese turno no era mío",
    )
    # Already linked by the current code: never rewritten.
    _legacy_request(
        connection,
        "r4",
        attendance="a4",
        mark="check_in",
        action="correct",
        justification="Marca duplicada",
    )
    _legacy_event(
        connection,
        "e5",
        attendance="a4",
        event_type="check_in_correction",
        reason="Solicitud del colaborador: Marca duplicada · Nota del supervisor: Ok",
        linked_to="r4",
    )
    # One request, two candidate events: ambiguous, nothing is linked.
    _legacy_request(
        connection,
        "r5",
        attendance="a5",
        mark="check_in",
        action="correct",
        justification="Marqué tarde",
    )
    for event_id in ("e6", "e7"):
        _legacy_event(
            connection,
            event_id,
            attendance="a5",
            event_type="check_in_correction",
            reason="Solicitud del colaborador: Marqu\u00e9 tarde",
        )
    # Rejected requests wrote no event; a reason that matches but came from another
    # supervisor is not the one the approval wrote.
    _legacy_request(
        connection,
        "r6",
        attendance="a6",
        mark="check_in",
        action="correct",
        justification="Error del reloj",
        status="rejected",
    )
    _legacy_event(
        connection,
        "e8",
        attendance="a6",
        event_type="check_in_correction",
        reason="Solicitud del colaborador: Error del reloj",
    )
    _legacy_request(
        connection,
        "r7",
        attendance="a7",
        mark="check_in",
        action="correct",
        justification="Otra justificación",
    )
    _legacy_event(
        connection,
        "e9",
        attendance="a7",
        actor="s2",
        event_type="check_in_correction",
        reason="Solicitud del colaborador: Otra justificación",
    )
    # A reason with the request prefix but a different mark type is not a candidate.
    _legacy_request(
        connection,
        "r8",
        attendance="a8",
        mark="check_out",
        action="correct",
        justification="Salí antes",
    )
    _legacy_event(
        connection,
        "e10",
        attendance="a8",
        event_type="check_in_correction",
        reason="Solicitud del colaborador: Salí antes",
    )
    connection.commit()

    assert preview_patch.backfill_attendance_request_links(connection) == 3
    links = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT id, attendance_request_id FROM staff_attendance_events"
        )
    }
    assert links == {
        "e1": "r1",
        "e2": None,
        "e3": "r2",
        "e4": "r3",
        "e5": "r4",
        "e6": None,
        "e7": None,
        "e8": None,
        "e9": None,
        "e10": None,
    }

    # Running it again finds nothing left to link.
    assert preview_patch.backfill_attendance_request_links(connection) == 0


def test_preview_upgrade_registers_the_email_switch_columns() -> None:
    assert preview_patch.ADDED_COLUMNS["staffing_settings"]["attendance_email_enabled"] == (
        "BOOLEAN NOT NULL DEFAULT 1"
    )
    assert preview_patch.ADDED_COLUMNS["staffing_settings_events"] == {
        "previous_attendance_request_sla_hours": "INTEGER NOT NULL DEFAULT 24",
        "attendance_request_sla_hours": "INTEGER NOT NULL DEFAULT 24",
        "previous_attendance_email_enabled": "BOOLEAN NOT NULL DEFAULT 1",
        "attendance_email_enabled": "BOOLEAN NOT NULL DEFAULT 1",
    }

    connection = sqlite3.connect(":memory:")
    connection.execute(
        'CREATE TABLE "staffing_settings" (\n'
        "\tid INTEGER NOT NULL, \n"
        "\tcheck_in_early_grace_minutes INTEGER NOT NULL DEFAULT 15, \n"
        "\tlateness_tolerance_minutes INTEGER NOT NULL DEFAULT 0, \n"
        "\tattendance_request_sla_hours INTEGER NOT NULL DEFAULT 24, \n"
        "\tupdated_at DATETIME NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    connection.execute(
        "INSERT INTO staffing_settings (id, updated_at) VALUES (1, '2026-10-30 12:00:00')"
    )
    connection.commit()
    preview_patch.ensure_added_columns(connection, "staffing_settings")
    preview_patch.ensure_added_columns(connection, "staffing_settings")
    row = connection.execute(
        "SELECT attendance_email_enabled FROM staffing_settings WHERE id = 1"
    ).fetchone()
    assert row == (1,)


def test_preview_upgrade_registers_the_push_retry_column() -> None:
    assert preview_patch.ADDED_COLUMNS["member_push_deliveries"] == {
        "next_attempt_at": "DATETIME"
    }

    connection = sqlite3.connect(":memory:")
    connection.execute(
        'CREATE TABLE "member_push_deliveries" (\n'
        "\tid CHAR(32) NOT NULL, \n"
        "\tstatus VARCHAR(16) NOT NULL, \n"
        "\tPRIMARY KEY (id)\n"
        ")"
    )
    preview_patch.ensure_added_columns(connection, "member_push_deliveries")
    preview_patch.ensure_added_columns(connection, "member_push_deliveries")
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(member_push_deliveries)")
    }
    assert "next_attempt_at" in columns
