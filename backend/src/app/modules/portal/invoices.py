"""Member self-service invoices: listing, signed downloads and requests.

The fiscal documents belong to the billing module. This layer only exposes the
invoices issued to the authenticated member —income invoices and credit notes
alike— without operator, event or XML details used by the staff. A member can
also request an invoice for their own sale or membership payment: the origin is
checked against the member before the billing service sees it.

The PDF and XML are opened by the system browser, which cannot send the Bearer
token. Instead of putting the 30-day member session in a URL, the listing
returns short-lived links signed with ``SECRET_KEY`` and bound to one document.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
from uuid import UUID

from sqlmodel import Session, func, select

from app.modules.billing.errors import OriginNotFound
from app.modules.billing.models import GlobalInvoiceSale, Invoice
from app.modules.billing.service import (
    FiscalProfileView,
    InvoiceView,
    create_invoice,
    get_fiscal_profile,
    invoice_pdf,
    invoice_xml,
    save_fiscal_profile,
)
from app.modules.inventory.models import Sale, SaleReturn
from app.modules.memberships.models import Member, Membership, Payment, Plan
from app.modules.portal.service import MemberPortalError, signing_secret

DOWNLOAD_LINK_LIFETIME = timedelta(minutes=10)
DOWNLOAD_KINDS = ("pdf", "xml")
# Only a stamped comprobante (or a cancelled one already issued) has a
# representation impresa or an XML worth delivering: a request without stamp has
# no fiscal validity and the PDF would not be reproducible by the PAC.
DELIVERABLE_STATUSES = ("stamped", "cancelled")
BILLABLE_ORIGIN_TYPES = ("sale", "membership_payment")


class InvalidDownloadLink(MemberPortalError):
    pass


@dataclass(frozen=True)
class MemberInvoiceItem:
    id: UUID
    series: str
    folio: int
    folio_label: str
    status: str
    origin_type: str
    origin_reference: str
    currency: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    payment_form: str
    payment_method: str
    uuid: str | None
    is_simulated: bool
    issued_at: datetime | None
    stamped_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    pdf_path: str | None
    xml_path: str | None


@dataclass(frozen=True)
class MemberInvoicePage:
    items: list[MemberInvoiceItem]
    total: int
    page: int
    page_size: int
    pages: int


@dataclass(frozen=True)
class BillableOriginItem:
    origin_type: str
    origin_id: UUID
    reference: str
    occurred_at: datetime
    total_cents: int
    description: str
    payment_method: str


@dataclass(frozen=True)
class BillableOriginPage:
    items: list[BillableOriginItem]
    total: int
    page: int
    page_size: int
    pages: int


def list_member_invoices(
    session: Session,
    member_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    now: datetime | None = None,
) -> MemberInvoicePage:
    _require_member(session, member_id)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    expires_at_epoch = int(
        ((now or datetime.now(timezone.utc)) + DOWNLOAD_LINK_LIFETIME).timestamp()
    )

    condition = Invoice.member_id == member_id
    total = int(
        session.exec(select(func.count(Invoice.id)).where(condition)).one() or 0
    )
    rows = session.exec(
        select(Invoice)
        .where(condition)
        .order_by(Invoice.created_at.desc(), Invoice.folio.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return MemberInvoicePage(
        items=[_member_invoice(invoice, expires_at_epoch) for invoice in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


def list_billable_origins(
    session: Session,
    member_id: UUID,
    *,
    origin_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> BillableOriginPage:
    """The member's own sales and payments that still accept a CFDI.

    Origins already covered by a live invoice (individual or global) and
    returned sales are excluded, so the app only offers what the billing
    service would accept.
    """

    _require_member(session, member_id)
    if origin_type is not None and origin_type not in BILLABLE_ORIGIN_TYPES:
        raise MemberPortalError("El tipo de operación no es facturable.")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)

    items: list[BillableOriginItem] = []
    if origin_type in (None, "sale"):
        items.extend(_billable_sales(session, member_id))
    if origin_type in (None, "membership_payment"):
        items.extend(_billable_payments(session, member_id))
    items.sort(key=lambda item: _timestamp(item.occurred_at), reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    return BillableOriginPage(
        items=items[start : start + page_size],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


def request_member_invoice(
    session: Session,
    member_id: UUID,
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
    now: datetime | None = None,
) -> tuple[MemberInvoiceItem, bool]:
    """Request an invoice for one of the member's own operations.

    Ownership is checked here, before the billing service resolves the origin,
    so a member can never invoice somebody else's sale or payment. The fiscal
    data is saved to the profile even when the request is later rejected
    (already invoiced, invalid amount), so the next attempt starts from it.
    """

    member = _require_member(session, member_id)
    if origin_type not in BILLABLE_ORIGIN_TYPES:
        raise OriginNotFound("El tipo de operación no es facturable.")
    _require_owned_origin(session, member_id, origin_type, origin_id)
    save_fiscal_profile(
        session,
        member_id=member.id,
        rfc=rfc,
        legal_name=legal_name,
        tax_regime=tax_regime,
        postal_code=postal_code,
        cfdi_use=cfdi_use,
        email=email,
    )
    view, created = create_invoice(
        session,
        origin_type=origin_type,
        origin_id=origin_id,
        rfc=rfc,
        legal_name=legal_name,
        tax_regime=tax_regime,
        postal_code=postal_code,
        cfdi_use=cfdi_use,
        idempotency_key=idempotency_key,
        email=email,
        payment_form=payment_form,
        payment_method=payment_method,
        actor_id=None,
        channel="member_app",
    )
    # Defensive: a replayed idempotency key must still resolve to this member.
    if view.member_id != member_id:
        raise OriginNotFound("La operación no pertenece al socio.")
    expires_at_epoch = int(
        ((now or datetime.now(timezone.utc)) + DOWNLOAD_LINK_LIFETIME).timestamp()
    )
    return _member_invoice(view, expires_at_epoch), created


def member_fiscal_profile(
    session: Session, member_id: UUID
) -> FiscalProfileView | None:
    _require_member(session, member_id)
    return get_fiscal_profile(session, member_id)


def verify_download_link(
    invoice_id: UUID,
    kind: str,
    expires_at_epoch: int,
    signature: str,
    *,
    now: datetime | None = None,
) -> None:
    occurred_at = now or datetime.now(timezone.utc)
    if kind not in DOWNLOAD_KINDS or expires_at_epoch < int(occurred_at.timestamp()):
        raise InvalidDownloadLink("El enlace de descarga no es válido o expiró")
    expected = _sign(invoice_id, kind, expires_at_epoch)
    if not hmac.compare_digest(expected, signature):
        raise InvalidDownloadLink("El enlace de descarga no es válido o expiró")


def download_member_invoice(
    session: Session, invoice_id: UUID, kind: str
) -> tuple[str, bytes | str]:
    if kind == "pdf":
        return invoice_pdf(session, invoice_id)
    return invoice_xml(session, invoice_id)


def _billable_sales(session: Session, member_id: UUID) -> list[BillableOriginItem]:
    invoiceable = select(Invoice.origin_id).where(
        Invoice.origin_type == "sale", Invoice.status != "cancelled"
    )
    returned = select(SaleReturn.sale_id)
    globally_invoiced = (
        select(GlobalInvoiceSale.sale_id)
        .join(Invoice, GlobalInvoiceSale.invoice_id == Invoice.id)
        .where(Invoice.status != "cancelled")
    )
    rows = session.exec(
        select(Sale)
        .where(
            Sale.member_id == member_id,
            Sale.status == "completed",
            Sale.payment_method != "account",
            Sale.total_cents > 0,
            ~Sale.id.in_(invoiceable),
            ~Sale.id.in_(returned),
            ~Sale.id.in_(globally_invoiced),
        )
        .order_by(Sale.sold_at.desc())
    ).all()
    return [
        BillableOriginItem(
            origin_type="sale",
            origin_id=sale.id,
            reference=sale.folio,
            occurred_at=sale.sold_at,
            total_cents=sale.total_cents,
            description=(sale.note or "Venta en mostrador")[:300],
            payment_method=sale.payment_method,
        )
        for sale in rows
    ]


def _billable_payments(session: Session, member_id: UUID) -> list[BillableOriginItem]:
    invoiceable = select(Invoice.origin_id).where(
        Invoice.origin_type == "membership_payment", Invoice.status != "cancelled"
    )
    rows = session.exec(
        select(Payment, Plan)
        .outerjoin(Membership, Payment.membership_id == Membership.id)
        .outerjoin(Plan, Membership.plan_id == Plan.id)
        .where(
            Payment.member_id == member_id,
            Payment.amount_cents > 0,
            ~Payment.id.in_(invoiceable),
        )
        .order_by(Payment.paid_at.desc())
    ).all()
    return [
        BillableOriginItem(
            origin_type="membership_payment",
            origin_id=payment.id,
            reference=f"PAGO-{str(payment.id)[:8].upper()}",
            occurred_at=payment.paid_at,
            total_cents=payment.amount_cents,
            description=f"Membresía {plan.name}"[:300] if plan is not None else "Membresía",
            payment_method=payment.method,
        )
        for payment, plan in rows
    ]


def _require_owned_origin(
    session: Session, member_id: UUID, origin_type: str, origin_id: UUID
) -> None:
    if origin_type == "sale":
        sale = session.get(Sale, origin_id)
        if sale is None or sale.member_id != member_id:
            raise OriginNotFound("La operación no existe o no pertenece al socio.")
        return
    if origin_type == "membership_payment":
        payment = session.get(Payment, origin_id)
        if payment is None or payment.member_id != member_id:
            raise OriginNotFound("La operación no existe o no pertenece al socio.")
        return
    raise OriginNotFound("El tipo de operación no es facturable.")


def _timestamp(value: datetime) -> float:
    # SQLite returns naive datetimes even for timezone-aware columns.
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _member_invoice(
    invoice: Invoice | InvoiceView, expires_at_epoch: int
) -> MemberInvoiceItem:
    deliverable = invoice.status in DELIVERABLE_STATUSES
    return MemberInvoiceItem(
        id=invoice.id,
        series=invoice.series,
        folio=invoice.folio,
        folio_label=f"{invoice.series}-{invoice.folio:06d}",
        status=invoice.status,
        origin_type=invoice.origin_type,
        origin_reference=invoice.origin_reference,
        currency=invoice.currency,
        subtotal_cents=invoice.subtotal_cents,
        tax_cents=invoice.tax_cents,
        total_cents=invoice.total_cents,
        payment_form=invoice.payment_form,
        payment_method=invoice.payment_method,
        uuid=invoice.uuid,
        is_simulated=invoice.is_simulated,
        issued_at=invoice.issued_at,
        stamped_at=invoice.stamped_at,
        cancelled_at=invoice.cancelled_at,
        created_at=invoice.created_at,
        pdf_path=(
            _signed_path(invoice.id, "pdf", expires_at_epoch)
            if deliverable
            else None
        ),
        xml_path=(
            _signed_path(invoice.id, "xml", expires_at_epoch)
            if deliverable
            else None
        ),
    )


def _signed_path(invoice_id: UUID, kind: str, expires_at_epoch: int) -> str:
    signature = _sign(invoice_id, kind, expires_at_epoch)
    return (
        f"/member/invoices/{invoice_id}/{kind}"
        f"?exp={expires_at_epoch}&sig={signature}"
    )


def _sign(invoice_id: UUID, kind: str, expires_at_epoch: int) -> str:
    message = f"{invoice_id}:{kind}:{expires_at_epoch}".encode("utf-8")
    return hmac.new(signing_secret(), message, sha256).hexdigest()


def _require_member(session: Session, member_id: UUID) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise MemberPortalError("Socio no encontrado")
    return member
