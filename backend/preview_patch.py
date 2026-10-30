"""Bring an existing SQLite preview database up to date with the models.

``SQLModel.metadata.create_all`` only creates missing *tables*; it never alters
an existing one. The preview database therefore has to be patched by hand when a
model gains a column or a CHECK constraint changes. This script is idempotent.

    .\\.venv\\Scripts\\python.exe preview_patch.py

Adding a column is always safe. Rebuilding the maintenance demo data is not, so
it only happens with an explicit flag:

    .\\.venv\\Scripts\\python.exe preview_patch.py --reset-maintenance

The reset drops the maintenance tables (and clears ``exercises.equipment_id``)
so ``seed_maintenance.py`` can repopulate them from scratch.
"""

import sqlite3
import sys
from uuid import NAMESPACE_URL, uuid5

DB = r".\gym_preview.db"

# Columns added after the preview database was first created.
ADDED_COLUMNS = {
    "exercises": {"equipment_id": "CHAR(32)"},
    "sales": {
        "origin": "VARCHAR(16) NOT NULL DEFAULT 'online'",
        "client_reference": "VARCHAR(64)",
        "class_reservation_id": "CHAR(32)",
        "physio_appointment_id": "CHAR(32)",
    },
    "members": {"credit_limit_cents": "BIGINT"},
    "plans": {"daily_entry_limit": "INTEGER"},
    "physio_packs": {
        "voided_at": "DATETIME",
        "voided_by": "CHAR(32)",
        "void_reason": "VARCHAR(300)",
        "voided_sessions": "INTEGER NOT NULL DEFAULT 0",
    },
    "physio_appointments": {"room_id": "CHAR(32)"},
    "staff_attendance": {
        "voided_at": "DATETIME",
        "voided_by": "CHAR(32)",
        "void_reason": "VARCHAR(300)",
    },
    "member_account_statement_deliveries": {
        "retry_of_id": "CHAR(32)",
        "purpose": "VARCHAR(16) NOT NULL DEFAULT 'statement'",
    },
    "payments": {
        "period_starts_at": "DATETIME",
        "period_ends_at": "DATETIME",
        "cash_session_id": "CHAR(32)",
        "collected_by": "CHAR(32)",
        "note": "VARCHAR(200)",
    },
    "progress_photos": {"origin": "VARCHAR(8) NOT NULL DEFAULT 'staff'"},
    "kiosk_devices": {"token_expires_at": "DATETIME"},
    "staff_notifications": {"resolved_at": "DATETIME"},
    "staffing_settings": {
        "attendance_request_sla_hours": "INTEGER NOT NULL DEFAULT 24",
        "attendance_email_enabled": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "staffing_settings_events": {
        "previous_attendance_request_sla_hours": "INTEGER NOT NULL DEFAULT 24",
        "attendance_request_sla_hours": "INTEGER NOT NULL DEFAULT 24",
        "previous_attendance_email_enabled": "BOOLEAN NOT NULL DEFAULT 1",
        "attendance_email_enabled": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "staff_attendance_requests": {"due_at": "DATETIME"},
    "staff_attendance_events": {"attendance_request_id": "CHAR(32)"},
    "access_settings": {
        "max_occupancy": "INTEGER",
        "occupancy_window_seconds": "INTEGER NOT NULL DEFAULT 7200",
    },
    "invoices": {
        "global_year": "INTEGER",
        "global_month": "INTEGER",
        "related_invoice_id": "CHAR(32)",
        "credit_note_reason": "VARCHAR(24)",
        "credit_note_note": "VARCHAR(300)",
        "cancellation_requested_at": "DATETIME",
        "cancellation_checked_at": "DATETIME",
    },
}

# New RBAC rows for features added after the preview database was seeded.
# Production gets them from the Alembic migrations; the preview only runs
# ``create_all`` (which never updates existing rows), so they are patched here.
PREVIEW_PERMISSIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "sales.credit",
        "Administrar límites de crédito de socios",
        ("owner", "manager"),
    ),
    (
        "sales.service_refund",
        "Reembolsar servicios cobrados (clases premium)",
        ("owner", "manager"),
    ),
    (
        "finance.manage",
        "Conciliar pagos y administrar cuentas bancarias",
        ("owner", "accountant"),
    ),
    (
        "physio.read",
        "Consultar fisioterapia, agenda y saldos",
        ("owner", "manager", "reception", "trainer"),
    ),
    (
        "physio.manage",
        "Administrar fisioterapia, paquetes y citas",
        ("owner", "manager", "reception"),
    ),
    (
        "physio.adjust",
        "Extender o anular paquetes de fisioterapia",
        ("owner", "manager"),
    ),
)

