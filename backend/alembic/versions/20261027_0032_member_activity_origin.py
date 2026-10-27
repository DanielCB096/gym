"""Origin of workouts and measurements: staff panel or member app.

Both tables keep ``origin`` so the trainer can tell apart what the member
recorded from the app. Rows created before this migration are staff records.

Revision ID: 20261027_0032
Revises: 20261027_0031
"""

from alembic import op
import sqlalchemy as sa

revision = "20261027_0032"
down_revision = "20261027_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workout_logs",
        sa.Column(
            "origin",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'staff'"),
        ),
    )
    op.add_column(
        "body_measurements",
        sa.Column(
            "origin",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'staff'"),
        ),
    )
    op.create_check_constraint(
        "ck_workout_logs_origin",
        "workout_logs",
        "origin IN ('staff', 'app')",
    )
    op.create_check_constraint(
        "ck_body_measurements_origin",
        "body_measurements",
        "origin IN ('staff', 'app')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_body_measurements_origin", "body_measurements", type_="check")
    op.drop_constraint("ck_workout_logs_origin", "workout_logs", type_="check")
    op.drop_column("body_measurements", "origin")
    op.drop_column("workout_logs", "origin")
