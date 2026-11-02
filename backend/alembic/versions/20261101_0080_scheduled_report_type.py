"""Identify the report in scheduled delivery records.

Revision ID: 20261101_0080
Revises: 20261101_0079
"""

from alembic import op
import sqlalchemy as sa

revision = "20261101_0080"
down_revision = "20261101_0079"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "scheduled_report_deliveries",
        sa.Column(
            "report_name",
            sa.String(length=16),
            server_default=sa.text("'revenue'"),
            nullable=False,
        ),
    )
    op.alter_column(
        "scheduled_report_deliveries",
        "report_name",
        server_default=None,
    )
    op.create_check_constraint(
        "ck_scheduled_report_deliveries_report_name",
        "scheduled_report_deliveries",
        "report_name IN ('overview', 'revenue', 'memberships', 'operations', 'maintenance', 'inventory')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    other_report_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM scheduled_report_deliveries "
            "WHERE report_name != 'revenue'"
        )
    ).scalar()
    if other_report_count:
        raise RuntimeError(
            "No se puede retirar la identificación de reportes mientras "
            f"conserve {other_report_count} entrega(s) que no sean de ingresos."
        )
    op.drop_constraint(
        "ck_scheduled_report_deliveries_report_name",
        "scheduled_report_deliveries",
        type_="check",
    )
    op.drop_column("scheduled_report_deliveries", "report_name")
