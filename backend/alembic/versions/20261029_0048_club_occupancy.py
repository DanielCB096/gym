"""Estimated club occupancy for the reception kiosk.

The engine already denied entries with ``occupancy_full``, but the kiosk always
sent ``current_occupancy=0`` and ``max_occupancy=1`` because nothing counted how
many members were inside. The kiosk only records entries, so a visit is assumed
to end after ``occupancy_window_seconds`` (two hours by default): a member
counts as inside while their latest authorized entry —from the kiosk or from
reception— falls inside that window, and scanning again refreshes it.
``max_occupancy`` is NULL by default, which keeps the rule disabled and changes
no decision until the club sets a number.

Revision ID: 20261029_0048
Revises: 20261029_0047
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0048"
down_revision = "20261029_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "access_settings",
        sa.Column("max_occupancy", sa.Integer(), nullable=True),
    )
    op.add_column(
        "access_settings",
        sa.Column(
            "occupancy_window_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("7200"),
        ),
    )
    op.create_check_constraint(
        "ck_access_settings_max_occupancy",
        "access_settings",
        "max_occupancy IS NULL OR (max_occupancy >= 1 AND max_occupancy <= 10000)",
    )
    op.create_check_constraint(
        "ck_access_settings_occupancy_window",
        "access_settings",
        "occupancy_window_seconds >= 300 AND occupancy_window_seconds <= 86400",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_access_settings_occupancy_window", "access_settings", type_="check"
    )
    op.drop_constraint(
        "ck_access_settings_max_occupancy", "access_settings", type_="check"
    )
    op.drop_column("access_settings", "occupancy_window_seconds")
    op.drop_column("access_settings", "max_occupancy")
