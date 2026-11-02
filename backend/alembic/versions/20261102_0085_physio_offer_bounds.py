"""Cap physiotherapy offer sessions and validity in the database.

Revision ID: 20261102_0085
Revises: 20261102_0084
"""

from alembic import op

revision = "20261102_0085"
down_revision = "20261102_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_physio_offers_sessions_max",
        "physio_offers",
        "sessions <= 52",
    )
    op.create_check_constraint(
        "ck_physio_offers_validity_max",
        "physio_offers",
        "validity_days <= 366",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_physio_offers_validity_max",
        "physio_offers",
        type_="check",
    )
    op.drop_constraint(
        "ck_physio_offers_sessions_max",
        "physio_offers",
        type_="check",
    )
