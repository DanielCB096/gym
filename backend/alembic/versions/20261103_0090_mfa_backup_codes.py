"""Add MFA backup codes and challenge attempt limits.

Revision ID: 20261103_0090
Revises: 20261103_0089
"""

import sqlalchemy as sa
from alembic import op


revision = "20261103_0090"
down_revision = "20261103_0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mfa_challenges",
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_sha256", name="uq_mfa_backup_codes_hash"),
    )
    op.create_index(
        "ix_mfa_backup_codes_user_used",
        "mfa_backup_codes",
        ["user_id", "used_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mfa_backup_codes_user_used", table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")
    op.drop_column("mfa_challenges", "failed_attempts")
