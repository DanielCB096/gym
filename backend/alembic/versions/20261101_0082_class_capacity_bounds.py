"""Cap the class capacity and the cancellation window in the schema.

``capacity > 0`` and ``cancel_window_hours >= 0`` were all the database knew: the
``500`` and the ``168`` the panel enforces lived only in the request models, so
any other writer —a seed, a script, a future CLI— could store a room for two
thousand people or a window longer than a year and nothing would object. The
ceilings are declared in ``classes/models.py`` and this migration freezes the SQL
they produced; the tests pin both against each other.

They are added as new constraints instead of widening ``..._capacity_positive`` so
the existing names keep describing what they check and the migration stays
additive: no row is rewritten and no existing constraint is revalidated.

Revision ID: 20261101_0082
Revises: 20261101_0081
"""

from alembic import op

revision = "20261101_0082"
down_revision = "20261101_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_class_rooms_capacity_max",
        "class_rooms",
        "capacity <= 500",
    )
    op.create_check_constraint(
        "ck_class_sessions_capacity_max",
        "class_sessions",
        "capacity <= 500",
    )
    op.create_check_constraint(
        "ck_class_sessions_window_max",
        "class_sessions",
        "cancel_window_hours <= 168",
    )


def downgrade() -> None:
    op.drop_constraint("ck_class_sessions_window_max", "class_sessions", type_="check")
    op.drop_constraint(
        "ck_class_sessions_capacity_max", "class_sessions", type_="check"
    )
    op.drop_constraint("ck_class_rooms_capacity_max", "class_rooms", type_="check")