# SQLite cannot alter a CHECK constraint in place, so a table that gains an
# allowed value is rebuilt: create the replacement under a temporary name, copy
# the rows, drop the old table and rename. ``foreign_keys`` is off for the
# duration, so the other tables keep pointing at the final name. Each entry
# holds one or more (old, new) pairs to replace in the original CREATE TABLE.
CHECK_UPGRADES = {
    "sales": (
        (
            "CONSTRAINT ck_sales_payment_method CHECK (payment_method IN "
            "('cash', 'card', 'transfer'))",
            "CONSTRAINT ck_sales_payment_method CHECK (payment_method IN "
            "('cash', 'card', 'transfer', 'account'))",
        ),
    ),
    "sale_returns": (
        (
            "CONSTRAINT ck_sale_returns_method CHECK (refund_method IN "
            "('cash', 'card', 'transfer'))",
            "CONSTRAINT ck_sale_returns_method CHECK (refund_method IN "
            "('cash', 'card', 'transfer', 'account'))",
        ),
    ),
    "payment_attempts": (
        (
            "CONSTRAINT ck_payment_attempts_card_method_required CHECK "
            "(method <> 'card' OR payment_method_id IS NOT NULL)",
            "CONSTRAINT ck_payment_attempts_card_method_required CHECK "
            "(method <> 'card' OR payment_method_id IS NOT NULL OR provider IS NULL)",
        ),
    ),
    "invoices": (
        (
            "CONSTRAINT ck_invoices_origin_type CHECK (origin_type IN "
            "('sale', 'membership_payment'))",
            "CONSTRAINT ck_invoices_origin_type CHECK (origin_type IN "
            "('sale', 'membership_payment', 'global', 'credit_note'))",
        ),
    ),
    "member_notifications": (
        (
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring'))",
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service'))",
        ),
        (
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service'))",
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled'))",
        ),
        (
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled'))",
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder'))",
        ),
        (
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder'))",
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved'))",
        ),
        (
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved'))",
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved', "
            "'class_cancelled', 'class_rescheduled'))",
        ),
        (
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved', "
            "'class_cancelled', 'class_rescheduled'))",
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved', "
            "'class_cancelled', 'class_rescheduled', 'physio_appointment_scheduled', "
            "'physio_appointment_cancelled', 'physio_appointment_rescheduled'))",
        ),
        (
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved', "
            "'class_cancelled', 'class_rescheduled', 'physio_appointment_scheduled', "
            "'physio_appointment_cancelled', 'physio_appointment_rescheduled'))",
            "CONSTRAINT ck_member_notifications_kind CHECK (kind IN "
            "('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved', "
            "'class_cancelled', 'class_rescheduled', 'physio_appointment_scheduled', "
            "'physio_appointment_cancelled', 'physio_appointment_rescheduled', "
            "'physio_reminder'))",
        ),
    ),
    "staff_notifications": (
        (
            "CONSTRAINT ck_staff_notifications_kind CHECK (kind IN "
            "('workout_pending_review', 'maintenance_ticket_assigned'))",
            "CONSTRAINT ck_staff_notifications_kind CHECK (kind IN "
            "('workout_pending_review', 'maintenance_ticket_assigned', "
            "'kiosk_token_expiring'))",
        ),
        (
            "CONSTRAINT ck_staff_notifications_kind CHECK (kind IN "
            "('workout_pending_review', 'maintenance_ticket_assigned', "
            "'kiosk_token_expiring', 'attendance_corrected', 'attendance_voided', "
            "'attendance_request_pending', 'attendance_request_approved', "
            "'attendance_request_rejected'))",
            "CONSTRAINT ck_staff_notifications_kind CHECK (kind IN "
            "('workout_pending_review', 'maintenance_ticket_assigned', "
            "'kiosk_token_expiring', 'attendance_corrected', 'attendance_voided', "
            "'attendance_request_pending', 'attendance_request_approved', "
            "'attendance_request_rejected', 'attendance_request_overdue'))",
        ),
    ),
    "staffing_settings": (),
    "staff_attendance_events": (
        (
            "CONSTRAINT ck_staff_attendance_events_type CHECK "
            "(event_type IN ('check_in', 'check_out'))",
            "CONSTRAINT ck_staff_attendance_events_type CHECK "
            "(event_type IN ('check_in', 'check_out', 'check_in_correction', "
            "'check_out_correction'))",
        ),
        (
            "CONSTRAINT ck_staff_attendance_events_type CHECK "
            "(event_type IN ('check_in', 'check_out', 'check_in_correction', "
            "'check_out_correction'))",
            "CONSTRAINT ck_staff_attendance_events_type CHECK "
            "(event_type IN ('check_in', 'check_out', 'check_in_correction', "
            "'check_out_correction', 'check_out_voided', 'attendance_voided'))",
        ),
    ),
    "physio_packs": (),
}

