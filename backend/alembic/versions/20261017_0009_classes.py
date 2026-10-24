"""Create the class schedule and reservations tables.

Adds the class catalog (``class_types``, ``class_rooms``), the scheduled
occurrences (``class_sessions``) and the roster (``class_reservations``). The
roster row carries the whole member lifecycle — waitlist, seat, attendance and
cancellation — so attendance stays 1:1 with the reservation.

The ``classes.read`` / ``classes.manage`` permissions already exist since the
identity RBAC migration (``20261015_0002``) and are granted to owner, manager
and trainer, so this revision does not touch permissions.

Revision ID: 20261017_0009
Revises: 20261017_0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261017_0009"
down_revision = "20261017_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "class_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_class_types_name_lower", "class_types", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "class_rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("capacity > 0", name="ck_class_rooms_capacity_positive"),
    )
    op.create_index("uq_class_rooms_name_lower", "class_rooms", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "class_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("class_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="scheduled", nullable=False),
        sa.Column("access_type", sa.String(length=16), server_default="included", nullable=False),
        sa.Column("extra_price_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("waitlist_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("cancel_window_hours", sa.Integer(), server_default="4", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_class_sessions_time_order"),
        sa.CheckConstraint("capacity > 0", name="ck_class_sessions_capacity_positive"),
        sa.CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_class_sessions_status"),
        sa.CheckConstraint("access_type IN ('included', 'premium')", name="ck_class_sessions_access_type"),
        sa.CheckConstraint("extra_price_cents >= 0", name="ck_class_sessions_price_nonnegative"),
        sa.CheckConstraint("cancel_window_hours >= 0", name="ck_class_sessions_window_nonnegative"),
        sa.ForeignKeyConstraint(["class_type_id"], ["class_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["room_id"], ["class_rooms.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instructor_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cancelled_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_class_sessions_start", "class_sessions", ["starts_at"])
    op.create_index("ix_class_sessions_status_start", "class_sessions", ["status", "starts_at"])
    op.create_index("ix_class_sessions_room_start", "class_sessions", ["room_id", "starts_at"])
    op.create_index("ix_class_sessions_instructor_start", "class_sessions", ["instructor_id", "starts_at"])

    op.create_table(
        "class_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="reserved", nullable=False),
        sa.Column("origin", sa.String(length=16), server_default="reception", nullable=False),
        sa.Column("waitlist_position", sa.Integer(), nullable=True),
        sa.Column("late_cancellation", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('waitlist', 'reserved', 'attended', 'no_show', 'cancelled')",
            name="ck_class_reservations_status",
        ),
        sa.CheckConstraint("origin IN ('app', 'reception', 'web')", name="ck_class_reservations_origin"),
        sa.CheckConstraint(
            "waitlist_position IS NULL OR waitlist_position > 0",
            name="ck_class_reservations_position_positive",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["class_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cancelled_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["marked_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_class_reservations_active",
        "class_reservations",
        ["session_id", "member_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('waitlist', 'reserved', 'attended')"),
    )
    op.create_index(
        "ix_class_reservations_session_status", "class_reservations", ["session_id", "status"]
    )
    op.create_index(
        "ix_class_reservations_member_time", "class_reservations", ["member_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_class_reservations_member_time", table_name="class_reservations")
    op.drop_index("ix_class_reservations_session_status", table_name="class_reservations")
    op.drop_index("uq_class_reservations_active", table_name="class_reservations")
    op.drop_table("class_reservations")
    op.drop_index("ix_class_sessions_instructor_start", table_name="class_sessions")
    op.drop_index("ix_class_sessions_room_start", table_name="class_sessions")
    op.drop_index("ix_class_sessions_status_start", table_name="class_sessions")
    op.drop_index("ix_class_sessions_start", table_name="class_sessions")
    op.drop_table("class_sessions")
    op.drop_index("uq_class_rooms_name_lower", table_name="class_rooms")
    op.drop_table("class_rooms")
    op.drop_index("uq_class_types_name_lower", table_name="class_types")
    op.drop_table("class_types")
