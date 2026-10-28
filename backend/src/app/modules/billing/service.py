"""Business rules for CFDI invoicing.

The service turns a confirmed sale or membership payment into a *requested*
invoice, stamps it through the PAC (simulated in preview) and records every
state change in an append-only trail. It never deletes a comprobante: a wrong
one is cancelled and kept, and the origin is only freed for a replacement when
the previous invoice is cancelled.

Money rule: the club quotes prices with VAT included. ``total_cents`` is the
amount the member paid; the service derives the taxable base and the transferred
VAT from it (``split_tax_inclusive``), so the CFDI total always matches the
receipt and every concept adds up to that total.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import os
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.mailer import (
    EmailAttachment,
    MailDeliveryFailed,
    MailNotConfigured,
    send_email,
)
from app.modules.billing import cfdi, documents
from app.modules.billing.errors import (
    BillingMemberNotFound,
    CreditNoteBalanceExceeded,
    CreditNoteNotAllowed,
    FiscalDataInvalid,
    GlobalInvoiceNoEligibleSales,
    GlobalInvoicePeriodConflict,
    GlobalInvoicePeriodInvalid,
    GlobalInvoicePeriodOpen,
    InvoiceDeliveryFailed,
    InvoiceEmailNotConfigured,
    InvoiceIdempotencyConflict,
    InvoiceNotDeliverable,
    InvoiceNotFound,
    InvoiceNumberingError,
    InvoiceRecipientMissing,
    InvoiceStateError,
    OriginAlreadyInvoiced,
    OriginNotFound,
    OriginNotInvoiceable,
    PacRejected,
    PaymentComplementBalanceExceeded,
    PaymentComplementNotAllowed,
    PaymentComplementNotFound,
)
from app.modules.billing.models import (
    INVOICE_ORIGIN_TYPES,
    PAYMENT_COMPLEMENT_SOURCE_TYPES,
    GlobalInvoiceSale,
    Invoice,
    InvoiceEvent,
    InvoiceItem,
    InvoicePayment,
    InvoicePaymentEvent,
    MemberFiscalProfile,
    utc_now,
)
from app.modules.billing.pac import pac_gateway
from app.modules.inventory.models import Sale, SaleItem, SaleReturn
from app.modules.memberships.models import Member, Membership, Payment, Plan
from app.timezone import club_date, club_timezone, local_midnight

CANCELLATION_REASONS = frozenset({"01", "02", "03", "04"})
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
DEFAULT_SERIES = "A"
DEFAULT_PAYMENT_SERIES = "P"
PAYMENT_METHODS = frozenset({"PUE", "PPD"})
# The invoice that will be paid as PPD uses FormaPago 99, but each complement
# must state how the money actually arrived; "por definir" is not a payment.
PAYMENT_COMPLEMENT_FORMS = cfdi.PAYMENT_FORMS - {"99"}
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
GLOBAL_MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
GLOBAL_EXCLUSION_KEYS = (
    "returned",
    "zero_total",
    "account",
    "member",
    "individual_invoice",
    "global_invoice",
)
# A credit note only adjusts an income invoice with a known receptor. The
# public-general global invoice and another credit note cannot be credited.
CREDIT_NOTE_SOURCE_TYPES = frozenset({"sale", "membership_payment"})
CREDIT_NOTE_REASONS = {
    "return": "Devolución",
    "discount": "Descuento",
    "correction": "Corrección de importe",
    "other": "Otro motivo",
}
# PPD receivables are aged from the stamp date: that is when the invoice becomes
# collectible. The outstanding balance lands in exactly one bucket, so the four
# amounts always add up to the cartera total.
PPD_AGING_BUCKETS = ("current", "days_31_60", "days_61_90", "over_90")


@dataclass(frozen=True)
class InvoiceItemView:
    position: int
    description: str
    sat_product_code: str
    sat_unit_code: str
    unit_name: str
    quantity: int
    unit_price_cents: int
    subtotal_cents: int
    tax_cents: int
    total_cents: int


@dataclass(frozen=True)
class InvoiceEventView:
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_id: UUID | None
    detail: dict[str, object]
    occurred_at: datetime


@dataclass(frozen=True)
class CreditNoteRef:
    invoice_id: UUID
    folio_label: str
    status: str
    total_cents: int
    reason: str
    note: str | None
    created_at: datetime


@dataclass(frozen=True)
class PaymentComplementRef:
    payment_id: UUID
    folio_label: str
    status: str
    partiality_number: int
    amount_cents: int
    payment_form: str
    paid_on: date
    prior_balance_cents: int
    outstanding_balance_cents: int
    uuid: str | None
    is_simulated: bool
    created_at: datetime


@dataclass(frozen=True)
class PaymentComplementView:
    id: UUID
    invoice_id: UUID
    invoice_folio_label: str
    series: str
    folio: int
    folio_label: str
    status: str
    partiality_number: int
    amount_cents: int
    currency: str
    payment_form: str
    paid_on: date
    prior_balance_cents: int
    outstanding_balance_cents: int
    tax_rate_percent: int
    uuid: str | None
    is_simulated: bool
    provider: str | None
    provider_reference: str | None
    xml_available: bool
    issued_at: datetime | None
    stamped_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason_code: str | None
    cancellation_note: str | None
    created_at: datetime
    created_by: UUID | None
    events: tuple[InvoiceEventView, ...] = field(default=())


@dataclass(frozen=True)
class InvoiceView:
    id: UUID
    series: str
    folio: int
    folio_label: str
    status: str
    origin_type: str
    origin_id: UUID
    origin_reference: str
    global_year: int | None
    global_month: int | None
    member_id: UUID | None
    member_name: str | None
    receptor_rfc: str
    receptor_name: str
    receptor_tax_regime: str
    receptor_postal_code: str
    receptor_cfdi_use: str
    receptor_email: str | None
    currency: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    tax_rate_percent: int
    payment_form: str
    payment_method: str
    uuid: str | None
    is_simulated: bool
    provider: str | None
    provider_reference: str | None
    xml_available: bool
    issued_at: datetime | None
    stamped_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason_code: str | None
    cancellation_replacement_uuid: str | None
    cancellation_note: str | None
    created_at: datetime
    created_by: UUID | None
    related_invoice_id: UUID | None = None
    related_invoice_folio_label: str | None = None
    related_invoice_status: str | None = None
    credit_note_reason: str | None = None
    credit_note_note: str | None = None
    credited_cents: int = 0
    credit_balance_cents: int = 0
    credit_notes: tuple[CreditNoteRef, ...] = field(default=())
    paid_cents: int = 0
    payment_balance_cents: int = 0
    payment_status: str = "not_applicable"
    payment_complements: tuple[PaymentComplementRef, ...] = field(default=())
    items: tuple[InvoiceItemView, ...] = field(default=())
    events: tuple[InvoiceEventView, ...] = field(default=())
    global_sales: tuple["GlobalInvoiceSaleView", ...] = field(default=())


@dataclass(frozen=True)
class InvoicePage:
    items: tuple[InvoiceView, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class InvoiceSummary:
    total: int
    requested: int
    failed: int
    stamped: int
    cancelled: int
    simulated: int
    stamped_cents: int
    cancelled_cents: int
    credit_notes: int
    credit_note_cents: int
    net_stamped_cents: int


@dataclass(frozen=True)
class PpdAging:
    current_cents: int = 0
    days_31_60_cents: int = 0
    days_61_90_cents: int = 0
    over_90_cents: int = 0


@dataclass(frozen=True)
class PpdReceivableRow:
    invoice_id: UUID
    folio_label: str
    receptor_name: str
    receptor_rfc: str
    origin_type: str
    origin_reference: str
    member_id: UUID | None
    member_name: str | None
    currency: str
    total_cents: int
    paid_cents: int
    balance_cents: int
    stamped_at: datetime | None
    age_days: int
    aging_bucket: str
    uuid: str | None
    is_simulated: bool
    stamped_complements: int
    requested_complements: int
    failed_complements: int
    last_payment_on: date | None


@dataclass(frozen=True)
class PpdReceivableSummary:
    as_of: date
    invoices: int
    total_cents: int
    paid_cents: int
    outstanding_cents: int
    aging: PpdAging
    oldest_stamped_at: datetime | None
    stamped_complements: int
    stamped_complement_cents: int
    requested_complements: int
    requested_complement_cents: int
    failed_complements: int
    failed_complement_cents: int


@dataclass(frozen=True)
class PpdReceivablePage:
    items: tuple[PpdReceivableRow, ...]
    total: int
    page: int
    page_size: int
    summary: PpdReceivableSummary


@dataclass(frozen=True)
class OriginOption:
    origin_type: str
    origin_id: UUID
    reference: str
    member_id: UUID | None
    member_name: str | None
    occurred_at: datetime
    total_cents: int
    description: str
    payment_method: str


@dataclass(frozen=True)
class OriginPage:
    items: tuple[OriginOption, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class FiscalProfileView:
    member_id: UUID
    rfc: str
    legal_name: str
    tax_regime: str
    postal_code: str
    cfdi_use: str
    email: str | None
    updated_at: datetime


@dataclass(frozen=True)
class InvoiceDeliveryView:
    invoice_id: UUID
    recipient: str
    status: str
    attachments: tuple[str, ...]
    sent_at: datetime


@dataclass(frozen=True)
class GlobalInvoiceSaleView:
    sale_id: UUID
    sale_folio: str
    sold_at: datetime
    total_cents: int


@dataclass(frozen=True)
class GlobalInvoiceRef:
    invoice_id: UUID
    folio_label: str
    status: str


@dataclass(frozen=True)
class GlobalEligibleSaleView:
    sale_id: UUID
    folio: str
    sold_at: datetime
    total_cents: int
    payment_method: str
    description: str


@dataclass(frozen=True)
class GlobalInvoiceEligibilityView:
    year: int
    month: int
    period_start: datetime
    period_end: datetime
    period_closed: bool
    total_candidates: int
    eligible_count: int
    eligible_total_cents: int
    subtotal_cents: int
    tax_cents: int
    excluded_counts: dict[str, int]
    items: tuple[GlobalEligibleSaleView, ...]
    page: int
    page_size: int
    existing_invoice: GlobalInvoiceRef | None


@dataclass(frozen=True)
class _GlobalCandidates:
    sales: tuple[Sale, ...]
    eligible: tuple[Sale, ...]
    excluded_counts: dict[str, int]
    subtotal_cents: int
    tax_cents: int
    total_cents: int


@dataclass(frozen=True)
class _OriginLine:
    description: str
    quantity: int
    total_cents: int
    product_id: UUID | None = None
    sale_item_id: UUID | None = None


@dataclass(frozen=True)
class _ResolvedOrigin:
    origin_type: str
    origin_id: UUID
    reference: str
    member_id: UUID | None
    method: str
    total_cents: int
    lines: tuple[_OriginLine, ...]


def invoice_series() -> str:
    raw = (os.getenv("CFDI_SERIES", DEFAULT_SERIES) or DEFAULT_SERIES).strip().upper()
    if not raw or len(raw) > 10:
        return DEFAULT_SERIES
    return raw


def tax_rate_percent() -> int:
    raw = (os.getenv("CFDI_TAX_RATE_PERCENT", "16") or "16").strip()
    try:
        value = int(raw)
    except ValueError:
        return cfdi.DEFAULT_TAX_RATE_PERCENT
    if value < 0 or value > 100:
        return cfdi.DEFAULT_TAX_RATE_PERCENT
    return value


def issuer_config() -> cfdi.IssuerConfig:
    return cfdi.IssuerConfig(
        rfc=(os.getenv("GYM_RFC", cfdi.DEFAULT_ISSUER_RFC) or "").strip().upper()
        or cfdi.DEFAULT_ISSUER_RFC,
        legal_name=(
            os.getenv("GYM_LEGAL_NAME")
            or os.getenv("GYM_NAME")
            or cfdi.DEFAULT_ISSUER_NAME
        )
        .strip()
        or cfdi.DEFAULT_ISSUER_NAME,
        tax_regime=(os.getenv("GYM_TAX_REGIME", cfdi.DEFAULT_ISSUER_TAX_REGIME) or "").strip()
        or cfdi.DEFAULT_ISSUER_TAX_REGIME,
        postal_code=(os.getenv("GYM_POSTAL_CODE", cfdi.DEFAULT_ISSUER_POSTAL_CODE) or "").strip()
        or cfdi.DEFAULT_ISSUER_POSTAL_CODE,
        certificate_number=(
            os.getenv("CFDI_CERTIFICATE_NUMBER", cfdi.DEFAULT_CERTIFICATE_NUMBER) or ""
        ).strip()
        or cfdi.DEFAULT_CERTIFICATE_NUMBER,
        product_code=(os.getenv("CFDI_PRODUCT_CODE", cfdi.DEFAULT_PRODUCT_CODE) or "").strip()
        or cfdi.DEFAULT_PRODUCT_CODE,
        service_code=(os.getenv("CFDI_SERVICE_CODE", cfdi.DEFAULT_SERVICE_CODE) or "").strip()
        or cfdi.DEFAULT_SERVICE_CODE,
    )


def _fingerprint(values: dict[str, str | None]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _member_name(member: Member | None) -> str | None:
    if member is None:
        return None
    return f"{member.first_name} {member.last_name}".strip()


def _money_label(cents: int) -> str:
    value = (Decimal(cents) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"${value:,.2f}"


def _get_invoice(session: Session, invoice_id: UUID) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceNotFound("La factura no existe.")
    return invoice


def _invoice_items(session: Session, invoice_id: UUID) -> tuple[InvoiceItem, ...]:
    return tuple(
        session.exec(
            select(InvoiceItem)
            .where(InvoiceItem.invoice_id == invoice_id)
            .order_by(InvoiceItem.position)
        ).all()
    )


def _invoice_view(
    session: Session,
    invoice: Invoice,
    *,
    full: bool = False,
    member_name: str | None = None,
) -> InvoiceView:
    items: tuple[InvoiceItemView, ...] = ()
    events: tuple[InvoiceEventView, ...] = ()
    global_sales: tuple[GlobalInvoiceSaleView, ...] = ()
    related_invoice_folio_label: str | None = None
    related_invoice_status: str | None = None
    credit_notes: tuple[CreditNoteRef, ...] = ()
    credited_cents = 0
    credit_balance_cents = 0
    payment_complements: tuple[PaymentComplementRef, ...] = ()
    paid_cents = 0
    payment_balance_cents = 0
    payment_status = "not_applicable"
    if full:
        items = tuple(
            InvoiceItemView(
                position=item.position,
                description=item.description,
                sat_product_code=item.sat_product_code,
                sat_unit_code=item.sat_unit_code,
                unit_name=item.unit_name,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                subtotal_cents=item.subtotal_cents,
                tax_cents=item.tax_cents,
                total_cents=item.total_cents,
            )
            for item in _invoice_items(session, invoice.id)
        )
        events = tuple(
            InvoiceEventView(
                event_type=event.event_type,
                from_status=event.from_status,
                to_status=event.to_status,
                actor_id=event.actor_id,
                detail=event.detail,
                occurred_at=event.occurred_at,
            )
            for event in session.exec(
                select(InvoiceEvent)
                .where(InvoiceEvent.invoice_id == invoice.id)
                .order_by(InvoiceEvent.occurred_at)
            ).all()
        )
        if member_name is None and invoice.member_id is not None:
            member_name = _member_name(session.get(Member, invoice.member_id))
        if invoice.origin_type == "global":
            global_sales = tuple(
                GlobalInvoiceSaleView(
                    sale_id=entry.sale_id,
                    sale_folio=entry.sale_folio,
                    sold_at=entry.sold_at,
                    total_cents=entry.total_cents,
                )
                for entry in session.exec(
                    select(GlobalInvoiceSale)
                    .where(GlobalInvoiceSale.invoice_id == invoice.id)
                    .order_by(GlobalInvoiceSale.sold_at, GlobalInvoiceSale.sale_folio)
                ).all()
            )
        if invoice.origin_type == "credit_note" and invoice.related_invoice_id is not None:
            related = session.get(Invoice, invoice.related_invoice_id)
            if related is not None:
                related_invoice_folio_label = f"{related.series}-{related.folio:06d}"
                related_invoice_status = related.status
        if (
            invoice.origin_type in CREDIT_NOTE_SOURCE_TYPES
            and invoice.status == "stamped"
        ):
            note_rows = tuple(
                session.exec(
                    select(Invoice)
                    .where(
                        Invoice.origin_type == "credit_note",
                        Invoice.related_invoice_id == invoice.id,
                    )
                    .order_by(Invoice.created_at, Invoice.folio)
                ).all()
            )
            credit_notes = tuple(
                CreditNoteRef(
                    invoice_id=note.id,
                    folio_label=f"{note.series}-{note.folio:06d}",
                    status=note.status,
                    total_cents=note.total_cents,
                    reason=note.credit_note_reason or "other",
                    note=note.credit_note_note,
                    created_at=note.created_at,
                )
                for note in note_rows
            )
            credited_cents = sum(
                note.total_cents for note in note_rows if note.status == "stamped"
            )
            credit_balance_cents = max(0, invoice.total_cents - credited_cents)
        if invoice.payment_method == "PPD":
            payment_rows = tuple(
                session.exec(
                    select(InvoicePayment)
                    .where(InvoicePayment.invoice_id == invoice.id)
                    .order_by(InvoicePayment.created_at, InvoicePayment.folio)
                ).all()
            )
            payment_complements = tuple(
                PaymentComplementRef(
                    payment_id=payment.id,
                    folio_label=f"{payment.series}-{payment.folio:06d}",
                    status=payment.status,
                    partiality_number=payment.partiality_number,
                    amount_cents=payment.amount_cents,
                    payment_form=payment.payment_form,
                    paid_on=payment.paid_on,
                    prior_balance_cents=payment.prior_balance_cents,
                    outstanding_balance_cents=payment.outstanding_balance_cents,
                    uuid=payment.uuid,
                    is_simulated=payment.is_simulated,
                    created_at=payment.created_at,
                )
                for payment in payment_rows
            )
            paid_cents = sum(
                payment.amount_cents
                for payment in payment_rows
                if payment.status == "stamped"
            )
            payment_balance_cents = max(0, invoice.total_cents - paid_cents)
            payment_status = (
                "paid"
                if payment_balance_cents == 0
                else "partial"
                if paid_cents > 0
                else "unpaid"
            )

    return InvoiceView(
        id=invoice.id,
        series=invoice.series,
        folio=invoice.folio,
        folio_label=f"{invoice.series}-{invoice.folio:06d}",
        status=invoice.status,
        origin_type=invoice.origin_type,
        origin_id=invoice.origin_id,
        origin_reference=invoice.origin_reference,
        global_year=invoice.global_year,
        global_month=invoice.global_month,
        member_id=invoice.member_id,
        member_name=member_name,
        receptor_rfc=invoice.receptor_rfc,
        receptor_name=invoice.receptor_name,
        receptor_tax_regime=invoice.receptor_tax_regime,
        receptor_postal_code=invoice.receptor_postal_code,
        receptor_cfdi_use=invoice.receptor_cfdi_use,
        receptor_email=invoice.receptor_email,
        currency=invoice.currency,
        subtotal_cents=invoice.subtotal_cents,
        tax_cents=invoice.tax_cents,
        total_cents=invoice.total_cents,
        tax_rate_percent=invoice.tax_rate_percent,
        payment_form=invoice.payment_form,
        payment_method=invoice.payment_method,
        uuid=invoice.uuid,
        is_simulated=invoice.is_simulated,
        provider=invoice.provider,
        provider_reference=invoice.provider_reference,
        xml_available=bool(invoice.xml_content),
        issued_at=invoice.issued_at,
        stamped_at=invoice.stamped_at,
        cancelled_at=invoice.cancelled_at,
        cancellation_reason_code=invoice.cancellation_reason_code,
        cancellation_replacement_uuid=invoice.cancellation_replacement_uuid,
        cancellation_note=invoice.cancellation_note,
        created_at=invoice.created_at,
        created_by=invoice.created_by,
        related_invoice_id=invoice.related_invoice_id,
        related_invoice_folio_label=related_invoice_folio_label,
        related_invoice_status=related_invoice_status,
        credit_note_reason=invoice.credit_note_reason,
        credit_note_note=invoice.credit_note_note,
        credited_cents=credited_cents,
        credit_balance_cents=credit_balance_cents,
        credit_notes=credit_notes,
        paid_cents=paid_cents,
        payment_balance_cents=payment_balance_cents,
        payment_status=payment_status,
        payment_complements=payment_complements,
        items=items,
        events=events,
        global_sales=global_sales,
    )


def _record_event(
    session: Session,
    invoice: Invoice,
    event_type: str,
    *,
    from_status: str | None,
    to_status: str | None,
    actor_id: UUID | None,
    detail: dict[str, object],
) -> None:
    session.add(
        InvoiceEvent(
            invoice_id=invoice.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            detail=detail,
        )
    )


def _active_global_invoice_for_sale(session: Session, sale_id: UUID) -> Invoice | None:
    """The live global invoice that already covers ``sale_id``, if any."""

    invoice_id = session.exec(
        select(GlobalInvoiceSale.invoice_id)
        .join(Invoice, GlobalInvoiceSale.invoice_id == Invoice.id)
        .where(
            GlobalInvoiceSale.sale_id == sale_id,
            Invoice.status != "cancelled",
        )
    ).first()
    return session.get(Invoice, invoice_id) if invoice_id is not None else None


def _resolve_sale(session: Session, origin_id: UUID) -> _ResolvedOrigin:
    sale = session.get(Sale, origin_id)
    if sale is None:
        raise OriginNotFound("La venta no existe.")
    if sale.status != "completed":
        raise OriginNotInvoiceable(
            "La venta está totalmente devuelta; no se puede facturar.",
            origin_type="sale",
            origin_id=str(sale.id),
        )
    if sale.payment_method == "account":
        raise OriginNotInvoiceable(
            "Una venta cargada a la cuenta del socio requiere CFDI PPD con "
            "complemento de pago; ese flujo todavía no está disponible.",
            origin_type="sale",
            origin_id=str(sale.id),
        )
    if sale.total_cents <= 0:
        raise OriginNotInvoiceable(
            "La venta no tiene importe facturable.",
            origin_type="sale",
            origin_id=str(sale.id),
        )
    if session.exec(select(SaleReturn.id).where(SaleReturn.sale_id == sale.id)).first():
        raise OriginNotInvoiceable(
            "La venta tiene devoluciones; cancela o ajusta la operación antes de facturarla.",
            origin_type="sale",
            origin_id=str(sale.id),
        )
    global_invoice = _active_global_invoice_for_sale(session, sale.id)
    if global_invoice is not None:
        raise OriginNotInvoiceable(
            "La venta ya está incluida en la factura global "
            f"{global_invoice.series}-{global_invoice.folio:06d}; requiere el "
            "procedimiento fiscal de sustitución o ajuste.",
            origin_type="sale",
            origin_id=str(sale.id),
        )
    items = tuple(
        session.exec(select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.id)).all()
    )
    if not items:
        raise OriginNotInvoiceable(
            "La venta no tiene conceptos.",
            origin_type="sale",
            origin_id=str(sale.id),
        )
    if sum(item.line_total_cents for item in items) != sale.total_cents:
        raise OriginNotInvoiceable(
            "La venta no cuadra con sus conceptos y no se puede desglosar para el CFDI.",
            origin_type="sale",
            origin_id=str(sale.id),
        )
    return _ResolvedOrigin(
        origin_type="sale",
        origin_id=sale.id,
        reference=sale.folio,
        member_id=sale.member_id,
        method=sale.payment_method,
        total_cents=sale.total_cents,
        lines=tuple(
            _OriginLine(
                description=item.product_name[:300],
                quantity=item.quantity,
                total_cents=item.line_total_cents,
                product_id=item.product_id,
                sale_item_id=item.id,
            )
            for item in items
        ),
    )


def _resolve_payment(session: Session, origin_id: UUID) -> _ResolvedOrigin:
    payment = session.get(Payment, origin_id)
    if payment is None:
        raise OriginNotFound("El pago no existe.")
    if payment.amount_cents <= 0:
        raise OriginNotInvoiceable(
            "El pago no tiene importe facturable.",
            origin_type="membership_payment",
            origin_id=str(payment.id),
        )
    membership = session.get(Membership, payment.membership_id)
    plan = session.get(Plan, membership.plan_id) if membership is not None else None
    description = f"Membresía {plan.name}" if plan is not None else "Membresía"
    if payment.period_starts_at is not None and payment.period_ends_at is not None:
        starts = club_date(payment.period_starts_at)
        ends = club_date(payment.period_ends_at)
        description = f"{description} ({starts:%d/%m/%Y} al {ends:%d/%m/%Y})"
    return _ResolvedOrigin(
        origin_type="membership_payment",
        origin_id=payment.id,
        reference=f"PAGO-{str(payment.id)[:8].upper()}",
        member_id=payment.member_id,
        method=payment.method,
        total_cents=payment.amount_cents,
        lines=(
            _OriginLine(
                description=description[:300],
                quantity=1,
                total_cents=payment.amount_cents,
            ),
        ),
    )


def _resolve_origin(session: Session, origin_type: str, origin_id: UUID) -> _ResolvedOrigin:
    if origin_type == "sale":
        return _resolve_sale(session, origin_id)
    if origin_type == "membership_payment":
        return _resolve_payment(session, origin_id)
    raise OriginNotFound("El tipo de operación no es facturable.")


def _next_folio(session: Session, series: str) -> int:
    highest = session.exec(
        select(func.max(Invoice.folio)).where(Invoice.series == series)
    ).first()
    return int(highest or 0) + 1


def _global_period(year: int, month: int) -> tuple[datetime, datetime]:
    """UTC bounds of a club-local calendar month (start inclusive, end exclusive)."""

    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise GlobalInvoicePeriodInvalid(
            "El periodo de la factura global no es válido.", field="period"
        )
    tz = club_timezone()
    start = local_midnight(date(year, month, 1), tz)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    end = local_midnight(next_month, tz)
    return start, end


def _global_period_label(year: int, month: int) -> str:
    return f"{GLOBAL_MONTH_NAMES[month - 1]} de {year}"


def _active_global_invoice_for_period(
    session: Session, year: int, month: int
) -> Invoice | None:
    return session.exec(
        select(Invoice).where(
            Invoice.origin_type == "global",
            Invoice.global_year == year,
            Invoice.global_month == month,
            Invoice.status != "cancelled",
        )
    ).first()


def _global_candidates(
    session: Session,
    *,
    start: datetime,
    end: datetime,
    rate: int,
) -> _GlobalCandidates:
    """Classify the month's sales into eligible and excluded public-general batches."""

    sales = tuple(
        session.exec(
            select(Sale)
            .where(Sale.sold_at >= start, Sale.sold_at < end)
            .order_by(Sale.sold_at, Sale.folio)
        ).all()
    )
    excluded_counts = {key: 0 for key in GLOBAL_EXCLUSION_KEYS}
    if not sales:
        return _GlobalCandidates(
            sales=(),
            eligible=(),
            excluded_counts=excluded_counts,
            subtotal_cents=0,
            tax_cents=0,
            total_cents=0,
        )

    sale_ids = [sale.id for sale in sales]
    returned_ids = set(
        session.exec(
            select(SaleReturn.sale_id).where(SaleReturn.sale_id.in_(sale_ids))
        ).all()
    )
    individually_invoiced_ids = set(
        session.exec(
            select(Invoice.origin_id).where(
                Invoice.origin_type == "sale",
                Invoice.origin_id.in_(sale_ids),
                Invoice.status != "cancelled",
            )
        ).all()
    )
    globally_invoiced_ids = set(
        session.exec(
            select(GlobalInvoiceSale.sale_id)
            .join(Invoice, GlobalInvoiceSale.invoice_id == Invoice.id)
            .where(
                GlobalInvoiceSale.sale_id.in_(sale_ids),
                Invoice.status != "cancelled",
            )
        ).all()
    )

    eligible: list[Sale] = []
    for sale in sales:
        if sale.status != "completed" or sale.id in returned_ids:
            excluded_counts["returned"] += 1
        elif sale.total_cents <= 0:
            excluded_counts["zero_total"] += 1
        elif sale.payment_method == "account":
            excluded_counts["account"] += 1
        elif sale.member_id is not None:
            excluded_counts["member"] += 1
        elif sale.id in individually_invoiced_ids:
            excluded_counts["individual_invoice"] += 1
        elif sale.id in globally_invoiced_ids:
            excluded_counts["global_invoice"] += 1
        else:
            eligible.append(sale)

    total_cents = sum(sale.total_cents for sale in eligible)
    subtotal_cents, tax_cents = cfdi.split_tax_inclusive(total_cents, rate)
    return _GlobalCandidates(
        sales=sales,
        eligible=tuple(eligible),
        excluded_counts=excluded_counts,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=total_cents,
    )


