"""Let a staff notice be closed once the work it announced is done.

The trainer's inbox reports a workout as pending until someone reviews it, but
the notice had no way of knowing that the review already happened: the item
stayed in the list and in the badge forever. ``resolved_at`` is written by the
service that completes the work (the routine review) and is what makes the
inbox stop reporting an item the panel already attended. It is separate from
``read_at`` so the two states remain distinguishable: a notice can be read and
still pending, or resolved without the reader having opened it.

Revision ID: 20261029_0054
Revises: 20261029_0053
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0054"
down_revision = "20261029_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff_notifications",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("staff_notifications", "resolved_at")
