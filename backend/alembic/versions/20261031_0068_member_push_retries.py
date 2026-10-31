"""Retry a failed member push automatically in the next pass.

A push that fails on a transport error is not final any more: the row keeps a
``next_attempt_at`` so a later pass tries again after a growing wait, up to a
fixed number of attempts. The status/next pair gets its own index because the
pass filters exactly on those two columns to find the retries that are due.

Revision ID: 20261031_0068
Revises: 20261031_0067
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0068"
down_revision = "20261031_0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "member_push_deliveries",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_member_push_deliveries_status_next",
        "member_push_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_member_push_deliveries_status_next",
        table_name="member_push_deliveries",
    )
    op.drop_column("member_push_deliveries", "next_attempt_at")
