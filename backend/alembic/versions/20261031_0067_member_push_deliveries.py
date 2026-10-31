"""Give the member app a queue of push notifications.

The notices already reach the member inbox inside the app; this revision adds
the way to also ring the phone. A token is one installation, so a member may
have several and a device that changes accounts moves the token to the new
member. The delivery row is written in the same transaction as the notice, one
per active token, and keeps the token as a snapshot so a retired device still
explains where an attempt went.

Revision ID: 20261031_0067
Revises: 20261031_0066
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0067"
down_revision = "20261031_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_push_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=8), nullable=False),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
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
            ["member_id"],
            ["members.id"],
            name="fk_member_push_tokens_member",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("token", name="uq_member_push_tokens_token"),
        sa.CheckConstraint(
            "platform IN ('ios', 'android')",
            name="ck_member_push_tokens_platform",
        ),
    )
    op.create_index(
        "ix_member_push_tokens_member_active",
        "member_push_tokens",
        ["member_id", "active"],
    )

    op.create_table(
        "member_push_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
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
            name="fk_member_push_deliveries_notification",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name="fk_member_push_deliveries_member",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "notification_id",
            "token",
            name="uq_member_push_deliveries_notification_token",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed')",
            name="ck_member_push_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_member_push_deliveries_attempts"
        ),
    )
    op.create_index(
        "ix_member_push_deliveries_status_created",
        "member_push_deliveries",
        ["status", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    deliveries = bind.execute(
        sa.text("SELECT count(*) FROM member_push_deliveries")
    ).scalar()
    if deliveries:
        raise RuntimeError(
            "No se puede revertir mientras existan envíos push "
            f"({deliveries}); se perdería la trazabilidad de los avisos"
        )

    op.drop_index(
        "ix_member_push_deliveries_status_created",
        table_name="member_push_deliveries",
    )
    op.drop_table("member_push_deliveries")
    op.drop_index(
        "ix_member_push_tokens_member_active",
        table_name="member_push_tokens",
    )
    op.drop_table("member_push_tokens")
