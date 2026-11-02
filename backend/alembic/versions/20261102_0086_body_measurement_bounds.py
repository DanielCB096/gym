"""Cap body measurement weight and circumferences in the database.

Revision ID: 20261102_0086
Revises: 20261102_0085
"""

from alembic import op

revision = "20261102_0086"
down_revision = "20261102_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_body_measurements_weight_max",
        "body_measurements",
        "weight_kg IS NULL OR weight_kg <= 500",
    )
    op.create_check_constraint(
        "ck_body_measurements_waist_max",
        "body_measurements",
        "waist_cm IS NULL OR waist_cm <= 400",
    )
    op.create_check_constraint(
        "ck_body_measurements_chest_max",
        "body_measurements",
        "chest_cm IS NULL OR chest_cm <= 400",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_body_measurements_chest_max",
        "body_measurements",
        type_="check",
    )
    op.drop_constraint(
        "ck_body_measurements_waist_max",
        "body_measurements",
        type_="check",
    )
    op.drop_constraint(
        "ck_body_measurements_weight_max",
        "body_measurements",
        type_="check",
    )
