"""Add administrative MFA state and temporary login challenges.

Revision ID: 20261103_0089
Revises: 20261103_0088
"""

import sqlalchemy as sa
from alembic import op


revision = "20261103_0089"
down_revision = "20261103_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_users", sa.Column("mfa_secret_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column("app_users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "mfa_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("challenge_sha256", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_sha256", name="uq_mfa_challenges_challenge_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_mfa_challenges_expiry_order"),
    )
    op.create_index(
        "ix_mfa_challenges_user_expiry",
        "mfa_challenges",
        ["user_id", "expires_at", "used_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mfa_challenges_user_expiry", table_name="mfa_challenges")
    op.drop_table("mfa_challenges")
    op.drop_column("app_users", "mfa_enabled_at")
    op.drop_column("app_users", "mfa_secret_encrypted")
    op.drop_column("app_users", "mfa_enabled")
