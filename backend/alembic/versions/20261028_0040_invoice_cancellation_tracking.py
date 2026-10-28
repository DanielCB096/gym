"""Track cancellations that the SAT leaves in process.

A cancellation answered with ``202`` means the request is still pending at the
SAT: the invoice stays ``stamped`` and, until now, nothing recorded that a
request had been sent. These columns keep the request and the last time the
state was queried, so the operator can follow it instead of sending a blind
retry.

Revision ID: 20261028_0040
Revises: 20261028_0039
"""

from alembic import op
import sqlalchemy as sa

revision = "20261028_0040"
down_revision = "20261028_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("cancellation_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "cancellation_checked_at")
    op.drop_column("invoices", "cancellation_requested_at")
