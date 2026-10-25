"""Monthly global CFDI for public-general walk-in sales.

Widens ``invoices.origin_type`` with ``global``, stores the club-local period of
a global comprobante and adds ``global_invoice_sales``: the traceability link
between a global invoice and every sale included in the batch.

Only one live (not cancelled) global invoice may exist per month. The partial
unique index frees the month when the comprobante is cancelled, so a replacement
can be issued while the previous batch and its operations remain in the history.

Revision ID: 20261024_0025
Revises: 20261023_0024
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261024_0025"
down_revision = "20261023_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("global_year", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("global_month", sa.Integer(), nullable=True))

    op.drop_constraint("ck_invoices_origin_type", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_origin_type",
        "invoices",
        "origin_type IN ('sale', 'membership_payment', 'global')",
    )
    op.create_check_constraint(
        "ck_invoices_global_period",
        "invoices",
        "(origin_type = 'global' AND global_year IS NOT NULL "
        "AND global_month BETWEEN 1 AND 12) OR "
        "(origin_type <> 'global' AND global_year IS NULL "
        "AND global_month IS NULL)",
    )
    op.create_index(
        "uq_invoices_active_global_period",
        "invoices",
        ["global_year", "global_month"],
        unique=True,
        postgresql_where=sa.text(
            "origin_type = 'global' AND status <> 'cancelled'"
        ),
        sqlite_where=sa.text("origin_type = 'global' AND status <> 'cancelled'"),
    )

    op.create_table(
        "global_invoice_sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sale_folio", sa.String(length=32), nullable=False),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "invoice_id", "sale_id", name="uq_global_invoice_sales_invoice_sale"
        ),
        sa.CheckConstraint(
            "total_cents > 0", name="ck_global_invoice_sales_total_positive"
        ),
    )
    op.create_index(
        "ix_global_invoice_sales_sale", "global_invoice_sales", ["sale_id"]
    )
    op.create_index(
        "ix_global_invoice_sales_invoice", "global_invoice_sales", ["invoice_id"]
    )


def downgrade() -> None:
    has_global = op.get_bind().execute(
        sa.text("SELECT 1 FROM invoices WHERE origin_type = 'global' LIMIT 1")
    ).first()
    if has_global is not None:
        raise RuntimeError(
            "No se puede revertir la migración mientras existan facturas globales."
        )
    op.drop_index("ix_global_invoice_sales_invoice", table_name="global_invoice_sales")
    op.drop_index("ix_global_invoice_sales_sale", table_name="global_invoice_sales")
    op.drop_table("global_invoice_sales")
    op.drop_index("uq_invoices_active_global_period", table_name="invoices")
    op.drop_constraint("ck_invoices_global_period", "invoices", type_="check")
    op.drop_constraint("ck_invoices_origin_type", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_origin_type",
        "invoices",
        "origin_type IN ('sale', 'membership_payment')",
    )
    op.drop_column("invoices", "global_month")
    op.drop_column("invoices", "global_year")
