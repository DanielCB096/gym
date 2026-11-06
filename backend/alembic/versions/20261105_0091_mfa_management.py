"""Add the pending secret used to rotate or enable MFA without locking out.

Revision ID: 20261105_0091
Revises: 20261103_0090
"""

import sqlalchemy as sa
from alembic import op


revision = "20261105_0091"
down_revision = "20261103_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_users",
        sa.Column("mfa_pending_secret_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "app_users",
        sa.Column("mfa_pending_created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_users", "mfa_pending_created_at")
    op.drop_column("app_users", "mfa_pending_secret_encrypted")
