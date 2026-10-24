"""Link a statement delivery retry to its original attempt.

The delivery log is append-only: retrying a failed or preview delivery creates a
new row instead of rewriting the old one. ``retry_of_id`` keeps that chain so the
panel can show which attempt was retried without losing the failure history.

Revision ID: 20261019_0021
Revises: 20261019_0020
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_0021"
down_revision = "20261019_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "member_account_statement_deliveries",
        sa.Column("retry_of_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_member_account_statement_deliveries_retry_of",
        "member_account_statement_deliveries",
        "member_account_statement_deliveries",
        ["retry_of_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_member_account_statement_deliveries_retry_of",
        "member_account_statement_deliveries",
        type_="foreignkey",
    )
    op.drop_column("member_account_statement_deliveries", "retry_of_id")
