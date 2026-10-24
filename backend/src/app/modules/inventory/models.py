from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel

# Single-register first version: every product keeps its stock in this location.
# The schema already isolates stock per location so a second point of sale can be
# added without reshaping the tables.
DEFAULT_LOCATION = "Mostrador"

PRODUCT_CATEGORY_DEFAULT = "General"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(SQLModel, table=True):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_products_price_nonnegative"),
        CheckConstraint("cost_cents IS NULL OR cost_cents >= 0", name="ck_products_cost_nonnegative"),
        CheckConstraint("stock_min >= 0", name="ck_products_stock_min_nonnegative"),
        Index("uq_products_sku_lower", text("lower(sku)"), unique=True),
        Index(
            "uq_products_barcode",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
            sqlite_where=text("barcode IS NOT NULL"),
        ),
        Index("ix_products_category", "category"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sku: str = Field(max_length=60)
    name: str = Field(max_length=160)
    category: str = Field(
        default=PRODUCT_CATEGORY_DEFAULT,
        sa_column=Column(String(80), nullable=False, server_default=text("'General'")),
    )
    barcode: str | None = Field(default=None, max_length=64)
    price_cents: int = Field(sa_type=BigInteger)
    cost_cents: int | None = Field(default=None, sa_type=BigInteger)
    stock_min: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class InventoryStock(SQLModel, table=True):
    __tablename__ = "inventory_stock"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_stock_nonnegative"),
        UniqueConstraint("product_id", "location", name="uq_inventory_stock_product_location"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    product_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    )
    location: str = Field(
        default=DEFAULT_LOCATION,
        sa_column=Column(String(60), nullable=False, server_default=text("'Mostrador'")),
    )
    quantity: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class InventoryMovement(SQLModel, table=True):
    """Append-only stock ledger: every change explains quantity, reason and origin."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('intake', 'sale', 'adjustment', 'waste', 'return')",
            name="ck_inventory_movements_type",
        ),
        CheckConstraint("quantity <> 0", name="ck_inventory_movements_quantity_nonzero"),
        Index("ix_inventory_movements_product_time", "product_id", "occurred_at"),
        Index("ix_inventory_movements_reference", "reference_type", "reference_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    product_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    )
    location: str = Field(
        default=DEFAULT_LOCATION,
        sa_column=Column(String(60), nullable=False, server_default=text("'Mostrador'")),
    )
    movement_type: str = Field(max_length=20)
    quantity: int
    reason: str | None = Field(default=None, max_length=200)
    reference_type: str | None = Field(default=None, max_length=20)
    reference_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    actor_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class CashSession(SQLModel, table=True):
    """A shift of the register. Only one session may be open at a time."""

    __tablename__ = "cash_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="ck_cash_sessions_status"),
        CheckConstraint("opening_cash_cents >= 0", name="ck_cash_sessions_opening_nonnegative"),
        CheckConstraint(
            "counted_cash_cents IS NULL OR counted_cash_cents >= 0",
            name="ck_cash_sessions_counted_nonnegative",
        ),
        Index(
            "uq_cash_sessions_one_open",
            "status",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
        Index("ix_cash_sessions_opened_at", "opened_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: str = Field(
        default="open",
        sa_column=Column(String(16), nullable=False, server_default=text("'open'")),
    )
    opened_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    opened_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    opening_cash_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    closed_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    closed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    expected_cash_cents: int | None = Field(default=None, sa_type=BigInteger)
    counted_cash_cents: int | None = Field(default=None, sa_type=BigInteger)
    difference_cents: int | None = Field(default=None, sa_type=BigInteger)
    notes: str | None = Field(default=None, sa_column=Column(Text))


class Sale(SQLModel, table=True):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint(
            "payment_method IN ('cash', 'card', 'transfer', 'account')",
            name="ck_sales_payment_method",
        ),
        CheckConstraint("status IN ('completed', 'refunded')", name="ck_sales_status"),
        CheckConstraint(
            "subtotal_cents >= 0 AND discount_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0",
            name="ck_sales_amounts_nonnegative",
        ),
        CheckConstraint("origin IN ('online', 'offline')", name="ck_sales_origin"),
        UniqueConstraint("folio", name="uq_sales_folio"),
        UniqueConstraint("client_reference", name="uq_sales_client_reference"),
        Index("ix_sales_sold_at", "sold_at"),
        Index("ix_sales_cash_session", "cash_session_id"),
        Index("ix_sales_member_sold", "member_id", "sold_at"),
        Index("ix_sales_origin", "origin"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    folio: str = Field(max_length=32)
    cash_session_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("cash_sessions.id", ondelete="RESTRICT")),
    )
    member_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT")),
    )
    cashier_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    subtotal_cents: int = Field(sa_type=BigInteger)
    discount_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    tax_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    total_cents: int = Field(sa_type=BigInteger)
    payment_method: str = Field(max_length=16)
    status: str = Field(
        default="completed",
        sa_column=Column(String(16), nullable=False, server_default=text("'completed'")),
    )
    origin: str = Field(
        default="online",
        sa_column=Column(String(16), nullable=False, server_default=text("'online'")),
    )
    client_reference: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=200)
    sold_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class SaleItem(SQLModel, table=True):
    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="ck_sale_items_price_nonnegative"),
        CheckConstraint("line_total_cents >= 0", name="ck_sale_items_total_nonnegative"),
        Index("ix_sale_items_sale", "sale_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sale_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)
    )
    product_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    )
    product_name: str = Field(max_length=160)
    sku: str = Field(max_length=60)
    location: str = Field(
        default=DEFAULT_LOCATION,
        sa_column=Column(String(60), nullable=False, server_default=text("'Mostrador'")),
    )
    quantity: int
    unit_price_cents: int = Field(sa_type=BigInteger)
    line_total_cents: int = Field(sa_type=BigInteger)


# A returned line either goes back to the sellable balance (`restock`) or is
# received and immediately discarded as shrinkage (`write_off`). The write-off
# still records the goods coming back (+return) and leaving again (-waste) so the
# inventory ledger always sums to the stock balance.
RETURN_DISPOSITIONS = ("restock", "write_off")


class SaleReturn(SQLModel, table=True):
    """Append-only refund against an original sale.

    A return never rewrites the sale: it references it, snapshots the returned
    lines with the price they were sold at, and appends the matching inventory
    movements. ``cash_session_id`` links the refund to the shift that paid it so
    a cash refund lowers the expected cash at close.
    """

    __tablename__ = "sale_returns"
    __table_args__ = (
        CheckConstraint(
            "refund_method IN ('cash', 'card', 'transfer', 'account')",
            name="ck_sale_returns_method",
        ),
        CheckConstraint("total_refund_cents >= 0", name="ck_sale_returns_total_nonnegative"),
        UniqueConstraint("folio", name="uq_sale_returns_folio"),
        Index("ix_sale_returns_sale", "sale_id"),
        Index("ix_sale_returns_returned_at", "returned_at"),
        Index("ix_sale_returns_cash_session", "cash_session_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    folio: str = Field(max_length=32)
    sale_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)
    )
    cash_session_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("cash_sessions.id", ondelete="RESTRICT")),
    )
    member_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT")),
    )
    actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    refund_method: str = Field(max_length=16)
    total_refund_cents: int = Field(sa_type=BigInteger)
    reason: str = Field(max_length=200)
    returned_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class SaleReturnItem(SQLModel, table=True):
    """A returned line of a sale. Append-only: it never overwrites the sale line."""

    __tablename__ = "sale_return_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_return_items_quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="ck_sale_return_items_price_nonnegative"),
        CheckConstraint("line_refund_cents >= 0", name="ck_sale_return_items_total_nonnegative"),
        CheckConstraint(
            "disposition IN ('restock', 'write_off')",
            name="ck_sale_return_items_disposition",
        ),
        Index("ix_sale_return_items_return", "return_id"),
        Index("ix_sale_return_items_sale_item", "sale_item_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    return_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("sale_returns.id", ondelete="RESTRICT"), nullable=False)
    )
    sale_item_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False)
    )
    product_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    )
    product_name: str = Field(max_length=160)
    sku: str = Field(max_length=60)
    quantity: int
    unit_price_cents: int = Field(sa_type=BigInteger)
    line_refund_cents: int = Field(sa_type=BigInteger)
    disposition: str = Field(max_length=16)


# A member account ("cuenta del socio") has no stored balance: it is the sum of
# the sales tendered with ``payment_method = "account"`` minus the returns
# credited back to the account and the payments recorded in this table. Keeping
# each event in its natural table avoids a second ledger that could drift.
MEMBER_ACCOUNT_PAYMENT_METHODS = ("cash", "card", "transfer")


class MemberAccountPayment(SQLModel, table=True):
    """A payment a member makes against their store account.

    ``cash_session_id`` links the payment to the shift that received it, so a
    cash payment raises the expected cash at close while a card or transfer
    payment only reduces the receivable.
    """

    __tablename__ = "member_account_payments"
    __table_args__ = (
        CheckConstraint(
            "method IN ('cash', 'card', 'transfer')",
            name="ck_member_account_payments_method",
        ),
        CheckConstraint(
            "amount_cents > 0", name="ck_member_account_payments_amount_positive"
        ),
        Index("ix_member_account_payments_member_paid", "member_id", "paid_at"),
        Index("ix_member_account_payments_cash_session", "cash_session_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False
        )
    )
    cash_session_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("cash_sessions.id", ondelete="RESTRICT")),
    )
    actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    method: str = Field(max_length=16)
    amount_cents: int = Field(sa_type=BigInteger)
    note: str | None = Field(default=None, max_length=200)
    paid_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


# Sending a statement is a communication event, not an account movement: the
# balance is still computed from the documents. This audit table records who
# sent which document, to whom, and whether the SMTP transport actually ran or
# the preview mode only simulated it.
MEMBER_ACCOUNT_STATEMENT_FORMATS = ("pdf", "csv")
MEMBER_ACCOUNT_STATEMENT_DELIVERY_STATUSES = ("sent", "simulated", "failed")
# A statement is the document a member asks for; a reminder is a collection
# follow-up with the same snapshot. They share the append-only audit table so the
# panel can show one chronological history, but the purpose keeps the cooldown
# and the reporting rules separate.
MEMBER_ACCOUNT_STATEMENT_PURPOSES = ("statement", "reminder")


class MemberAccountStatementDelivery(SQLModel, table=True):
    """Audit trail of the statements sent to a member."""

    __tablename__ = "member_account_statement_deliveries"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('email')",
            name="ck_member_account_statement_deliveries_channel",
        ),
        CheckConstraint(
            "format IN ('pdf', 'csv')",
            name="ck_member_account_statement_deliveries_format",
        ),
        CheckConstraint(
            "status IN ('sent', 'simulated', 'failed')",
            name="ck_member_account_statement_deliveries_status",
        ),
        CheckConstraint(
            "purpose IN ('statement', 'reminder')",
            name="ck_member_account_statement_deliveries_purpose",
        ),
        Index(
            "ix_member_account_statement_deliveries_member_created",
            "member_id",
            "created_at",
        ),
        Index(
            "ix_member_account_statement_deliveries_member_purpose_created",
            "member_id",
            "purpose",
            "created_at",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False
        )
    )
    actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    channel: str = Field(default="email", max_length=16)
    recipient: str = Field(max_length=254)
    format: str = Field(max_length=8)
    purpose: str = Field(default="statement", max_length=16)
    status: str = Field(max_length=16)
    as_of: date = Field(sa_column=Column(Date, nullable=False))
    error: str | None = Field(default=None, max_length=500)
    retry_of_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("member_account_statement_deliveries.id", ondelete="SET NULL"),
        ),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


# A purchase order is drafted, sent to the supplier, received (fully) or
# cancelled. Only ``created`` and ``sent`` orders accept goods; a fully received
# order is closed, and cancelling is only allowed while nothing has arrived.
PURCHASE_ORDER_STATUSES = ("created", "sent", "received", "cancelled")
OPEN_PURCHASE_ORDER_STATUSES = ("created", "sent")


class Supplier(SQLModel, table=True):
    """A vendor the club restocks from."""

    __tablename__ = "suppliers"
    __table_args__ = (
        Index("uq_suppliers_name_lower", text("lower(name)"), unique=True),
        Index("ix_suppliers_active", "is_active"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, sa_column=Column(Text))
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class PurchaseOrder(SQLModel, table=True):
    """A restock order sent to a supplier.

    The order records what was requested (its lines) and what actually arrived
    (``received_quantity`` per line), so a short delivery stays visible instead
    of silently changing the request. Receiving goods appends ``intake``
    movements to the inventory ledger tagged with
    ``reference_type = "purchase_order"``; the order itself is never rewritten
    beyond its status and received quantities.
    """

    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'sent', 'received', 'cancelled')",
            name="ck_purchase_orders_status",
        ),
        CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0",
            name="ck_purchase_orders_amounts_nonnegative",
        ),
        UniqueConstraint("folio", name="uq_purchase_orders_folio"),
        Index("ix_purchase_orders_supplier_created", "supplier_id", "created_at"),
        Index("ix_purchase_orders_status", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    folio: str = Field(max_length=32)
    supplier_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
        )
    )
    status: str = Field(
        default="created",
        sa_column=Column(String(16), nullable=False, server_default=text("'created'")),
    )
    subtotal_cents: int = Field(sa_type=BigInteger)
    tax_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    total_cents: int = Field(sa_type=BigInteger)
    expected_at: date | None = Field(default=None, sa_type=Date)
    notes: str | None = Field(default=None, max_length=200)
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    received_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    sent_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    received_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class PurchaseOrderItem(SQLModel, table=True):
    """A requested line of a purchase order, with how much of it has arrived."""

    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_order_items_quantity_positive"),
        CheckConstraint(
            "received_quantity >= 0", name="ck_purchase_order_items_received_nonnegative"
        ),
        CheckConstraint(
            "received_quantity <= quantity", name="ck_purchase_order_items_received_within"
        ),
        CheckConstraint(
            "unit_cost_cents >= 0", name="ck_purchase_order_items_cost_nonnegative"
        ),
        CheckConstraint(
            "line_total_cents >= 0", name="ck_purchase_order_items_total_nonnegative"
        ),
        Index("ix_purchase_order_items_order", "purchase_order_id"),
        Index("ix_purchase_order_items_product", "product_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    purchase_order_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False
        )
    )
    product_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        )
    )
    product_name: str = Field(max_length=160)
    sku: str = Field(max_length=60)
    quantity: int
    received_quantity: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    unit_cost_cents: int = Field(sa_type=BigInteger)
    line_total_cents: int = Field(sa_type=BigInteger)