def list_global_invoice_eligibility(
    session: Session,
    *,
    year: int,
    month: int,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> GlobalInvoiceEligibilityView:
    """Review the walk-in sales that a monthly global invoice would include."""

    start, end = _global_period(year, month)
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    candidates = _global_candidates(
        session, start=start, end=end, rate=tax_rate_percent()
    )
    active = _active_global_invoice_for_period(session, year, month)
    offset = (page - 1) * page_size
    items = tuple(
        GlobalEligibleSaleView(
            sale_id=sale.id,
            folio=sale.folio,
            sold_at=sale.sold_at,
            total_cents=sale.total_cents,
            payment_method=sale.payment_method,
            description=(sale.note or "Venta en mostrador")[:200],
        )
        for sale in candidates.eligible[offset : offset + page_size]
    )
    return GlobalInvoiceEligibilityView(
        year=year,
        month=month,
        period_start=start,
        period_end=end,
        period_closed=utc_now() >= end,
        total_candidates=len(candidates.sales),
        eligible_count=len(candidates.eligible),
        eligible_total_cents=candidates.total_cents,
        subtotal_cents=candidates.subtotal_cents,
        tax_cents=candidates.tax_cents,
        excluded_counts=candidates.excluded_counts,
        items=items,
        page=page,
        page_size=page_size,
        existing_invoice=(
            GlobalInvoiceRef(
                invoice_id=active.id,
                folio_label=f"{active.series}-{active.folio:06d}",
                status=active.status,
            )
            if active is not None
            else None
        ),
    )


def create_global_invoice(
    session: Session,
    *,
    year: int,
    month: int,
    idempotency_key: str,
    actor_id: UUID | None = None,
) -> tuple[InvoiceView, bool]:
    """Request the monthly CFDI that groups public-general walk-in sales.

    The period must already be closed: billing a running month would leave later
    sales out and block their regular global invoice. The eligible set is
    recomputed here, never trusted from the review screen, so an operation
    invoiced individually between review and confirmation is left out.
    """

    start, end = _global_period(year, month)
    if utc_now() < end:
        raise GlobalInvoicePeriodOpen(
            "Solo se puede emitir la factura global de un mes ya cerrado."
        )

    key = (idempotency_key or "").strip()
    if not key:
        raise FiscalDataInvalid(
            "La clave de idempotencia es obligatoria.", field="idempotency_key"
        )
    if len(key) > 128:
        raise FiscalDataInvalid(
            "La clave de idempotencia excede 128 caracteres.",
            field="idempotency_key",
        )

    fingerprint = _fingerprint(
        {
            "origin_type": "global",
            "year": str(year),
            "month": f"{month:02d}",
        }
    )
    existing = session.exec(
        select(Invoice).where(Invoice.idempotency_key == key)
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise InvoiceIdempotencyConflict(
                "La clave de idempotencia ya se usó con otra solicitud de factura."
            )
        return _invoice_view(session, existing, full=True), False

    active = _active_global_invoice_for_period(session, year, month)
    if active is not None:
        raise GlobalInvoicePeriodConflict(str(active.id))

    rate = tax_rate_percent()
    candidates = _global_candidates(session, start=start, end=end, rate=rate)
    if not candidates.eligible:
        raise GlobalInvoiceNoEligibleSales(
            "El periodo no tiene ventas de público en general pendientes de "
            "facturar en la factura global."
        )

    series = invoice_series()
    folio = _next_folio(session, series)
    issuer = issuer_config()
    origin_id = uuid5(
        NAMESPACE_URL, f"ritmo-gym:global-invoice:{year}-{month:02d}"
    )
    invoice = Invoice(
        series=series,
        folio=folio,
        status="requested",
        origin_type="global",
        origin_id=origin_id,
        origin_reference=f"GLOBAL-{year}-{month:02d}",
        global_year=year,
        global_month=month,
        member_id=None,
        receptor_rfc=cfdi.PUBLIC_GENERAL_RFC,
        receptor_name=cfdi.PUBLIC_GENERAL_NAME,
        receptor_tax_regime=cfdi.PUBLIC_GENERAL_TAX_REGIME,
        receptor_postal_code=issuer.postal_code,
        receptor_cfdi_use=cfdi.PUBLIC_GENERAL_CFDI_USE,
        receptor_email=None,
        currency=cfdi.DEFAULT_CURRENCY,
        subtotal_cents=candidates.subtotal_cents,
        tax_cents=candidates.tax_cents,
        total_cents=candidates.total_cents,
        tax_rate_percent=rate,
        payment_form="99",
        payment_method="PUE",
        idempotency_key=key,
        request_fingerprint=fingerprint,
        created_by=actor_id,
    )
    session.add(invoice)
    session.flush()

    operation_label = "operación" if len(candidates.eligible) == 1 else "operaciones"
    item = InvoiceItem(
        invoice_id=invoice.id,
        position=1,
        description=(
            f"Venta de productos y servicios al público en general "
            f"({_global_period_label(year, month)}, "
            f"{len(candidates.eligible)} {operation_label})"
        )[:300],
        sat_product_code=issuer.product_code,
        sat_unit_code="ACT",
        unit_name="Actividad",
        quantity=len(candidates.eligible),
        unit_price_cents=round(
            candidates.subtotal_cents / len(candidates.eligible)
        ),
        subtotal_cents=candidates.subtotal_cents,
        tax_cents=candidates.tax_cents,
        total_cents=candidates.total_cents,
    )
    session.add(item)
    for sale in candidates.eligible:
        session.add(
            GlobalInvoiceSale(
                invoice_id=invoice.id,
                sale_id=sale.id,
                sale_folio=sale.folio,
                sold_at=sale.sold_at,
                total_cents=sale.total_cents,
            )
        )
    session.flush()

    invoice.xml_content = cfdi.build_cfdi_xml(
        invoice=invoice,
        items=(item,),
        issuer=issuer,
    )
    _record_event(
        session,
        invoice,
        "invoice_requested",
        from_status=None,
        to_status="requested",
        actor_id=actor_id,
        detail={
            "origin_type": "global",
            "origin_id": str(origin_id),
            "origin_reference": invoice.origin_reference,
            "period_year": year,
            "period_month": month,
            "sales_count": len(candidates.eligible),
            "total_cents": candidates.total_cents,
        },
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        replay = session.exec(
            select(Invoice).where(Invoice.idempotency_key == key)
        ).first()
        if replay is not None and replay.request_fingerprint == fingerprint:
            return _invoice_view(session, replay, full=True), False
        active = _active_global_invoice_for_period(session, year, month)
        if active is not None:
            raise GlobalInvoicePeriodConflict(str(active.id)) from error
        raise InvoiceNumberingError(
            "No fue posible asignar el folio de la factura global; intenta de nuevo."
        ) from error

    session.refresh(invoice)
    return _invoice_view(session, invoice, full=True), True


def create_invoice(
    session: Session,
    *,
    origin_type: str,
    origin_id: UUID,
    rfc: str,
    legal_name: str,
    tax_regime: str,
    postal_code: str,
    cfdi_use: str,
    idempotency_key: str,
    email: str | None = None,
    payment_form: str | None = None,
    payment_method: str | None = None,
    actor_id: UUID | None = None,
    channel: str = "staff",
) -> tuple[InvoiceView, bool]:
    """Request an invoice for one sale or membership payment.

    Returns ``(invoice, created)``: ``created`` is ``False`` when the same
    idempotency key replays an existing request, which lets the caller answer
    without duplicating folios, XML or events. A PPD invoice is issued with
    FormaPago 99 (payment still undefined); each partiality is a payment
    complement created later from the billing panel.

    ``channel`` only labels the request event (``staff`` or ``member_app``);
    the authorization decision belongs to the caller.
    """

    key = (idempotency_key or "").strip()
    if not key:
        raise FiscalDataInvalid("La clave de idempotencia es obligatoria.", field="idempotency_key")
    if len(key) > 128:
        raise FiscalDataInvalid("La clave de idempotencia excede 128 caracteres.", field="idempotency_key")

    fiscal = cfdi.normalize_fiscal_data(
        rfc=rfc,
        legal_name=legal_name,
        tax_regime=tax_regime,
        postal_code=postal_code,
        cfdi_use=cfdi_use,
        email=email,
    )
    requested_form = (payment_form or "").strip()
    requested_method = (payment_method or "PUE").strip().upper()
    if requested_method not in ("PUE", "PPD"):
        raise FiscalDataInvalid(
            "El método de pago debe ser PUE o PPD.", field="payment_method"
        )
    fingerprint = _fingerprint(
        {
            "origin_type": origin_type,
            "origin_id": str(origin_id),
            "rfc": fiscal.rfc,
            "legal_name": fiscal.legal_name,
            "tax_regime": fiscal.tax_regime,
            "postal_code": fiscal.postal_code,
            "cfdi_use": fiscal.cfdi_use,
            "email": fiscal.email,
            "payment_form": requested_form,
            "payment_method": requested_method,
        }
    )

    existing = session.exec(
        select(Invoice).where(Invoice.idempotency_key == key)
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise InvoiceIdempotencyConflict(
                "La clave de idempotencia ya se usó con otra solicitud de factura."
            )
        return _invoice_view(session, existing, full=True), False

    origin = _resolve_origin(session, origin_type, origin_id)
    form = requested_form or cfdi.payment_form_for_method(origin.method)
    if requested_method == "PPD":
        if requested_form and requested_form != "99":
            raise FiscalDataInvalid(
                "Una factura PPD debe usar la forma de pago 99 (por definir).",
                field="payment_form",
            )
        form = "99"
    if form not in cfdi.PAYMENT_FORMS:
        raise FiscalDataInvalid(
            "La forma de pago no es una clave del SAT válida.", field="payment_form"
        )

    active = session.exec(
        select(Invoice).where(
            Invoice.origin_type == origin.origin_type,
            Invoice.origin_id == origin.origin_id,
            Invoice.status != "cancelled",
        )
    ).first()
    if active is not None:
        raise OriginAlreadyInvoiced(str(active.id))

    series = invoice_series()
    folio = _next_folio(session, series)
    rate = tax_rate_percent()
    issuer = issuer_config()

    item_rows: list[InvoiceItem] = []
    subtotal_cents = 0
    tax_cents = 0
    for position, line in enumerate(origin.lines, start=1):
        line_base, line_tax = cfdi.split_tax_inclusive(line.total_cents, rate)
        subtotal_cents += line_base
        tax_cents += line_tax
        item_rows.append(
            InvoiceItem(
                position=position,
                description=line.description,
                sat_product_code=(
                    issuer.service_code
                    if origin.origin_type == "membership_payment"
                    else issuer.product_code
                ),
                sat_unit_code="E48" if origin.origin_type == "membership_payment" else "H87",
                unit_name="Servicio" if origin.origin_type == "membership_payment" else "Pieza",
                quantity=line.quantity,
                unit_price_cents=line.total_cents,
                subtotal_cents=line_base,
                tax_cents=line_tax,
                total_cents=line.total_cents,
                product_id=line.product_id,
                sale_item_id=line.sale_item_id,
            )
        )
    if subtotal_cents + tax_cents != origin.total_cents:
        raise OriginNotInvoiceable(
            "El desglose de impuestos no cuadra con el total de la operación.",
            origin_type=origin.origin_type,
            origin_id=str(origin.origin_id),
        )

    invoice = Invoice(
        series=series,
        folio=folio,
        status="requested",
        origin_type=origin.origin_type,
        origin_id=origin.origin_id,
        origin_reference=origin.reference,
        member_id=origin.member_id,
        receptor_rfc=fiscal.rfc,
        receptor_name=fiscal.legal_name,
        receptor_tax_regime=fiscal.tax_regime,
        receptor_postal_code=fiscal.postal_code,
        receptor_cfdi_use=fiscal.cfdi_use,
        receptor_email=fiscal.email,
        currency=cfdi.DEFAULT_CURRENCY,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=origin.total_cents,
        tax_rate_percent=rate,
        payment_form=form,
        payment_method=requested_method,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        created_by=actor_id,
    )
    session.add(invoice)
    session.flush()

    for item in item_rows:
        item.invoice_id = invoice.id
        session.add(item)
    session.flush()

    invoice.xml_content = cfdi.build_cfdi_xml(
        invoice=invoice,
        items=item_rows,
        issuer=issuer_config(),
    )
    _record_event(
        session,
        invoice,
        "invoice_requested",
        from_status=None,
        to_status="requested",
        actor_id=actor_id,
        detail={
            "origin_type": origin.origin_type,
            "origin_id": str(origin.origin_id),
            "origin_reference": origin.reference,
            "total_cents": origin.total_cents,
            "payment_method": requested_method,
            "payment_form": form,
            "channel": channel,
        },
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        # Another request may have won the race for the same origin or key.
        active = session.exec(
            select(Invoice).where(
                Invoice.origin_type == origin.origin_type,
                Invoice.origin_id == origin.origin_id,
                Invoice.status != "cancelled",
            )
        ).first()
        if active is not None:
            raise OriginAlreadyInvoiced(str(active.id)) from error
        raise InvoiceNumberingError(
            "No fue posible asignar el folio de la factura; intenta de nuevo."
        ) from error

    session.refresh(invoice)
    return _invoice_view(session, invoice, full=True), True


class InvoiceNotInvoiceableDetail(FiscalDataInvalid):
    """The amount breakdown does not match; surfaced as a 422."""


def _related_invoice_uuid(session: Session, invoice: Invoice) -> str | None:
    if invoice.origin_type != "credit_note" or invoice.related_invoice_id is None:
        return None
    related = session.get(Invoice, invoice.related_invoice_id)
    return related.uuid if related is not None else None


def _build_invoice_xml(
    session: Session,
    invoice: Invoice,
    items: Sequence[InvoiceItem],
    *,
    simulated: bool = False,
) -> str:
    return cfdi.build_cfdi_xml(
        invoice=invoice,
        items=items,
        issuer=issuer_config(),
        simulated=simulated,
        related_uuid=_related_invoice_uuid(session, invoice),
    )


def _stamped_credit_cents(session: Session, invoice_id: UUID) -> int:
    """Amount already credited by stamped notes, which is the fiscal balance used."""

    return int(
        session.exec(
            select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(
                Invoice.origin_type == "credit_note",
                Invoice.related_invoice_id == invoice_id,
                Invoice.status == "stamped",
            )
        ).first()
        or 0
    )


def _credit_balance_cents(session: Session, invoice: Invoice) -> int:
    return max(0, invoice.total_cents - _stamped_credit_cents(session, invoice.id))


def create_credit_note(
    session: Session,
    *,
    invoice_id: UUID,
    amount_cents: int,
    reason: str,
    idempotency_key: str,
    note: str | None = None,
    actor_id: UUID | None = None,
) -> tuple[InvoiceView, bool]:
    """Request a credit note (CFDI de egreso) for part or all of an invoice.

    Only a stamped income invoice with a known receptor can be credited. The
    original row is locked while the remaining balance is checked; a requested
    note does not consume the balance until it is stamped, so ``stamp_invoice``
    checks it again while holding the same lock.
    """

    key = (idempotency_key or "").strip()
    if not key:
        raise FiscalDataInvalid(
            "La clave de idempotencia es obligatoria.", field="idempotency_key"
        )
    if len(key) > 128:
        raise FiscalDataInvalid(
            "La clave de idempotencia excede 128 caracteres.",
            field="idempotency_key",
        )
    normalized_reason = (reason or "").strip().lower()
    if normalized_reason not in CREDIT_NOTE_REASONS:
        raise FiscalDataInvalid(
            "El motivo de la nota de crédito no es válido.", field="reason"
        )
    normalized_note = (note or "").strip() or None
    if normalized_note is not None and len(normalized_note) > 300:
        raise FiscalDataInvalid(
            "La nota de la nota de crédito excede 300 caracteres.", field="note"
        )
    if amount_cents <= 0:
        raise FiscalDataInvalid(
            "El importe de la nota de crédito debe ser mayor que cero.",
            field="amount_cents",
        )

    fingerprint = _fingerprint(
        {
            "origin_type": "credit_note",
            "related_invoice_id": str(invoice_id),
            "amount_cents": str(amount_cents),
            "reason": normalized_reason,
            "note": normalized_note,
        }
    )
    existing = session.exec(
        select(Invoice).where(Invoice.idempotency_key == key)
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise InvoiceIdempotencyConflict(
                "La clave de idempotencia ya se usó con otra solicitud de factura."
            )
        return _invoice_view(session, existing, full=True), False

    related = session.exec(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    ).first()
    if related is None:
        raise InvoiceNotFound("La factura no existe.")
    if related.status != "stamped":
        raise CreditNoteNotAllowed(
            "Solo se puede emitir una nota de crédito sobre una factura timbrada y vigente."
        )
    if related.origin_type not in CREDIT_NOTE_SOURCE_TYPES:
        if related.origin_type == "global":
            raise CreditNoteNotAllowed(
                "La factura global no admite notas de crédito; ajusta las ventas "
                "incluidas mediante el procedimiento fiscal correspondiente."
            )
        raise CreditNoteNotAllowed(
            "Una nota de crédito no se puede ajustar con otra nota de crédito."
        )
    if related.payment_method == "PPD":
        raise CreditNoteNotAllowed(
            "La factura está emitida con método PPD; los ajustes se realizan sobre "
            "sus complementos de pago. Esta versión no permite notas de crédito "
            "sobre facturas PPD."
        )
    balance = _credit_balance_cents(session, related)
    if balance <= 0:
        raise CreditNoteNotAllowed("La factura ya está totalmente acreditada.")
    if amount_cents > balance:
        raise CreditNoteBalanceExceeded(
            "El importe excede el saldo acreditable disponible "
            f"({_money_label(balance)}).",
            field="amount_cents",
        )

    folio_label = f"{related.series}-{related.folio:06d}"
    rate = related.tax_rate_percent
    subtotal_cents, tax_cents = cfdi.split_tax_inclusive(amount_cents, rate)
    series = invoice_series()
    issuer = issuer_config()
    reason_label = CREDIT_NOTE_REASONS[normalized_reason]

    invoice = Invoice(
        series=series,
        folio=_next_folio(session, series),
        status="requested",
        origin_type="credit_note",
        origin_id=related.id,
        origin_reference=folio_label,
        related_invoice_id=related.id,
        credit_note_reason=normalized_reason,
        credit_note_note=normalized_note,
        member_id=related.member_id,
        receptor_rfc=related.receptor_rfc,
        receptor_name=related.receptor_name,
        receptor_tax_regime=related.receptor_tax_regime,
        receptor_postal_code=related.receptor_postal_code,
        receptor_cfdi_use=related.receptor_cfdi_use,
        receptor_email=related.receptor_email,
        currency=related.currency,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=amount_cents,
        tax_rate_percent=rate,
        payment_form=related.payment_form,
        payment_method="PUE",
        idempotency_key=key,
        request_fingerprint=fingerprint,
        created_by=actor_id,
    )
    session.add(invoice)
    session.flush()

    is_service = related.origin_type == "membership_payment"
    item = InvoiceItem(
        invoice_id=invoice.id,
        position=1,
        description=(
            f"Nota de crédito · {reason_label.lower()} de la factura {folio_label}"
        )[:300],
        sat_product_code=issuer.service_code if is_service else issuer.product_code,
        sat_unit_code="E48" if is_service else "H87",
        unit_name="Servicio" if is_service else "Pieza",
        quantity=1,
        unit_price_cents=amount_cents,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=amount_cents,
    )
    session.add(item)
    session.flush()

    invoice.xml_content = _build_invoice_xml(session, invoice, (item,))
    _record_event(
        session,
        invoice,
        "invoice_requested",
        from_status=None,
        to_status="requested",
        actor_id=actor_id,
        detail={
            "origin_type": "credit_note",
            "origin_id": str(related.id),
            "origin_reference": folio_label,
            "related_invoice_id": str(related.id),
            "reason": normalized_reason,
            "note": normalized_note,
            "total_cents": amount_cents,
            "remaining_balance_cents": balance - amount_cents,
        },
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        replay = session.exec(
            select(Invoice).where(Invoice.idempotency_key == key)
        ).first()
        if replay is not None and replay.request_fingerprint == fingerprint:
            return _invoice_view(session, replay, full=True), False
        raise InvoiceNumberingError(
            "No fue posible asignar el folio de la nota de crédito; intenta de nuevo."
        ) from error

    session.refresh(invoice)
    return _invoice_view(session, invoice, full=True), True


def stamp_invoice(
    session: Session,
    invoice_id: UUID,
    *,
    actor_id: UUID | None = None,
) -> InvoiceView:
    invoice = _get_invoice(session, invoice_id)
    if invoice.status == "stamped":
        return _invoice_view(session, invoice, full=True)
    if invoice.status == "cancelled":
        raise InvoiceStateError("Una factura cancelada no se puede volver a timbrar.")

    if invoice.origin_type == "credit_note" and invoice.related_invoice_id is not None:
        related = session.exec(
            select(Invoice)
            .where(Invoice.id == invoice.related_invoice_id)
            .with_for_update()
        ).first()
        if related is None or related.status != "stamped":
            previous = invoice.status
            invoice.status = "failed"
            invoice.updated_at = utc_now()
            _record_event(
                session,
                invoice,
                "invoice_stamp_failed",
                from_status=previous,
                to_status="failed",
                actor_id=actor_id,
                detail={
                    "code": "related_not_stamped",
                    "error": (
                        "La factura relacionada ya no está timbrada; la nota de "
                        "crédito no se puede timbrar."
                    ),
                },
            )
            session.commit()
            raise CreditNoteNotAllowed(
                "La factura relacionada ya no está timbrada; la nota de crédito "
                "no se puede timbrar."
            )
        balance = _credit_balance_cents(session, related)
        if invoice.total_cents > balance:
            previous = invoice.status
            invoice.status = "failed"
            invoice.updated_at = utc_now()
            _record_event(
                session,
                invoice,
                "invoice_stamp_failed",
                from_status=previous,
                to_status="failed",
                actor_id=actor_id,
                detail={
                    "code": "credit_balance_exceeded",
                    "error": (
                        "El importe de la nota de crédito excede el saldo "
                        f"acreditable disponible ({_money_label(balance)})."
                    ),
                },
            )
            session.commit()
            raise CreditNoteBalanceExceeded(
                "El importe de la nota de crédito excede el saldo acreditable "
                f"disponible ({_money_label(balance)}).",
                field="amount_cents",
            )

    items = _invoice_items(session, invoice.id)
    xml = invoice.xml_content or _build_invoice_xml(session, invoice, items)
    try:
        outcome = pac_gateway().stamp(xml)
    except PacRejected as error:
        previous = invoice.status
        invoice.status = "failed"
        invoice.updated_at = utc_now()
        _record_event(
            session,
            invoice,
            "invoice_stamp_failed",
            from_status=previous,
            to_status="failed",
            actor_id=actor_id,
            detail={"error": str(error), "code": error.code},
        )
        session.commit()
        raise

    previous = invoice.status
    invoice.status = "stamped"
    invoice.uuid = outcome.uuid
    invoice.is_simulated = outcome.simulated
    invoice.provider = outcome.provider
    invoice.provider_reference = outcome.provider_reference
    invoice.xml_content = outcome.stamped_xml
    invoice.issued_at = outcome.issued_at
    invoice.stamped_at = utc_now()
    invoice.stamped_by = actor_id
    _record_event(
        session,
        invoice,
        "invoice_stamped",
        from_status=previous,
        to_status="stamped",
        actor_id=actor_id,
        detail={
            "provider": outcome.provider,
            "provider_reference": outcome.provider_reference,
            "simulated": outcome.simulated,
            "uuid": outcome.uuid,
        },
    )
    session.commit()
    session.refresh(invoice)
    return _invoice_view(session, invoice, full=True)


def cancel_invoice(
    session: Session,
    invoice_id: UUID,
    *,
    reason_code: str,
    replacement_uuid: str | None = None,
    note: str | None = None,
    actor_id: UUID | None = None,
) -> InvoiceView:
    invoice = session.exec(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    ).first()
    if invoice is None:
        raise InvoiceNotFound("La factura no existe.")
    if invoice.status != "stamped":
        raise InvoiceStateError("Solo se puede cancelar una factura timbrada.")
    if invoice.origin_type in CREDIT_NOTE_SOURCE_TYPES:
        live_note = session.exec(
            select(Invoice.folio).where(
                Invoice.origin_type == "credit_note",
                Invoice.related_invoice_id == invoice.id,
                Invoice.status == "stamped",
            )
        ).first()
        if live_note is not None:
            raise CreditNoteNotAllowed(
                "La factura tiene notas de crédito timbradas vigentes; cancélalas "
                "antes de cancelar la factura."
            )
    live_payment = session.exec(
        select(InvoicePayment.folio).where(
            InvoicePayment.invoice_id == invoice.id,
            InvoicePayment.status == "stamped",
        )
    ).first()
    if live_payment is not None:
        raise PaymentComplementNotAllowed(
            "La factura tiene complementos de pago timbrados vigentes; cancélalos "
            "antes de cancelar la factura."
        )
    reason = (reason_code or "").strip()
    if reason not in CANCELLATION_REASONS:
        raise FiscalDataInvalid(
            "El motivo de cancelación debe ser 01, 02, 03 o 04.", field="reason_code"
        )
    replacement = (replacement_uuid or "").strip() or None
    if reason == "01" and replacement is None:
        raise FiscalDataInvalid(
            "El motivo 01 requiere el UUID del comprobante que sustituye.",
            field="replacement_uuid",
        )
    if replacement is not None:
        if not UUID_PATTERN.match(replacement):
            raise FiscalDataInvalid(
                "El UUID de sustitución no tiene un formato válido.",
                field="replacement_uuid",
            )
        if invoice.uuid is not None and replacement.lower() == invoice.uuid.lower():
            raise FiscalDataInvalid(
                "El UUID de sustitución debe ser distinto del comprobante cancelado.",
                field="replacement_uuid",
            )
    normalized_note = (note or "").strip() or None
    if normalized_note is not None and len(normalized_note) > 300:
        raise FiscalDataInvalid("La nota de cancelación excede 300 caracteres.", field="note")

    outcome = pac_gateway().cancel(
        uuid=invoice.uuid,
        reason_code=reason,
        replacement_uuid=replacement,
    )
    if not outcome.accepted:
        raise PacRejected("El PAC rechazó la cancelación del comprobante.")

    invoice.status = "cancelled"
    invoice.cancelled_at = utc_now()
    invoice.cancelled_by = actor_id
    invoice.cancellation_reason_code = reason
    invoice.cancellation_replacement_uuid = replacement
    invoice.cancellation_note = normalized_note
    _record_event(
        session,
        invoice,
        "invoice_cancelled",
        from_status="stamped",
        to_status="cancelled",
        actor_id=actor_id,
        detail={
            "reason_code": reason,
            "replacement_uuid": replacement,
            "note": normalized_note,
            "provider": outcome.provider,
            "simulated": outcome.simulated,
        },
    )
    session.commit()
    session.refresh(invoice)
    return _invoice_view(session, invoice, full=True)


def payment_series() -> str:
    raw = (
        os.getenv("CFDI_PAYMENT_SERIES", DEFAULT_PAYMENT_SERIES)
        or DEFAULT_PAYMENT_SERIES
    ).strip().upper()
    if not raw or len(raw) > 10:
        return DEFAULT_PAYMENT_SERIES
    return raw


def _get_payment(session: Session, payment_id: UUID) -> InvoicePayment:
    payment = session.get(InvoicePayment, payment_id)
    if payment is None:
        raise PaymentComplementNotFound("El complemento de pago no existe.")
    return payment


def _next_payment_folio(session: Session, series: str) -> int:
    last = session.exec(
        select(func.max(InvoicePayment.folio)).where(InvoicePayment.series == series)
    ).first()
    return int(last or 0) + 1


def _stamped_paid_cents(session: Session, invoice_id: UUID) -> int:
    return int(
        session.exec(
            select(func.coalesce(func.sum(InvoicePayment.amount_cents), 0)).where(
                InvoicePayment.invoice_id == invoice_id,
                InvoicePayment.status == "stamped",
            )
        ).first()
        or 0
    )


def _payment_balance_cents(session: Session, invoice: Invoice) -> int:
    return max(0, invoice.total_cents - _stamped_paid_cents(session, invoice.id))


def _next_partiality_number(session: Session, invoice_id: UUID) -> int:
    last = session.exec(
        select(func.max(InvoicePayment.partiality_number)).where(
            InvoicePayment.invoice_id == invoice_id,
            InvoicePayment.status == "stamped",
        )
    ).first()
    return int(last or 0) + 1


def _payment_events(session: Session, payment_id: UUID) -> tuple[InvoiceEventView, ...]:
    return tuple(
        InvoiceEventView(
            event_type=event.event_type,
            from_status=event.from_status,
            to_status=event.to_status,
            actor_id=event.actor_id,
            detail=event.detail,
            occurred_at=event.occurred_at,
        )
        for event in session.exec(
            select(InvoicePaymentEvent)
            .where(InvoicePaymentEvent.payment_id == payment_id)
            .order_by(InvoicePaymentEvent.occurred_at)
        ).all()
    )


def _payment_view(session: Session, payment: InvoicePayment) -> PaymentComplementView:
    invoice = session.get(Invoice, payment.invoice_id)
    return PaymentComplementView(
        id=payment.id,
        invoice_id=payment.invoice_id,
        invoice_folio_label=(
            f"{invoice.series}-{invoice.folio:06d}" if invoice is not None else ""
        ),
        series=payment.series,
        folio=payment.folio,
        folio_label=f"{payment.series}-{payment.folio:06d}",
        status=payment.status,
        partiality_number=payment.partiality_number,
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        payment_form=payment.payment_form,
        paid_on=payment.paid_on,
        prior_balance_cents=payment.prior_balance_cents,
        outstanding_balance_cents=payment.outstanding_balance_cents,
        tax_rate_percent=payment.tax_rate_percent,
        uuid=payment.uuid,
        is_simulated=payment.is_simulated,
        provider=payment.provider,
        provider_reference=payment.provider_reference,
        xml_available=bool(payment.xml_content),
        issued_at=payment.issued_at,
        stamped_at=payment.stamped_at,
        cancelled_at=payment.cancelled_at,
        cancellation_reason_code=payment.cancellation_reason_code,
        cancellation_note=payment.cancellation_note,
        created_at=payment.created_at,
        created_by=payment.created_by,
        events=_payment_events(session, payment.id),
    )


def _record_payment_event(
    session: Session,
    payment: InvoicePayment,
    event_type: str,
    *,
    from_status: str | None,
    to_status: str | None,
    actor_id: UUID | None,
    detail: dict[str, object],
) -> None:
    session.add(
        InvoicePaymentEvent(
            payment_id=payment.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            detail=detail,
        )
    )


def _fail_payment(
    session: Session,
    payment: InvoicePayment,
    *,
    code: str,
    message: str,
    actor_id: UUID | None,
) -> None:
    previous = payment.status
    payment.status = "failed"
    payment.updated_at = utc_now()
    _record_payment_event(
        session,
        payment,
        "payment_stamp_failed",
        from_status=previous,
        to_status="failed",
        actor_id=actor_id,
        detail={"code": code, "error": message},
    )
    session.commit()


def _build_payment_xml(
    payment: InvoicePayment,
    invoice: Invoice,
    *,
    simulated: bool = False,
) -> str:
    return cfdi.build_payment_complement_xml(
        payment=payment,
        invoice=invoice,
        issuer=issuer_config(),
        related_uuid=invoice.uuid,
        simulated=simulated,
    )


def _parse_paid_on(value: date | datetime | str | None) -> date:
    if value is None:
        return club_date(datetime.now(timezone.utc))
    if isinstance(value, datetime):
        return club_date(value)
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as error:
        raise FiscalDataInvalid(
            "La fecha de pago no es válida (usa el formato AAAA-MM-DD).",
            field="paid_on",
        ) from error


def create_payment_complement(
    session: Session,
    *,
    invoice_id: UUID,
    amount_cents: int,
    payment_form: str,
    idempotency_key: str,
    paid_on: date | datetime | str | None = None,
    actor_id: UUID | None = None,
) -> tuple[PaymentComplementView, bool]:
    """Request a payment complement (partiality) for a stamped PPD invoice.

    A requested complement does not consume the balance until it is stamped;
    ``stamp_payment_complement`` validates it again while holding the invoice
    lock. The amount may be partial or the whole outstanding balance.
    """

    key = (idempotency_key or "").strip()
    if not key:
        raise FiscalDataInvalid(
            "La clave de idempotencia es obligatoria.", field="idempotency_key"
        )
    if len(key) > 128:
        raise FiscalDataInvalid(
            "La clave de idempotencia excede 128 caracteres.",
            field="idempotency_key",
        )
    if amount_cents <= 0:
        raise FiscalDataInvalid(
            "El importe del complemento debe ser mayor que cero.",
            field="amount_cents",
        )
    form = (payment_form or "").strip()
    if form not in PAYMENT_COMPLEMENT_FORMS:
        raise FiscalDataInvalid(
            "La forma de pago del complemento no es válida; elige cómo se pagó "
            "(no puede ser 99).",
            field="payment_form",
        )
    payment_date = _parse_paid_on(paid_on)
    fingerprint = _fingerprint(
        {
            "origin_type": "payment_complement",
            "invoice_id": str(invoice_id),
            "amount_cents": str(amount_cents),
            "payment_form": form,
            "paid_on": payment_date.isoformat(),
        }
    )
    existing = session.exec(
        select(InvoicePayment).where(InvoicePayment.idempotency_key == key)
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise InvoiceIdempotencyConflict(
                "La clave de idempotencia ya se usó con otro complemento de pago."
            )
        return _payment_view(session, existing), False

    invoice = session.exec(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    ).first()
    if invoice is None:
        raise InvoiceNotFound("La factura no existe.")
    if invoice.status != "stamped":
        raise PaymentComplementNotAllowed(
            "Solo una factura timbrada y vigente puede recibir complementos de pago."
        )
    if invoice.payment_method != "PPD":
        raise PaymentComplementNotAllowed(
            "Solo las facturas emitidas con método PPD (pago en parcialidades o "
            "diferido) requieren complementos de pago."
        )
    if invoice.origin_type not in PAYMENT_COMPLEMENT_SOURCE_TYPES:
        raise PaymentComplementNotAllowed(
            "Este tipo de comprobante no admite complementos de pago."
        )
    issued_on = club_date(invoice.issued_at or invoice.created_at)
    if payment_date < issued_on:
        raise FiscalDataInvalid(
            "La fecha de pago no puede ser anterior a la emisión de la factura.",
            field="paid_on",
        )
    if payment_date > club_date(datetime.now(timezone.utc)):
        raise FiscalDataInvalid(
            "La fecha de pago no puede ser futura.", field="paid_on"
        )
    balance = _payment_balance_cents(session, invoice)
    if balance <= 0:
        raise PaymentComplementNotAllowed(
            "La factura ya está pagada en su totalidad."
        )
    if amount_cents > balance:
        raise PaymentComplementBalanceExceeded(
            "El importe excede el saldo pendiente de pago "
            f"({_money_label(balance)}).",
            field="amount_cents",
        )

    series = payment_series()
    payment = InvoicePayment(
        invoice_id=invoice.id,
        series=series,
        folio=_next_payment_folio(session, series),
        status="requested",
        partiality_number=_next_partiality_number(session, invoice.id),
        amount_cents=amount_cents,
        currency=invoice.currency,
        payment_form=form,
        paid_on=payment_date,
        prior_balance_cents=balance,
        outstanding_balance_cents=balance - amount_cents,
        tax_rate_percent=invoice.tax_rate_percent,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        created_by=actor_id,
    )
    session.add(payment)
    session.flush()
    payment.xml_content = _build_payment_xml(payment, invoice)
    _record_payment_event(
        session,
        payment,
        "payment_requested",
        from_status=None,
        to_status="requested",
        actor_id=actor_id,
        detail={
            "invoice_id": str(invoice.id),
            "invoice_folio": f"{invoice.series}-{invoice.folio:06d}",
            "partiality_number": payment.partiality_number,
            "amount_cents": amount_cents,
            "prior_balance_cents": balance,
            "outstanding_balance_cents": balance - amount_cents,
            "payment_form": form,
            "paid_on": payment_date.isoformat(),
        },
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        replay = session.exec(
            select(InvoicePayment).where(InvoicePayment.idempotency_key == key)
        ).first()
        if replay is not None and replay.request_fingerprint == fingerprint:
            return _payment_view(session, replay), False
        raise InvoiceNumberingError(
            "No fue posible asignar el folio del complemento de pago; intenta de nuevo."
        ) from error

    session.refresh(payment)
    return _payment_view(session, payment), True


def stamp_payment_complement(
    session: Session,
    payment_id: UUID,
    *,
    actor_id: UUID | None = None,
) -> PaymentComplementView:
    preview = _get_payment(session, payment_id)
    invoice = session.exec(
        select(Invoice).where(Invoice.id == preview.invoice_id).with_for_update()
    ).first()
    payment = session.exec(
        select(InvoicePayment)
        .where(InvoicePayment.id == payment_id)
        .with_for_update()
    ).first()
    if payment is None:
        raise PaymentComplementNotFound("El complemento de pago no existe.")
    if payment.status == "stamped":
        return _payment_view(session, payment)
    if payment.status == "cancelled":
        raise PaymentComplementNotAllowed(
            "Un complemento de pago cancelado no se puede volver a timbrar."
        )

    if (
        invoice is None
        or invoice.status != "stamped"
        or invoice.payment_method != "PPD"
        or invoice.origin_type not in PAYMENT_COMPLEMENT_SOURCE_TYPES
    ):
        message = (
            "La factura relacionada ya no está timbrada y vigente; el complemento "
            "de pago no se puede timbrar."
        )
        _fail_payment(
            session,
            payment,
            code="invoice_not_payable",
            message=message,
            actor_id=actor_id,
        )
        raise PaymentComplementNotAllowed(message)

    balance = _payment_balance_cents(session, invoice)
    if payment.amount_cents > balance:
        message = (
            "El importe del complemento excede el saldo pendiente de pago "
            f"({_money_label(balance)})."
        )
        _fail_payment(
            session,
            payment,
            code="payment_balance_exceeded",
            message=message,
            actor_id=actor_id,
        )
        raise PaymentComplementBalanceExceeded(message, field="amount_cents")

    payment.partiality_number = _next_partiality_number(session, invoice.id)
    payment.prior_balance_cents = balance
    payment.outstanding_balance_cents = balance - payment.amount_cents
    payment.tax_rate_percent = invoice.tax_rate_percent
    payment.xml_content = _build_payment_xml(payment, invoice)
    try:
        outcome = pac_gateway().stamp(payment.xml_content)
    except PacRejected as error:
        _fail_payment(
            session,
            payment,
            code=error.code or "pac_rejected",
            message=str(error),
            actor_id=actor_id,
        )
        raise

    previous = payment.status
    payment.status = "stamped"
    payment.uuid = outcome.uuid
    payment.is_simulated = outcome.simulated
    payment.provider = outcome.provider
    payment.provider_reference = outcome.provider_reference
    payment.xml_content = outcome.stamped_xml
    payment.issued_at = outcome.issued_at
    payment.stamped_at = utc_now()
    payment.stamped_by = actor_id
    _record_payment_event(
        session,
        payment,
        "payment_stamped",
        from_status=previous,
        to_status="stamped",
        actor_id=actor_id,
        detail={
            "provider": outcome.provider,
            "provider_reference": outcome.provider_reference,
            "simulated": outcome.simulated,
            "uuid": outcome.uuid,
            "partiality_number": payment.partiality_number,
            "prior_balance_cents": payment.prior_balance_cents,
            "outstanding_balance_cents": payment.outstanding_balance_cents,
        },
    )
    session.commit()
    session.refresh(payment)
    return _payment_view(session, payment)


def cancel_payment_complement(
    session: Session,
    payment_id: UUID,
    *,
    reason_code: str,
    replacement_uuid: str | None = None,
    note: str | None = None,
    actor_id: UUID | None = None,
) -> PaymentComplementView:
    payment = session.exec(
        select(InvoicePayment)
        .where(InvoicePayment.id == payment_id)
        .with_for_update()
    ).first()
    if payment is None:
        raise PaymentComplementNotFound("El complemento de pago no existe.")
    if payment.status != "stamped":
        raise PaymentComplementNotAllowed(
            "Solo se puede cancelar un complemento de pago timbrado."
        )
    latest = session.exec(
        select(func.max(InvoicePayment.partiality_number)).where(
            InvoicePayment.invoice_id == payment.invoice_id,
            InvoicePayment.status == "stamped",
        )
    ).first()
    if payment.partiality_number != int(latest or 0):
        raise PaymentComplementNotAllowed(
            "Solo se puede cancelar la última parcialidad vigente; los saldos de "
            "los complementos posteriores dependen de ella."
        )
    reason = (reason_code or "").strip()
    if reason not in CANCELLATION_REASONS:
        raise FiscalDataInvalid(
            "El motivo de cancelación debe ser 01, 02, 03 o 04.", field="reason_code"
        )
    replacement = (replacement_uuid or "").strip() or None
    if reason == "01" and replacement is None:
        raise FiscalDataInvalid(
            "El motivo 01 requiere el UUID del comprobante que sustituye.",
            field="replacement_uuid",
        )
    if replacement is not None:
        if not UUID_PATTERN.match(replacement):
            raise FiscalDataInvalid(
                "El UUID de sustitución no tiene un formato válido.",
                field="replacement_uuid",
            )
        if payment.uuid is not None and replacement.lower() == payment.uuid.lower():
            raise FiscalDataInvalid(
                "El UUID de sustitución debe ser distinto del complemento cancelado.",
                field="replacement_uuid",
            )
    normalized_note = (note or "").strip() or None
    if normalized_note is not None and len(normalized_note) > 300:
        raise FiscalDataInvalid(
            "La nota de cancelación excede 300 caracteres.", field="note"
        )

    outcome = pac_gateway().cancel(
        uuid=payment.uuid,
        reason_code=reason,
        replacement_uuid=replacement,
    )
    if not outcome.accepted:
        raise PacRejected("El PAC rechazó la cancelación del complemento de pago.")

    payment.status = "cancelled"
    payment.cancelled_at = utc_now()
    payment.cancelled_by = actor_id
    payment.cancellation_reason_code = reason
    payment.cancellation_note = normalized_note
    _record_payment_event(
        session,
        payment,
        "payment_cancelled",
        from_status="stamped",
        to_status="cancelled",
        actor_id=actor_id,
        detail={
            "reason_code": reason,
            "replacement_uuid": replacement,
            "note": normalized_note,
            "provider": outcome.provider,
            "simulated": outcome.simulated,
        },
    )
    session.commit()
    session.refresh(payment)
    return _payment_view(session, payment)


def get_payment_complement(session: Session, payment_id: UUID) -> PaymentComplementView:
    return _payment_view(session, _get_payment(session, payment_id))


def payment_complement_xml(session: Session, payment_id: UUID) -> tuple[str, str]:
    payment = _get_payment(session, payment_id)
    if payment.status not in ("stamped", "cancelled"):
        raise InvoiceNotDeliverable(
            "Solo se puede descargar el XML de un complemento de pago timbrado."
        )
    invoice = session.get(Invoice, payment.invoice_id)
    if invoice is None:
        raise InvoiceNotFound("La factura relacionada no existe.")
    content = payment.xml_content
    if not content:
        content = _build_payment_xml(
            payment, invoice, simulated=payment.is_simulated
        )
    return cfdi.payment_complement_xml_filename(payment), content


def payment_complement_pdf(session: Session, payment_id: UUID) -> tuple[str, bytes]:
    """Render the printable payment complement; only a stamped one qualifies."""

    payment = _get_payment(session, payment_id)
    if payment.status not in ("stamped", "cancelled"):
        raise InvoiceNotDeliverable(
            "Solo se puede descargar la representación impresa de un complemento "
            "de pago timbrado."
        )
    invoice = session.get(Invoice, payment.invoice_id)
    if invoice is None:
        raise InvoiceNotFound("La factura relacionada no existe.")
    content = documents.build_payment_complement_pdf(
        payment=payment,
        invoice=invoice,
        issuer=issuer_config(),
    )
    return documents.payment_complement_pdf_filename(payment), content


def get_invoice(session: Session, invoice_id: UUID) -> InvoiceView:
    return _invoice_view(session, _get_invoice(session, invoice_id), full=True)


def invoice_xml(session: Session, invoice_id: UUID) -> tuple[str, str]:
    invoice = _get_invoice(session, invoice_id)
    content = invoice.xml_content
    if not content:
        content = _build_invoice_xml(
            session,
            invoice,
            _invoice_items(session, invoice.id),
            simulated=invoice.is_simulated,
        )
    return cfdi.invoice_xml_filename(invoice), content


def invoice_pdf(session: Session, invoice_id: UUID) -> tuple[str, bytes]:
    """Render the printable CFDI; only stamped or cancelled invoices qualify."""

    invoice = _get_invoice(session, invoice_id)
    if invoice.status not in ("stamped", "cancelled"):
        raise InvoiceNotDeliverable(
            "Solo se puede descargar la representación impresa de una factura timbrada."
        )
    related = (
        session.get(Invoice, invoice.related_invoice_id)
        if invoice.related_invoice_id is not None
        else None
    )
    content = documents.build_invoice_pdf(
        invoice=invoice,
        items=_invoice_items(session, invoice.id),
        issuer=issuer_config(),
        related_invoice=related,
    )
    return documents.invoice_pdf_filename(invoice), content


def _invoice_email_body(
    invoice: Invoice, issuer: cfdi.IssuerConfig, related: Invoice | None = None
) -> str:
    is_credit_note = invoice.origin_type == "credit_note"
    document_label = "nota de crédito" if is_credit_note else "comprobante fiscal"
    lines = [
        f"Hola {invoice.receptor_name},",
        "",
        "Adjuntamos la representación impresa (PDF) y el XML de la "
        f"{document_label} {invoice.series}-{invoice.folio:06d}.",
        "",
    ]
    if is_credit_note and related is not None:
        lines.extend(
            [
                "Factura relacionada: "
                f"{related.series}-{related.folio:06d}"
                f"{f' (UUID {related.uuid})' if related.uuid else ''}",
                "",
            ]
        )
    lines.extend(
        [
            f"Total: {_money_label(invoice.total_cents)} {invoice.currency}",
            f"Forma de pago: {invoice.payment_form}",
            f"UUID SAT: {invoice.uuid or 'Comprobante simulado sin UUID'}",
            f"Emisor: {issuer.legal_name} (RFC {issuer.rfc})",
            "",
            "Conserva el archivo XML como comprobante fiscal. Este correo se generó "
            "automáticamente; si no reconoces la operación, contacta al club.",
        ]
    )
    if invoice.is_simulated:
        lines.extend(
            [
                "",
                "AVISO: este comprobante fue generado en modo simulación y no "
                "tiene validez fiscal.",
            ]
        )
    return "\n".join(lines)


def send_invoice_email(
    session: Session,
    invoice_id: UUID,
    *,
    recipient: str | None = None,
    actor_id: UUID | None = None,
) -> InvoiceDeliveryView:
    """Email the PDF and XML of a stamped invoice and audit the attempt."""

    invoice = _get_invoice(session, invoice_id)
    if invoice.status != "stamped":
        raise InvoiceNotDeliverable(
            "Solo se puede enviar por correo una factura timbrada."
        )
    target = (recipient or invoice.receptor_email or "").strip().lower()
    if not target:
        raise InvoiceRecipientMissing(
            "La factura no tiene correo del receptor; captura un destinatario.",
            field="email",
        )
    if "@" not in target or len(target) > 254:
        raise FiscalDataInvalid(
            "El correo del destinatario no es válido.", field="email"
        )

    items = _invoice_items(session, invoice.id)
    issuer = issuer_config()
    related = (
        session.get(Invoice, invoice.related_invoice_id)
        if invoice.related_invoice_id is not None
        else None
    )
    xml_content = invoice.xml_content or _build_invoice_xml(
        session,
        invoice,
        items,
        simulated=invoice.is_simulated,
    )
    pdf_content = documents.build_invoice_pdf(
        invoice=invoice,
        items=items,
        issuer=issuer,
        related_invoice=related,
    )
    attachments = [
        EmailAttachment(
            content=pdf_content,
            filename=documents.invoice_pdf_filename(invoice),
            maintype="application",
            subtype="pdf",
        ),
        EmailAttachment(
            content=xml_content.encode("utf-8"),
            filename=cfdi.invoice_xml_filename(invoice),
            maintype="application",
            subtype="xml",
        ),
    ]
    audit_detail: dict[str, object] = {
        "recipient": target,
        "attachments": ["pdf", "xml"],
    }
    subject_prefix = "Nota de crédito" if invoice.origin_type == "credit_note" else "Factura"
    try:
        delivery_status = send_email(
            recipient=target,
            subject=(
                f"{subject_prefix} {invoice.series}-{invoice.folio:06d} · "
                f"{issuer.legal_name}"
            ),
            body=_invoice_email_body(invoice, issuer, related),
            attachments=attachments,
            not_configured_message=(
                "El envío de facturas no está configurado (SMTP_HOST)."
            ),
            failure_label="No se pudo enviar la factura",
        )
    except MailNotConfigured as error:
        _record_event(
            session,
            invoice,
            "invoice_email_failed",
            from_status=invoice.status,
            to_status=invoice.status,
            actor_id=actor_id,
            detail={**audit_detail, "reason": "not_configured", "error": str(error)},
        )
        session.commit()
        raise InvoiceEmailNotConfigured(str(error)) from error
    except MailDeliveryFailed as error:
        _record_event(
            session,
            invoice,
            "invoice_email_failed",
            from_status=invoice.status,
            to_status=invoice.status,
            actor_id=actor_id,
            detail={**audit_detail, "reason": "transport", "error": str(error)},
        )
        session.commit()
        raise InvoiceDeliveryFailed(str(error)) from error

    sent_at = utc_now()
    _record_event(
        session,
        invoice,
        "invoice_email_sent",
        from_status=invoice.status,
        to_status=invoice.status,
        actor_id=actor_id,
        detail={
            **audit_detail,
            "delivery_status": delivery_status,
            "simulated": delivery_status == "simulated",
        },
    )
    session.commit()
    return InvoiceDeliveryView(
        invoice_id=invoice.id,
        recipient=target,
        status=delivery_status,
        attachments=("pdf", "xml"),
        sent_at=sent_at,
    )


def list_invoices(
    session: Session,
    *,
    status_filter: str | None = None,
    origin_type: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> InvoicePage:
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    conditions = []
    if status_filter:
        if status_filter not in ("requested", "failed", "stamped", "cancelled"):
            raise InvoiceStateError("El estado de factura no es válido.")
        conditions.append(Invoice.status == status_filter)
    if origin_type:
        if origin_type not in INVOICE_ORIGIN_TYPES:
            raise InvoiceStateError("El tipo de comprobante no es válido.")
        conditions.append(Invoice.origin_type == origin_type)
    term = (search or "").strip().lower()
    if term:
        conditions.append(
            or_(
                func.lower(Invoice.receptor_name).contains(term),
                func.lower(Invoice.receptor_rfc).contains(term),
                func.lower(Invoice.origin_reference).contains(term),
            )
        )

    total = session.exec(
        select(func.count()).select_from(Invoice).where(*conditions)
    ).first() or 0
    rows = session.exec(
        select(Invoice, Member)
        .outerjoin(Member, Invoice.member_id == Member.id)
        .where(*conditions)
        .order_by(Invoice.created_at.desc(), Invoice.folio.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = tuple(
        _invoice_view(session, invoice, member_name=_member_name(member))
        for invoice, member in rows
    )
    return InvoicePage(items=items, total=int(total), page=page, page_size=page_size)


def invoice_summary(session: Session) -> InvoiceSummary:
    counts = {"requested": 0, "failed": 0, "stamped": 0, "cancelled": 0}
    for status_value, count in session.exec(
        select(Invoice.status, func.count()).group_by(Invoice.status)
    ).all():
        if status_value in counts:
            counts[status_value] = int(count)
    stamped_cents = session.exec(
        select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(
            Invoice.status == "stamped",
            Invoice.origin_type != "credit_note",
        )
    ).first() or 0
    credit_note_cents = session.exec(
        select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(
            Invoice.status == "stamped",
            Invoice.origin_type == "credit_note",
        )
    ).first() or 0
    credit_notes = session.exec(
        select(func.count())
        .select_from(Invoice)
        .where(
            Invoice.status == "stamped",
            Invoice.origin_type == "credit_note",
        )
    ).first() or 0
    cancelled_cents = session.exec(
        select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(
            Invoice.status == "cancelled",
            Invoice.origin_type != "credit_note",
        )
    ).first() or 0
    simulated = session.exec(
        select(func.count()).select_from(Invoice).where(Invoice.is_simulated.is_(True))
    ).first() or 0
    stamped_total = int(stamped_cents)
    credit_note_total = int(credit_note_cents)
    return InvoiceSummary(
        total=sum(counts.values()),
        requested=counts["requested"],
        failed=counts["failed"],
        stamped=counts["stamped"],
        cancelled=counts["cancelled"],
        simulated=int(simulated),
        stamped_cents=stamped_total,
        cancelled_cents=int(cancelled_cents),
        credit_notes=int(credit_notes),
        credit_note_cents=credit_note_total,
        net_stamped_cents=stamped_total - credit_note_total,
    )


def _ppd_aging_bucket(age_days: int) -> str:
    if age_days <= 30:
        return "current"
    if age_days <= 60:
        return "days_31_60"
    if age_days <= 90:
        return "days_61_90"
    return "over_90"


def list_ppd_receivables(
    session: Session,
    *,
    search: str | None = None,
    aging_bucket: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    today: date | None = None,
) -> PpdReceivablePage:
    """Open PPD balance aged from the stamp date, with complement control.

    Only a stamped PPD invoice with a positive balance belongs to the cartera.
    A stamped complement reduces that balance; a requested or failed one does
    not, so it is reported separately as pending stamping. The summary covers
    the whole cartera while search, bucket and pagination only filter the list.
    """

    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    if aging_bucket and aging_bucket not in PPD_AGING_BUCKETS:
        raise InvoiceStateError("El tramo de antigüedad no es válido.")
    as_of = today or club_date(datetime.now(timezone.utc))

    invoice_rows = session.exec(
        select(Invoice, Member)
        .outerjoin(Member, Invoice.member_id == Member.id)
        .where(
            Invoice.status == "stamped",
            Invoice.payment_method == "PPD",
        )
        .order_by(Invoice.stamped_at, Invoice.folio)
    ).all()
    invoice_ids = [invoice.id for invoice, _ in invoice_rows]
    payments_by_invoice: dict[UUID, list[InvoicePayment]] = {}
    if invoice_ids:
        for payment in session.exec(
            select(InvoicePayment)
            .where(InvoicePayment.invoice_id.in_(invoice_ids))
            .order_by(InvoicePayment.created_at, InvoicePayment.folio)
        ).all():
            payments_by_invoice.setdefault(payment.invoice_id, []).append(payment)

    rows: list[PpdReceivableRow] = []
    bucket_totals = [0, 0, 0, 0]
    open_invoices = 0
    total_cents = 0
    paid_cents = 0
    outstanding_cents = 0
    oldest_stamped_at: datetime | None = None
    oldest_age_days = -1
    stamped_complements = 0
    stamped_complement_cents = 0
    requested_complements = 0
    requested_complement_cents = 0
    failed_complements = 0
    failed_complement_cents = 0

    for invoice, member in invoice_rows:
        payments = payments_by_invoice.get(invoice.id, [])
        invoice_paid_cents = sum(
            payment.amount_cents
            for payment in payments
            if payment.status == "stamped"
        )
        balance_cents = max(0, invoice.total_cents - invoice_paid_cents)
        if balance_cents <= 0:
            continue
        stamped_at = invoice.stamped_at or invoice.created_at
        age_days = max((as_of - club_date(stamped_at)).days, 0)
        bucket = _ppd_aging_bucket(age_days)
        row_stamped = 0
        row_requested = 0
        row_requested_cents = 0
        row_failed = 0
        row_failed_cents = 0
        last_payment_on: date | None = None
        for payment in payments:
            if payment.status == "stamped":
                row_stamped += 1
                if last_payment_on is None or payment.paid_on > last_payment_on:
                    last_payment_on = payment.paid_on
            elif payment.status == "requested":
                row_requested += 1
                row_requested_cents += payment.amount_cents
            elif payment.status == "failed":
                row_failed += 1
                row_failed_cents += payment.amount_cents
        rows.append(
            PpdReceivableRow(
                invoice_id=invoice.id,
                folio_label=f"{invoice.series}-{invoice.folio:06d}",
                receptor_name=invoice.receptor_name,
                receptor_rfc=invoice.receptor_rfc,
                origin_type=invoice.origin_type,
                origin_reference=invoice.origin_reference,
                member_id=invoice.member_id,
                member_name=_member_name(member),
                currency=invoice.currency,
                total_cents=invoice.total_cents,
                paid_cents=invoice_paid_cents,
                balance_cents=balance_cents,
                stamped_at=stamped_at,
                age_days=age_days,
                aging_bucket=bucket,
                uuid=invoice.uuid,
                is_simulated=invoice.is_simulated,
                stamped_complements=row_stamped,
                requested_complements=row_requested,
                failed_complements=row_failed,
                last_payment_on=last_payment_on,
            )
        )
        open_invoices += 1
        total_cents += invoice.total_cents
        paid_cents += invoice_paid_cents
        outstanding_cents += balance_cents
        bucket_totals[PPD_AGING_BUCKETS.index(bucket)] += balance_cents
        if age_days > oldest_age_days:
            oldest_age_days = age_days
            oldest_stamped_at = stamped_at
        stamped_complements += row_stamped
        stamped_complement_cents += invoice_paid_cents
        requested_complements += row_requested
        requested_complement_cents += row_requested_cents
        failed_complements += row_failed
        failed_complement_cents += row_failed_cents

    term = (search or "").strip().lower()
    if term:
        rows = [
            row
            for row in rows
            if term in row.receptor_name.lower()
            or term in row.receptor_rfc.lower()
            or term in row.origin_reference.lower()
            or term in row.folio_label.lower()
        ]
    if aging_bucket:
        rows = [row for row in rows if row.aging_bucket == aging_bucket]

    start = (page - 1) * page_size
    summary = PpdReceivableSummary(
        as_of=as_of,
        invoices=open_invoices,
        total_cents=total_cents,
        paid_cents=paid_cents,
        outstanding_cents=outstanding_cents,
        aging=PpdAging(*bucket_totals),
        oldest_stamped_at=oldest_stamped_at,
        stamped_complements=stamped_complements,
        stamped_complement_cents=stamped_complement_cents,
        requested_complements=requested_complements,
        requested_complement_cents=requested_complement_cents,
        failed_complements=failed_complements,
        failed_complement_cents=failed_complement_cents,
    )
    return PpdReceivablePage(
        items=tuple(rows[start : start + page_size]),
        total=len(rows),
        page=page,
        page_size=page_size,
        summary=summary,
    )


def list_origin_options(
    session: Session,
    *,
    origin_type: str,
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> OriginPage:
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    term = (search or "").strip().lower()

    if origin_type == "sale":
        active_ids = select(Invoice.origin_id).where(
            Invoice.origin_type == "sale",
            Invoice.status != "cancelled",
        )
        returned_ids = select(SaleReturn.sale_id)
        globally_invoiced_ids = (
            select(GlobalInvoiceSale.sale_id)
            .join(Invoice, GlobalInvoiceSale.invoice_id == Invoice.id)
            .where(Invoice.status != "cancelled")
        )
        conditions = [
            Sale.status == "completed",
            Sale.payment_method != "account",
            Sale.total_cents > 0,
            ~Sale.id.in_(active_ids),
            ~Sale.id.in_(returned_ids),
            ~Sale.id.in_(globally_invoiced_ids),
        ]
        if term:
            conditions.append(
                or_(
                    func.lower(Sale.folio).contains(term),
                    func.lower(Member.first_name).contains(term),
                    func.lower(Member.last_name).contains(term),
                    func.lower(func.coalesce(Sale.note, "")).contains(term),
                )
            )
        total = session.exec(
            select(func.count())
            .select_from(Sale)
            .outerjoin(Member, Sale.member_id == Member.id)
            .where(*conditions)
        ).first() or 0
        rows = session.exec(
            select(Sale, Member)
            .outerjoin(Member, Sale.member_id == Member.id)
            .where(*conditions)
            .order_by(Sale.sold_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = tuple(
            OriginOption(
                origin_type="sale",
                origin_id=sale.id,
                reference=sale.folio,
                member_id=sale.member_id,
                member_name=_member_name(member),
                occurred_at=sale.sold_at,
                total_cents=sale.total_cents,
                description=(sale.note or "Venta en mostrador")[:300],
                payment_method=sale.payment_method,
            )
            for sale, member in rows
        )
        return OriginPage(items=items, total=int(total), page=page, page_size=page_size)

    if origin_type == "membership_payment":
        active_ids = select(Invoice.origin_id).where(
            Invoice.origin_type == "membership_payment",
            Invoice.status != "cancelled",
        )
        conditions = [
            Payment.amount_cents > 0,
            ~Payment.id.in_(active_ids),
        ]
        if term:
            conditions.append(
                or_(
                    func.lower(Member.first_name).contains(term),
                    func.lower(Member.last_name).contains(term),
                    func.lower(Plan.name).contains(term),
                )
            )
        base = (
            select(func.count())
            .select_from(Payment)
            .join(Member, Payment.member_id == Member.id)
            .join(Membership, Payment.membership_id == Membership.id)
            .join(Plan, Membership.plan_id == Plan.id)
        )
        total = session.exec(base.where(*conditions)).first() or 0
        rows = session.exec(
            select(Payment, Member, Plan)
            .join(Member, Payment.member_id == Member.id)
            .join(Membership, Payment.membership_id == Membership.id)
            .join(Plan, Membership.plan_id == Plan.id)
            .where(*conditions)
            .order_by(Payment.paid_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = tuple(
            OriginOption(
                origin_type="membership_payment",
                origin_id=payment.id,
                reference=f"PAGO-{str(payment.id)[:8].upper()}",
                member_id=payment.member_id,
                member_name=_member_name(member),
                occurred_at=payment.paid_at,
                total_cents=payment.amount_cents,
                description=f"Membresía {plan.name}"[:300],
                payment_method=payment.method,
            )
            for payment, member, plan in rows
        )
        return OriginPage(items=items, total=int(total), page=page, page_size=page_size)

    raise OriginNotFound("El tipo de operación no es facturable.")


def get_fiscal_profile(session: Session, member_id: UUID) -> FiscalProfileView | None:
    if session.get(Member, member_id) is None:
        raise BillingMemberNotFound("El socio no existe.")
    profile = session.exec(
        select(MemberFiscalProfile).where(MemberFiscalProfile.member_id == member_id)
    ).first()
    return _fiscal_profile_view(profile) if profile is not None else None


def save_fiscal_profile(
    session: Session,
    *,
    member_id: UUID,
    rfc: str,
    legal_name: str,
    tax_regime: str,
    postal_code: str,
    cfdi_use: str,
    email: str | None = None,
) -> FiscalProfileView:
    if session.get(Member, member_id) is None:
        raise BillingMemberNotFound("El socio no existe.")
    fiscal = cfdi.normalize_fiscal_data(
        rfc=rfc,
        legal_name=legal_name,
        tax_regime=tax_regime,
        postal_code=postal_code,
        cfdi_use=cfdi_use,
        email=email,
    )
    profile = session.exec(
        select(MemberFiscalProfile).where(MemberFiscalProfile.member_id == member_id)
    ).first()
    if profile is None:
        profile = MemberFiscalProfile(
            member_id=member_id,
            rfc=fiscal.rfc,
            legal_name=fiscal.legal_name,
            tax_regime=fiscal.tax_regime,
            postal_code=fiscal.postal_code,
            cfdi_use=fiscal.cfdi_use,
            email=fiscal.email,
        )
        session.add(profile)
    else:
        profile.rfc = fiscal.rfc
        profile.legal_name = fiscal.legal_name
        profile.tax_regime = fiscal.tax_regime
        profile.postal_code = fiscal.postal_code
        profile.cfdi_use = fiscal.cfdi_use
        profile.email = fiscal.email
        profile.updated_at = utc_now()
        session.add(profile)
    session.commit()
    session.refresh(profile)
    return _fiscal_profile_view(profile)


def _fiscal_profile_view(profile: MemberFiscalProfile) -> FiscalProfileView:
    return FiscalProfileView(
        member_id=profile.member_id,
        rfc=profile.rfc,
        legal_name=profile.legal_name,
        tax_regime=profile.tax_regime,
        postal_code=profile.postal_code,
        cfdi_use=profile.cfdi_use,
        email=profile.email,
        updated_at=profile.updated_at,
    )
