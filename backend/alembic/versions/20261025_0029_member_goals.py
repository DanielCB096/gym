"""Member progress goals for body measurements.

A goal stores one target for one measurement (weight, waist, chest or body
fat), the starting value frozen when it was created and the status
(``active``/``achieved``/``cancelled``). Progress is calculated against the
latest measurement; a new measurement closes the goal automatically when it
meets the target. Only one active goal per member and metric is allowed, but
achieved and cancelled rows stay as history.

Revision ID: 20261025_0029
Revises: 20261025_0028
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261025_0029"
down_revision = "20261025_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(length=24), nullable=False),
        sa.Column("direction", sa.String(length=12), nullable=False),
        sa.Column("target_value", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("baseline_value", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("baseline_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("achieved_value", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "metric IN ('weight_kg', 'waist_cm', 'chest_cm', 'body_fat_percent')",
            name="ck_member_goals_metric",
        ),
        sa.CheckConstraint(
            "direction IN ('decrease', 'increase')",
            name="ck_member_goals_direction",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'achieved', 'cancelled')",
            name="ck_member_goals_status",
        ),
        sa.CheckConstraint("target_value > 0", name="ck_member_goals_target_positive"),
        sa.CheckConstraint(
            "baseline_value IS NULL OR baseline_value >= 0",
            name="ck_member_goals_baseline_nonnegative",
        ),
        sa.CheckConstraint(
            "achieved_value IS NULL OR achieved_value >= 0",
            name="ck_member_goals_achieved_nonnegative",
        ),
        sa.CheckConstraint(
            "achieved_at IS NULL OR status = 'achieved'",
            name="ck_member_goals_achieved_state",
        ),
        sa.CheckConstraint(
            "status <> 'achieved' OR achieved_at IS NOT NULL",
            name="ck_member_goals_achieved_date",
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' OR cancelled_at IS NOT NULL",
            name="ck_member_goals_cancelled_date",
        ),
    )
    op.create_index(
        "ix_member_goals_member_status",
        "member_goals",
        ["member_id", "status", "created_at"],
    )
    op.create_index(
        "uq_member_goals_active_metric",
        "member_goals",
        ["member_id", "metric"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    has_goals = op.get_bind().execute(
        sa.text("SELECT 1 FROM member_goals LIMIT 1")
    ).first()
    if has_goals is not None:
        raise RuntimeError(
            "No se puede revertir la migración mientras existan metas de socios."
        )
    op.drop_index("uq_member_goals_active_metric", table_name="member_goals")
    op.drop_index("ix_member_goals_member_status", table_name="member_goals")
    op.drop_table("member_goals")