# Constraints added to an existing table. The first value is a marker used to
# detect whether the constraint is already present; the second is the SQL
# fragment inserted before the closing parenthesis of CREATE TABLE.
ADDED_CONSTRAINTS = {
    "staffing_settings": (
        (
            "ck_staffing_settings_request_sla",
            "CONSTRAINT ck_staffing_settings_request_sla CHECK "
            "(attendance_request_sla_hours >= 0 AND attendance_request_sla_hours <= 720)",
        ),
    ),
    "physio_packs": (
        (
            "ck_physio_packs_voided_range",
            "CONSTRAINT ck_physio_packs_voided_range CHECK "
            "(voided_sessions >= 0 AND voided_sessions <= sessions_total)",
        ),
    ),
    "invoices": (
        (
            "ck_invoices_global_period",
            "CONSTRAINT ck_invoices_global_period CHECK "
            "((origin_type = 'global' AND global_year IS NOT NULL "
            "AND global_month BETWEEN 1 AND 12) OR "
            "(origin_type <> 'global' AND global_year IS NULL "
            "AND global_month IS NULL))",
        ),
        (
            "ck_invoices_credit_note",
            "CONSTRAINT ck_invoices_credit_note CHECK "
            "((origin_type = 'credit_note' AND related_invoice_id IS NOT NULL "
            "AND credit_note_reason IS NOT NULL) OR "
            "(origin_type <> 'credit_note' AND related_invoice_id IS NULL "
            "AND credit_note_reason IS NULL AND credit_note_note IS NULL))",
        ),
        (
            "REFERENCES invoices (id) ON DELETE RESTRICT",
            "FOREIGN KEY(related_invoice_id) REFERENCES invoices (id) "
            "ON DELETE RESTRICT",
        ),
    ),
}

# Columns that stopped being NOT NULL. SQLite cannot alter a column in place,
# so the table is rebuilt the same way as for a CHECK change. Alembic does the
# real ``ALTER COLUMN`` in production.
RELAXED_COLUMNS = {
    "sale_items": ("product_id",),
    "sale_return_items": ("product_id",),
}

MAINTENANCE_TABLES = (
    "maintenance_checklists",
    "maintenance_records",
    "maintenance_tickets",
    "equipment",
)


