"""Give each member their own silence window for pushes.

The club's window (ADR-061) silences everyone at once. This table stores one
optional pair of hours per member, interpreted in the club's time zone: while
the clock is inside it, that member's waiting pushes stay in the queue and the
next pass after it sends them.

Revision ID: 20261031_0074
Revises: 20261031_0073
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0074"
down_revision = "20261031_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_notification_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("quiet_start", sa.Time(), nullable=True),
        sa.Column("quiet_end", sa.Time(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name="fk_member_notification_settings_member",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "member_id",
            name="uq_member_notification_settings_member",
        ),
        sa.CheckConstraint(
            "(quiet_start IS NULL AND quiet_end IS NULL) OR "
            "(quiet_start IS NOT NULL AND quiet_end IS NOT NULL "
            "AND quiet_start <> quiet_end)",
            name="ck_member_notification_settings_quiet_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("member_notification_settings")
