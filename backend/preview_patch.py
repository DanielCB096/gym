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
    },
    "members": {"credit_limit_cents": "BIGINT"},
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
)

# SQLite cannot alter a CHECK constraint in place, so a table that gains an
# allowed value is rebuilt: create the replacement under a temporary name, copy
# the rows, drop the old table and rename. ``foreign_keys`` is off for the
# duration, so the other tables keep pointing at the final name.
CHECK_UPGRADES = {
    "sales": (
        "CONSTRAINT ck_sales_payment_method CHECK (payment_method IN "
        "('cash', 'card', 'transfer'))",
        "CONSTRAINT ck_sales_payment_method CHECK (payment_method IN "
        "('cash', 'card', 'transfer', 'account'))",
    ),
    "sale_returns": (
        "CONSTRAINT ck_sale_returns_method CHECK (refund_method IN "
        "('cash', 'card', 'transfer'))",
        "CONSTRAINT ck_sale_returns_method CHECK (refund_method IN "
        "('cash', 'card', 'transfer', 'account'))",
    ),
    "payment_attempts": (
        "CONSTRAINT ck_payment_attempts_card_method_required CHECK "
        "(method <> 'card' OR payment_method_id IS NOT NULL)",
        "CONSTRAINT ck_payment_attempts_card_method_required CHECK "
        "(method <> 'card' OR payment_method_id IS NOT NULL OR provider IS NULL)",
    ),
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


def upgrade_check(
    connection: sqlite3.Connection, table: str, old_check: str, new_check: str
) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    if row is None or row[0] is None:
        return
    sql = row[0]
    if new_check in sql:
        print(f"{table}: CHECK already up to date")
        return
    if old_check not in sql:
        print(f"{table}: CHECK not found, leaving it untouched")
        return

    index_sql = [
        item[0]
        for item in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name = ? AND sql IS NOT NULL",
            (table,),
        ).fetchall()
    ]
    temporary = f"{table}__upgrade"
    create_sql = sql.replace(old_check, new_check)
    create_sql = create_sql.replace(f"CREATE TABLE {table} ", f"CREATE TABLE {temporary} ", 1)
    connection.execute(create_sql)
    connection.execute(f"INSERT INTO {temporary} SELECT * FROM {table}")
    connection.execute(f"DROP TABLE {table}")
    connection.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
    for statement in index_sql:
        connection.execute(statement)
    print(f"{table}: rebuilt with the new CHECK")


def main(reset_maintenance: bool) -> None:
    connection = sqlite3.connect(DB)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        tables = table_names(connection)

        for table, columns in ADDED_COLUMNS.items():
            if table not in tables:
                continue
            present = column_names(connection, table)
            for column, sql_type in columns.items():
                if column in present:
                    print(f"{table}.{column} already present")
                    continue
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
                print(f"Added {table}.{column}")

        for table, (old_check, new_check) in CHECK_UPGRADES.items():
            if table in tables:
                upgrade_check(connection, table, old_check, new_check)

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
        if "payments" in tables:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_payments_cash_session "
                "ON payments (cash_session_id)"
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
