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

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import json
import os
import re
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.billing import cfdi
from app.modules.billing.errors import (
    BillingMemberNotFound,
    FiscalDataInvalid,
    InvoiceIdempotencyConflict,
    InvoiceNotFound,
    InvoiceNumberingError,
    InvoiceStateError,
    OriginAlreadyInvoiced,
    OriginNotFound,
    OriginNotInvoiceable,
    PacRejected,
)
from app.modules.billing.models import (
    Invoice,
    InvoiceEvent,
    InvoiceItem,
    MemberFiscalProfile,
    utc_now,
)
from app.modules.billing.pac import pac_gateway
from app.modules.inventory.models import Sale, SaleItem, SaleReturn
from app.modules.memberships.models import Member, Membership, Payment, Plan
from app.timezone import club_date

CANCELLATION_REASONS = frozenset({"01", "02", "03", "04"})
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
DEFAULT_SERIES = "A"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


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
class InvoiceView:
    id: UUID
    series: str
    folio: int
    folio_label: str
    status: str
    origin_type: str
    origin_id: UUID
    origin_reference: str
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
    items: tuple[InvoiceItemView, ...] = field(default=())
    events: tuple[InvoiceEventView, ...] = field(default=())


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

    return InvoiceView(
        id=invoice.id,
        series=invoice.series,
        folio=invoice.folio,
        folio_label=f"{invoice.series}-{invoice.folio:06d}",
        status=invoice.status,
        origin_type=invoice.origin_type,
        origin_id=invoice.origin_id,
        origin_reference=invoice.origin_reference,
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
        items=items,
        events=events,
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
    actor_id: UUID | None = None,
) -> tuple[InvoiceView, bool]:
    """Request an invoice for one sale or membership payment.

    Returns ``(invoice, created)``: ``created`` is ``False`` when the same
    idempotency key replays an existing request, which lets the caller answer
    without duplicating folios, XML or events.
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
        payment_method="PUE",
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

    items = _invoice_items(session, invoice.id)
    xml = invoice.xml_content or cfdi.build_cfdi_xml(
        invoice=invoice,
        items=items,
        issuer=issuer_config(),
    )
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
    invoice = _get_invoice(session, invoice_id)
    if invoice.status != "stamped":
        raise InvoiceStateError("Solo se puede cancelar una factura timbrada.")
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


def get_invoice(session: Session, invoice_id: UUID) -> InvoiceView:
    return _invoice_view(session, _get_invoice(session, invoice_id), full=True)


def invoice_xml(session: Session, invoice_id: UUID) -> tuple[str, str]:
    invoice = _get_invoice(session, invoice_id)
    content = invoice.xml_content
    if not content:
        content = cfdi.build_cfdi_xml(
            invoice=invoice,
            items=_invoice_items(session, invoice.id),
            issuer=issuer_config(),
            simulated=invoice.is_simulated,
        )
    return cfdi.invoice_xml_filename(invoice), content


def list_invoices(
    session: Session,
    *,
    status_filter: str | None = None,
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
            Invoice.status == "stamped"
        )
    ).first() or 0
    cancelled_cents = session.exec(
        select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(
            Invoice.status == "cancelled"
        )
    ).first() or 0
    simulated = session.exec(
        select(func.count()).select_from(Invoice).where(Invoice.is_simulated.is_(True))
    ).first() or 0
    return InvoiceSummary(
        total=sum(counts.values()),
        requested=counts["requested"],
        failed=counts["failed"],
        stamped=counts["stamped"],
        cancelled=counts["cancelled"],
        simulated=int(simulated),
        stamped_cents=int(stamped_cents),
        cancelled_cents=int(cancelled_cents),
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
        conditions = [
            Sale.status == "completed",
            Sale.payment_method != "account",
            Sale.total_cents > 0,
            ~Sale.id.in_(active_ids),
            ~Sale.id.in_(returned_ids),
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
