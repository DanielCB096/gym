"""Track the origin of a sale and make offline sync idempotent.

Sales rung while the register has no connection are queued in the browser and
later sent to ``POST /admin/sales/offline``. Each queued sale carries a device
generated ``client_reference``; the unique constraint makes replaying a batch
safe (a second attempt returns ``duplicate`` instead of charging the member or
discounting the stock twice). ``origin`` distinguishes ``online`` sales from
``offline`` ones so the register and the reports can audit them.

``client_reference`` stays null for ordinary online sales; PostgreSQL and SQLite
both allow multiple nulls in a unique constraint.

Revision ID: 20261019_0018
Revises: 20261019_0017
"""

from alembic import op
import sqlalchemy as sa

revision = "20261019_0018"
down_revision = "20261019_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales",
        sa.Column(
            "origin",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'online'"),
        ),
    )
    op.add_column(
        "sales",
        sa.Column("client_reference", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_sales_origin",
        "sales",
        "origin IN ('online', 'offline')",
    )
    op.create_unique_constraint(
        "uq_sales_client_reference",
        "sales",
        ["client_reference"],
    )
    op.create_index("ix_sales_origin", "sales", ["origin"])


def downgrade() -> None:
    op.drop_index("ix_sales_origin", table_name="sales")
    op.drop_constraint("uq_sales_client_reference", "sales", type_="unique")
    op.drop_constraint("ck_sales_origin", "sales", type_="check")
    op.drop_column("sales", "client_reference")
    op.drop_column("sales", "origin")
