"""Optional daily entry limit per membership plan.

The kiosk already asks the access engine for a decision; this column gives the
plan the only policy input it was missing. ``NULL`` keeps a plan unlimited, so
existing rows need no backfill.

Revision ID: 20261028_0043
Revises: 20261028_0042
"""

from alembic import op
import sqlalchemy as sa

revision = "20261028_0043"
down_revision = "20261028_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans", sa.Column("daily_entry_limit", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_plans_daily_entry_limit",
        "plans",
        "daily_entry_limit IS NULL OR daily_entry_limit >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_plans_daily_entry_limit", "plans", type_="check")
    op.drop_column("plans", "daily_entry_limit")
