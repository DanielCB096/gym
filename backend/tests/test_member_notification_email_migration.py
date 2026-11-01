"""The member email migration preserves the default-off and audit guarantees."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20261031_0078_member_notification_emails.py"
)
spec = importlib.util.spec_from_file_location(
    "member_notification_email_migration", MIGRATION_PATH
)
migration = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(migration)


def _create_base_schema(connection: Connection) -> None:
    connection.exec_driver_sql("CREATE TABLE members (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql(
        "CREATE TABLE member_notifications (id CHAR(32) PRIMARY KEY)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE member_notification_preferences ("
        "id CHAR(32) PRIMARY KEY, member_id CHAR(32), category VARCHAR(24), "
        "push_enabled BOOLEAN NOT NULL DEFAULT 1)"
    )


def _run_migration(connection: Connection, operation) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        operation()


def test_upgrade_defaults_existing_preferences_to_email_off() -> None:
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            _create_base_schema(connection)
            connection.exec_driver_sql(
                "INSERT INTO member_notification_preferences "
                "(id, member_id, category, push_enabled) "
                "VALUES ('p1', 'm1', 'classes', 1)"
            )
            _run_migration(connection, migration.upgrade)

            row = connection.exec_driver_sql(
                "SELECT push_enabled, email_enabled "
                "FROM member_notification_preferences WHERE id = 'p1'"
            ).fetchone()
            assert row == (1, 0)
            tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert "member_notification_email_preference_events" in tables
            assert "member_notification_email_deliveries" in tables
    finally:
        engine.dispose()


def test_downgrade_refuses_to_delete_consent_history() -> None:
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            _create_base_schema(connection)
            member_id = uuid4().hex
            event_id = uuid4().hex
            connection.exec_driver_sql(
                "INSERT INTO members (id) VALUES (?)", (member_id,)
            )
            _run_migration(connection, migration.upgrade)
            connection.exec_driver_sql(
                "INSERT INTO member_notification_email_preference_events "
                "(id, member_id, category, enabled, consent_version) "
                "VALUES (?, ?, 'classes', 1, 'v1')",
                (event_id, member_id),
            )

            with pytest.raises(RuntimeError, match="consentimientos"):
                _run_migration(connection, migration.downgrade)
    finally:
        engine.dispose()
