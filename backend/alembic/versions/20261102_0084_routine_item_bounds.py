"""Cap routine item sets and rest in the database.

Revision ID: 20261102_0084
Revises: 20261102_0083
"""

from alembic import op

revision = "20261102_0084"
down_revision = "20261102_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_routine_items_sets_max",
        "routine_items",
        "sets <= 50",
    )
    op.create_check_constraint(
        "ck_routine_items_rest_max",
        "routine_items",
        "rest_seconds IS NULL OR rest_seconds <= 1800",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_routine_items_rest_max",
        "routine_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_routine_items_sets_max",
        "routine_items",
        type_="check",
    )
