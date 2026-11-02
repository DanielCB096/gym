"""Add short-lived one-use member card setup flows.

Revision ID: 20261102_0087
Revises: 20261102_0086
"""

import sqlalchemy as sa
from alembic import op


revision = "20261102_0087"
down_revision = "20261102_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_payment_method_setups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payment_method_id", sa.Uuid(), nullable=True),
        sa.Column("payment_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'submitted', 'expired')",
            name="ck_member_payment_method_setups_status",
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_method_id"],
            ["payment_methods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_attempt_id"],
            ["payment_attempts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_member_payment_method_setups_token_digest"),
    )
    op.create_index(
        "ix_member_payment_method_setups_expiry",
        "member_payment_method_setups",
        ["status", "expires_at"],
    )
    op.create_index(
        "uq_member_payment_method_setups_pending_member",
        "member_payment_method_setups",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_member_payment_method_setups_pending_member",
        table_name="member_payment_method_setups",
    )
    op.drop_index(
        "ix_member_payment_method_setups_expiry",
        table_name="member_payment_method_setups",
    )
    op.drop_table("member_payment_method_setups")