def column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def table_names(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def seed_preview_permissions(connection: sqlite3.Connection) -> None:
    if "permissions" not in table_names(connection):
        return
    for code, description, role_codes in PREVIEW_PERMISSIONS:
        row = connection.execute(
            "SELECT id FROM permissions WHERE code = ?", (code,)
        ).fetchone()
        if row is None:
            permission_id = uuid5(NAMESPACE_URL, f"ritmo-gym:permission:{code}").hex
            connection.execute(
                "INSERT INTO permissions (id, code, description) VALUES (?, ?, ?)",
                (permission_id, code, description),
            )
            print(f"Added permission {code}")
        else:
            permission_id = row[0]
        for role_code in role_codes:
            role = connection.execute(
                "SELECT id FROM roles WHERE code = ?", (role_code,)
            ).fetchone()
            if role is None:
                continue
            connection.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
                "VALUES (?, ?)",
                (role[0], permission_id),
            )
        print(f"Granted {code} to {', '.join(role_codes)}")


def relax_columns(connection: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    if row is None or row[0] is None:
        return
    create_sql = row[0]
    changed = False
    for column in columns:
        for quoted in (f'"{column}"', column):
            old = f"{quoted} CHAR(32) NOT NULL"
            if old in create_sql:
                create_sql = create_sql.replace(old, f"{quoted} CHAR(32)")
                changed = True
                break
    if not changed:
        print(f"{table}: no NOT NULL to relax")
        return

    index_sql = [
        item[0]
        for item in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name = ? AND sql IS NOT NULL",
            (table,),
        ).fetchall()
    ]
    temporary = f"{table}__upgrade"
    create_sql = create_sql.replace(
        f'CREATE TABLE "{table}" ', f'CREATE TABLE "{temporary}" ', 1
    )
    if f"CREATE TABLE {table} " in create_sql:
        create_sql = create_sql.replace(
            f"CREATE TABLE {table} ", f"CREATE TABLE {temporary} ", 1
        )
    connection.execute(create_sql)
    connection.execute(f"INSERT INTO {temporary} SELECT * FROM {table}")
    connection.execute(f"DROP TABLE {table}")
    connection.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
    for statement in index_sql:
        connection.execute(statement)
    print(f"{table}: rebuilt without NOT NULL on {', '.join(columns)}")


def upgrade_checks(
    connection: sqlite3.Connection,
    table: str,
    replacements: tuple[tuple[str, str], ...],
    additions: tuple[tuple[str, str], ...],
) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    if row is None or row[0] is None:
        return
    sql = row[0]
    # Walk the replacements in order so a database that stopped at an earlier
    # revision still reaches the latest CHECK (e.g. six kinds → seven → ten).
    create_sql = sql
    applied = 0
    satisfied = 0
    unmatched = 0
    for old, new in replacements:
        if new in create_sql:
            satisfied += 1
            continue
        if old not in create_sql:
            unmatched += 1
            continue
        create_sql = create_sql.replace(old, new)
        applied += 1
    if unmatched and not applied and not satisfied:
        print(f"{table}: expected CHECK not found, leaving it untouched")
        return
    pending_additions = [
        (marker, clause) for marker, clause in additions if marker not in sql
    ]
    if not applied and not pending_additions:
        print(f"{table}: CHECKs already up to date")
        return

    index_sql = [
        item[0]
        for item in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name = ? AND sql IS NOT NULL",
            (table,),
        ).fetchall()
    ]
    temporary = f"{table}__upgrade"
    for _, clause in pending_additions:
        closing = create_sql.rfind(")")
        create_sql = create_sql[:closing] + f",\n\t{clause}\n)" + create_sql[closing + 1 :]
    create_sql = create_sql.replace(f'CREATE TABLE "{table}" ', f'CREATE TABLE "{temporary}" ', 1)
    if table in create_sql:
        create_sql = create_sql.replace(f"CREATE TABLE {table} ", f"CREATE TABLE {temporary} ", 1)
    connection.execute(create_sql)
    connection.execute(f"INSERT INTO {temporary} SELECT * FROM {table}")
    connection.execute(f"DROP TABLE {table}")
    connection.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
    for statement in index_sql:
        connection.execute(statement)
    print(f"{table}: rebuilt with the new CHECKs")


