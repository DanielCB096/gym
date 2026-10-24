"""Add the access_events table.

Persists access decisions (reader or manual) so the admin panel can show the
access log and today's counters. ``event_id`` is the device-side identifier and
is unique to keep offline synchronisation idempotent.

Revision ID: 20261016_0004
Revises: 20261016_0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261016_0004"
down_revision = "20261016_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reader_id", sa.String(length=80), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("authorized", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="reader", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offline", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("direction IN ('entry', 'exit')", name="ck_access_events_direction"),
        sa.CheckConstraint("source IN ('reader', 'manual')", name="ck_access_events_source"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("event_id", name="uq_access_events_event_id"),
    )
    op.create_index("ix_access_events_occurred_at", "access_events", ["occurred_at"])
    op.create_index("ix_access_events_member_occurred", "access_events", ["member_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_access_events_member_occurred", table_name="access_events")
    op.drop_index("ix_access_events_occurred_at", table_name="access_events")
    op.drop_table("access_events")
