"""Member notification inbox fed by domain events.

Reception, trainers and the schedule already change things the member owns: a
workout gets reviewed, a goal is reached or cancelled, a waitlist spot opens up,
the membership is about to expire. This table turns those events into Spanish
messages the app can show in one place.

``dedupe_key`` is only used by producers that may run repeatedly for the same
fact (the expiring-membership reminder, once per 7/3/1-day window). The unique
index is partial so the many one-shot event rows, which leave it NULL, are never
compared with each other.

Revision ID: 20261027_0035
Revises: 20261027_0034
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_0035"
down_revision = "20261027_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
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
            "kind IN ('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring')",
            name="ck_member_notifications_kind",
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 140",
            name="ck_member_notifications_title_length",
        ),
        sa.CheckConstraint(
            "length(body) BETWEEN 1 AND 500",
            name="ck_member_notifications_body_length",
        ),
    )
    op.create_index(
        "ix_member_notifications_member_time",
        "member_notifications",
        ["member_id", "created_at"],
    )
    op.create_index(
        "ix_member_notifications_member_unread",
        "member_notifications",
        ["member_id", "read_at"],
    )
    op.create_index(
        "ix_member_notifications_dedupe",
        "member_notifications",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
        sqlite_where=sa.text("dedupe_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_member_notifications_dedupe", table_name="member_notifications")
    op.drop_index("ix_member_notifications_member_unread", table_name="member_notifications")
    op.drop_index("ix_member_notifications_member_time", table_name="member_notifications")
    op.drop_table("member_notifications")
