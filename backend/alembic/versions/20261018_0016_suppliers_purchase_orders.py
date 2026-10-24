"""Add suppliers and purchase orders (restocking).

The club can now order stock from a supplier instead of only adjusting the
balance by hand. A purchase order records what was requested (its lines) and
what actually arrived (``received_quantity`` per line), so a short delivery
stays visible. Receiving goods appends ``intake`` movements to the existing
``inventory_movements`` ledger tagged with ``reference_type = "purchase_order"``
and refreshes the product's replacement cost; no new movement type is needed.

No new permission is created: suppliers and orders are managed with
``inventory.read`` / ``inventory.manage``, which the manager already holds.

Revision ID: 20261018_0016
Revises: 20261018_0015
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261018_0016"
down_revision = "20261018_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_suppliers_name_lower", "suppliers", [sa.text("lower(name)")], unique=True)
    op.create_index("ix_suppliers_active", "suppliers", ["is_active"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("folio", sa.String(length=32), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="created", nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("expected_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("received_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('created', 'sent', 'received', 'cancelled')",
            name="ck_purchase_orders_status",
        ),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0",
            name="ck_purchase_orders_amounts_nonnegative",
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["received_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("folio", name="uq_purchase_orders_folio"),
    )
    op.create_index(
        "ix_purchase_orders_supplier_created", "purchase_orders", ["supplier_id", "created_at"]
    )
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])

    op.create_table(
        "purchase_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=60), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("received_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unit_cost_cents", sa.BigInteger(), nullable=False),
        sa.Column("line_total_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_items_quantity_positive"),
        sa.CheckConstraint(
            "received_quantity >= 0", name="ck_purchase_order_items_received_nonnegative"
        ),
        sa.CheckConstraint(
            "received_quantity <= quantity", name="ck_purchase_order_items_received_within"
        ),
        sa.CheckConstraint(
            "unit_cost_cents >= 0", name="ck_purchase_order_items_cost_nonnegative"
        ),
        sa.CheckConstraint(
            "line_total_cents >= 0", name="ck_purchase_order_items_total_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_purchase_order_items_order", "purchase_order_items", ["purchase_order_id"])
    op.create_index("ix_purchase_order_items_product", "purchase_order_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_order_items_product", table_name="purchase_order_items")
    op.drop_index("ix_purchase_order_items_order", table_name="purchase_order_items")
    op.drop_table("purchase_order_items")
    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_supplier_created", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index("ix_suppliers_active", table_name="suppliers")
    op.drop_index("uq_suppliers_name_lower", table_name="suppliers")
    op.drop_table("suppliers")
