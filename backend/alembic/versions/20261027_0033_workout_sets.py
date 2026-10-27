"""Per-set workout detail: repetitions and weight of every performed set.

Sets are optional and always tied to an existing workout log. The exercise must
belong to the routine version frozen in the assignment, which is validated by
the service; the database keeps the unique ``(workout, exercise, set_number)``
line and the numeric ranges as a second line of defense.

Revision ID: 20261027_0033
Revises: 20261027_0032
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_0033"
down_revision = "20261027_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workout_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workout_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workout_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exercises.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("set_number > 0", name="ck_workout_sets_number_positive"),
        sa.CheckConstraint("reps >= 1 AND reps <= 100", name="ck_workout_sets_reps_range"),
        sa.CheckConstraint(
            "weight_kg IS NULL OR (weight_kg >= 0 AND weight_kg <= 1000)",
            name="ck_workout_sets_weight_range",
        ),
    )
    op.create_index(
        "uq_workout_sets_line",
        "workout_sets",
        ["workout_id", "exercise_id", "set_number"],
        unique=True,
    )
    op.create_index("ix_workout_sets_workout", "workout_sets", ["workout_id"])


def downgrade() -> None:
    op.drop_index("ix_workout_sets_workout", table_name="workout_sets")
    op.drop_index("uq_workout_sets_line", table_name="workout_sets")
    op.drop_table("workout_sets")
