"""Create the point of sale and inventory tables.

Adds the product catalog, the stock balance with its append-only movement
ledger, the register shifts (cash sessions) and the sales with their line
items. Stock is materialised in ``inventory_stock`` for fast reads but every
change is also appended to ``inventory_movements`` so the balance can always be
reconciled against its history.

Also adds the ``sales.read`` / ``sales.manage`` permissions so the register can
be operated without overloading ``inventory.manage``. As in earlier permission
migrations the inserts look roles and permissions up by code, so they stay
correct even where a preview seed already created the permission with a
different id.

Revision ID: 20261017_0008
Revises: 20261016_0007
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261017_0008"
down_revision = "20261016_0007"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("sales.read", "Consultar ventas y cortes de caja"),
    ("sales.manage", "Registrar ventas y operar la caja"),
)
ROLE_PERMISSIONS = {
    "owner": ("sales.read", "sales.manage"),
    "manager": ("sales.read", "sales.manage"),
    "reception": ("sales.read", "sales.manage"),
    "accountant": ("sales.read",),
}


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sku", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), server_default="General", nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("stock_min", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("price_cents >= 0", name="ck_products_price_nonnegative"),
        sa.CheckConstraint("cost_cents IS NULL OR cost_cents >= 0", name="ck_products_cost_nonnegative"),
        sa.CheckConstraint("stock_min >= 0", name="ck_products_stock_min_nonnegative"),
    )
    op.create_index("uq_products_sku_lower", "products", [sa.text("lower(sku)")], unique=True)
    op.create_index(
        "uq_products_barcode",
        "products",
        ["barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    op.create_index("ix_products_category", "products", ["category"])

    op.create_table(
        "inventory_stock",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location", sa.String(length=60), server_default="Mostrador", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_inventory_stock_nonnegative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("product_id", "location", name="uq_inventory_stock_product_location"),
    )

    op.create_table(
        "inventory_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location", sa.String(length=60), server_default="Mostrador", nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("reference_type", sa.String(length=20), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "movement_type IN ('intake', 'sale', 'adjustment', 'waste', 'return')",
            name="ck_inventory_movements_type",
        ),
        sa.CheckConstraint("quantity <> 0", name="ck_inventory_movements_quantity_nonzero"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_inventory_movements_product_time", "inventory_movements", ["product_id", "occurred_at"])
    op.create_index("ix_inventory_movements_reference", "inventory_movements", ["reference_type", "reference_id"])

    op.create_table(
        "cash_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("opened_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("opening_cash_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_cash_cents", sa.BigInteger(), nullable=True),
        sa.Column("counted_cash_cents", sa.BigInteger(), nullable=True),
        sa.Column("difference_cents", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_cash_sessions_status"),
        sa.CheckConstraint("opening_cash_cents >= 0", name="ck_cash_sessions_opening_nonnegative"),
        sa.CheckConstraint(
            "counted_cash_cents IS NULL OR counted_cash_cents >= 0",
            name="ck_cash_sessions_counted_nonnegative",
        ),
        sa.ForeignKeyConstraint(["opened_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_cash_sessions_one_open",
        "cash_sessions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index("ix_cash_sessions_opened_at", "cash_sessions", ["opened_at"])

    op.create_table(
        "sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("folio", sa.String(length=32), nullable=False),
        sa.Column("cash_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cashier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("discount_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("payment_method", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="completed", nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("payment_method IN ('cash', 'card', 'transfer')", name="ck_sales_payment_method"),
        sa.CheckConstraint("status IN ('completed', 'refunded')", name="ck_sales_status"),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND discount_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0",
            name="ck_sales_amounts_nonnegative",
        ),
        sa.ForeignKeyConstraint(["cash_session_id"], ["cash_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cashier_id"], ["app_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("folio", name="uq_sales_folio"),
    )
    op.create_index("ix_sales_sold_at", "sales", ["sold_at"])
    op.create_index("ix_sales_cash_session", "sales", ["cash_session_id"])
    op.create_index("ix_sales_member_sold", "sales", ["member_id", "sold_at"])

    op.create_table(
        "sale_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sale_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=60), nullable=False),
        sa.Column("location", sa.String(length=60), server_default="Mostrador", nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("line_total_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_sale_items_price_nonnegative"),
        sa.CheckConstraint("line_total_cents >= 0", name="ck_sale_items_total_nonnegative"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sale_items_sale", "sale_items", ["sale_id"])

    for code, description in PERMISSIONS:
        permission_id = _stable_id("permission", code)
        op.execute(
            "INSERT INTO permissions (id, code, description) "
            f"SELECT '{permission_id}'::uuid, '{code}', '{description}' "
            f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{code}')"
        )
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        for permission_code in permission_codes:
            op.execute(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT roles.id, permissions.id FROM roles, permissions "
                f"WHERE roles.code = '{role_code}' AND permissions.code = '{permission_code}' "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            )


def downgrade() -> None:
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        for permission_code in permission_codes:
            op.execute(
                "DELETE FROM role_permissions USING roles, permissions "
                "WHERE role_permissions.role_id = roles.id AND role_permissions.permission_id = permissions.id "
                f"AND roles.code = '{role_code}' AND permissions.code = '{permission_code}'"
            )
    for code, _ in PERMISSIONS:
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")

    op.drop_index("ix_sale_items_sale", table_name="sale_items")
    op.drop_table("sale_items")
    op.drop_index("ix_sales_member_sold", table_name="sales")
    op.drop_index("ix_sales_cash_session", table_name="sales")
    op.drop_index("ix_sales_sold_at", table_name="sales")
    op.drop_table("sales")
    op.drop_index("ix_cash_sessions_opened_at", table_name="cash_sessions")
    op.drop_index("uq_cash_sessions_one_open", table_name="cash_sessions")
    op.drop_table("cash_sessions")
    op.drop_index("ix_inventory_movements_reference", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_product_time", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_table("inventory_stock")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("uq_products_barcode", table_name="products")
    op.drop_index("uq_products_sku_lower", table_name="products")
    op.drop_table("products")
