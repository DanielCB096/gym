"""Add independent member email preferences and queued deliveries.

Revision ID: 20261031_0078
Revises: 20261031_0077
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0078"
down_revision = "20261031_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "member_notification_preferences",
        sa.Column(
            "email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "member_notification_email_preference_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "consent_version", sa.String(length=40), nullable=False
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name="fk_member_notification_email_preference_events_member",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "category IN ('membership', 'classes', 'billing', 'equipment', 'physio')",
            name="ck_member_notification_email_preference_events_category",
        ),
    )
    op.create_index(
        "ix_member_notification_email_preference_events_member_changed",
        "member_notification_email_preference_events",
        ["member_id", "changed_at"],
    )
    op.create_table(
        "member_notification_email_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column("message_id", sa.String(length=320), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["member_notifications.id"],
            name="fk_member_notification_email_deliveries_notification",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name="fk_member_notification_email_deliveries_member",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "notification_id",
            name="uq_member_notification_email_deliveries_notification",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed', 'cancelled')",
            name="ck_member_notification_email_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_member_notification_email_deliveries_attempts",
        ),
    )
    op.create_index(
        "ix_member_notification_email_deliveries_status_created",
        "member_notification_email_deliveries",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_member_notification_email_deliveries_message_id",
        "member_notification_email_deliveries",
        ["message_id"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    event_count = bind.execute(
        sa.text("SELECT count(*) FROM member_notification_email_preference_events")
    ).scalar()
    delivery_count = bind.execute(
        sa.text("SELECT count(*) FROM member_notification_email_deliveries")
    ).scalar()
    enabled_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notification_preferences "
            "WHERE email_enabled = true"
        )
    ).scalar()
    if event_count or delivery_count or enabled_count:
        raise RuntimeError(
            "No se puede retirar el correo de avisos del socio mientras haya "
            f"consentimientos ({event_count}), entregas ({delivery_count}) o "
            f"preferencias activas ({enabled_count}); conserva o archiva esos datos primero."
        )
    op.drop_index(
        "ix_member_notification_email_deliveries_message_id",
        table_name="member_notification_email_deliveries",
    )
    op.drop_index(
        "ix_member_notification_email_deliveries_status_created",
        table_name="member_notification_email_deliveries",
    )
    op.drop_table("member_notification_email_deliveries")
    op.drop_index(
        "ix_member_notification_email_preference_events_member_changed",
        table_name="member_notification_email_preference_events",
    )
    op.drop_table("member_notification_email_preference_events")
    op.drop_column("member_notification_preferences", "email_enabled")
