"""Shifts and attendance for the staff: the three tables the module always lacked.

``staffing`` shipped its models and its endpoints, the panel schedules shifts and
marks attendance from them, and the preview database has all three tables because
``create_all`` builds whatever the models declare. A database built with Alembic
never got them: the module arrived without a migration, so on PostgreSQL every
shift and attendance query would have failed with ``relation does not exist``.

This closes the gap for the schema a fresh database is expected to have, matching
column for column what the models already publish. The constraints travel with
the tables so the rules the service assumes (a shift that ends after it starts,
one attendance per shift, an append-only event log deduplicated by request id)
are enforced by the database too.

Revision ID: 20261027_0038
Revises: 20261027_0037
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_0038"
down_revision = "20261027_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_shifts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'scheduled'"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_staff_shifts_period_valid"),
        sa.CheckConstraint(
            "status IN ('scheduled', 'cancelled')", name="ck_staff_shifts_status"
        ),
    )
    op.create_index(
        "ix_staff_shifts_employee_start", "staff_shifts", ["employee_id", "starts_at"]
    )
    op.create_index("ix_staff_shifts_start_status", "staff_shifts", ["starts_at", "status"])

    op.create_table(
        "staff_attendance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shift_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_shifts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_in_source", sa.String(length=20), nullable=False),
        sa.Column(
            "check_in_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_source", sa.String(length=20), nullable=True),
        sa.Column(
            "check_out_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('present', 'late')", name="ck_staff_attendance_status"
        ),
        sa.CheckConstraint(
            "check_out_at IS NULL OR check_out_at >= check_in_at",
            name="ck_staff_attendance_checkout_order",
        ),
        sa.UniqueConstraint("shift_id", name="uq_staff_attendance_shift"),
    )
    op.create_index(
        "ix_staff_attendance_employee_checkin",
        "staff_attendance",
        ["employee_id", "check_in_at"],
    )

    op.create_table(
        "staff_attendance_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "attendance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_attendance.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "event_type IN ('check_in', 'check_out')",
            name="ck_staff_attendance_events_type",
        ),
        sa.CheckConstraint(
            "source IN ('staff_app', 'manual', 'access_reader')",
            name="ck_staff_attendance_events_source",
        ),
        sa.UniqueConstraint("request_id", name="uq_staff_attendance_events_request"),
    )
    op.create_index(
        "ix_staff_attendance_events_request_id", "staff_attendance_events", ["request_id"]
    )
    op.create_index(
        "ix_staff_attendance_events_attendance_time",
        "staff_attendance_events",
        ["attendance_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_staff_attendance_events_attendance_time", table_name="staff_attendance_events")
    op.drop_index("ix_staff_attendance_events_request_id", table_name="staff_attendance_events")
    op.drop_table("staff_attendance_events")
    op.drop_index("ix_staff_attendance_employee_checkin", table_name="staff_attendance")
    op.drop_table("staff_attendance")
    op.drop_index("ix_staff_shifts_start_status", table_name="staff_shifts")
    op.drop_index("ix_staff_shifts_employee_start", table_name="staff_shifts")
    op.drop_table("staff_shifts")
