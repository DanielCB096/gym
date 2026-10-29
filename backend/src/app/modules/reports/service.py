"""Read-only analytics over the data the other modules already keep.

Reports never write. They aggregate what memberships, the point of sale, access
control, classes, routines and maintenance recorded, and they keep two kinds of
money apart on purpose:

* **collected** money —``payments`` (memberships) and ``sales`` (point of sale)—
  is cash the club actually received;
* **expected** money —the monthly recurring value of the active memberships— is
  what the club would bill next month. It is *not* a collection and the panel
  labels it as such, because the payment gateway is still a preview stub.

Every report is bounded to a period (``date_from``/``date_to``, both inclusive)
and to a maximum span, so a request can never scan an unbounded table. Both the
period bounds and the day/hour buckets use the club's calendar
(:data:`DEFAULT_TIMEZONE`, overridable with ``APP_TIMEZONE``): timestamps are
stored in UTC, so they are converted before grouping. Otherwise an evening sale
(made after 18:00 in Mexico) would be counted on the next UTC day and a report
ending "today" would miss it. The day buckets are computed in SQL, with a
dialect-aware expression that SQLAlchemy compiles for both SQLite and
PostgreSQL.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlmodel import Session

from app.modules.access.models import AccessEvent
from app.modules.billing.service import PpdReceivableSummary, list_ppd_receivables
from app.modules.classes.models import ClassReservation, ClassSession
from app.modules.inventory.models import (
    OPEN_PURCHASE_ORDER_STATUSES,
    CashSession,
    InventoryMovement,
    InventoryStock,
    Product,
    PurchaseOrder,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
    Supplier,
)
from app.modules.maintenance.models import (
    LIVE_EQUIPMENT_STATUSES,
    OPEN_TICKET_STATUSES,
    Equipment,
    MaintenanceRecord,
    MaintenanceTicket,
)
from app.modules.memberships.models import (
    Member,
    Membership,
    MembershipEvent,
    Payment,
    Plan,
)
from app.modules.routines.models import BodyMeasurement, WorkoutLog
from app.timezone import DEFAULT_TIMEZONE, club_timezone, local_midnight

DEFAULT_PERIOD_DAYS = 30
MAX_PERIOD_DAYS = 730

# Category used for sale lines without a product (a premium class charge), so
# the category breakdown never loses that revenue.
SERVICE_CATEGORY = "Servicios"

# Plans shorter than this are day passes. They are left out of the recurring
# value: normalising a one-day plan to a month would inflate the figure.
MIN_RECURRING_PLAN_DAYS = 7
DAYS_PER_MONTH = 30
EXPIRING_SOON_DAYS = 7
TOP_PRODUCT_LIMIT = 10

REPORT_NAMES = ("overview", "revenue", "memberships", "operations", "maintenance", "inventory")

# Membership events that add a live membership versus the ones that end one.
ACTIVATION_EVENTS = ("payment_confirmed", "manual_activation")
TERMINATION_EVENTS = ("cancelled", "frozen")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ReportError(Exception):
    pass


class InvalidReportPeriod(ReportError):
    pass


class UnknownReport(ReportError):
    pass


# --------------------------------------------------------------------------- #
# Timezone-aware SQL helpers
# --------------------------------------------------------------------------- #
#
# The zone itself is resolved by ``app.timezone`` (shared with the access log,
# the point of sale and maintenance). Here we only turn it into SQL: the day and
# hour buckets of a stored UTC timestamp.


def _offset_seconds(local_timezone: ZoneInfo, reference: datetime) -> int:
    offset = reference.astimezone(local_timezone).utcoffset()
    return int(offset.total_seconds()) if offset is not None else 0


def _local_day_expression(session: Session, column, period: "ReportPeriod"):
    """SQL group key: the local calendar day of a stored UTC timestamp.

    PostgreSQL converts the instant with ``timezone(...)``. SQLite —preview and
    tests— has no timezone-aware date function, so the column is shifted by the
    zone offset. The offset is taken once per period, which is exact for zones
    without DST (the default, ``America/Mexico_City``).
    """

    bind = session.get_bind()
    if bind is not None and bind.dialect.name.startswith("postgres"):
        return func.date(func.timezone(period.local_timezone.key, column))
    return func.date(column, f"{_offset_seconds(period.local_timezone, period.end_at):+d} seconds")


def _local_hour_expression(session: Session, column, period: "ReportPeriod"):
    """SQL expression: local hour of day (0-23) of a stored UTC timestamp."""

    bind = session.get_bind()
    if bind is not None and bind.dialect.name.startswith("postgres"):
        return func.extract("hour", func.timezone(period.local_timezone.key, column))
    shifted = func.datetime(column, f"{_offset_seconds(period.local_timezone, period.end_at):+d} seconds")
    return func.extract("hour", shifted)


# --------------------------------------------------------------------------- #
# Period
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReportPeriod:
    date_from: date
    date_to: date
    # Calendar the window is expressed in. Both bounds and every day/hour bucket
    # use it, so a report matches the club's clock instead of UTC.
    timezone_name: str = DEFAULT_TIMEZONE

    @property
    def local_timezone(self) -> ZoneInfo:
        return club_timezone(self.timezone_name)

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    @property
    def start_at(self) -> datetime:
        return local_midnight(self.date_from, self.local_timezone)

    @property
    def end_at(self) -> datetime:
        # Half-open upper bound: the whole ``date_to`` local day is included.
        return local_midnight(self.date_to + timedelta(days=1), self.local_timezone)


def resolve_period(
    date_from: date | None = None,
    date_to: date | None = None,
    *,
    today: date | None = None,
    timezone_name: str | None = None,
) -> ReportPeriod:
    """Normalises and validates the requested window.

    With no arguments the period is the last :data:`DEFAULT_PERIOD_DAYS` days
    ending **today in the club's calendar** (``APP_TIMEZONE``, default
    :data:`DEFAULT_TIMEZONE`), both ends inclusive. The dates are local calendar
    days, so a report ending "today" includes the sales and refunds made during
    the local evening.
    """

    name = club_timezone(timezone_name).key
    reference = today or datetime.now(timezone.utc).astimezone(club_timezone(name)).date()
    end = date_to or reference
    start = date_from or (end - timedelta(days=DEFAULT_PERIOD_DAYS - 1))
    if start > end:
        raise InvalidReportPeriod("La fecha inicial no puede ser posterior a la final")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise InvalidReportPeriod(
            f"El periodo no puede exceder {MAX_PERIOD_DAYS} días"
        )
    return ReportPeriod(date_from=start, date_to=end, timezone_name=name)


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CountRow:
    label: str
    count: int


@dataclass(frozen=True)
class AmountRow:
    label: str
    count: int
    amount_cents: int


@dataclass(frozen=True)
class RevenueDay:
    day: date
    pos_cents: int
    membership_cents: int
    sales_count: int
    # Refunds paid that day. ``pos_cents`` is already net of them; the extra
    # field exposes the gross figure so the export and the tooltip can show it.
    refunds_cents: int = 0

    @property
    def total_cents(self) -> int:
        return self.pos_cents + self.membership_cents


@dataclass(frozen=True)
class AccessDay:
    day: date
    total: int
    denied: int


@dataclass(frozen=True)
class ClassDay:
    day: date
    sessions: int
    attended: int


@dataclass(frozen=True)
class EventDay:
    day: date
    activations: int
    terminations: int


@dataclass(frozen=True)
class PlanTotal:
    plan_id: UUID
    name: str
    price_cents: int
    duration_days: int
    active_count: int
    monthly_cents: int
    recurring: bool


@dataclass(frozen=True)
class ProductTotal:
    product_id: UUID | None
    name: str
    sku: str
    quantity: int
    amount_cents: int


@dataclass(frozen=True)
class EquipmentTotal:
    equipment_id: UUID
    name: str
    category: str
    location: str | None
    status: str
    records_count: int
    cost_cents: int
    open_tickets: int


@dataclass(frozen=True)
class MovementTotal:
    """Inventory ledger activity for one movement type in the period.

    ``units`` is signed: positive for goods coming in (intake, returns),
    negative for goods leaving (sales, waste) and either sign for adjustments.
    """

    label: str
    movements: int
    units: int


@dataclass(frozen=True)
class InventoryProductTotal:
    product_id: UUID
    name: str
    sku: str
    category: str
    quantity: int
    cost_cents: int
    price_cents: int
    cost_value_cents: int
    retail_value_cents: int


@dataclass(frozen=True)
class OverviewReport:
    period: ReportPeriod
    pos_cents: int
    pos_gross_cents: int
    refunds_cents: int
    refunds_count: int
    membership_cents: int
    sales_count: int
    average_ticket_cents: int
    payments_count: int
    mrr_expected_cents: int
    maintenance_cost_cents: int
    maintenance_records: int
    access_total: int
    access_denied: int
    access_manual: int
    class_sessions: int
    class_capacity: int
    class_attended: int
    class_no_show: int
    class_occupancy_percent: int
    workouts: int
    measurements: int
    members_by_status: list[CountRow]
    memberships_by_status: list[CountRow]
    new_members: int
    members_expiring: int
    equipment_by_status: list[CountRow]
    equipment_total: int
    tickets_open: int
    tickets_critical: int
    revenue_by_day: list[RevenueDay]
    access_by_day: list[AccessDay]


@dataclass(frozen=True)
class RevenueReport:
    period: ReportPeriod
    pos_cents: int
    pos_gross_cents: int
    refunds_cents: int
    refunds_count: int
    membership_cents: int
    sales_count: int
    average_ticket_cents: int
    payments_count: int
    by_day: list[RevenueDay]
    pos_by_method: list[AmountRow]
    membership_by_method: list[AmountRow]
    by_category: list[AmountRow]
    top_products: list[ProductTotal]
    cash_sessions_opened: int
    cash_sessions_closed: int
    cash_difference_cents: int
    ppd_receivables: PpdReceivableSummary


@dataclass(frozen=True)
class MembershipReport:
    period: ReportPeriod
    members_total: int
    members_by_status: list[CountRow]
    memberships_by_status: list[CountRow]
    by_plan: list[PlanTotal]
    mrr_expected_cents: int
    payments_cents: int
    payments_count: int
    events: list[CountRow]
    events_by_day: list[EventDay]
    new_members: int
    members_expiring: int


@dataclass(frozen=True)
class OperationsReport:
    period: ReportPeriod
    access_total: int
    access_authorized: int
    access_denied: int
    access_manual: int
    access_by_day: list[AccessDay]
    access_by_hour: list[CountRow]
    class_sessions: int
    class_capacity: int
    class_reserved: int
    class_attended: int
    class_no_show: int
    class_waitlist: int
    class_cancelled: int
    class_occupancy_percent: int
    classes_by_day: list[ClassDay]
    workouts: int
    workout_minutes: int
    measurements: int
    workouts_by_day: list[CountRow]


@dataclass(frozen=True)
class MaintenanceReport:
    period: ReportPeriod
    cost_cents: int
    records_count: int
    by_kind: list[AmountRow]
    by_equipment: list[EquipmentTotal]
    tickets_created: int
    tickets_by_status: list[CountRow]
    tickets_by_severity: list[CountRow]
    equipment_by_status: list[CountRow]
    preventives_due: int


@dataclass(frozen=True)
class InventoryReport:
    """Stock on hand (a snapshot) plus what the period did to it.

    The valuation half reads the current balances —there is no stored history of
    stock levels, only the movement ledger— so it is a snapshot ``al corte`` and
    ignores the period. The movement, purchase and supplier halves are bounded
    to the period like every other report. Money is kept in cents throughout.
    """

    period: ReportPeriod
    # Snapshot: current stock, independent of the period window.
    products_total: int
    products_active: int
    products_inactive: int
    stock_units: int
    stock_value_cents: int
    retail_value_cents: int
    low_stock: int
    out_of_stock: int
    by_category: list[AmountRow]
    by_product: list[InventoryProductTotal]
    suppliers_total: int
    suppliers_active: int
    open_orders: int
    open_orders_value_cents: int
    # Period: what the ledger and the purchase orders did in the window.
    movements_count: int
    movements_by_type: list[MovementTotal]
    units_in: int
    units_out: int
    orders_created: int
    orders_by_status: list[CountRow]
    orders_value_cents: int
    orders_received: int
    orders_received_value_cents: int
    by_supplier: list[AmountRow]


@dataclass(frozen=True)
class ExportTable:
    title: str
    headers: list[str]
    rows: list[list[str]]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _int(value: object) -> int:
    return int(value or 0)  # type: ignore[arg-type]


def _to_day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _days(period: ReportPeriod) -> list[date]:
    return [period.date_from + timedelta(days=offset) for offset in range(period.days)]


def _scalar(session: Session, statement) -> int:
    # ``session.exec`` yields a ``Row`` for a plain ``select(expression)``, so the
    # value is unwrapped explicitly instead of relying on scalar coercion.
    value = session.exec(statement).one()
    if isinstance(value, (int, float)):
        return int(value)
    return _int(value[0])


def _count(session: Session, model, *conditions) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return _scalar(session, statement)


def _grouped_counts(session: Session, column, *conditions) -> list[CountRow]:
    statement = select(column, func.count()).group_by(column).order_by(func.count().desc())
    if conditions:
        statement = statement.where(*conditions)
    return [
        CountRow(label=str(label), count=_int(count))
        for label, count in session.exec(statement).all()
    ]


def _daily_counts(
    session: Session,
    day_column,
    *,
    period: ReportPeriod | None = None,
    date_column: bool = False,
    conditions: tuple = (),
) -> dict[date, int]:
    """Counts per day for a datetime (or plain date) column.

    Plain date columns are already local and are grouped as stored; UTC
    timestamps are grouped by the club's local day.
    """

    day_expression = (
        func.date(day_column)
        if date_column or period is None
        else _local_day_expression(session, day_column, period)
    )
    statement = select(day_expression, func.count()).group_by(day_expression)
    if period is not None:
        if date_column:
            statement = statement.where(
                day_column >= period.date_from, day_column <= period.date_to
            )
        else:
            statement = statement.where(
                day_column >= period.start_at, day_column < period.end_at
            )
    if conditions:
        statement = statement.where(*conditions)
    return {_to_day(raw): _int(count) for raw, count in session.exec(statement).all()}


def _daily_amounts(session: Session, day_column, expression, period, *conditions) -> dict[date, int]:
    day_expression = _local_day_expression(session, day_column, period)
    statement = (
        select(day_expression, expression)
        .where(day_column >= period.start_at, day_column < period.end_at)
        .group_by(day_expression)
    )
    if conditions:
        statement = statement.where(*conditions)
    return {_to_day(raw): _int(value) for raw, value in session.exec(statement).all()}


# --------------------------------------------------------------------------- #
# Shared pieces
# --------------------------------------------------------------------------- #


def _pos_totals(session: Session, period: ReportPeriod) -> tuple[int, int, int, int]:
    """Counter money for the period as ``(sales_count, gross_cents, refunds_count, refunds_cents)``.

    Sales are counted **whatever their status**: a fully refunded sale is still a
    transaction that was rung up in this period, and its refund is subtracted
    separately, so counting it in the gross keeps gross minus refunds truthful
    instead of dropping it from one side and not the other.

    Refunds are netted on a **cash basis**: a refund belongs to the period it was
    paid in (``returned_at``), not to the day of the original sale. That matches
    how the cash session already treats a refund—it lowers the expected cash of
    the shift that paid it—and keeps net counter money reconcilable with the till.
    """

    sales_row = session.exec(
        select(
            func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)
        ).where(
            Sale.sold_at >= period.start_at,
            Sale.sold_at < period.end_at,
        )
    ).one()
    refunds_row = session.exec(
        select(
            func.count(SaleReturn.id),
            func.coalesce(func.sum(SaleReturn.total_refund_cents), 0),
        ).where(
            SaleReturn.returned_at >= period.start_at,
            SaleReturn.returned_at < period.end_at,
        )
    ).one()
    return _int(sales_row[0]), _int(sales_row[1]), _int(refunds_row[0]), _int(refunds_row[1])


def _payment_totals(session: Session, period: ReportPeriod) -> tuple[int, int]:
    statement = select(
        func.count(Payment.id), func.coalesce(func.sum(Payment.amount_cents), 0)
    ).where(Payment.paid_at >= period.start_at, Payment.paid_at < period.end_at)
    row = session.exec(statement).one()
    return _int(row[0]), _int(row[1])


def _revenue_by_day(session: Session, period: ReportPeriod) -> list[RevenueDay]:
    pos = _daily_amounts(
        session,
        Sale.sold_at,
        func.coalesce(func.sum(Sale.total_cents), 0),
        period,
    )
    sales_counts = _daily_amounts(
        session,
        Sale.sold_at,
        func.count(Sale.id),
        period,
    )
    refunds = _daily_amounts(
        session,
        SaleReturn.returned_at,
        func.coalesce(func.sum(SaleReturn.total_refund_cents), 0),
        period,
    )
    membership = _daily_amounts(
        session,
        Payment.paid_at,
        func.coalesce(func.sum(Payment.amount_cents), 0),
        period,
    )
    return [
        RevenueDay(
            day=day,
            pos_cents=pos.get(day, 0) - refunds.get(day, 0),
            membership_cents=membership.get(day, 0),
            sales_count=sales_counts.get(day, 0),
            refunds_cents=refunds.get(day, 0),
        )
        for day in _days(period)
    ]


def _pos_method_totals(session: Session, period: ReportPeriod) -> dict[str, tuple[int, int]]:
    """Gross counter money per payment method: ``{method: (sales_count, gross_cents)}``."""

    return {
        str(method): (_int(count), _int(amount))
        for method, count, amount in session.exec(
            select(
                Sale.payment_method,
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.total_cents), 0),
            )
            .where(Sale.sold_at >= period.start_at, Sale.sold_at < period.end_at)
            .group_by(Sale.payment_method)
        ).all()
    }


def _refund_method_totals(session: Session, period: ReportPeriod) -> dict[str, int]:
    """Refunded money per payout method in the period: ``{method: refund_cents}``."""

    return {
        str(method): _int(amount)
        for method, amount in session.exec(
            select(
                SaleReturn.refund_method,
                func.coalesce(func.sum(SaleReturn.total_refund_cents), 0),
            )
            .where(
                SaleReturn.returned_at >= period.start_at,
                SaleReturn.returned_at < period.end_at,
            )
            .group_by(SaleReturn.refund_method)
        ).all()
    }


def _sold_category_totals(session: Session, period: ReportPeriod) -> dict[str, list[int]]:
    """Sold quantity and money per category: ``{category: [quantity, cents]}``."""

    return {
        str(category): [_int(quantity), _int(amount)]
        for category, quantity, amount in session.exec(
            select(
                func.coalesce(Product.category, SERVICE_CATEGORY),
                func.coalesce(func.sum(SaleItem.quantity), 0),
                func.coalesce(func.sum(SaleItem.line_total_cents), 0),
            )
            .outerjoin(Product, Product.id == SaleItem.product_id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(Sale.sold_at >= period.start_at, Sale.sold_at < period.end_at)
            .group_by(Product.category)
        ).all()
    }


def _returned_category_totals(session: Session, period: ReportPeriod) -> dict[str, list[int]]:
    """Returned quantity and money per category, by the day the refund was paid."""

    return {
        str(category): [_int(quantity), _int(amount)]
        for category, quantity, amount in session.exec(
            select(
                func.coalesce(Product.category, SERVICE_CATEGORY),
                func.coalesce(func.sum(SaleReturnItem.quantity), 0),
                func.coalesce(func.sum(SaleReturnItem.line_refund_cents), 0),
            )
            .outerjoin(Product, Product.id == SaleReturnItem.product_id)
            .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
            .where(
                SaleReturn.returned_at >= period.start_at,
                SaleReturn.returned_at < period.end_at,
            )
            .group_by(Product.category)
        ).all()
    }


def _product_totals(session: Session, period: ReportPeriod) -> dict[UUID | None, dict]:
    """Net quantity and money per product: sales minus refunds paid in the period.

    A service line (a premium class) has no product id; it is grouped under
    ``None`` and keeps its own description, so the report still balances.
    """

    totals: dict[UUID | None, dict] = {}

    def bucket(product_id: UUID | None, name: object, sku: object) -> dict:
        return totals.setdefault(
            product_id,
            {"name": str(name), "sku": str(sku), "quantity": 0, "amount_cents": 0},
        )

    for product_id, name, sku, quantity, amount in session.exec(
        select(
            SaleItem.product_id,
            SaleItem.product_name,
            SaleItem.sku,
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.coalesce(func.sum(SaleItem.line_total_cents), 0),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(Sale.sold_at >= period.start_at, Sale.sold_at < period.end_at)
        .group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.sku)
    ).all():
        entry = bucket(product_id, name, sku)
        entry["quantity"] += _int(quantity)
        entry["amount_cents"] += _int(amount)

    for product_id, name, sku, quantity, amount in session.exec(
        select(
            SaleReturnItem.product_id,
            SaleReturnItem.product_name,
            SaleReturnItem.sku,
            func.coalesce(func.sum(SaleReturnItem.quantity), 0),
            func.coalesce(func.sum(SaleReturnItem.line_refund_cents), 0),
        )
        .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
        .where(
            SaleReturn.returned_at >= period.start_at,
            SaleReturn.returned_at < period.end_at,
        )
        .group_by(SaleReturnItem.product_id, SaleReturnItem.product_name, SaleReturnItem.sku)
    ).all():
        entry = bucket(product_id, name, sku)
        entry["quantity"] -= _int(quantity)
        entry["amount_cents"] -= _int(amount)

    return totals


def _access_totals(session: Session, period: ReportPeriod) -> tuple[int, int, int]:
    statement = select(
        func.count(AccessEvent.id),
        func.coalesce(func.sum(case((AccessEvent.authorized.is_(False), 1), else_=0)), 0),
        func.coalesce(func.sum(case((AccessEvent.source == "manual", 1), else_=0)), 0),
    ).where(
        AccessEvent.occurred_at >= period.start_at,
        AccessEvent.occurred_at < period.end_at,
    )
    row = session.exec(statement).one()
    return _int(row[0]), _int(row[1]), _int(row[2])


def _access_by_day(session: Session, period: ReportPeriod) -> list[AccessDay]:
    access_day = _local_day_expression(session, AccessEvent.occurred_at, period)
    statement = (
        select(
            access_day,
            func.count(AccessEvent.id),
            func.coalesce(
                func.sum(case((AccessEvent.authorized.is_(False), 1), else_=0)), 0
            ),
        )
        .where(
            AccessEvent.occurred_at >= period.start_at,
            AccessEvent.occurred_at < period.end_at,
        )
        .group_by(access_day)
    )
    buckets = {
        _to_day(raw): (_int(total), _int(denied))
        for raw, total, denied in session.exec(statement).all()
    }
    return [
        AccessDay(day=day, total=buckets.get(day, (0, 0))[0], denied=buckets.get(day, (0, 0))[1])
        for day in _days(period)
    ]


def _class_totals(session: Session, period: ReportPeriod) -> dict[str, int]:
    """Sessions offered and reservations by status for sessions in the period."""

    sessions, capacity = session.exec(
        select(func.count(ClassSession.id), func.coalesce(func.sum(ClassSession.capacity), 0)).where(
            ClassSession.starts_at >= period.start_at,
            ClassSession.starts_at < period.end_at,
        )
    ).one()
    status_rows = session.exec(
        select(ClassReservation.status, func.count(ClassReservation.id))
        .join(ClassSession, ClassSession.id == ClassReservation.session_id)
        .where(
            ClassSession.starts_at >= period.start_at,
            ClassSession.starts_at < period.end_at,
        )
        .group_by(ClassReservation.status)
    ).all()
    totals = {
        "sessions": _int(sessions),
        "capacity": _int(capacity),
        "reserved": 0,
        "attended": 0,
        "no_show": 0,
        "waitlist": 0,
        "cancelled": 0,
    }
    for status, count in status_rows:
        if status in totals:
            totals[status] = _int(count)
    # "Occupied" matches the classes module: a confirmed or attended seat.
    occupied = totals["reserved"] + totals["attended"]
    totals["occupied"] = occupied
    totals["occupancy_percent"] = (
        round(occupied / totals["capacity"] * 100) if totals["capacity"] else 0
    )
    return totals


def _membership_state(session: Session, *, now: datetime | None = None) -> dict[str, object]:
    reference = now or datetime.now(timezone.utc)
    expiring_limit = reference + timedelta(days=EXPIRING_SOON_DAYS)
    expiring = _count(
        session,
        Membership,
        Membership.status == "active",
        Membership.ends_at >= reference,
        Membership.ends_at < expiring_limit,
    )
    return {
        "members_by_status": _grouped_counts(session, Member.status),
        "memberships_by_status": _grouped_counts(session, Membership.status),
        "expiring": expiring,
    }


def _plan_totals(session: Session) -> list[PlanTotal]:
    rows = session.exec(
        select(
            Plan.id,
            Plan.name,
            Plan.price_cents,
            Plan.duration_days,
            func.count(Membership.id),
        )
        .join(Membership, Membership.plan_id == Plan.id)
        .where(Membership.status == "active")
        .group_by(Plan.id, Plan.name, Plan.price_cents, Plan.duration_days)
        .order_by(func.count(Membership.id).desc(), Plan.name)
    ).all()
    totals: list[PlanTotal] = []
    for plan_id, name, price_cents, duration_days, active_count in rows:
        interval = max(_int(duration_days), 1)
        recurring = interval >= MIN_RECURRING_PLAN_DAYS
        monthly = (
            round(_int(price_cents) * DAYS_PER_MONTH / interval) if recurring else 0
        )
        totals.append(
            PlanTotal(
                plan_id=plan_id,
                name=str(name),
                price_cents=_int(price_cents),
                duration_days=interval,
                active_count=_int(active_count),
                monthly_cents=monthly,
                recurring=recurring,
            )
        )
    return totals


def _mrr_expected_cents(plans: list[PlanTotal]) -> int:
    return sum(plan.monthly_cents * plan.active_count for plan in plans)


def _fleet_status(session: Session) -> list[CountRow]:
    return _grouped_counts(session, Equipment.status)


def _ticket_totals(session: Session) -> tuple[int, int]:
    open_tickets = _count(session, MaintenanceTicket, MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES))
    critical = _count(
        session,
        MaintenanceTicket,
        MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES),
        MaintenanceTicket.severity == "critical",
    )
    return open_tickets, critical


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


def overview(session: Session, period: ReportPeriod) -> OverviewReport:
    sales_count, pos_gross_cents, refunds_count, refunds_cents = _pos_totals(session, period)
    pos_cents = pos_gross_cents - refunds_cents
    payments_count, membership_cents = _payment_totals(session, period)
    maintenance_cost = _scalar(
        session,
        select(func.coalesce(func.sum(MaintenanceRecord.cost_cents), 0)).where(
            MaintenanceRecord.performed_at >= period.start_at,
            MaintenanceRecord.performed_at < period.end_at,
        ),
    )
    maintenance_records = _count(
        session,
        MaintenanceRecord,
        MaintenanceRecord.performed_at >= period.start_at,
        MaintenanceRecord.performed_at < period.end_at,
    )
    access_total, access_denied, access_manual = _access_totals(session, period)
    classes = _class_totals(session, period)
    workouts = _count(
        session,
        WorkoutLog,
        WorkoutLog.performed_at >= period.date_from,
        WorkoutLog.performed_at <= period.date_to,
    )
    measurements = _count(
        session,
        BodyMeasurement,
        BodyMeasurement.measured_at >= period.start_at,
        BodyMeasurement.measured_at < period.end_at,
    )
    state = _membership_state(session)
    plans = _plan_totals(session)
    fleet = _fleet_status(session)
    open_tickets, critical_tickets = _ticket_totals(session)
    return OverviewReport(
        period=period,
        pos_cents=pos_cents,
        pos_gross_cents=pos_gross_cents,
        refunds_cents=refunds_cents,
        refunds_count=refunds_count,
        membership_cents=membership_cents,
        sales_count=sales_count,
        average_ticket_cents=pos_gross_cents // sales_count if sales_count else 0,
        payments_count=payments_count,
        mrr_expected_cents=_mrr_expected_cents(plans),
        maintenance_cost_cents=maintenance_cost,
        maintenance_records=maintenance_records,
        access_total=access_total,
        access_denied=access_denied,
        access_manual=access_manual,
        class_sessions=classes["sessions"],
        class_capacity=classes["capacity"],
        class_attended=classes["attended"],
        class_no_show=classes["no_show"],
        class_occupancy_percent=classes["occupancy_percent"],
        workouts=workouts,
        measurements=measurements,
        members_by_status=state["members_by_status"],  # type: ignore[arg-type]
        memberships_by_status=state["memberships_by_status"],  # type: ignore[arg-type]
        new_members=_count(session, Member, Member.created_at >= period.start_at, Member.created_at < period.end_at),
        members_expiring=state["expiring"],  # type: ignore[arg-type]
        equipment_by_status=fleet,
        equipment_total=sum(row.count for row in fleet),
        tickets_open=open_tickets,
        tickets_critical=critical_tickets,
        revenue_by_day=_revenue_by_day(session, period),
        access_by_day=_access_by_day(session, period),
    )


def revenue(session: Session, period: ReportPeriod) -> RevenueReport:
    sales_count, pos_gross_cents, refunds_count, refunds_cents = _pos_totals(session, period)
    pos_cents = pos_gross_cents - refunds_cents
    payments_count, membership_cents = _payment_totals(session, period)

    method_totals = _pos_method_totals(session, period)
    refund_method_totals = _refund_method_totals(session, period)
    pos_by_method = [
        AmountRow(
            label=method,
            count=method_totals.get(method, (0, 0))[0],
            amount_cents=method_totals.get(method, (0, 0))[1]
            - refund_method_totals.get(method, 0),
        )
        for method in sorted(
            set(method_totals) | set(refund_method_totals),
            key=lambda method: method_totals.get(method, (0, 0))[1]
            - refund_method_totals.get(method, 0),
            reverse=True,
        )
    ]
    membership_by_method = [
        AmountRow(label=str(method), count=_int(count), amount_cents=_int(amount))
        for method, count, amount in session.exec(
            select(
                Payment.method,
                func.count(Payment.id),
                func.coalesce(func.sum(Payment.amount_cents), 0),
            )
            .where(Payment.paid_at >= period.start_at, Payment.paid_at < period.end_at)
            .group_by(Payment.method)
            .order_by(func.coalesce(func.sum(Payment.amount_cents), 0).desc())
        ).all()
    ]
    category_totals = _sold_category_totals(session, period)
    for category, (quantity, amount) in _returned_category_totals(session, period).items():
        bucket = category_totals.setdefault(category, [0, 0])
        bucket[0] -= quantity
        bucket[1] -= amount
    by_category = [
        AmountRow(label=category, count=quantity, amount_cents=amount)
        for category, (quantity, amount) in sorted(
            category_totals.items(), key=lambda item: item[1][1], reverse=True
        )
    ]
    top_products: list[ProductTotal] = []
    for product_id, data in sorted(
        _product_totals(session, period).items(),
        key=lambda item: item[1]["amount_cents"],
        reverse=True,
    ):
        if data["quantity"] == 0 and data["amount_cents"] == 0:
            continue
        top_products.append(
            ProductTotal(
                product_id=product_id,
                name=data["name"],
                sku=data["sku"],
                quantity=data["quantity"],
                amount_cents=data["amount_cents"],
            )
        )
        if len(top_products) >= TOP_PRODUCT_LIMIT:
            break
    opened = _count(
        session,
        CashSession,
        CashSession.opened_at >= period.start_at,
        CashSession.opened_at < period.end_at,
    )
    closed = _count(
        session,
        CashSession,
        CashSession.status == "closed",
        CashSession.closed_at >= period.start_at,
        CashSession.closed_at < period.end_at,
    )
    difference = _scalar(
        session,
        select(
            func.coalesce(
                func.sum(func.abs(func.coalesce(CashSession.difference_cents, 0))), 0
            )
        ).where(
            CashSession.status == "closed",
            CashSession.closed_at >= period.start_at,
            CashSession.closed_at < period.end_at,
        ),
    )
    return RevenueReport(
        period=period,
        pos_cents=pos_cents,
        pos_gross_cents=pos_gross_cents,
        refunds_cents=refunds_cents,
        refunds_count=refunds_count,
        membership_cents=membership_cents,
        sales_count=sales_count,
        average_ticket_cents=pos_gross_cents // sales_count if sales_count else 0,
        payments_count=payments_count,
        by_day=_revenue_by_day(session, period),
        pos_by_method=pos_by_method,
        membership_by_method=membership_by_method,
        by_category=by_category,
        top_products=top_products,
        cash_sessions_opened=opened,
        cash_sessions_closed=closed,
        cash_difference_cents=difference,
        ppd_receivables=list_ppd_receivables(session, page=1, page_size=1).summary,
    )


def memberships(session: Session, period: ReportPeriod) -> MembershipReport:
    plans = _plan_totals(session)
    state = _membership_state(session)
    payments_count, payments_cents = _payment_totals(session, period)
    events = _grouped_counts(
        session,
        MembershipEvent.event_type,
        MembershipEvent.occurred_at >= period.start_at,
        MembershipEvent.occurred_at < period.end_at,
    )
    event_day = _local_day_expression(session, MembershipEvent.occurred_at, period)
    event_buckets = session.exec(
        select(
            event_day,
            func.coalesce(
                func.sum(case((MembershipEvent.event_type.in_(ACTIVATION_EVENTS), 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((MembershipEvent.event_type.in_(TERMINATION_EVENTS), 1), else_=0)), 0
            ),
        )
        .where(
            MembershipEvent.occurred_at >= period.start_at,
            MembershipEvent.occurred_at < period.end_at,
        )
        .group_by(event_day)
    ).all()
    buckets = {
        _to_day(raw): (_int(activations), _int(terminations))
        for raw, activations, terminations in event_buckets
    }
    return MembershipReport(
        period=period,
        members_total=_count(session, Member),
        members_by_status=state["members_by_status"],  # type: ignore[arg-type]
        memberships_by_status=state["memberships_by_status"],  # type: ignore[arg-type]
        by_plan=plans,
        mrr_expected_cents=_mrr_expected_cents(plans),
        payments_cents=payments_cents,
        payments_count=payments_count,
        events=events,
        events_by_day=[
            EventDay(
                day=day,
                activations=buckets.get(day, (0, 0))[0],
                terminations=buckets.get(day, (0, 0))[1],
            )
            for day in _days(period)
        ],
        new_members=_count(
            session,
            Member,
            Member.created_at >= period.start_at,
            Member.created_at < period.end_at,
        ),
        members_expiring=state["expiring"],  # type: ignore[arg-type]
    )


def operations(session: Session, period: ReportPeriod) -> OperationsReport:
    access_total, access_denied, access_manual = _access_totals(session, period)
    access_hour = _local_hour_expression(session, AccessEvent.occurred_at, period)
    access_by_hour = [
        CountRow(label=f"{_int(hour):02d}", count=_int(count))
        for hour, count in session.exec(
            select(access_hour, func.count(AccessEvent.id))
            .where(
                AccessEvent.occurred_at >= period.start_at,
                AccessEvent.occurred_at < period.end_at,
            )
            .group_by(access_hour)
            .order_by(access_hour)
        ).all()
    ]
    classes = _class_totals(session, period)
    class_day = _local_day_expression(session, ClassSession.starts_at, period)
    class_day_rows = session.exec(
        select(
            class_day,
            func.count(ClassSession.id),
            func.coalesce(
                func.sum(
                    case(
                        (
                            ClassReservation.status == "attended",
                            case((ClassReservation.id.is_not(None), 1), else_=0),
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .outerjoin(ClassReservation, ClassReservation.session_id == ClassSession.id)
        .where(
            ClassSession.starts_at >= period.start_at,
            ClassSession.starts_at < period.end_at,
        )
        .group_by(class_day)
    ).all()
    class_buckets = {
        _to_day(raw): (_int(sessions), _int(attended))
        for raw, sessions, attended in class_day_rows
    }
    workout_days = _daily_counts(
        session, WorkoutLog.performed_at, period=period, date_column=True
    )
    return OperationsReport(
        period=period,
        access_total=access_total,
        access_authorized=access_total - access_denied,
        access_denied=access_denied,
        access_manual=access_manual,
        access_by_day=_access_by_day(session, period),
        access_by_hour=access_by_hour,
        class_sessions=classes["sessions"],
        class_capacity=classes["capacity"],
        class_reserved=classes["reserved"],
        class_attended=classes["attended"],
        class_no_show=classes["no_show"],
        class_waitlist=classes["waitlist"],
        class_cancelled=classes["cancelled"],
        class_occupancy_percent=classes["occupancy_percent"],
        classes_by_day=[
            ClassDay(
                day=day,
                sessions=class_buckets.get(day, (0, 0))[0],
                attended=class_buckets.get(day, (0, 0))[1],
            )
            for day in _days(period)
        ],
        workouts=_count(
            session,
            WorkoutLog,
            WorkoutLog.performed_at >= period.date_from,
            WorkoutLog.performed_at <= period.date_to,
        ),
        workout_minutes=_scalar(
            session,
            select(func.coalesce(func.sum(WorkoutLog.duration_minutes), 0)).where(
                WorkoutLog.performed_at >= period.date_from,
                WorkoutLog.performed_at <= period.date_to,
            ),
        ),
        measurements=_count(
            session,
            BodyMeasurement,
            BodyMeasurement.measured_at >= period.start_at,
            BodyMeasurement.measured_at < period.end_at,
        ),
        workouts_by_day=[
            CountRow(label=day.isoformat(), count=workout_days.get(day, 0))
            for day in _days(period)
        ],
    )


def maintenance(session: Session, period: ReportPeriod) -> MaintenanceReport:
    cost_cents = _scalar(
        session,
        select(func.coalesce(func.sum(MaintenanceRecord.cost_cents), 0)).where(
            MaintenanceRecord.performed_at >= period.start_at,
            MaintenanceRecord.performed_at < period.end_at,
        ),
    )
    records_count = _count(
        session,
        MaintenanceRecord,
        MaintenanceRecord.performed_at >= period.start_at,
        MaintenanceRecord.performed_at < period.end_at,
    )
    by_kind = [
        AmountRow(label=str(kind), count=_int(count), amount_cents=_int(amount))
        for kind, count, amount in session.exec(
            select(
                MaintenanceRecord.kind,
                func.count(MaintenanceRecord.id),
                func.coalesce(func.sum(MaintenanceRecord.cost_cents), 0),
            )
            .where(
                MaintenanceRecord.performed_at >= period.start_at,
                MaintenanceRecord.performed_at < period.end_at,
            )
            .group_by(MaintenanceRecord.kind)
            .order_by(func.coalesce(func.sum(MaintenanceRecord.cost_cents), 0).desc())
        ).all()
    ]
    open_counts = {
        equipment_id: _int(count)
        for equipment_id, count in session.exec(
            select(MaintenanceTicket.equipment_id, func.count(MaintenanceTicket.id))
            .where(MaintenanceTicket.status.in_(OPEN_TICKET_STATUSES))
            .group_by(MaintenanceTicket.equipment_id)
        ).all()
    }
    by_equipment = [
        EquipmentTotal(
            equipment_id=equipment_id,
            name=str(name),
            category=str(category),
            location=location,
            status=str(status),
            records_count=_int(records),
            cost_cents=_int(cost),
            open_tickets=open_counts.get(equipment_id, 0),
        )
        for equipment_id, name, category, location, status, records, cost in session.exec(
            select(
                Equipment.id,
                Equipment.name,
                Equipment.category,
                Equipment.location,
                Equipment.status,
                func.count(MaintenanceRecord.id),
                func.coalesce(func.sum(MaintenanceRecord.cost_cents), 0),
            )
            .join(MaintenanceRecord, MaintenanceRecord.equipment_id == Equipment.id)
            .where(
                MaintenanceRecord.performed_at >= period.start_at,
                MaintenanceRecord.performed_at < period.end_at,
            )
            .group_by(
                Equipment.id,
                Equipment.name,
                Equipment.category,
                Equipment.location,
                Equipment.status,
            )
            .order_by(func.coalesce(func.sum(MaintenanceRecord.cost_cents), 0).desc())
        ).all()
    ]
    return MaintenanceReport(
        period=period,
        cost_cents=cost_cents,
        records_count=records_count,
        by_kind=by_kind,
        by_equipment=by_equipment,
        tickets_created=_count(
            session,
            MaintenanceTicket,
            MaintenanceTicket.created_at >= period.start_at,
            MaintenanceTicket.created_at < period.end_at,
        ),
        tickets_by_status=_grouped_counts(
            session,
            MaintenanceTicket.status,
            MaintenanceTicket.created_at >= period.start_at,
            MaintenanceTicket.created_at < period.end_at,
        ),
        tickets_by_severity=_grouped_counts(
            session,
            MaintenanceTicket.severity,
            MaintenanceTicket.created_at >= period.start_at,
            MaintenanceTicket.created_at < period.end_at,
        ),
        equipment_by_status=_fleet_status(session),
        preventives_due=_count(
            session,
            Equipment,
            Equipment.status.in_(LIVE_EQUIPMENT_STATUSES),
            Equipment.next_preventive_due.is_not(None),
            Equipment.next_preventive_due < period.date_to,
        ),
    )


def inventory(session: Session, period: ReportPeriod) -> InventoryReport:
    """Valuation of the stock on hand plus the period's movements and purchases.

    The valuation is a **snapshot at the time of the query**, not a historical
    balance: the club stores the current quantity per product and location in
    ``inventory_stock``, not its day-by-day value. The period window therefore
    only bounds the movement ledger and the purchase orders, and the panel
    labels the valuation as a corte.
    """

    quantity_by_product = {
        product_id: _int(quantity)
        for product_id, quantity in session.exec(
            select(
                InventoryStock.product_id,
                func.coalesce(func.sum(InventoryStock.quantity), 0),
            ).group_by(InventoryStock.product_id)
        ).all()
    }

    products_total = 0
    products_active = 0
    products_inactive = 0
    stock_units = 0
    stock_value_cents = 0
    retail_value_cents = 0
    low_stock = 0
    out_of_stock = 0
    category_units: dict[str, int] = {}
    category_value_cents: dict[str, int] = {}
    by_product: list[InventoryProductTotal] = []

    for product_id, name, sku, category, price_cents, cost_cents, stock_min, is_active in session.exec(
        select(
            Product.id,
            Product.name,
            Product.sku,
            Product.category,
            Product.price_cents,
            Product.cost_cents,
            Product.stock_min,
            Product.is_active,
        ).order_by(Product.name)
    ).all():
        quantity = quantity_by_product.get(product_id, 0)
        cost_cents = _int(cost_cents)
        price_cents = _int(price_cents)
        stock_min = _int(stock_min)
        cost_value_cents = quantity * cost_cents
        retail = quantity * price_cents

        products_total += 1
        stock_units += quantity
        stock_value_cents += cost_value_cents
        retail_value_cents += retail
        category_units[category] = category_units.get(category, 0) + quantity
        category_value_cents[category] = (
            category_value_cents.get(category, 0) + cost_value_cents
        )
        if is_active:
            products_active += 1
            # Same rule as the point-of-sale summary: active products only, and a
            # product at or below its minimum but still above zero is "low", while
            # zero or less is "out".
            if quantity <= 0:
                out_of_stock += 1
            elif quantity <= stock_min:
                low_stock += 1
        else:
            products_inactive += 1

        by_product.append(
            InventoryProductTotal(
                product_id=product_id,
                name=name,
                sku=sku,
                category=category,
                quantity=quantity,
                cost_cents=cost_cents,
                price_cents=price_cents,
                cost_value_cents=cost_value_cents,
                retail_value_cents=retail,
            )
        )

    by_category = [
        AmountRow(
            label=label,
            count=category_units[label],
            amount_cents=category_value_cents[label],
        )
        for label in sorted(
            category_value_cents,
            key=lambda name: (-category_value_cents[name], name),
        )
    ]
    by_product.sort(key=lambda item: (-item.cost_value_cents, item.name))

    movement_conditions = (
        InventoryMovement.occurred_at >= period.start_at,
        InventoryMovement.occurred_at < period.end_at,
    )
    movements_by_type = [
        MovementTotal(label=str(movement_type), movements=_int(movements), units=_int(units))
        for movement_type, movements, units in session.exec(
            select(
                InventoryMovement.movement_type,
                func.count(InventoryMovement.id),
                func.coalesce(func.sum(InventoryMovement.quantity), 0),
            )
            .where(*movement_conditions)
            .group_by(InventoryMovement.movement_type)
            .order_by(func.count(InventoryMovement.id).desc())
        ).all()
    ]
    units_in = _scalar(
        session,
        select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
            *movement_conditions,
            InventoryMovement.quantity > 0,
        ),
    )
    units_out = abs(
        _scalar(
            session,
            select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
                *movement_conditions,
                InventoryMovement.quantity < 0,
            ),
        )
    )

    order_conditions = (
        PurchaseOrder.created_at >= period.start_at,
        PurchaseOrder.created_at < period.end_at,
    )
    orders_value_cents = _scalar(
        session,
        select(func.coalesce(func.sum(PurchaseOrder.total_cents), 0)).where(
            *order_conditions,
            PurchaseOrder.status != "cancelled",
        ),
    )
    orders_received_at = (
        PurchaseOrder.received_at.is_not(None),
        PurchaseOrder.received_at >= period.start_at,
        PurchaseOrder.received_at < period.end_at,
    )
    by_supplier = [
        AmountRow(label=str(name), count=_int(count), amount_cents=_int(amount))
        for name, count, amount in session.exec(
            select(
                Supplier.name,
                func.count(PurchaseOrder.id),
                func.coalesce(func.sum(PurchaseOrder.total_cents), 0),
            )
            .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .where(*order_conditions, PurchaseOrder.status != "cancelled")
            .group_by(Supplier.name)
            .order_by(func.coalesce(func.sum(PurchaseOrder.total_cents), 0).desc())
        ).all()
    ]

    open_orders_condition = PurchaseOrder.status.in_(OPEN_PURCHASE_ORDER_STATUSES)

    return InventoryReport(
        period=period,
        products_total=products_total,
        products_active=products_active,
        products_inactive=products_inactive,
        stock_units=stock_units,
        stock_value_cents=stock_value_cents,
        retail_value_cents=retail_value_cents,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        by_category=by_category,
        by_product=by_product,
        suppliers_total=_count(session, Supplier),
        suppliers_active=_count(session, Supplier, Supplier.is_active.is_(True)),
        open_orders=_count(session, PurchaseOrder, open_orders_condition),
        open_orders_value_cents=_scalar(
            session,
            select(func.coalesce(func.sum(PurchaseOrder.total_cents), 0)).where(
                open_orders_condition
            ),
        ),
        movements_count=_count(session, InventoryMovement, *movement_conditions),
        movements_by_type=movements_by_type,
        units_in=units_in,
        units_out=units_out,
        orders_created=_count(session, PurchaseOrder, *order_conditions),
        orders_by_status=_grouped_counts(session, PurchaseOrder.status, *order_conditions),
        orders_value_cents=orders_value_cents,
        orders_received=_count(session, PurchaseOrder, *orders_received_at),
        orders_received_value_cents=_scalar(
            session,
            select(func.coalesce(func.sum(PurchaseOrder.total_cents), 0)).where(
                *orders_received_at
            ),
        ),
        by_supplier=by_supplier,
    )


# --------------------------------------------------------------------------- #
# Dispatch and export
# --------------------------------------------------------------------------- #


def build_report(session: Session, report: str, period: ReportPeriod):
    if report == "overview":
        return overview(session, period)
    if report == "revenue":
        return revenue(session, period)
    if report == "memberships":
        return memberships(session, period)
    if report == "operations":
        return operations(session, period)
    if report == "maintenance":
        return maintenance(session, period)
    if report == "inventory":
        return inventory(session, period)
    raise UnknownReport(f"Reporte desconocido: {report}")


def _money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def build_export(payload, period: ReportPeriod) -> ExportTable:
    """Flattens the given report into the CSV table it exports.

    Each report exports its main table: the daily breakdown for the money and
    operation reports, the plan table for memberships, the equipment table for
    maintenance, the valued-stock table for inventory and the KPI list for the
    overview.
    """

    if isinstance(payload, OverviewReport):
        return ExportTable(
            title="Resumen",
            headers=["Indicador", "Valor"],
            rows=[
                ["Periodo", f"{period.date_from.isoformat()} a {period.date_to.isoformat()}"],
                ["Ingresos de mostrador (MXN)", _money(payload.pos_cents)],
                ["Ventas de mostrador (MXN)", _money(payload.pos_gross_cents)],
                ["Devoluciones de mostrador (MXN)", _money(payload.refunds_cents)],
                ["Cobros de membresía (MXN)", _money(payload.membership_cents)],
                ["Ventas", str(payload.sales_count)],
                ["Ticket promedio (MXN)", _money(payload.average_ticket_cents)],
                ["Cobros registrados", str(payload.payments_count)],
                ["Ingreso recurrente esperado (MXN)", _money(payload.mrr_expected_cents)],
                ["Costo de mantenimiento (MXN)", _money(payload.maintenance_cost_cents)],
                ["Accesos", str(payload.access_total)],
                ["Accesos denegados", str(payload.access_denied)],
                ["Clases programadas", str(payload.class_sessions)],
                ["Ocupación de clases (%)", str(payload.class_occupancy_percent)],
                ["Entrenamientos", str(payload.workouts)],
                ["Equipos fuera de servicio", str(_label_count(payload.equipment_by_status, "out_of_service"))],
                ["Tickets abiertos", str(payload.tickets_open)],
            ],
        )
    if isinstance(payload, RevenueReport):
        return ExportTable(
            title="Ingresos por día",
            headers=["Fecha", "Ventas", "Mostrador (MXN)", "Devoluciones (MXN)", "Membresías (MXN)", "Total (MXN)"],
            rows=[
                [
                    day.day.isoformat(),
                    str(day.sales_count),
                    _money(day.pos_cents),
                    _money(day.refunds_cents),
                    _money(day.membership_cents),
                    _money(day.total_cents),
                ]
                for day in payload.by_day
            ],
        )
    if isinstance(payload, MembershipReport):
        return ExportTable(
            title="Membresías por plan",
            headers=["Plan", "Duración (días)", "Precio (MXN)", "Activas", "Mensual equivalente (MXN)"],
            rows=[
                [
                    plan.name,
                    str(plan.duration_days),
                    _money(plan.price_cents),
                    str(plan.active_count),
                    _money(plan.monthly_cents) if plan.recurring else "no recurrente",
                ]
                for plan in payload.by_plan
            ],
        )
    if isinstance(payload, OperationsReport):
        rows: list[list[str]] = []
        access = {day.day: day for day in payload.access_by_day}
        classes = {day.day: day for day in payload.classes_by_day}
        workouts = {row.label: row.count for row in payload.workouts_by_day}
        for day in _days(period):
            rows.append(
                [
                    day.isoformat(),
                    str(access[day].total),
                    str(access[day].denied),
                    str(classes[day].sessions),
                    str(classes[day].attended),
                    str(workouts.get(day.isoformat(), 0)),
                ]
            )
        return ExportTable(
            title="Operación por día",
            headers=["Fecha", "Accesos", "Denegados", "Clases", "Asistencias", "Entrenamientos"],
            rows=rows,
        )
    if isinstance(payload, MaintenanceReport):
        return ExportTable(
            title="Mantenimiento por equipo",
            headers=["Equipo", "Categoría", "Ubicación", "Estado", "Servicios", "Costo (MXN)", "Tickets abiertos"],
            rows=[
                [
                    item.name,
                    item.category,
                    item.location or "—",
                    item.status,
                    str(item.records_count),
                    _money(item.cost_cents),
                    str(item.open_tickets),
                ]
                for item in payload.by_equipment
            ],
        )
    if isinstance(payload, InventoryReport):
        return ExportTable(
            title="Inventario valorizado",
            headers=[
                "Producto",
                "SKU",
                "Categoría",
                "Existencia",
                "Costo unitario (MXN)",
                "Precio (MXN)",
                "Valor al costo (MXN)",
                "Valor a venta (MXN)",
            ],
            rows=[
                [
                    item.name,
                    item.sku,
                    item.category,
                    str(item.quantity),
                    _money(item.cost_cents),
                    _money(item.price_cents),
                    _money(item.cost_value_cents),
                    _money(item.retail_value_cents),
                ]
                for item in payload.by_product
            ],
        )
    raise UnknownReport("Reporte desconocido")


def _label_count(rows: list[CountRow], label: str) -> int:
    for row in rows:
        if row.label == label:
            return row.count
    return 0
