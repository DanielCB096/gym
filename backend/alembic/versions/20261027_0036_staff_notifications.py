"""Staff notification inbox fed by domain events.

The member got an inbox on 2026-10-27; this is the other half of the same
conversation. A workout logged from the app is work waiting on a trainer, and a
maintenance ticket with a name on it is work waiting on a technician. Neither
was announced anywhere except the panel's sample-data bell.

The row shape mirrors ``member_notifications`` on purpose: a frozen Spanish
snapshot, an untyped ``ref_id`` for deep-linking and a partial unique
``dedupe_key`` for producers that may run twice for the same fact. The owner is
an ``app_users`` account because that is what signs in to the panel; the
employee a trainer-owned assignment or a ticket points at is resolved to that
account when the notice is emitted, and the notice is skipped when the employee
has no active account.

Revision ID: 20261027_0036
Revises: 20261027_0035
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_0036"
down_revision = "20261027_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('workout_pending_review', 'maintenance_ticket_assigned')",
            name="ck_staff_notifications_kind",
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 140",
            name="ck_staff_notifications_title_length",
        ),
        sa.CheckConstraint(
            "length(body) BETWEEN 1 AND 500",
            name="ck_staff_notifications_body_length",
        ),
    )
    op.create_index(
        "ix_staff_notifications_user_time",
        "staff_notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_staff_notifications_user_unread",
        "staff_notifications",
        ["user_id", "read_at"],
    )
    op.create_index(
        "ix_staff_notifications_dedupe",
        "staff_notifications",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
        sqlite_where=sa.text("dedupe_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_staff_notifications_dedupe", table_name="staff_notifications")
    op.drop_index("ix_staff_notifications_user_unread", table_name="staff_notifications")
    op.drop_index("ix_staff_notifications_user_time", table_name="staff_notifications")
    op.drop_table("staff_notifications")
