"""Queue and deliver Web Push to the browsers the staff uses.

The panel's accounts work in a browser, so their notices reach them through the
Web Push protocol instead of Expo. A subscription is one browser profile that
opted in; a delivery is one push queued for one notice and one subscription,
written with the notice itself. The endpoint of a delivery is a snapshot so the
history still says where the attempt went after the subscription is retired.

Revision ID: 20261031_0076
Revises: 20261031_0074
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0076"
down_revision = "20261031_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_push_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=200), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_users.id"],
            name="fk_staff_push_subscriptions_user",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "endpoint",
            name="uq_staff_push_subscriptions_endpoint",
        ),
    )
    op.create_index(
        "ix_staff_push_subscriptions_user_active",
        "staff_push_subscriptions",
        ["user_id", "active"],
    )
    op.create_table(
        "staff_push_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notice_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["notice_id"],
            ["staff_notifications.id"],
            name="fk_staff_push_deliveries_notice",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_users.id"],
            name="fk_staff_push_deliveries_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["staff_push_subscriptions.id"],
            name="fk_staff_push_deliveries_subscription",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed')",
            name="ck_staff_push_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_staff_push_deliveries_attempts",
        ),
        sa.UniqueConstraint(
            "notice_id",
            "subscription_id",
            name="uq_staff_push_deliveries_notice_subscription",
        ),
    )
    op.create_index(
        "ix_staff_push_deliveries_status_created",
        "staff_push_deliveries",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staff_push_deliveries_status_created",
        table_name="staff_push_deliveries",
    )
    op.drop_table("staff_push_deliveries")
    op.drop_index(
        "ix_staff_push_subscriptions_user_active",
        table_name="staff_push_subscriptions",
    )
    op.drop_table("staff_push_subscriptions")
