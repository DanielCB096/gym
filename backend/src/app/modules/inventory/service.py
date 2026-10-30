"""Point of sale and inventory service.

Money is always handled in integer cents. Stock is materialised in
``inventory_stock`` for fast reads but every change is also appended to
``inventory_movements`` so the balance can always be reconciled against its
history. Negative adjustments (sales, waste, downward corrections) run as an
atomic ``UPDATE ... WHERE quantity + delta >= 0`` so two simultaneous sales can
never drive the stock below zero.

Folios (``V-YYYYMMDD-XXXXXX``, ``D-YYYYMMDD-XXXXXX``) carry the club's local
calendar day, not the UTC one, so the date in the folio matches the date the
operator sees on the ticket.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.identity.models import AppUser
from app.modules.inventory.models import (
    DEFAULT_LOCATION,
    MEMBER_ACCOUNT_PAYMENT_METHODS,
    OPEN_PURCHASE_ORDER_STATUSES,
    PRODUCT_CATEGORY_DEFAULT,
    PURCHASE_ORDER_STATUSES,
    RETURN_DISPOSITIONS,
    CashSession,
    InventoryMovement,
    InventoryStock,
    MemberAccountPayment,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
    Supplier,
    utc_now,
)
from app.modules.memberships.models import Member, Payment
from app.timezone import club_date, club_day_stamp

DEFAULT_PRODUCT_PAGE_SIZE = 25
DEFAULT_SALE_PAGE_SIZE = 25
DEFAULT_RETURN_PAGE_SIZE = 25
DEFAULT_SUPPLIER_PAGE_SIZE = 25
DEFAULT_PURCHASE_ORDER_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
PRODUCT_STATES = ("active", "low", "out", "inactive")
# Ways a sale can be tendered. "account" charges the goods to the member's
# account instead of collecting money at the counter.
PAYMENT_METHODS = ("cash", "card", "transfer")
SALE_PAYMENT_METHODS = (*PAYMENT_METHODS, "account")
# Service lines (a premium class) share the sales ledger but never touch stock.
SERVICE_SKU = "CLASE"
MANUAL_MOVEMENT_TYPES = ("intake", "adjustment", "waste")

# Areas/state labels used by the panel.
STOCK_LOW = "low"
STOCK_OUT = "out"
STOCK_ACTIVE = "active"
STOCK_INACTIVE = "inactive"


class InventoryError(Exception):
    pass


class InvalidProductData(InventoryError):
    pass


class ProductNotFound(InventoryError):
    pass


class DuplicateProductSku(InventoryError):
    pass


class DuplicateProductBarcode(InventoryError):
    pass


class ProductUnavailable(InventoryError):
    pass


class InvalidCart(InventoryError):
    pass


class InsufficientStock(InventoryError):
    pass


class MemberUnavailable(InventoryError):
    pass


class CashSessionAlreadyOpen(InventoryError):
    pass


class NoOpenCashSession(InventoryError):
    pass


class CashSessionNotFound(InventoryError):
    pass


class InvalidCashSessionState(InventoryError):
    pass


class DifferenceExplanationRequired(InventoryError):
    pass


class SaleNotFound(InventoryError):
    pass


class SaleItemNotFound(InventoryError):
    pass


class InvalidReturn(InventoryError):
    pass


class ReturnExceedsSold(InventoryError):
    pass


class ServiceAlreadyRefunded(InventoryError):
    pass


class InvalidAccountPayment(InventoryError):
    pass


class NoOutstandingBalance(InventoryError):
    pass


class PaymentExceedsBalance(InventoryError):
    pass


class InvalidCreditLimit(InventoryError):
    pass


class CreditLimitExceeded(InventoryError):
    pass


class SupplierNotFound(InventoryError):
    pass


class DuplicateSupplierName(InventoryError):
    pass


class InvalidSupplierData(InventoryError):
    pass


class PurchaseOrderNotFound(InventoryError):
    pass


class InvalidPurchaseOrderData(InventoryError):
    pass


class InvalidPurchaseOrderState(InventoryError):
    pass


class PurchaseOrderOverReceive(InventoryError):
    pass


@dataclass(frozen=True)
class ProductItem:
    id: UUID
    sku: str
    name: str
    category: str
    barcode: str | None
    price_cents: int
    cost_cents: int | None
    stock_min: int
    is_active: bool
    stock: int
    updated_at: datetime


@dataclass(frozen=True)
class ProductSummary:
    total: int
    active: int
    low_stock: int
    out_of_stock: int
    inactive: int


@dataclass(frozen=True)
class ProductPage:
    items: list[ProductItem]
    total: int
    page: int
    page_size: int
    pages: int
    summary: ProductSummary
    categories: list[str]


@dataclass(frozen=True)
class SaleLine:
    sale_item_id: UUID
    product_id: UUID | None
    product_name: str
    sku: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    refunded_quantity: int = 0
    returnable_quantity: int = 0


@dataclass(frozen=True)
class SaleItemView:
    id: UUID
    folio: str
    status: str
    payment_method: str
    member_id: UUID | None
    member_name: str | None
    cashier_id: UUID | None
    cashier_email: str | None
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    refunded_cents: int
    note: str | None
    sold_at: datetime
    cash_session_id: UUID | None
    origin: str
    client_reference: str | None
    lines: list[SaleLine]


@dataclass(frozen=True)
class SaleSummary:
    count: int
    total_cents: int
    cash_cents: int
    card_cents: int
    transfer_cents: int
    account_cents: int
    refunds_cents: int
    refunded_count: int


@dataclass(frozen=True)
class SalePage:
    items: list[SaleItemView]
    total: int
    page: int
    page_size: int
    pages: int
    summary: SaleSummary


@dataclass(frozen=True)
class OfflineSaleEntry:
    client_reference: str
    items: list[tuple[UUID, int]]
    payment_method: str
    member_id: UUID | None
    note: str | None
    sold_at: datetime


@dataclass(frozen=True)
class OfflineSaleResult:
    client_reference: str
    status: str
    sale: SaleItemView | None = None
    error: str | None = None


@dataclass(frozen=True)
class OfflineSaleSync:
    results: list[OfflineSaleResult]
    created: int
    duplicates: int
    rejected: int


@dataclass(frozen=True)
class SaleReturnLine:
    sale_item_id: UUID
    product_id: UUID | None
    product_name: str
    sku: str
    quantity: int
    unit_price_cents: int
    line_refund_cents: int
    disposition: str


@dataclass(frozen=True)
class SaleReturnView:
    id: UUID
    folio: str
    sale_id: UUID
    sale_folio: str
    cash_session_id: UUID | None
    member_id: UUID | None
    member_name: str | None
    actor_id: UUID | None
    actor_email: str | None
    refund_method: str
    total_refund_cents: int
    reason: str
    returned_at: datetime
    lines: list[SaleReturnLine]


@dataclass(frozen=True)
class SaleReturnSummary:
    count: int
    total_refund_cents: int
    cash_refund_cents: int
    card_refund_cents: int
    transfer_refund_cents: int
    account_refund_cents: int


@dataclass(frozen=True)
class SaleReturnPage:
    items: list[SaleReturnView]
    total: int
    page: int
    page_size: int
    pages: int
    summary: SaleReturnSummary


@dataclass(frozen=True)
class CashSessionView:
    id: UUID
    status: str
    opened_by: UUID | None
    opened_by_email: str | None
    opened_at: datetime
    opening_cash_cents: int
    closed_by: UUID | None
    closed_by_email: str | None
    closed_at: datetime | None
    expected_cash_cents: int
    counted_cash_cents: int | None
    difference_cents: int | None
    notes: str | None
    sales_count: int
    total_sales_cents: int
    cash_sales_cents: int
    card_sales_cents: int
    transfer_sales_cents: int
    account_sales_cents: int
    refunds_count: int
    total_refunds_cents: int
    cash_refunds_cents: int
    account_refunds_cents: int
    account_payments_count: int
    account_payments_cents: int
    cash_account_payments_cents: int
    membership_payments_count: int
    membership_payments_cents: int
    cash_membership_payments_cents: int


@dataclass(frozen=True)
class MemberAccountEntry:
    """One line of a member's account statement.

    ``amount_cents`` is signed: a charge to the account is positive, while a
    credit (return) or a payment is negative. ``balance_cents`` is the account
    balance right after the entry was applied.
    """

    kind: str
    occurred_at: datetime
    description: str
    reference: str
    method: str | None
    amount_cents: int
    balance_cents: int


@dataclass(frozen=True)
class AccountAging:
    """Outstanding balance grouped by the age of the charge that created it.

    Credits and payments are applied FIFO to the oldest charges, so a payment
    always clears the oldest debt first and the buckets always add up to the
    positive balance. A credit balance (negative) produces all zeros.
    """

    current_cents: int = 0
    days_31_60_cents: int = 0
    days_61_90_cents: int = 0
    over_90_cents: int = 0


@dataclass(frozen=True)
class MemberAccountSummary:
    member_id: UUID
    member_name: str
    email: str | None
    phone: str | None
    member_status: str
    charges_cents: int
    credits_cents: int
    payments_cents: int
    balance_cents: int
    credit_limit_cents: int | None
    credit_available_cents: int | None
    over_limit: bool
    aging: AccountAging
    charges_count: int
    payments_count: int
    last_activity_at: datetime | None
    oldest_charge_at: datetime | None


@dataclass(frozen=True)
class MemberAccountStatement:
    summary: MemberAccountSummary
    entries: list[MemberAccountEntry]
    as_of: date


@dataclass(frozen=True)
class MemberAccountPaymentView:
    id: UUID
    member_id: UUID
    member_name: str | None
    cash_session_id: UUID | None
    actor_id: UUID | None
    actor_email: str | None
    method: str
    amount_cents: int
    note: str | None
    paid_at: datetime
    balance_cents: int


@dataclass(frozen=True)
class MemberAccountPage:
    items: list[MemberAccountSummary]
    total: int
    page: int
    page_size: int
    pages: int
    total_receivable_cents: int
    total_credit_cents: int
    members_with_balance: int
    aging: AccountAging
    over_limit_members: int
    as_of: date


@dataclass(frozen=True)
class SupplierItem:
    id: UUID
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SupplierPage:
    items: list[SupplierItem]
    total: int
    page: int
    page_size: int
    pages: int


@dataclass(frozen=True)
class PurchaseOrderLine:
    item_id: UUID
    product_id: UUID
    product_name: str
    sku: str
    quantity: int
    received_quantity: int
    pending_quantity: int
    unit_cost_cents: int
    line_total_cents: int


@dataclass(frozen=True)
class PurchaseOrderView:
    id: UUID
    folio: str
    supplier_id: UUID
    supplier_name: str
    status: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    expected_at: date | None
    notes: str | None
    created_by: UUID | None
    created_by_email: str | None
    received_by: UUID | None
    received_by_email: str | None
    created_at: datetime
    sent_at: datetime | None
    received_at: datetime | None
    cancelled_at: datetime | None
    lines: list[PurchaseOrderLine]


@dataclass(frozen=True)
class PurchaseOrderSummary:
    count: int
    created: int
    sent: int
    received: int
    cancelled: int
    total_cents: int


@dataclass(frozen=True)
class PurchaseOrderPage:
    items: list[PurchaseOrderView]
    total: int
    page: int
    page_size: int
    pages: int
    summary: PurchaseOrderSummary


# --------------------------------------------------------------------------
# Product catalog
# --------------------------------------------------------------------------


def _normalize_required(value: str, field: str, *, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise InvalidProductData(f"{field} is required")
    if len(normalized) > max_length:
        raise InvalidProductData(f"{field} is too long")
    return normalized


def create_product(
    session: Session,
    *,
    sku: str,
    name: str,
    category: str = PRODUCT_CATEGORY_DEFAULT,
    price_cents: int,
    cost_cents: int | None = None,
    barcode: str | None = None,
    stock_min: int = 0,
    initial_stock: int = 0,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ProductItem:
    normalized_sku = _normalize_required(sku, "sku", max_length=60)
    normalized_name = _normalize_required(name, "name", max_length=160)
    normalized_category = (category or "").strip() or PRODUCT_CATEGORY_DEFAULT
    normalized_barcode = (barcode or "").strip() or None
    if price_cents < 0:
        raise InvalidProductData("price_cents must be zero or greater")
    if cost_cents is not None and cost_cents < 0:
        raise InvalidProductData("cost_cents must be zero or greater")
    if stock_min < 0:
        raise InvalidProductData("stock_min must be zero or greater")
    if initial_stock < 0:
        raise InvalidProductData("initial_stock must be zero or greater")

    if _sku_exists(session, normalized_sku):
        raise DuplicateProductSku("El SKU ya está registrado")
    if normalized_barcode is not None and _barcode_exists(session, normalized_barcode):
        raise DuplicateProductBarcode("El código de barras ya está registrado")

    occurred_at = _as_utc(now or utc_now())
    product = Product(
        sku=normalized_sku,
        name=normalized_name,
        category=normalized_category,
        barcode=normalized_barcode,
        price_cents=price_cents,
        cost_cents=cost_cents,
        stock_min=stock_min,
    )
    session.add(product)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateProductSku("El SKU o código de barras ya está registrado") from error

    stock = InventoryStock(product_id=product.id, location=DEFAULT_LOCATION, quantity=initial_stock)
    session.add(stock)
    if initial_stock > 0:
        session.add(
            InventoryMovement(
                product_id=product.id,
                location=DEFAULT_LOCATION,
                movement_type="intake",
                quantity=initial_stock,
                reason="Existencia inicial",
                reference_type="product",
                reference_id=product.id,
                actor_id=actor_id,
                occurred_at=occurred_at,
            )
        )
    session.commit()
    session.refresh(product)
    return _product_item(product, initial_stock)


def update_product(
    session: Session,
    product_id: UUID,
    *,
    name: str,
    category: str,
    price_cents: int,
    cost_cents: int | None,
    barcode: str | None,
    stock_min: int,
    is_active: bool,
    actor_id: UUID | None = None,
) -> ProductItem:
    product = session.get(Product, product_id)
    if product is None:
        raise ProductNotFound("Producto no encontrado")
    normalized_name = _normalize_required(name, "name", max_length=160)
    normalized_category = (category or "").strip() or PRODUCT_CATEGORY_DEFAULT
    normalized_barcode = (barcode or "").strip() or None
    if price_cents < 0:
        raise InvalidProductData("price_cents must be zero or greater")
    if cost_cents is not None and cost_cents < 0:
        raise InvalidProductData("cost_cents must be zero or greater")
    if stock_min < 0:
        raise InvalidProductData("stock_min must be zero or greater")
    if normalized_barcode is not None and _barcode_exists(session, normalized_barcode, excluding=product_id):
        raise DuplicateProductBarcode("El código de barras ya está registrado")

    product.name = normalized_name
    product.category = normalized_category
    product.price_cents = price_cents
    product.cost_cents = cost_cents
    product.barcode = normalized_barcode
    product.stock_min = stock_min
    product.is_active = is_active
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateProductBarcode("El código de barras ya está registrado") from error
    session.refresh(product)
    return _product_item(product, _current_stock(session, product.id))


def list_products(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PRODUCT_PAGE_SIZE,
    search: str | None = None,
    category: str | None = None,
    state: str | None = None,
) -> ProductPage:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    if state is not None and state not in PRODUCT_STATES:
        raise ValueError("Unsupported product state filter")
    page_size = min(page_size, MAX_PAGE_SIZE)
    term = (search or "").strip().lower()
    category_term = (category or "").strip()

    stock_quantity = func.coalesce(InventoryStock.quantity, 0)

    def _apply_filters(statement):
        if term:
            like = f"%{term}%"
            statement = statement.where(
                or_(
                    func.lower(Product.sku).like(like),
                    func.lower(Product.name).like(like),
                    func.lower(func.coalesce(Product.barcode, "")).like(like),
                    func.lower(Product.category).like(like),
                )
            )
        if category_term:
            statement = statement.where(Product.category == category_term)
        if state == STOCK_OUT:
            statement = statement.where(Product.is_active.is_(True), stock_quantity <= 0)
        elif state == STOCK_LOW:
            statement = statement.where(
                Product.is_active.is_(True),
                stock_quantity > 0,
                stock_quantity <= Product.stock_min,
            )
        elif state == STOCK_ACTIVE:
            statement = statement.where(Product.is_active.is_(True), stock_quantity > Product.stock_min)
        elif state == STOCK_INACTIVE:
            statement = statement.where(Product.is_active.is_(False))
        return statement

    join_condition = and_(
        InventoryStock.product_id == Product.id,
        InventoryStock.location == DEFAULT_LOCATION,
    )
    count_stmt = _apply_filters(
        select(func.count(Product.id))
        .select_from(Product)
        .outerjoin(InventoryStock, join_condition)
    )
    rows_stmt = _apply_filters(
        select(Product, stock_quantity.label("quantity"))
        .select_from(Product)
        .outerjoin(InventoryStock, join_condition)
    )

    total = int(session.exec(count_stmt).one() or 0)
    rows = session.exec(
        rows_stmt.order_by(Product.name, Product.sku)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_product_item(product, int(quantity or 0)) for product, quantity in rows]
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return ProductPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=_product_summary(session),
        categories=_product_categories(session),
    )


def register_stock_movement(
    session: Session,
    product_id: UUID,
    *,
    movement_type: str,
    quantity: int,
    reason: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> ProductItem:
    if movement_type not in MANUAL_MOVEMENT_TYPES:
        raise InvalidProductData("Tipo de movimiento no válido")
    if quantity == 0:
        raise InvalidProductData("La cantidad debe ser distinta de cero")
    if movement_type == "adjustment":
        delta = quantity
    elif movement_type == "intake":
        if quantity < 0:
            raise InvalidProductData("La entrada debe ser una cantidad positiva")
        delta = quantity
    else:  # waste
        if quantity < 0:
            raise InvalidProductData("La merma debe ser una cantidad positiva")
        delta = -quantity

    product = session.get(Product, product_id)
    if product is None:
        raise ProductNotFound("Producto no encontrado")
    normalized_reason = (reason or "").strip() or None
    if movement_type in ("adjustment", "waste") and normalized_reason is None:
        raise InvalidProductData("El motivo es obligatorio para ajustes y mermas")

    occurred_at = _as_utc(now or utc_now())
    stock = _apply_stock_delta(session, product_id, delta)
    session.add(
        InventoryMovement(
            product_id=product_id,
            location=DEFAULT_LOCATION,
            movement_type=movement_type,
            quantity=delta,
            reason=normalized_reason,
            reference_type="manual",
            reference_id=None,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )
    )
    session.commit()
    session.refresh(product)
    return _product_item(product, stock)


# --------------------------------------------------------------------------
# Cash session (register shift)
# --------------------------------------------------------------------------


def open_cash_session(
    session: Session,
    *,
    opening_cash_cents: int,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> CashSessionView:
    if opening_cash_cents < 0:
        raise InvalidProductData("El fondo de caja no puede ser negativo")
    if _find_open_cash_session(session) is not None:
        raise CashSessionAlreadyOpen("Ya hay un turno de caja abierto")
    occurred_at = _as_utc(now or utc_now())
    cash_session = CashSession(
        status="open",
        opened_by=actor_id,
        opened_at=occurred_at,
        opening_cash_cents=opening_cash_cents,
    )
    session.add(cash_session)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise CashSessionAlreadyOpen("Ya hay un turno de caja abierto") from error
    session.refresh(cash_session)
    return _cash_session_view(session, cash_session)


def current_cash_session(session: Session) -> CashSessionView | None:
    cash_session = _find_open_cash_session(session)
    if cash_session is None:
        return None
    return _cash_session_view(session, cash_session)


def list_cash_sessions(session: Session, *, limit: int = 20) -> list[CashSessionView]:
    sessions = session.exec(
        select(CashSession).order_by(CashSession.opened_at.desc()).limit(limit)
    ).all()
    return [_cash_session_view(session, cash_session) for cash_session in sessions]


def close_cash_session(
    session: Session,
    cash_session_id: UUID,
    *,
    counted_cash_cents: int,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> CashSessionView:
    if counted_cash_cents < 0:
        raise InvalidProductData("El efectivo contado no puede ser negativo")
    cash_session = session.get(CashSession, cash_session_id)
    if cash_session is None:
        raise CashSessionNotFound("Turno de caja no encontrado")
    if cash_session.status != "open":
        raise InvalidCashSessionState("El turno de caja ya está cerrado")

    totals = _cash_session_totals(session, cash_session.id)
    expected = (
        cash_session.opening_cash_cents
        + totals["cash_cents"]
        - totals["cash_refunds_cents"]
        + totals["cash_account_payments_cents"]
        + totals["cash_membership_payments_cents"]
    )
    difference = counted_cash_cents - expected
    normalized_notes = (notes or "").strip() or None
    if difference != 0 and normalized_notes is None:
        raise DifferenceExplanationRequired("Explica la diferencia de efectivo para cerrar el turno")

    occurred_at = _as_utc(now or utc_now())
    cash_session.status = "closed"
    cash_session.closed_by = actor_id
    cash_session.closed_at = occurred_at
    cash_session.expected_cash_cents = expected
    cash_session.counted_cash_cents = counted_cash_cents
    cash_session.difference_cents = difference
    cash_session.notes = normalized_notes
    session.add(cash_session)
    session.commit()
    session.refresh(cash_session)
    return _cash_session_view(session, cash_session)


# --------------------------------------------------------------------------
# Sales
# --------------------------------------------------------------------------


def register_sale(
    session: Session,
    *,
    items: list[tuple[UUID, int]],
    payment_method: str,
    member_id: UUID | None = None,
    note: str | None = None,
    cashier_id: UUID | None = None,
    now: datetime | None = None,
    origin: str = "online",
    client_reference: str | None = None,
) -> SaleItemView:
    if payment_method not in SALE_PAYMENT_METHODS:
        raise InvalidCart("Forma de pago no válida")
    if origin not in ("online", "offline"):
        raise InvalidCart("Origen de venta no válido")
    reference = (client_reference or "").strip() or None
    if reference is not None and len(reference) > 64:
        raise InvalidCart("El identificador de la venta sin conexión es demasiado largo")
    if not items:
        raise InvalidCart("La venta no tiene productos")
    product_ids = [product_id for product_id, _ in items]
    if len(set(product_ids)) != len(product_ids):
        raise InvalidCart("Cada producto debe aparecer una sola vez en la venta")
    for _, quantity in items:
        if quantity <= 0:
            raise InvalidCart("Las cantidades deben ser mayores a cero")

    cash_session = _find_open_cash_session(session)
    if cash_session is None:
        raise NoOpenCashSession("Abre el turno de caja antes de registrar ventas")

    member = session.get(Member, member_id) if member_id is not None else None
    if member_id is not None and member is None:
        raise MemberUnavailable("Socio no encontrado")
    if payment_method == "account":
        if member is None:
            raise InvalidCart("Selecciona al socio para cargar la venta a su cuenta")
        if member.status == "inactive":
            raise MemberUnavailable("El socio está inactivo y no puede comprar a cuenta")

    products = session.exec(select(Product).where(Product.id.in_(product_ids))).all()
    products_by_id = {product.id: product for product in products}
    for product_id in product_ids:
        product = products_by_id.get(product_id)
        if product is None:
            raise ProductNotFound("Producto no encontrado")
        if not product.is_active:
            raise ProductUnavailable(f"El producto {product.name} está inactivo")

    sale_total_cents = sum(
        products_by_id[product_id].price_cents * quantity
        for product_id, quantity in items
    )
    if (
        payment_method == "account"
        and member is not None
        and member.credit_limit_cents is not None
    ):
        balance = member_account_balance(session, member.id)
        available = member.credit_limit_cents - balance
        if sale_total_cents > available:
            raise CreditLimitExceeded(
                "La venta excede el crédito disponible del socio: "
                f"disponible {_money(max(available, 0))} "
                f"de {_money(member.credit_limit_cents)}"
            )

    occurred_at = _as_utc(now or utc_now())
    sale = Sale(
        folio=_build_folio(occurred_at),
        cash_session_id=cash_session.id,
        member_id=member_id,
        cashier_id=cashier_id,
        subtotal_cents=0,
        discount_cents=0,
        tax_cents=0,
        total_cents=0,
        payment_method=payment_method,
        status="completed",
        origin=origin,
        client_reference=reference,
        note=(note or "").strip() or None,
        sold_at=occurred_at,
    )
    session.add(sale)

    lines: list[SaleLine] = []
    subtotal_cents = 0
    for product_id, quantity in items:
        product = products_by_id[product_id]
        _apply_stock_delta(session, product_id, -quantity)
        line_total = product.price_cents * quantity
        subtotal_cents += line_total
        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            location=DEFAULT_LOCATION,
            quantity=quantity,
            unit_price_cents=product.price_cents,
            line_total_cents=line_total,
        )
        session.add(sale_item)
        session.add(
            InventoryMovement(
                product_id=product.id,
                location=DEFAULT_LOCATION,
                movement_type="sale",
                quantity=-quantity,
                reason=None,
                reference_type="sale",
                reference_id=sale.id,
                actor_id=cashier_id,
                occurred_at=occurred_at,
            )
        )
        lines.append(
            SaleLine(
                sale_item_id=sale_item.id,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=quantity,
                unit_price_cents=product.price_cents,
                line_total_cents=line_total,
                refunded_quantity=0,
                returnable_quantity=quantity,
            )
        )

    sale.subtotal_cents = subtotal_cents
    sale.total_cents = subtotal_cents
    try:
        session.commit()
    except IntegrityError as error:  # pragma: no cover - folio collision is practically impossible
        session.rollback()
        raise InvalidCart("No se pudo registrar la venta") from error
    session.refresh(sale)
    return _sale_view(session, sale, lines)


def register_service_sale(
    session: Session,
    *,
    member_id: UUID,
    description: str,
    amount_cents: int,
    payment_method: str,
    cashier_id: UUID | None = None,
    note: str | None = None,
    class_reservation_id: UUID | None = None,
    physio_appointment_id: UUID | None = None,
    sku: str = SERVICE_SKU,
    now: datetime | None = None,
) -> Sale:
    """Charge a service (a premium class) as a regular sale.

    The sale carries a single line with ``product_id = None``: a service has no
    stock, so it never touches the inventory ledger, but it lands in the same
    sales table as any other charge. That keeps the cash close, the member
    account, the revenue report and invoicing working without a parallel
    ledger.

    The caller owns the transaction: this function never commits, so marking a
    class attendance and charging it for it succeed or fail together.
    """
    if payment_method not in SALE_PAYMENT_METHODS:
        raise InvalidCart("Forma de pago no válida")
    if amount_cents <= 0:
        raise InvalidCart("El importe del cobro debe ser mayor a cero")
    normalized = (description or "").strip()
    if not normalized:
        raise InvalidCart("El cobro necesita un concepto")
    if len(normalized) > 160:
        raise InvalidCart("El concepto del cobro es demasiado largo")
    normalized_note = (note or "").strip() or None
    if normalized_note is not None and len(normalized_note) > 200:
        raise InvalidCart("La nota del cobro es demasiado larga")

    member = session.get(Member, member_id)
    if member is None:
        raise MemberUnavailable("Socio no encontrado")
    if member.status == "inactive":
        raise MemberUnavailable("El socio está inactivo y no puede pagar servicios")

    cash_session = _find_open_cash_session(session)
    if cash_session is None:
        raise NoOpenCashSession("Abre el turno de caja antes de cobrar el servicio")

    if payment_method == "account" and member.credit_limit_cents is not None:
        balance = member_account_balance(session, member.id)
        available = member.credit_limit_cents - balance
        if amount_cents > available:
            raise CreditLimitExceeded(
                "El cobro excede el crédito disponible del socio: "
                f"disponible {_money(max(available, 0))} "
                f"de {_money(member.credit_limit_cents)}"
            )

    occurred_at = _as_utc(now or utc_now())
    sale = Sale(
        folio=_build_folio(occurred_at),
        cash_session_id=cash_session.id,
        member_id=member.id,
        cashier_id=cashier_id,
        subtotal_cents=amount_cents,
        discount_cents=0,
        tax_cents=0,
        total_cents=amount_cents,
        payment_method=payment_method,
        status="completed",
        origin="online",
        class_reservation_id=class_reservation_id,
        physio_appointment_id=physio_appointment_id,
        note=normalized_note,
        sold_at=occurred_at,
    )
    session.add(sale)
    session.add(
        SaleItem(
            sale_id=sale.id,
            product_id=None,
            product_name=normalized,
            sku=sku,
            location=DEFAULT_LOCATION,
            quantity=1,
            unit_price_cents=amount_cents,
            line_total_cents=amount_cents,
        )
    )
    return sale


def service_sale_for_reservation(session: Session, reservation_id: UUID) -> Sale | None:
    """Return the charge linked to a class reservation, if it was ever charged.

    A reservation may accumulate more than one sale if a charge is refunded and
    the member is later charged again, so the latest one wins.
    """
    return session.exec(
        select(Sale)
        .where(Sale.class_reservation_id == reservation_id)
        .order_by(Sale.sold_at.desc(), Sale.created_at.desc())
    ).first()


def service_sale_for_physio_appointment(session: Session, appointment_id: UUID) -> Sale | None:
    """Return the latest charge linked to a physiotherapy appointment."""
    return session.exec(
        select(Sale)
        .where(Sale.physio_appointment_id == appointment_id)
        .order_by(Sale.sold_at.desc(), Sale.created_at.desc())
    ).first()


def sync_offline_sales(
    session: Session,
    entries: list[OfflineSaleEntry],
    *,
    cashier_id: UUID | None = None,
    now: datetime | None = None,
) -> OfflineSaleSync:
    """Register a batch of sales made while the register was offline.

    Each entry is independent: one rejected sale does not roll back the others,
    and replaying the same batch is safe because ``client_reference`` is unique.
    The batch requires an open register shift; the offline sales are linked to the
    shift that receives the sync (closed shifts stay immutable). All entries keep
    the timestamp the device captured, so reports and folios reflect when the
    sale actually happened.
    """
    if not entries:
        raise InvalidCart("No hay ventas sin conexión por sincronizar")
    if _find_open_cash_session(session) is None:
        raise NoOpenCashSession(
            "Abre el turno de caja antes de sincronizar las ventas sin conexión"
        )

    current = _as_utc(now or utc_now())
    results: list[OfflineSaleResult] = []
    created = 0
    duplicates = 0
    rejected = 0

    for entry in entries:
        reference = (entry.client_reference or "").strip()
        if not reference:
            rejected += 1
            results.append(
                OfflineSaleResult(
                    client_reference="",
                    status="rejected",
                    error="La venta sin conexión no tiene identificador",
                )
            )
            continue
        if len(reference) > 64:
            rejected += 1
            results.append(
                OfflineSaleResult(
                    client_reference=reference,
                    status="rejected",
                    error="El identificador de la venta sin conexión es demasiado largo",
                )
            )
            continue

        existing = _offline_sale_view(session, reference)
        if existing is not None:
            duplicates += 1
            results.append(
                OfflineSaleResult(
                    client_reference=reference,
                    status="duplicate",
                    sale=existing,
                )
            )
            continue

        sold_at = _as_utc(entry.sold_at)
        if sold_at > current + timedelta(minutes=5):
            rejected += 1
            results.append(
                OfflineSaleResult(
                    client_reference=reference,
                    status="rejected",
                    error="La fecha de la venta no puede estar en el futuro",
                )
            )
            continue

        try:
            sale = register_sale(
                session,
                items=entry.items,
                payment_method=entry.payment_method,
                member_id=entry.member_id,
                note=entry.note,
                cashier_id=cashier_id,
                now=sold_at,
                origin="offline",
                client_reference=reference,
            )
        except InventoryError as error:
            session.rollback()
            raced = _offline_sale_view(session, reference)
            if raced is not None:
                duplicates += 1
                results.append(
                    OfflineSaleResult(
                        client_reference=reference,
                        status="duplicate",
                        sale=raced,
                    )
                )
            else:
                rejected += 1
                results.append(
                    OfflineSaleResult(
                        client_reference=reference,
                        status="rejected",
                        error=str(error),
                    )
                )
            continue

        created += 1
        results.append(
            OfflineSaleResult(
                client_reference=reference,
                status="created",
                sale=sale,
            )
        )

    return OfflineSaleSync(
        results=results,
        created=created,
        duplicates=duplicates,
        rejected=rejected,
    )


def _offline_sale_view(session: Session, reference: str) -> SaleItemView | None:
    sale = session.exec(select(Sale).where(Sale.client_reference == reference)).first()
    if sale is None:
        return None
    lines = _lines_by_sale(session, [sale.id]).get(sale.id, [])
    refunded = _refunded_cents_by_sale(session, [sale.id]).get(sale.id, 0)
    return _sale_view(session, sale, lines, refunded_cents=refunded)


def list_sales(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_SALE_PAGE_SIZE,
    search: str | None = None,
    payment_method: str | None = None,
    origin: str | None = None,
) -> SalePage:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    if payment_method is not None and payment_method not in SALE_PAYMENT_METHODS:
        raise ValueError("Unsupported payment method filter")
    if origin is not None and origin not in ("online", "offline"):
        raise ValueError("Unsupported origin filter")
    page_size = min(page_size, MAX_PAGE_SIZE)
    term = (search or "").strip().lower()

    def _apply_filters(statement):
        if term:
            like = f"%{term}%"
            statement = statement.where(
                or_(
                    func.lower(Sale.folio).like(like),
                    func.lower(func.coalesce(Member.first_name, "")).like(like),
                    func.lower(func.coalesce(Member.last_name, "")).like(like),
                    func.lower(func.coalesce(Member.email, "")).like(like),
                    func.lower(func.coalesce(AppUser.email, "")).like(like),
                )
            )
        if payment_method is not None:
            statement = statement.where(Sale.payment_method == payment_method)
        if origin is not None:
            statement = statement.where(Sale.origin == origin)
        return statement

    count_stmt = _apply_filters(
        select(func.count(Sale.id))
        .select_from(Sale)
        .outerjoin(Member, Member.id == Sale.member_id)
        .outerjoin(AppUser, AppUser.id == Sale.cashier_id)
    )
    rows_stmt = _apply_filters(
        select(Sale, Member, AppUser)
        .select_from(Sale)
        .outerjoin(Member, Member.id == Sale.member_id)
        .outerjoin(AppUser, AppUser.id == Sale.cashier_id)
    )

    total = int(session.exec(count_stmt).one() or 0)
    rows = session.exec(
        rows_stmt.order_by(Sale.sold_at.desc(), Sale.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    sale_ids = [sale.id for sale, _, _ in rows]
    lines_by_sale = _lines_by_sale(session, sale_ids)
    refunded_by_sale = _refunded_cents_by_sale(session, sale_ids)
    items = [
        _sale_view(
            session,
            sale,
            lines_by_sale.get(sale.id, []),
            member=member,
            cashier=cashier,
            refunded_cents=refunded_by_sale.get(sale.id, 0),
        )
        for sale, member, cashier in rows
    ]
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return SalePage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=_sale_summary(session),
    )


# --------------------------------------------------------------------------
# Returns (refunds and sale write-offs)
# --------------------------------------------------------------------------


def register_sale_return(
    session: Session,
    sale_id: UUID,
    *,
    lines: list[tuple[UUID, int, str]],
    reason: str,
    refund_method: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> SaleReturnView:
    """Register an append-only refund against an original sale.

    ``lines`` are ``(sale_item_id, quantity, disposition)``. A ``restock`` line
    goes back to the sellable balance; a ``write_off`` line is received and then
    discarded, so its net effect on stock is zero but the ledger still shows the
    return and the shrinkage. Returns require an open register shift.
    """
    if not lines:
        raise InvalidReturn("La devolución no tiene productos")
    normalized_reason = (reason or "").strip()
    if not normalized_reason:
        raise InvalidReturn("El motivo de la devolución es obligatorio")
    if len(normalized_reason) > 200:
        raise InvalidReturn("El motivo de la devolución es demasiado largo")
    if refund_method is not None and refund_method not in SALE_PAYMENT_METHODS:
        raise InvalidReturn("Forma de reembolso no válida")

    # Serialise returns of the same sale so two simultaneous requests cannot
    # refund more than was sold. Effective on PostgreSQL; a no-op on SQLite.
    sale = session.exec(
        select(Sale).where(Sale.id == sale_id).with_for_update()
    ).first()
    if sale is None:
        raise SaleNotFound("Venta no encontrada")

    cash_session = _find_open_cash_session(session)
    if cash_session is None:
        raise NoOpenCashSession("Abre el turno de caja antes de registrar devoluciones")

    if sale.payment_method == "account":
        # The club never collected money for this sale: the refund is a credit
        # to the member's account, never a cash payout.
        if sale.member_id is None:
            raise InvalidReturn("La venta a cuenta no tiene socio asociado")
        if refund_method is not None and refund_method != "account":
            raise InvalidReturn(
                "La venta se cargó a la cuenta del socio: la devolución debe abonarse a la misma cuenta"
            )
        method = "account"
    else:
        method = refund_method or sale.payment_method
        if method not in PAYMENT_METHODS:
            raise InvalidReturn("Forma de reembolso no válida")

    sale_items = session.exec(select(SaleItem).where(SaleItem.sale_id == sale_id)).all()
    items_by_id = {item.id: item for item in sale_items}
    already_refunded = _refunded_quantities_by_item(session, list(items_by_id))

    prepared: list[tuple[SaleItem, int, str]] = []
    seen: set[UUID] = set()
    for sale_item_id, quantity, disposition in lines:
        if disposition not in RETURN_DISPOSITIONS:
            raise InvalidReturn("Disposición de devolución no válida")
        if quantity <= 0:
            raise InvalidReturn("Las cantidades devueltas deben ser mayores a cero")
        if sale_item_id in seen:
            raise InvalidReturn("Cada producto debe aparecer una sola vez en la devolución")
        seen.add(sale_item_id)
        sale_item = items_by_id.get(sale_item_id)
        if sale_item is None:
            raise SaleItemNotFound("La línea no pertenece a la venta")
        if sale_item.product_id is None:
            raise InvalidReturn(
                "La línea es un servicio: su reembolso se registra desde la reserva de la clase"
            )
        available = sale_item.quantity - already_refunded.get(sale_item.id, 0)
        if quantity > available:
            raise ReturnExceedsSold("La cantidad devuelta supera lo vendido de ese producto")
        prepared.append((sale_item, quantity, disposition))

    occurred_at = _as_utc(now or utc_now())
    total_refund_cents = sum(item.unit_price_cents * quantity for item, quantity, _ in prepared)

    sale_return = SaleReturn(
        folio=_build_return_folio(occurred_at),
        sale_id=sale.id,
        cash_session_id=cash_session.id,
        member_id=sale.member_id,
        actor_id=actor_id,
        refund_method=method,
        total_refund_cents=total_refund_cents,
        reason=normalized_reason,
        returned_at=occurred_at,
    )
    session.add(sale_return)

    return_lines: list[SaleReturnLine] = []
    for sale_item, quantity, disposition in prepared:
        line_refund_cents = sale_item.unit_price_cents * quantity
        session.add(
            SaleReturnItem(
                return_id=sale_return.id,
                sale_item_id=sale_item.id,
                product_id=sale_item.product_id,
                product_name=sale_item.product_name,
                sku=sale_item.sku,
                quantity=quantity,
                unit_price_cents=sale_item.unit_price_cents,
                line_refund_cents=line_refund_cents,
                disposition=disposition,
            )
        )
        _apply_stock_delta(session, sale_item.product_id, quantity)
        session.add(
            InventoryMovement(
                product_id=sale_item.product_id,
                location=sale_item.location or DEFAULT_LOCATION,
                movement_type="return",
                quantity=quantity,
                reason=(
                    "Devolución revendible"
                    if disposition == "restock"
                    else "Devolución para baja"
                ),
                reference_type="sale_return",
                reference_id=sale_return.id,
                actor_id=actor_id,
                occurred_at=occurred_at,
            )
        )
        if disposition == "write_off":
            # The goods came back but cannot be resold: undo the intake and log
            # the shrinkage so the ledger keeps summing to the stock balance.
            _apply_stock_delta(session, sale_item.product_id, -quantity)
            session.add(
                InventoryMovement(
                    product_id=sale_item.product_id,
                    location=sale_item.location or DEFAULT_LOCATION,
                    movement_type="waste",
                    quantity=-quantity,
                    reason="Merma por devolución no revendible",
                    reference_type="sale_return",
                    reference_id=sale_return.id,
                    actor_id=actor_id,
                    occurred_at=occurred_at,
                )
            )
        return_lines.append(
            SaleReturnLine(
                sale_item_id=sale_item.id,
                product_id=sale_item.product_id,
                product_name=sale_item.product_name,
                sku=sale_item.sku,
                quantity=quantity,
                unit_price_cents=sale_item.unit_price_cents,
                line_refund_cents=line_refund_cents,
                disposition=disposition,
            )
        )

    # A sale flips to `refunded` only when every line has been fully returned;
    # a partial return leaves it `completed` but adds to its refunded total.
    refunded_totals = dict(already_refunded)
    for sale_item, quantity, _ in prepared:
        refunded_totals[sale_item.id] = refunded_totals.get(sale_item.id, 0) + quantity
    fully_returned = bool(sale_items) and all(
        refunded_totals.get(item.id, 0) >= item.quantity for item in sale_items
    )
    sale.status = "refunded" if fully_returned else "completed"
    session.add(sale)

    session.commit()
    session.refresh(sale_return)
    return _sale_return_view(session, sale_return, return_lines, sale=sale)


def refund_service_sale(
    session: Session,
    sale_id: UUID,
    *,
    reason: str,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> SaleReturnView | None:
    """Refund a service sale (the charge of a premium class).

    The refund mirrors the charge: the service line goes back in ``write_off``
    because nothing returns to stock, and the sale flips to ``refunded``. A cash
    refund needs an open register shift because the money leaves the drawer;
    card, transfer and account refunds are recorded without a shift since they
    never touch it. Returns ``None`` when the sale was already refunded, so a
    repeated cancellation is harmless.

    The caller owns the transaction: this function never commits.
    """
    normalized_reason = (reason or "").strip()
    if not normalized_reason:
        raise InvalidReturn("El motivo del reembolso es obligatorio")
    if len(normalized_reason) > 200:
        raise InvalidReturn("El motivo del reembolso es demasiado largo")

    sale = session.exec(
        select(Sale).where(Sale.id == sale_id).with_for_update()
    ).first()
    if sale is None:
        raise SaleNotFound("Venta no encontrada")
    if sale.class_reservation_id is None and sale.physio_appointment_id is None:
        raise InvalidReturn("La venta no corresponde a una reserva de clase ni a una cita")
    if sale.status == "refunded":
        return None

    method = "account" if sale.payment_method == "account" else sale.payment_method
    if method not in SALE_PAYMENT_METHODS:
        raise InvalidReturn("Forma de reembolso no válida")
    cash_session = _find_open_cash_session(session)
    if method == "cash" and cash_session is None:
        raise NoOpenCashSession("Abre el turno de caja para reembolsar el efectivo")

    sale_items = session.exec(select(SaleItem).where(SaleItem.sale_id == sale.id)).all()
    service_items = [item for item in sale_items if item.product_id is None]
    if not service_items:
        raise InvalidReturn("La venta no tiene una línea de servicio que reembolsar")

    occurred_at = _as_utc(now or utc_now())
    sale_return = SaleReturn(
        folio=_build_return_folio(occurred_at),
        sale_id=sale.id,
        cash_session_id=cash_session.id if cash_session is not None else None,
        member_id=sale.member_id,
        actor_id=actor_id,
        refund_method=method,
        total_refund_cents=sale.total_cents,
        reason=normalized_reason,
        returned_at=occurred_at,
    )
    session.add(sale_return)

    return_lines: list[SaleReturnLine] = []
    for item in service_items:
        line_refund_cents = item.line_total_cents
        session.add(
            SaleReturnItem(
                return_id=sale_return.id,
                sale_item_id=item.id,
                product_id=None,
                product_name=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                line_refund_cents=line_refund_cents,
                disposition="write_off",
            )
        )
        return_lines.append(
            SaleReturnLine(
                sale_item_id=item.id,
                product_id=None,
                product_name=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                line_refund_cents=line_refund_cents,
                disposition="write_off",
            )
        )

    sale.status = "refunded"
    session.add(sale)
    return _sale_return_view(session, sale_return, return_lines, sale=sale)


def list_sale_returns(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_RETURN_PAGE_SIZE,
    search: str | None = None,
    sale_id: UUID | None = None,
) -> SaleReturnPage:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    page_size = min(page_size, MAX_PAGE_SIZE)
    term = (search or "").strip().lower()

    def _apply_filters(statement):
        if term:
            like = f"%{term}%"
            statement = statement.where(
                or_(
                    func.lower(SaleReturn.folio).like(like),
                    func.lower(Sale.folio).like(like),
                    func.lower(Member.first_name).like(like),
                    func.lower(Member.last_name).like(like),
                    func.lower(func.coalesce(Member.email, "")).like(like),
                    func.lower(func.coalesce(AppUser.email, "")).like(like),
                    func.lower(SaleReturn.reason).like(like),
                )
            )
        if sale_id is not None:
            statement = statement.where(SaleReturn.sale_id == sale_id)
        return statement

    count_stmt = _apply_filters(
        select(func.count(SaleReturn.id))
        .select_from(SaleReturn)
        .join(Sale, Sale.id == SaleReturn.sale_id)
        .outerjoin(Member, Member.id == SaleReturn.member_id)
        .outerjoin(AppUser, AppUser.id == SaleReturn.actor_id)
    )
    rows_stmt = _apply_filters(
        select(SaleReturn, Sale, Member, AppUser)
        .select_from(SaleReturn)
        .join(Sale, Sale.id == SaleReturn.sale_id)
        .outerjoin(Member, Member.id == SaleReturn.member_id)
        .outerjoin(AppUser, AppUser.id == SaleReturn.actor_id)
    )

    total = int(session.exec(count_stmt).one() or 0)
    rows = session.exec(
        rows_stmt.order_by(SaleReturn.returned_at.desc(), SaleReturn.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return_ids = [sale_return.id for sale_return, _, _, _ in rows]
    lines_by_return = _return_lines_by_return(session, return_ids)
    items = [
        _sale_return_view(
            session,
            sale_return,
            lines_by_return.get(sale_return.id, []),
            sale=sale,
            member=member,
            actor=actor,
        )
        for sale_return, sale, member, actor in rows
    ]
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return SaleReturnPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=_sale_return_summary(session),
    )


# --------------------------------------------------------------------------
# Member account ("cuenta del socio")
# --------------------------------------------------------------------------


def _bump_activity(data: dict[str, object], value: datetime | None) -> None:
    if value is None:
        return
    moment = _as_utc(value)
    current = data.get("last_activity_at")
    if current is None or moment > current:  # type: ignore[operator]
        data["last_activity_at"] = moment


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _aging_from_charges(
    charges: list[tuple[datetime, int]],
    credit_cents: int,
    *,
    as_of: date,
) -> AccountAging:
    """Apply credits and payments FIFO to charges and bucket what remains.

    FIFO is the standard receivables convention: money received always settles
    the oldest debt first. The sum of the four buckets is therefore the positive
    balance of the account, while a credit balance leaves them all at zero.
    """

    available = max(credit_cents, 0)
    buckets = [0, 0, 0, 0]
    for occurred_at, amount in sorted(charges, key=lambda item: item[0]):
        if amount <= 0:
            continue
        remaining = amount
        if available > 0:
            applied = min(remaining, available)
            remaining -= applied
            available -= applied
        if remaining <= 0:
            continue
        age_days = max((as_of - club_date(occurred_at)).days, 0)
        index = 0 if age_days <= 30 else 1 if age_days <= 60 else 2 if age_days <= 90 else 3
        buckets[index] += remaining
    return AccountAging(*buckets)


def _member_account_totals(
    session: Session, *, today: date | None = None
) -> dict[UUID, dict[str, object]]:
    """Account totals per member, computed in grouped queries.

    A sale on account is a charge, an account-refund is a credit and a
    ``MemberAccountPayment`` is a payment. The balance is
    ``charges - credits - payments``; nothing is stored so the account can never
    drift from the documents that created it. The individual charges are also
    read once to compute the aging buckets (FIFO) for each member.
    """

    totals: dict[UUID, dict[str, object]] = {}
    charges_by_member: dict[UUID, list[tuple[datetime, int]]] = {}

    def bucket(member_id: UUID) -> dict[str, object]:
        return totals.setdefault(
            member_id,
            {
                "charges_cents": 0,
                "charges_count": 0,
                "credits_cents": 0,
                "payments_cents": 0,
                "payments_count": 0,
                "oldest_charge_at": None,
                "last_activity_at": None,
            },
        )

    for member_id, count, amount, oldest_at, last_at in session.exec(
        select(
            Sale.member_id,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_cents), 0),
            func.min(Sale.sold_at),
            func.max(Sale.sold_at),
        )
        .where(Sale.payment_method == "account", Sale.member_id.is_not(None))
        .group_by(Sale.member_id)
    ).all():
        data = bucket(member_id)
        data["charges_cents"] = int(amount or 0)
        data["charges_count"] = int(count or 0)
        if oldest_at is not None:
            data["oldest_charge_at"] = _as_utc(oldest_at)
        _bump_activity(data, last_at)

    for member_id, sold_at, amount in session.exec(
        select(Sale.member_id, Sale.sold_at, Sale.total_cents).where(
            Sale.payment_method == "account", Sale.member_id.is_not(None)
        )
    ).all():
        charges_by_member.setdefault(member_id, []).append(
            (_as_utc(sold_at), int(amount or 0))
        )

    for member_id, amount, last_at in session.exec(
        select(
            SaleReturn.member_id,
            func.coalesce(func.sum(SaleReturn.total_refund_cents), 0),
            func.max(SaleReturn.returned_at),
        )
        .where(SaleReturn.refund_method == "account", SaleReturn.member_id.is_not(None))
        .group_by(SaleReturn.member_id)
    ).all():
        data = bucket(member_id)
        data["credits_cents"] = int(amount or 0)
        _bump_activity(data, last_at)

    for member_id, count, amount, last_at in session.exec(
        select(
            MemberAccountPayment.member_id,
            func.count(MemberAccountPayment.id),
            func.coalesce(func.sum(MemberAccountPayment.amount_cents), 0),
            func.max(MemberAccountPayment.paid_at),
        ).group_by(MemberAccountPayment.member_id)
    ).all():
        data = bucket(member_id)
        data["payments_cents"] = int(amount or 0)
        data["payments_count"] = int(count or 0)
        _bump_activity(data, last_at)

    as_of = today or club_date(utc_now())
    for member_id, data in totals.items():
        data["aging"] = _aging_from_charges(
            charges_by_member.get(member_id, []),
            int(data.get("credits_cents", 0)) + int(data.get("payments_cents", 0)),
            as_of=as_of,
        )

    return totals


def _member_account_summary(
    member: Member, data: dict[str, object] | None = None
) -> MemberAccountSummary:
    bucket = data or {}
    charges = int(bucket.get("charges_cents", 0))  # type: ignore[arg-type]
    credits = int(bucket.get("credits_cents", 0))  # type: ignore[arg-type]
    payments = int(bucket.get("payments_cents", 0))  # type: ignore[arg-type]
    balance = charges - credits - payments
    limit = member.credit_limit_cents
    return MemberAccountSummary(
        member_id=member.id,
        member_name=f"{member.first_name} {member.last_name}".strip(),
        email=member.email,
        phone=member.phone,
        member_status=member.status,
        charges_cents=charges,
        credits_cents=credits,
        payments_cents=payments,
        balance_cents=balance,
        credit_limit_cents=limit,
        credit_available_cents=None if limit is None else limit - balance,
        over_limit=limit is not None and balance > limit,
        aging=bucket.get("aging") or AccountAging(),  # type: ignore[arg-type]
        charges_count=int(bucket.get("charges_count", 0)),  # type: ignore[arg-type]
        payments_count=int(bucket.get("payments_count", 0)),  # type: ignore[arg-type]
        last_activity_at=bucket.get("last_activity_at"),  # type: ignore[arg-type]
        oldest_charge_at=bucket.get("oldest_charge_at"),  # type: ignore[arg-type]
    )


def member_account_balance(session: Session, member_id: UUID) -> int:
    charges = session.exec(
        select(func.coalesce(func.sum(Sale.total_cents), 0)).where(
            Sale.member_id == member_id, Sale.payment_method == "account"
        )
    ).one()
    credits = session.exec(
        select(func.coalesce(func.sum(SaleReturn.total_refund_cents), 0)).where(
            SaleReturn.member_id == member_id,
            SaleReturn.refund_method == "account",
        )
    ).one()
    payments = session.exec(
        select(func.coalesce(func.sum(MemberAccountPayment.amount_cents), 0)).where(
            MemberAccountPayment.member_id == member_id
        )
    ).one()
    return int(charges or 0) - int(credits or 0) - int(payments or 0)


def list_member_accounts(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_SALE_PAGE_SIZE,
    search: str | None = None,
    over_limit: bool | None = None,
    today: date | None = None,
) -> MemberAccountPage:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    page_size = min(page_size, MAX_PAGE_SIZE)
    term = (search or "").strip().lower()
    as_of = today or club_date(utc_now())

    members = session.exec(select(Member).order_by(Member.first_name, Member.last_name)).all()
    totals = _member_account_totals(session, today=as_of)
    active = [
        summary
        for summary in (
            _member_account_summary(member, totals.get(member.id)) for member in members
        )
        if summary.balance_cents != 0
    ]
    total_receivable_cents = sum(
        summary.balance_cents for summary in active if summary.balance_cents > 0
    )
    total_credit_cents = sum(
        -summary.balance_cents for summary in active if summary.balance_cents < 0
    )
    members_with_balance = len(active)
    over_limit_members = sum(1 for summary in active if summary.over_limit)
    aging = AccountAging(
        current_cents=sum(summary.aging.current_cents for summary in active),
        days_31_60_cents=sum(summary.aging.days_31_60_cents for summary in active),
        days_61_90_cents=sum(summary.aging.days_61_90_cents for summary in active),
        over_90_cents=sum(summary.aging.over_90_cents for summary in active),
    )

    if term:
        active = [
            summary
            for summary in active
            if term
            in f"{summary.member_name} {summary.email or ''} {summary.phone or ''}".lower()
        ]
    if over_limit is not None:
        active = [summary for summary in active if summary.over_limit is over_limit]
    active.sort(
        key=lambda summary: (
            0 if summary.over_limit else 1,
            -summary.balance_cents,
            summary.member_name.lower(),
        )
    )

    total = len(active)
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    start = (page - 1) * page_size
    return MemberAccountPage(
        items=active[start : start + page_size],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_receivable_cents=total_receivable_cents,
        total_credit_cents=total_credit_cents,
        members_with_balance=members_with_balance,
        aging=aging,
        over_limit_members=over_limit_members,
        as_of=as_of,
    )


def member_account_statement(
    session: Session, member_id: UUID, *, today: date | None = None
) -> MemberAccountStatement:
    member = session.get(Member, member_id)
    if member is None:
        raise MemberUnavailable("Socio no encontrado")
    as_of = today or club_date(utc_now())

    raw: list[tuple[datetime, str, str, str, str | None, int]] = []
    for sale in session.exec(
        select(Sale).where(
            Sale.member_id == member_id, Sale.payment_method == "account"
        )
    ).all():
        raw.append(
            (
                _as_utc(sale.sold_at),
                "charge",
                "Venta a cuenta",
                sale.folio,
                "account",
                sale.total_cents,
            )
        )
    for sale_return in session.exec(
        select(SaleReturn).where(
            SaleReturn.member_id == member_id,
            SaleReturn.refund_method == "account",
        )
    ).all():
        raw.append(
            (
                _as_utc(sale_return.returned_at),
                "credit",
                "Devolución abonada",
                sale_return.folio,
                "account",
                -sale_return.total_refund_cents,
            )
        )
    for payment in session.exec(
        select(MemberAccountPayment).where(MemberAccountPayment.member_id == member_id)
    ).all():
        raw.append(
            (
                _as_utc(payment.paid_at),
                "payment",
                "Pago de cuenta",
                payment.note or "Cobro",
                payment.method,
                -payment.amount_cents,
            )
        )

    raw.sort(key=lambda entry: entry[0])
    running = 0
    entries: list[MemberAccountEntry] = []
    for occurred_at, kind, description, reference, method, amount in raw:
        running += amount
        entries.append(
            MemberAccountEntry(
                kind=kind,
                occurred_at=occurred_at,
                description=description,
                reference=reference,
                method=method,
                amount_cents=amount,
                balance_cents=running,
            )
        )

    charges = sum(entry.amount_cents for entry in entries if entry.kind == "charge")
    credits = -sum(entry.amount_cents for entry in entries if entry.kind == "credit")
    payments = -sum(entry.amount_cents for entry in entries if entry.kind == "payment")
    aging = _aging_from_charges(
        [
            (entry.occurred_at, entry.amount_cents)
            for entry in entries
            if entry.kind == "charge"
        ],
        credits + payments,
        as_of=as_of,
    )
    limit = member.credit_limit_cents
    summary = MemberAccountSummary(
        member_id=member.id,
        member_name=f"{member.first_name} {member.last_name}".strip(),
        email=member.email,
        phone=member.phone,
        member_status=member.status,
        charges_cents=charges,
        credits_cents=credits,
        payments_cents=payments,
        balance_cents=running,
        credit_limit_cents=limit,
        credit_available_cents=None if limit is None else limit - running,
        over_limit=limit is not None and running > limit,
        aging=aging,
        charges_count=sum(1 for entry in entries if entry.kind == "charge"),
        payments_count=sum(1 for entry in entries if entry.kind == "payment"),
        last_activity_at=entries[-1].occurred_at if entries else None,
        oldest_charge_at=min(
            (entry.occurred_at for entry in entries if entry.kind == "charge"),
            default=None,
        ),
    )
    entries.reverse()
    return MemberAccountStatement(summary=summary, entries=entries, as_of=as_of)


def update_member_credit_limit(
    session: Session,
    member_id: UUID,
    *,
    credit_limit_cents: int | None,
    today: date | None = None,
) -> MemberAccountSummary:
    """Set or clear the credit limit of a member.

    ``None`` means "no limit": the account keeps accepting charges, which keeps
    existing installations working without forcing a policy. ``0`` means the
    member cannot charge anything until the limit is raised.
    """

    if credit_limit_cents is not None and credit_limit_cents < 0:
        raise InvalidCreditLimit("El límite de crédito no puede ser negativo")
    member = session.get(Member, member_id)
    if member is None:
        raise MemberUnavailable("Socio no encontrado")

    member.credit_limit_cents = credit_limit_cents
    session.add(member)
    session.commit()
    session.refresh(member)
    totals = _member_account_totals(session, today=today)
    return _member_account_summary(member, totals.get(member.id))


def _member_account_payment_view(
    session: Session, payment: MemberAccountPayment
) -> MemberAccountPaymentView:
    member = session.get(Member, payment.member_id)
    actor = session.get(AppUser, payment.actor_id) if payment.actor_id is not None else None
    member_name = f"{member.first_name} {member.last_name}".strip() if member else None
    return MemberAccountPaymentView(
        id=payment.id,
        member_id=payment.member_id,
        member_name=member_name or None,
        cash_session_id=payment.cash_session_id,
        actor_id=payment.actor_id,
        actor_email=actor.email if actor is not None else None,
        method=payment.method,
        amount_cents=payment.amount_cents,
        note=payment.note,
        paid_at=_as_utc(payment.paid_at),
        balance_cents=member_account_balance(session, payment.member_id),
    )


def register_member_account_payment(
    session: Session,
    member_id: UUID,
    *,
    amount_cents: int,
    method: str,
    note: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MemberAccountPaymentView:
    """Record a payment against a member's account.

    The payment is linked to the open register shift so a cash payment raises
    the expected cash at close. Overpaying is rejected: an account never holds a
    credit created by a payment (a negative balance can only come from returns).
    """
    if method not in MEMBER_ACCOUNT_PAYMENT_METHODS:
        raise InvalidAccountPayment("Forma de pago no válida")
    if amount_cents <= 0:
        raise InvalidAccountPayment("El monto del pago debe ser mayor a cero")
    member = session.get(Member, member_id)
    if member is None:
        raise MemberUnavailable("Socio no encontrado")

    cash_session = _find_open_cash_session(session)
    if cash_session is None:
        raise NoOpenCashSession("Abre el turno de caja antes de registrar cobros")

    balance = member_account_balance(session, member_id)
    if balance <= 0:
        raise NoOutstandingBalance("El socio no tiene saldo pendiente")
    if amount_cents > balance:
        raise PaymentExceedsBalance("El pago supera el saldo pendiente del socio")

    normalized_note = (note or "").strip() or None
    if normalized_note is not None and len(normalized_note) > 200:
        raise InvalidAccountPayment("La nota es demasiado larga")

    payment = MemberAccountPayment(
        member_id=member_id,
        cash_session_id=cash_session.id,
        actor_id=actor_id,
        method=method,
        amount_cents=amount_cents,
        note=normalized_note,
        paid_at=_as_utc(now or utc_now()),
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return _member_account_payment_view(session, payment)


# --------------------------------------------------------------------------
# Suppliers and purchase orders (restocking)
# --------------------------------------------------------------------------


def _normalize_optional(value: str | None, *, max_length: int) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise InvalidSupplierData("El valor es demasiado largo")
    return normalized


def create_supplier(
    session: Session,
    *,
    name: str,
    contact_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    notes: str | None = None,
) -> SupplierItem:
    normalized_name = _normalize_required(name, "name", max_length=160)
    if _supplier_name_exists(session, normalized_name):
        raise DuplicateSupplierName("El proveedor ya está registrado")
    supplier = Supplier(
        name=normalized_name,
        contact_name=_normalize_optional(contact_name, max_length=120),
        phone=_normalize_optional(phone, max_length=40),
        email=_normalize_optional(email, max_length=160),
        notes=(notes or "").strip() or None,
    )
    session.add(supplier)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateSupplierName("El proveedor ya está registrado") from error
    session.refresh(supplier)
    return _supplier_item(supplier)


def update_supplier(
    session: Session,
    supplier_id: UUID,
    *,
    name: str,
    contact_name: str | None,
    phone: str | None,
    email: str | None,
    notes: str | None,
    is_active: bool,
) -> SupplierItem:
    supplier = session.get(Supplier, supplier_id)
    if supplier is None:
        raise SupplierNotFound("Proveedor no encontrado")
    normalized_name = _normalize_required(name, "name", max_length=160)
    if _supplier_name_exists(session, normalized_name, excluding=supplier_id):
        raise DuplicateSupplierName("El proveedor ya está registrado")
    supplier.name = normalized_name
    supplier.contact_name = _normalize_optional(contact_name, max_length=120)
    supplier.phone = _normalize_optional(phone, max_length=40)
    supplier.email = _normalize_optional(email, max_length=160)
    supplier.notes = (notes or "").strip() or None
    supplier.is_active = is_active
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateSupplierName("El proveedor ya está registrado") from error
    session.refresh(supplier)
    return _supplier_item(supplier)


def list_suppliers(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_SUPPLIER_PAGE_SIZE,
    search: str | None = None,
    active: bool | None = None,
) -> SupplierPage:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    page_size = min(page_size, MAX_PAGE_SIZE)
    term = (search or "").strip().lower()

    def _apply_filters(statement):
        if term:
            like = f"%{term}%"
            statement = statement.where(
                or_(
                    func.lower(Supplier.name).like(like),
                    func.lower(func.coalesce(Supplier.contact_name, "")).like(like),
                    func.lower(func.coalesce(Supplier.phone, "")).like(like),
                    func.lower(func.coalesce(Supplier.email, "")).like(like),
                )
            )
        if active is not None:
            statement = statement.where(Supplier.is_active.is_(active))
        return statement

    total = int(session.exec(_apply_filters(select(func.count(Supplier.id)))).one() or 0)
    rows = session.exec(
        _apply_filters(select(Supplier))
        .order_by(func.lower(Supplier.name), Supplier.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return SupplierPage(
        items=[_supplier_item(supplier) for supplier in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


def create_purchase_order(
    session: Session,
    *,
    supplier_id: UUID,
    lines: list[tuple[UUID, int, int]],
    expected_at: date | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PurchaseOrderView:
    supplier = session.get(Supplier, supplier_id)
    if supplier is None:
        raise SupplierNotFound("Proveedor no encontrado")
    if not supplier.is_active:
        raise InvalidPurchaseOrderData("El proveedor está inactivo")
    if not lines:
        raise InvalidPurchaseOrderData("La orden debe tener al menos un producto")

    seen: set[UUID] = set()
    prepared: list[tuple[Product, int, int]] = []
    for product_id, quantity, unit_cost_cents in lines:
        if quantity <= 0:
            raise InvalidPurchaseOrderData("La cantidad debe ser mayor que cero")
        if unit_cost_cents < 0:
            raise InvalidPurchaseOrderData("El costo no puede ser negativo")
        if product_id in seen:
            raise InvalidPurchaseOrderData("Un producto no puede repetirse en la orden")
        seen.add(product_id)
        product = session.get(Product, product_id)
        if product is None:
            raise ProductNotFound("Producto no encontrado")
        prepared.append((product, quantity, unit_cost_cents))

    occurred_at = _as_utc(now or utc_now())
    subtotal = sum(quantity * unit_cost_cents for _, quantity, unit_cost_cents in prepared)
    order = PurchaseOrder(
        folio=_build_purchase_folio(occurred_at),
        supplier_id=supplier_id,
        status="created",
        subtotal_cents=subtotal,
        tax_cents=0,
        total_cents=subtotal,
        expected_at=expected_at,
        notes=(notes or "").strip() or None,
        created_by=actor_id,
    )
    session.add(order)
    session.flush()
    for product, quantity, unit_cost_cents in prepared:
        session.add(
            PurchaseOrderItem(
                purchase_order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=quantity,
                received_quantity=0,
                unit_cost_cents=unit_cost_cents,
                line_total_cents=quantity * unit_cost_cents,
            )
        )
    session.commit()
    return get_purchase_order(session, order.id)


def send_purchase_order(
    session: Session,
    purchase_order_id: UUID,
    *,
    now: datetime | None = None,
) -> PurchaseOrderView:
    order = _require_purchase_order(session, purchase_order_id)
    if order.status != "created":
        raise InvalidPurchaseOrderState("Solo una orden recién creada puede enviarse")
    order.status = "sent"
    order.sent_at = _as_utc(now or utc_now())
    session.commit()
    return get_purchase_order(session, order.id)


def receive_purchase_order(
    session: Session,
    purchase_order_id: UUID,
    *,
    lines: list[tuple[UUID, int]],
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PurchaseOrderView:
    order = _require_purchase_order(session, purchase_order_id)
    if order.status not in OPEN_PURCHASE_ORDER_STATUSES:
        raise InvalidPurchaseOrderState("La orden ya no recibe mercancía")
    if not lines:
        raise InvalidPurchaseOrderData("Registra al menos un producto recibido")

    occurred_at = _as_utc(now or utc_now())
    item_rows = session.exec(
        select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order.id)
    ).all()
    items_by_id = {item.id: item for item in item_rows}
    received: list[tuple[PurchaseOrderItem, Product, int]] = []
    seen: set[UUID] = set()
    for item_id, quantity in lines:
        if quantity <= 0:
            raise InvalidPurchaseOrderData("La cantidad recibida debe ser mayor que cero")
        item = items_by_id.get(item_id)
        if item is None:
            raise InvalidPurchaseOrderData("La línea no pertenece a la orden")
        if item_id in seen:
            raise InvalidPurchaseOrderData("Una línea no puede recibirse dos veces")
        seen.add(item_id)
        if item.received_quantity + quantity > item.quantity:
            raise PurchaseOrderOverReceive("No se puede recibir más de lo pedido")
        product = session.get(Product, item.product_id)
        if product is None:
            raise ProductNotFound("Producto no encontrado")
        received.append((item, product, quantity))

    for item, product, quantity in received:
        _apply_stock_delta(session, product.id, quantity)
        session.add(
            InventoryMovement(
                product_id=product.id,
                location=DEFAULT_LOCATION,
                movement_type="intake",
                quantity=quantity,
                reason=f"Recepción {order.folio}",
                reference_type="purchase_order",
                reference_id=order.id,
                actor_id=actor_id,
                occurred_at=occurred_at,
            )
        )
        item.received_quantity += quantity
        # The last paid cost becomes the club's best estimate of replacement cost.
        product.cost_cents = item.unit_cost_cents

    if all(item.received_quantity >= item.quantity for item in item_rows):
        order.status = "received"
        order.received_at = occurred_at
        order.received_by = actor_id
    elif order.status == "created":
        # Receiving goods implies the order was placed with the supplier.
        order.status = "sent"
        order.sent_at = order.sent_at or occurred_at
    session.commit()
    return get_purchase_order(session, order.id)


def cancel_purchase_order(
    session: Session,
    purchase_order_id: UUID,
    *,
    now: datetime | None = None,
) -> PurchaseOrderView:
    order = _require_purchase_order(session, purchase_order_id)
    if order.status not in OPEN_PURCHASE_ORDER_STATUSES:
        raise InvalidPurchaseOrderState("La orden no se puede cancelar")
    received = session.exec(
        select(func.coalesce(func.sum(PurchaseOrderItem.received_quantity), 0)).where(
            PurchaseOrderItem.purchase_order_id == order.id
        )
    ).one()
    if int(received or 0) > 0:
        raise InvalidPurchaseOrderState("No se puede cancelar una orden con mercancía recibida")
    order.status = "cancelled"
    order.cancelled_at = _as_utc(now or utc_now())
    session.commit()
    return get_purchase_order(session, order.id)


def get_purchase_order(session: Session, purchase_order_id: UUID) -> PurchaseOrderView:
    order = _require_purchase_order(session, purchase_order_id)
    session.refresh(order)
    return _purchase_order_view(session, order)


def list_purchase_orders(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PURCHASE_ORDER_PAGE_SIZE,
    search: str | None = None,
    status: str | None = None,
    supplier_id: UUID | None = None,
) -> PurchaseOrderPage:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    if status is not None and status not in PURCHASE_ORDER_STATUSES:
        raise ValueError("Unsupported purchase order status filter")
    page_size = min(page_size, MAX_PAGE_SIZE)
    term = (search or "").strip().lower()

    def _apply_filters(statement):
        if term:
            like = f"%{term}%"
            statement = statement.where(
                or_(
                    func.lower(PurchaseOrder.folio).like(like),
                    func.lower(Supplier.name).like(like),
                )
            )
        if status is not None:
            statement = statement.where(PurchaseOrder.status == status)
        if supplier_id is not None:
            statement = statement.where(PurchaseOrder.supplier_id == supplier_id)
        return statement

    join_condition = Supplier.id == PurchaseOrder.supplier_id
    count_stmt = _apply_filters(
        select(func.count(PurchaseOrder.id)).select_from(PurchaseOrder).join(Supplier, join_condition)
    )
    rows_stmt = _apply_filters(
        select(PurchaseOrder).select_from(PurchaseOrder).join(Supplier, join_condition)
    )
    total = int(session.exec(count_stmt).one() or 0)
    orders = session.exec(
        rows_stmt.order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_purchase_order_view(session, order) for order in orders]
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PurchaseOrderPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=_purchase_order_summary(session),
    )


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------


def _sku_exists(session: Session, sku: str, *, excluding: UUID | None = None) -> bool:
    statement = select(Product.id).where(func.lower(Product.sku) == sku.casefold())
    if excluding is not None:
        statement = statement.where(Product.id != excluding)
    return session.exec(statement).first() is not None


def _barcode_exists(session: Session, barcode: str, *, excluding: UUID | None = None) -> bool:
    statement = select(Product.id).where(Product.barcode == barcode)
    if excluding is not None:
        statement = statement.where(Product.id != excluding)
    return session.exec(statement).first() is not None


def _current_stock(session: Session, product_id: UUID) -> int:
    quantity = session.exec(
        select(InventoryStock.quantity).where(
            InventoryStock.product_id == product_id,
            InventoryStock.location == DEFAULT_LOCATION,
        )
    ).first()
    return int(quantity or 0)


def _apply_stock_delta(session: Session, product_id: UUID, delta: int) -> int:
    """Apply a signed stock delta atomically, keeping the balance non-negative."""
    if delta == 0:
        raise ValueError("Stock delta must not be zero")
    if delta > 0:
        stock = session.exec(
            select(InventoryStock).where(
                InventoryStock.product_id == product_id,
                InventoryStock.location == DEFAULT_LOCATION,
            )
        ).first()
        if stock is None:
            stock = InventoryStock(product_id=product_id, location=DEFAULT_LOCATION, quantity=delta)
            session.add(stock)
            session.flush()
            return delta
        stock.quantity += delta
        session.flush()
        return stock.quantity

    result = session.execute(
        update(InventoryStock)
        .where(
            InventoryStock.product_id == product_id,
            InventoryStock.location == DEFAULT_LOCATION,
            InventoryStock.quantity + delta >= 0,
        )
        .values(quantity=InventoryStock.quantity + delta)
    )
    if result.rowcount != 1:
        raise InsufficientStock("Stock insuficiente para completar la operación")
    quantity = session.exec(
        select(InventoryStock.quantity).where(
            InventoryStock.product_id == product_id,
            InventoryStock.location == DEFAULT_LOCATION,
        )
    ).one()
    return int(quantity)


def _find_open_cash_session(session: Session) -> CashSession | None:
    return session.exec(select(CashSession).where(CashSession.status == "open")).first()


def _product_item(product: Product, stock: int) -> ProductItem:
    return ProductItem(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        barcode=product.barcode,
        price_cents=product.price_cents,
        cost_cents=product.cost_cents,
        stock_min=product.stock_min,
        is_active=product.is_active,
        stock=stock,
        updated_at=_as_utc(product.updated_at),
    )


def _product_summary(session: Session) -> ProductSummary:
    quantity = func.coalesce(InventoryStock.quantity, 0)
    statement = (
        select(
            func.count(Product.id),
            func.coalesce(
                func.sum(case((and_(Product.is_active.is_(True), quantity > Product.stock_min), 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(Product.is_active.is_(True), quantity > 0, quantity <= Product.stock_min),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((and_(Product.is_active.is_(True), quantity <= 0), 1), else_=0)), 0
            ),
            func.coalesce(func.sum(case((Product.is_active.is_(False), 1), else_=0)), 0),
        )
        .select_from(Product)
        .outerjoin(
            InventoryStock,
            and_(InventoryStock.product_id == Product.id, InventoryStock.location == DEFAULT_LOCATION),
        )
    )
    row = session.exec(statement).one()
    return ProductSummary(
        total=int(row[0] or 0),
        active=int(row[1] or 0),
        low_stock=int(row[2] or 0),
        out_of_stock=int(row[3] or 0),
        inactive=int(row[4] or 0),
    )


def _product_categories(session: Session) -> list[str]:
    rows = session.exec(
        select(Product.category)
        .where(Product.is_active.is_(True))
        .distinct()
        .order_by(Product.category)
    ).all()
    return [row for row in rows if row]


def _lines_by_sale(session: Session, sale_ids: list[UUID]) -> dict[UUID, list[SaleLine]]:
    if not sale_ids:
        return {}
    rows = session.exec(
        select(SaleItem).where(SaleItem.sale_id.in_(sale_ids)).order_by(SaleItem.id)
    ).all()
    refunded = _refunded_quantities_by_item(session, [item.id for item in rows])
    result: dict[UUID, list[SaleLine]] = {}
    for item in rows:
        refunded_quantity = refunded.get(item.id, 0)
        result.setdefault(item.sale_id, []).append(
            SaleLine(
                sale_item_id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                line_total_cents=item.line_total_cents,
                refunded_quantity=refunded_quantity,
                returnable_quantity=max(item.quantity - refunded_quantity, 0),
            )
        )
    return result


def _return_lines_by_return(
    session: Session, return_ids: list[UUID]
) -> dict[UUID, list[SaleReturnLine]]:
    if not return_ids:
        return {}
    rows = session.exec(
        select(SaleReturnItem).where(SaleReturnItem.return_id.in_(return_ids)).order_by(SaleReturnItem.id)
    ).all()
    result: dict[UUID, list[SaleReturnLine]] = {}
    for item in rows:
        result.setdefault(item.return_id, []).append(
            SaleReturnLine(
                sale_item_id=item.sale_item_id,
                product_id=item.product_id,
                product_name=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                line_refund_cents=item.line_refund_cents,
                disposition=item.disposition,
            )
        )
    return result


def _sale_view(
    session: Session,
    sale: Sale,
    lines: list[SaleLine],
    *,
    member: Member | None = None,
    cashier: AppUser | None = None,
    refunded_cents: int = 0,
) -> SaleItemView:
    if member is None and sale.member_id is not None:
        member = session.get(Member, sale.member_id)
    if cashier is None and sale.cashier_id is not None:
        cashier = session.get(AppUser, sale.cashier_id)
    member_name = f"{member.first_name} {member.last_name}".strip() if member is not None else None
    return SaleItemView(
        id=sale.id,
        folio=sale.folio,
        status=sale.status,
        payment_method=sale.payment_method,
        member_id=sale.member_id,
        member_name=member_name or None,
        cashier_id=sale.cashier_id,
        cashier_email=cashier.email if cashier is not None else None,
        subtotal_cents=sale.subtotal_cents,
        discount_cents=sale.discount_cents,
        tax_cents=sale.tax_cents,
        total_cents=sale.total_cents,
        refunded_cents=refunded_cents,
        note=sale.note,
        sold_at=_as_utc(sale.sold_at),
        cash_session_id=sale.cash_session_id,
        origin=sale.origin,
        client_reference=sale.client_reference,
        lines=lines,
    )


def _sale_return_view(
    session: Session,
    sale_return: SaleReturn,
    lines: list[SaleReturnLine],
    *,
    sale: Sale | None = None,
    member: Member | None = None,
    actor: AppUser | None = None,
) -> SaleReturnView:
    if sale is None:
        sale = session.get(Sale, sale_return.sale_id)
    if member is None and sale_return.member_id is not None:
        member = session.get(Member, sale_return.member_id)
    if actor is None and sale_return.actor_id is not None:
        actor = session.get(AppUser, sale_return.actor_id)
    member_name = f"{member.first_name} {member.last_name}".strip() if member is not None else None
    return SaleReturnView(
        id=sale_return.id,
        folio=sale_return.folio,
        sale_id=sale_return.sale_id,
        sale_folio=sale.folio if sale is not None else "",
        cash_session_id=sale_return.cash_session_id,
        member_id=sale_return.member_id,
        member_name=member_name or None,
        actor_id=sale_return.actor_id,
        actor_email=actor.email if actor is not None else None,
        refund_method=sale_return.refund_method,
        total_refund_cents=sale_return.total_refund_cents,
        reason=sale_return.reason,
        returned_at=_as_utc(sale_return.returned_at),
        lines=lines,
    )


def _sale_summary(session: Session) -> SaleSummary:
    statement = select(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.total_cents), 0),
        func.coalesce(func.sum(case((Sale.payment_method == "cash", Sale.total_cents), else_=0)), 0),
        func.coalesce(func.sum(case((Sale.payment_method == "card", Sale.total_cents), else_=0)), 0),
        func.coalesce(func.sum(case((Sale.payment_method == "transfer", Sale.total_cents), else_=0)), 0),
        func.coalesce(func.sum(case((Sale.payment_method == "account", Sale.total_cents), else_=0)), 0),
    ).where(Sale.status == "completed")
    row = session.exec(statement).one()
    refunds = _sale_return_summary(session)
    return SaleSummary(
        count=int(row[0] or 0),
        total_cents=int(row[1] or 0),
        cash_cents=int(row[2] or 0),
        card_cents=int(row[3] or 0),
        transfer_cents=int(row[4] or 0),
        account_cents=int(row[5] or 0),
        refunds_cents=refunds.total_refund_cents,
        refunded_count=refunds.count,
    )


def _sale_return_summary(session: Session) -> SaleReturnSummary:
    statement = select(
        func.count(SaleReturn.id),
        func.coalesce(func.sum(SaleReturn.total_refund_cents), 0),
        func.coalesce(func.sum(case((SaleReturn.refund_method == "cash", SaleReturn.total_refund_cents), else_=0)), 0),
        func.coalesce(func.sum(case((SaleReturn.refund_method == "card", SaleReturn.total_refund_cents), else_=0)), 0),
        func.coalesce(func.sum(case((SaleReturn.refund_method == "transfer", SaleReturn.total_refund_cents), else_=0)), 0),
        func.coalesce(func.sum(case((SaleReturn.refund_method == "account", SaleReturn.total_refund_cents), else_=0)), 0),
    )
    row = session.exec(statement).one()
    return SaleReturnSummary(
        count=int(row[0] or 0),
        total_refund_cents=int(row[1] or 0),
        cash_refund_cents=int(row[2] or 0),
        card_refund_cents=int(row[3] or 0),
        transfer_refund_cents=int(row[4] or 0),
        account_refund_cents=int(row[5] or 0),
    )


def _refunded_quantities_by_item(session: Session, sale_item_ids: list[UUID]) -> dict[UUID, int]:
    if not sale_item_ids:
        return {}
    rows = session.exec(
        select(SaleReturnItem.sale_item_id, func.coalesce(func.sum(SaleReturnItem.quantity), 0))
        .where(SaleReturnItem.sale_item_id.in_(sale_item_ids))
        .group_by(SaleReturnItem.sale_item_id)
    ).all()
    return {sale_item_id: int(quantity or 0) for sale_item_id, quantity in rows}


def _refunded_cents_by_sale(session: Session, sale_ids: list[UUID]) -> dict[UUID, int]:
    if not sale_ids:
        return {}
    rows = session.exec(
        select(SaleReturn.sale_id, func.coalesce(func.sum(SaleReturn.total_refund_cents), 0))
        .where(SaleReturn.sale_id.in_(sale_ids))
        .group_by(SaleReturn.sale_id)
    ).all()
    return {sale_id: int(amount or 0) for sale_id, amount in rows}


def _cash_session_totals(session: Session, cash_session_id: UUID) -> dict[str, int]:
    # Every sale rung up in the shift counts, even after a full return flips it
    # to ``refunded``: the cash did enter the drawer here, and the return rows
    # (linked to the shift that paid them) already subtract the outflow. Filtering
    # by status would erase the inflow and count the refund twice.
    rows = session.exec(
        select(Sale.payment_method, func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0))
        .where(Sale.cash_session_id == cash_session_id)
        .group_by(Sale.payment_method)
    ).all()
    totals = {
        "cash_cents": 0,
        "card_cents": 0,
        "transfer_cents": 0,
        "account_cents": 0,
        "count": 0,
        "total_cents": 0,
        "refund_count": 0,
        "total_refunds_cents": 0,
        "cash_refunds_cents": 0,
        "account_refunds_cents": 0,
        "account_payments_count": 0,
        "account_payments_cents": 0,
        "cash_account_payments_cents": 0,
        "membership_payments_count": 0,
        "membership_payments_cents": 0,
        "cash_membership_payments_cents": 0,
    }
    for method, count, amount in rows:
        totals["count"] += int(count or 0)
        totals["total_cents"] += int(amount or 0)
        if method == "cash":
            totals["cash_cents"] = int(amount or 0)
        elif method == "card":
            totals["card_cents"] = int(amount or 0)
        elif method == "transfer":
            totals["transfer_cents"] = int(amount or 0)
        elif method == "account":
            totals["account_cents"] = int(amount or 0)
    refund_rows = session.exec(
        select(
            SaleReturn.refund_method,
            func.count(SaleReturn.id),
            func.coalesce(func.sum(SaleReturn.total_refund_cents), 0),
        )
        .where(SaleReturn.cash_session_id == cash_session_id)
        .group_by(SaleReturn.refund_method)
    ).all()
    for method, count, amount in refund_rows:
        totals["refund_count"] += int(count or 0)
        totals["total_refunds_cents"] += int(amount or 0)
        if method == "cash":
            totals["cash_refunds_cents"] = int(amount or 0)
        elif method == "account":
            totals["account_refunds_cents"] = int(amount or 0)
    payment_rows = session.exec(
        select(
            MemberAccountPayment.method,
            func.count(MemberAccountPayment.id),
            func.coalesce(func.sum(MemberAccountPayment.amount_cents), 0),
        )
        .where(MemberAccountPayment.cash_session_id == cash_session_id)
        .group_by(MemberAccountPayment.method)
    ).all()
    for method, count, amount in payment_rows:
        totals["account_payments_count"] += int(count or 0)
        totals["account_payments_cents"] += int(amount or 0)
        if method == "cash":
            totals["cash_account_payments_cents"] = int(amount or 0)
    membership_payment_rows = session.exec(
        select(
            Payment.method,
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount_cents), 0),
        )
        .where(Payment.cash_session_id == cash_session_id)
        .group_by(Payment.method)
    ).all()
    for method, count, amount in membership_payment_rows:
        totals["membership_payments_count"] += int(count or 0)
        totals["membership_payments_cents"] += int(amount or 0)
        if method == "cash":
            totals["cash_membership_payments_cents"] = int(amount or 0)
    return totals


def _cash_session_view(session: Session, cash_session: CashSession) -> CashSessionView:
    totals = _cash_session_totals(session, cash_session.id)
    expected = (
        cash_session.opening_cash_cents
        + totals["cash_cents"]
        - totals["cash_refunds_cents"]
        + totals["cash_account_payments_cents"]
        + totals["cash_membership_payments_cents"]
    )
    opened_by_email = _user_email(session, cash_session.opened_by)
    closed_by_email = _user_email(session, cash_session.closed_by)
    if cash_session.status == "open":
        expected_cash_cents = expected
        counted_cash_cents = None
        difference_cents = None
    else:
        expected_cash_cents = cash_session.expected_cash_cents if cash_session.expected_cash_cents is not None else expected
        counted_cash_cents = cash_session.counted_cash_cents
        difference_cents = cash_session.difference_cents
    return CashSessionView(
        id=cash_session.id,
        status=cash_session.status,
        opened_by=cash_session.opened_by,
        opened_by_email=opened_by_email,
        opened_at=_as_utc(cash_session.opened_at),
        opening_cash_cents=cash_session.opening_cash_cents,
        closed_by=cash_session.closed_by,
        closed_by_email=closed_by_email,
        closed_at=_as_utc(cash_session.closed_at) if cash_session.closed_at is not None else None,
        expected_cash_cents=expected_cash_cents,
        counted_cash_cents=counted_cash_cents,
        difference_cents=difference_cents,
        notes=cash_session.notes,
        sales_count=totals["count"],
        total_sales_cents=totals["total_cents"],
        cash_sales_cents=totals["cash_cents"],
        card_sales_cents=totals["card_cents"],
        transfer_sales_cents=totals["transfer_cents"],
        account_sales_cents=totals["account_cents"],
        refunds_count=totals["refund_count"],
        total_refunds_cents=totals["total_refunds_cents"],
        cash_refunds_cents=totals["cash_refunds_cents"],
        account_refunds_cents=totals["account_refunds_cents"],
        account_payments_count=totals["account_payments_count"],
        account_payments_cents=totals["account_payments_cents"],
        cash_account_payments_cents=totals["cash_account_payments_cents"],
        membership_payments_count=totals["membership_payments_count"],
        membership_payments_cents=totals["membership_payments_cents"],
        cash_membership_payments_cents=totals["cash_membership_payments_cents"],
    )


def _user_email(session: Session, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    user = session.get(AppUser, user_id)
    return user.email if user is not None else None


def _supplier_name_exists(session: Session, name: str, *, excluding: UUID | None = None) -> bool:
    statement = select(Supplier.id).where(func.lower(Supplier.name) == name.casefold())
    if excluding is not None:
        statement = statement.where(Supplier.id != excluding)
    return session.exec(statement).first() is not None


def _require_purchase_order(session: Session, purchase_order_id: UUID) -> PurchaseOrder:
    order = session.get(PurchaseOrder, purchase_order_id)
    if order is None:
        raise PurchaseOrderNotFound("Orden de compra no encontrada")
    return order


def _supplier_item(supplier: Supplier) -> SupplierItem:
    return SupplierItem(
        id=supplier.id,
        name=supplier.name,
        contact_name=supplier.contact_name,
        phone=supplier.phone,
        email=supplier.email,
        notes=supplier.notes,
        is_active=supplier.is_active,
        created_at=_as_utc(supplier.created_at),
        updated_at=_as_utc(supplier.updated_at),
    )


def _purchase_order_lines(session: Session, order_id: UUID) -> list[PurchaseOrderLine]:
    rows = session.exec(
        select(PurchaseOrderItem)
        .where(PurchaseOrderItem.purchase_order_id == order_id)
        .order_by(PurchaseOrderItem.product_name, PurchaseOrderItem.id)
    ).all()
    return [
        PurchaseOrderLine(
            item_id=item.id,
            product_id=item.product_id,
            product_name=item.product_name,
            sku=item.sku,
            quantity=item.quantity,
            received_quantity=item.received_quantity,
            pending_quantity=item.quantity - item.received_quantity,
            unit_cost_cents=item.unit_cost_cents,
            line_total_cents=item.line_total_cents,
        )
        for item in rows
    ]


def _purchase_order_view(session: Session, order: PurchaseOrder) -> PurchaseOrderView:
    supplier = session.get(Supplier, order.supplier_id)
    return PurchaseOrderView(
        id=order.id,
        folio=order.folio,
        supplier_id=order.supplier_id,
        supplier_name=supplier.name if supplier is not None else "",
        status=order.status,
        subtotal_cents=order.subtotal_cents,
        tax_cents=order.tax_cents,
        total_cents=order.total_cents,
        expected_at=order.expected_at,
        notes=order.notes,
        created_by=order.created_by,
        created_by_email=_user_email(session, order.created_by),
        received_by=order.received_by,
        received_by_email=_user_email(session, order.received_by),
        created_at=_as_utc(order.created_at),
        sent_at=_as_utc(order.sent_at) if order.sent_at is not None else None,
        received_at=_as_utc(order.received_at) if order.received_at is not None else None,
        cancelled_at=_as_utc(order.cancelled_at) if order.cancelled_at is not None else None,
        lines=_purchase_order_lines(session, order.id),
    )


def _purchase_order_summary(session: Session) -> PurchaseOrderSummary:
    statement = select(
        func.count(PurchaseOrder.id),
        func.coalesce(func.sum(case((PurchaseOrder.status == "created", 1), else_=0)), 0),
        func.coalesce(func.sum(case((PurchaseOrder.status == "sent", 1), else_=0)), 0),
        func.coalesce(func.sum(case((PurchaseOrder.status == "received", 1), else_=0)), 0),
        func.coalesce(func.sum(case((PurchaseOrder.status == "cancelled", 1), else_=0)), 0),
        func.coalesce(
            func.sum(
                case((PurchaseOrder.status != "cancelled", PurchaseOrder.total_cents), else_=0)
            ),
            0,
        ),
    )
    row = session.exec(statement).one()
    return PurchaseOrderSummary(
        count=int(row[0] or 0),
        created=int(row[1] or 0),
        sent=int(row[2] or 0),
        received=int(row[3] or 0),
        cancelled=int(row[4] or 0),
        total_cents=int(row[5] or 0),
    )


def _build_folio(occurred_at: datetime) -> str:
    return f"V-{club_day_stamp(occurred_at)}-{uuid4().hex[:6].upper()}"


def _build_return_folio(occurred_at: datetime) -> str:
    return f"D-{club_day_stamp(occurred_at)}-{uuid4().hex[:6].upper()}"


def _build_purchase_folio(occurred_at: datetime) -> str:
    return f"OC-{club_day_stamp(occurred_at)}-{uuid4().hex[:6].upper()}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
