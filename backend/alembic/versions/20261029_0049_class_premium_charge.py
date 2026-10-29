"""Charge the extra of a premium class through the sales ledger.

A premium class was priced (``class_sessions.extra_price_cents``) but never
charged. The charge is a normal sale with a single service line, so it shows up
in the register shift, the member account, the revenue reports, the invoices and
the bank reconciliation without a second ledger. A service line has no product,
so ``product_id`` becomes nullable on sale lines and return lines, and the sale
points back to the reservation it paid for.

Revision ID: 20261029_0049
Revises: 20261029_0048
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0049"
down_revision = "20261029_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sale_items",
        "product_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "sale_return_items",
        "product_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "sales",
        sa.Column("class_reservation_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sales_class_reservation",
        "sales",
        "class_reservations",
        ["class_reservation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sales_class_reservation", "sales", ["class_reservation_id"]
    )


def downgrade() -> None:
    # Service lines have no product, so they cannot survive the NOT NULL
    # restore. Removing them also removes the class charges that only lived in
    # this revision; do it in FK order (returns before sales).
    op.execute("DELETE FROM sale_return_items WHERE product_id IS NULL")
    op.execute("DELETE FROM sale_items WHERE product_id IS NULL")
    op.drop_index("ix_sales_class_reservation", table_name="sales")
    op.drop_constraint("fk_sales_class_reservation", "sales", type_="foreignkey")
    op.drop_column("sales", "class_reservation_id")
    op.alter_column(
        "sale_return_items",
        "product_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "sale_items",
        "product_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
