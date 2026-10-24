"""Add sale returns (refunds and sale write-offs).

A return is append-only: it references the original sale and its lines, snapshots
the returned price, and appends the matching ``inventory_movements``. A
``restock`` line goes back to the sellable balance; a ``write_off`` line records
the goods coming back (``return``) and leaving again (``waste``) so the ledger
keeps summing to the stock balance. ``cash_session_id`` links a refund to the
shift that paid it, so a cash refund lowers the expected cash at close.

No new permission is created: the register is operated with ``sales.read`` /
``sales.manage``, which front desk already holds.

Revision ID: 20261018_0015
Revises: 20261017_0014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261018_0015"
down_revision = "20261017_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sale_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("folio", sa.String(length=32), nullable=False),
        sa.Column("sale_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cash_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("refund_method", sa.String(length=16), nullable=False),
        sa.Column("total_refund_cents", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("refund_method IN ('cash', 'card', 'transfer')", name="ck_sale_returns_method"),
        sa.CheckConstraint("total_refund_cents >= 0", name="ck_sale_returns_total_nonnegative"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cash_session_id"], ["cash_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("folio", name="uq_sale_returns_folio"),
    )
    op.create_index("ix_sale_returns_sale", "sale_returns", ["sale_id"])
    op.create_index("ix_sale_returns_returned_at", "sale_returns", ["returned_at"])
    op.create_index("ix_sale_returns_cash_session", "sale_returns", ["cash_session_id"])

    op.create_table(
        "sale_return_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("return_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sale_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=60), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("line_refund_cents", sa.BigInteger(), nullable=False),
        sa.Column("disposition", sa.String(length=16), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sale_return_items_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_sale_return_items_price_nonnegative"),
        sa.CheckConstraint("line_refund_cents >= 0", name="ck_sale_return_items_total_nonnegative"),
        sa.CheckConstraint(
            "disposition IN ('restock', 'write_off')",
            name="ck_sale_return_items_disposition",
        ),
        sa.ForeignKeyConstraint(["return_id"], ["sale_returns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sale_item_id"], ["sale_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sale_return_items_return", "sale_return_items", ["return_id"])
    op.create_index("ix_sale_return_items_sale_item", "sale_return_items", ["sale_item_id"])


def downgrade() -> None:
    op.drop_index("ix_sale_return_items_sale_item", table_name="sale_return_items")
    op.drop_index("ix_sale_return_items_return", table_name="sale_return_items")
    op.drop_table("sale_return_items")
    op.drop_index("ix_sale_returns_cash_session", table_name="sale_returns")
    op.drop_index("ix_sale_returns_returned_at", table_name="sale_returns")
    op.drop_index("ix_sale_returns_sale", table_name="sale_returns")
    op.drop_table("sale_returns")
