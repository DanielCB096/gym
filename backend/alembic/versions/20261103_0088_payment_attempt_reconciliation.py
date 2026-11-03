"""Track payment reconciliation attempts for scheduled renewals.

Revision ID: 20261103_0088
Revises: 20261102_0087
"""

import sqlalchemy as sa
from alembic import op


revision = "20261103_0088"
down_revision = "20261102_0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_attempts",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_payment_attempts_status_reconciled",
        "payment_attempts",
        ["status", "last_reconciled_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_attempts_status_reconciled",
        table_name="payment_attempts",
    )
    op.drop_column("payment_attempts", "last_reconciled_at")