def relax_attendance_shift_uniqueness(connection: sqlite3.Connection) -> None:
    """Replace ``UNIQUE (shift_id)`` with a partial unique index.

    A voided attendance keeps its row for the audit log but must stop occupying
    the shift, so the uniqueness only applies to rows whose ``voided_at`` is
    NULL. SQLite cannot drop a table constraint in place, so the table is
    rebuilt; the partial index is created afterwards.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = 'staff_attendance'"
    ).fetchone()
    if row is None or row[0] is None:
        return
    create_sql = row[0]
    marker = "CONSTRAINT uq_staff_attendance_shift UNIQUE (shift_id)"
    if marker in create_sql:
        index_sql = [
            item[0]
            for item in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name = 'staff_attendance' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        create_sql = create_sql.replace(f"{marker},", "")
        temporary = "staff_attendance__upgrade"
        create_sql = create_sql.replace(
            'CREATE TABLE "staff_attendance" ', f'CREATE TABLE "{temporary}" ', 1
        )
        if "CREATE TABLE staff_attendance " in create_sql:
            create_sql = create_sql.replace(
                "CREATE TABLE staff_attendance ", f"CREATE TABLE {temporary} ", 1
            )
        connection.execute(create_sql)
        connection.execute(f"INSERT INTO {temporary} SELECT * FROM staff_attendance")
        connection.execute("DROP TABLE staff_attendance")
        connection.execute(f"ALTER TABLE {temporary} RENAME TO staff_attendance")
        for statement in index_sql:
            connection.execute(statement)
        print("staff_attendance: rebuilt without the one-attendance-per-shift constraint")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_attendance_shift "
        "ON staff_attendance (shift_id) WHERE voided_at IS NULL"
    )


def ensure_attendance_event_indexes(connection: sqlite3.Connection) -> None:
    """Indexes the attendance reports need on a database created before them."""
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_staff_attendance_events_type_time "
        "ON staff_attendance_events (event_type, occurred_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_staff_attendance_events_request_link "
        "ON staff_attendance_events (attendance_request_id)"
    )


# Mirrors the data migration 20261031_0064. An approval writes the event reason as
# ``Solicitud del colaborador: <motivo>`` (plus the supervisor's note when there is
# one), so the link can be recovered without guessing by timestamp; the pairing has
# to be one-to-one or nothing is linked.
BACKFILL_ATTENDANCE_REQUEST_LINKS = """
WITH candidates AS (
    SELECT r.id AS request_id,
           e.id AS event_id,
           COUNT(*) OVER (PARTITION BY r.id) AS request_matches,
           COUNT(*) OVER (PARTITION BY e.id) AS event_matches
    FROM staff_attendance_requests AS r
    JOIN staff_attendance_events AS e
      ON e.attendance_id = r.attendance_id
     AND e.actor_id = r.decided_by
     AND e.source = 'manual'
     AND e.attendance_request_id IS NULL
     AND e.event_type = CASE
             WHEN r.action = 'correct' THEN r.mark || '_correction'
             WHEN r.mark = 'check_in' THEN 'attendance_voided'
             ELSE 'check_out_voided'
         END
     AND (
         e.reason = 'Solicitud del colaborador: ' || r.justification
         OR e.reason LIKE 'Solicitud del colaborador: ' || r.justification
            || ' · Nota del supervisor: %'
     )
    WHERE r.status = 'approved'
      AND r.decided_by IS NOT NULL
)
UPDATE staff_attendance_events
SET attendance_request_id = (
        SELECT candidates.request_id
        FROM candidates
        WHERE candidates.event_id = staff_attendance_events.id
          AND candidates.request_matches = 1
          AND candidates.event_matches = 1
    )
