"""Cap the duration of a physiotherapy service in the database.

Revision ID: 20261102_0083
Revises: 20261101_0082
"""

from alembic import op

revision = "20261102_0083"
down_revision = "20261101_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_physio_services_duration_max",
        "physio_services",
        "duration_minutes <= 480",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_physio_services_duration_max",
        "physio_services",
        type_="check",
    )
