"""Let the member switch the phone off by kind of notice.

The inbox already holds every notice; this revision adds the missing choice
between "tell me in the app" and "also ring my phone". One row per member and
category stores the switch the member moved; a missing row means enabled, so the
table only holds decisions and a new category starts on by default.

Revision ID: 20261031_0071
Revises: 20261031_0070
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0071"
down_revision = "20261031_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column(
            "push_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
            name="fk_member_notification_preferences_member",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "member_id",
            "category",
            name="uq_member_notification_preferences_member_category",
        ),
        sa.CheckConstraint(
            "category IN ('membership', 'classes', 'training', 'billing', "
            "'equipment', 'physio')",
            name="ck_member_notification_preferences_category",
        ),
    )


def downgrade() -> None:
    op.drop_table("member_notification_preferences")
