"""Allowed entry hours per membership plan for the reception kiosk.

The access engine already had ``AccessWindow`` and the schedule check, but the
kiosk always passed ``allowed_windows=None`` because no plan could hold one.
This table stores the windows in club local time: ``weekday`` follows
``datetime.weekday()`` (Monday is 0) and an end earlier than the start crosses
midnight. A plan with no rows stays open all day, so the migration needs no
backfill and changes no decision by itself.

Revision ID: 20261029_0047
Revises: 20261029_0046
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261029_0047"
down_revision = "20261029_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_access_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "weekday >= 0 AND weekday <= 6", name="ck_plan_access_windows_weekday"
        ),
        sa.CheckConstraint(
            "starts_at <> ends_at", name="ck_plan_access_windows_span"
        ),
        sa.UniqueConstraint(
            "plan_id",
            "weekday",
            "starts_at",
            "ends_at",
            name="uq_plan_access_windows_slot",
        ),
    )
    op.create_index(
        "ix_plan_access_windows_plan_id", "plan_access_windows", ["plan_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_plan_access_windows_plan_id", table_name="plan_access_windows"
    )
    op.drop_table("plan_access_windows")