WHERE id IN (
    SELECT candidates.event_id
    FROM candidates
    WHERE candidates.request_matches = 1
      AND candidates.event_matches = 1
)
"""


def backfill_attendance_request_links(connection: sqlite3.Connection) -> int:
    """Link the approvals written before the column existed (migration 0064)."""
    connection.execute(BACKFILL_ATTENDANCE_REQUEST_LINKS)
    # ``rowcount`` stays -1 for an UPDATE with a CTE; ``changes()`` has the count.
    return connection.execute("SELECT changes()").fetchone()[0]


def ensure_added_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    """Add the columns a later migration introduced, returning the new ones."""
    present = column_names(connection, table)
    added: set[str] = set()
    for column, sql_type in ADDED_COLUMNS[table].items():
        if column in present:
            print(f"{table}.{column} already present")
            continue
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        added.add(column)
        print(f"Added {table}.{column}")
    return added


def main(reset_maintenance: bool) -> None:
    connection = sqlite3.connect(DB)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        tables = table_names(connection)
        added: set[tuple[str, str]] = set()

        for table in ADDED_COLUMNS:
            if table not in tables:
                continue
            for column in ensure_added_columns(connection, table):
                added.add((table, column))

        # Match the migration: requests that were already pending before the
        # term existed get the 24-hour default measured from their creation.
        if ("staff_attendance_requests", "due_at") in added:
            connection.execute(
                "UPDATE staff_attendance_requests "
                "SET due_at = datetime(created_at, '+24 hours') "
                "WHERE status = 'pending' AND due_at IS NULL"
            )

        # Match the migration's backfill: devices that existed before the column
        # get a full 90-day window instead of expiring retroactively.
        if "kiosk_devices" in tables and "token_expires_at" in column_names(
            connection, "kiosk_devices"
        ):
            connection.execute(
                "UPDATE kiosk_devices "
                "SET token_expires_at = datetime('now', '+90 days') "
                "WHERE token_expires_at IS NULL"
            )

        for table, columns in RELAXED_COLUMNS.items():
            if table in tables:
                relax_columns(connection, table, columns)

        for table, replacements in CHECK_UPGRADES.items():
            if table in tables:
                upgrade_checks(
                    connection,
                    table,
                    replacements,
                    ADDED_CONSTRAINTS.get(table, ()),
                )

        if "staff_attendance" in tables:
            relax_attendance_shift_uniqueness(connection)
        if "staff_attendance_events" in tables:
            ensure_attendance_event_indexes(connection)
            if "staff_attendance_requests" in tables:
                linked = backfill_attendance_request_links(connection)
                print(f"Linked {linked} attendance events to their request")
        if "staff_attendance_requests" in tables:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_staff_attendance_requests_status_due "
                "ON staff_attendance_requests (status, due_at)"
            )

        seed_preview_permissions(connection)

        # The unique constraint that makes offline sale sync idempotent. SQLite
        # cannot add a table constraint in place, but a unique index has the
        # same effect and ``create_all`` builds the real constraint on a fresh
        # database.
        if "sales" in tables:
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_client_reference "
                "ON sales (client_reference)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_sales_origin ON sales (origin)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_sales_class_reservation "
                "ON sales (class_reservation_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_sales_physio_appointment "
                "ON sales (physio_appointment_id)"
            )
        if "physio_appointments" in tables:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_physio_appointments_room "
                "ON physio_appointments (room_id)"
            )
        if "payments" in tables:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_payments_cash_session "
                "ON payments (cash_session_id)"
            )
        if "invoices" in tables:
            connection.execute("DROP INDEX IF EXISTS uq_invoices_active_origin")
            connection.execute(
                "CREATE UNIQUE INDEX uq_invoices_active_origin "
                "ON invoices (origin_type, origin_id) "
                "WHERE status <> 'cancelled' AND origin_type <> 'credit_note'"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_active_global_period "
                "ON invoices (global_year, global_month) "
                "WHERE origin_type = 'global' AND status <> 'cancelled'"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_invoices_related "
                "ON invoices (related_invoice_id)"
            )

        if reset_maintenance:
            if "exercises" in tables:
                connection.execute("UPDATE exercises SET equipment_id = NULL")
                print("Cleared exercises.equipment_id links")
            for table in MAINTENANCE_TABLES:
                if table in tables:
                    connection.execute(f"DROP TABLE {table}")
                    print(f"Dropped {table}")

        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main("--reset-maintenance" in sys.argv[1:]))
