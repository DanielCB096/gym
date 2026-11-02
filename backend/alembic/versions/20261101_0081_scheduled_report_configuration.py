"""Persist scheduled report recipients and change history.

Revision ID: 20261101_0081
Revises: 20261101_0080
"""

from alembic import op
import sqlalchemy as sa

revision = "20261101_0081"
down_revision = "20261101_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_report_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_scheduled_report_configurations_singleton"),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scheduled_report_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("email_key", sa.String(length=254), nullable=False),
        sa.Column(
            "overview_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "revenue_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "memberships_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "operations_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "maintenance_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "inventory_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "email_key", name="uq_scheduled_report_recipient_email_key"
        ),
    )
    op.create_table(
        "scheduled_report_configuration_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("previous_snapshot", sa.Text(), nullable=False),
        sa.Column("next_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["app_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_report_configuration_events_changed",
        "scheduled_report_configuration_events",
        ["changed_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    event_count = bind.execute(
        sa.text("SELECT count(*) FROM scheduled_report_configuration_events")
    ).scalar()
    if event_count:
        raise RuntimeError(
            "No se puede retirar la auditoría de reportes mientras "
            f"conserve {event_count} cambio(s)."
        )
    op.drop_index(
        "ix_scheduled_report_configuration_events_changed",
        table_name="scheduled_report_configuration_events",
    )
    op.drop_table("scheduled_report_configuration_events")
    op.drop_table("scheduled_report_recipients")
    op.drop_table("scheduled_report_configurations")
