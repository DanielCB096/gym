"""Link exercises to a specific equipment.

The routines spec says an exercise may declare which machine it needs so that a
plan can be flagged when that machine is out of service. Until now the library
carried only the free-text ``equipment_name``. This revision adds an optional
``exercises.equipment_id`` reference to ``equipment``.

The link is optional and set to NULL if the equipment row ever disappears, so an
exercise is never lost by a maintenance action.

Revision ID: 20261017_0014
Revises: 20261017_0013
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261017_0014"
down_revision = "20261017_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exercises",
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_exercises_equipment",
        "exercises",
        "equipment",
        ["equipment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_exercises_equipment", "exercises", ["equipment_id"])


def downgrade() -> None:
    op.drop_index("ix_exercises_equipment", table_name="exercises")
    op.drop_constraint("fk_exercises_equipment", "exercises", type_="foreignkey")
    op.drop_column("exercises", "equipment_id")
