"""Member self-service invoices (read only) and signed download links.

The fiscal documents belong to the billing module. This layer only exposes the
invoices issued to the authenticated member —income invoices and credit notes
alike— without operator, event or XML details used by the staff.

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

from app.modules.billing.models import Invoice
from app.modules.billing.service import invoice_pdf, invoice_xml
from app.modules.memberships.models import Member
from app.modules.portal.service import MemberPortalError, signing_secret

DOWNLOAD_LINK_LIFETIME = timedelta(minutes=10)
DOWNLOAD_KINDS = ("pdf", "xml")
# Only a stamped comprobante (or a cancelled one already issued) has a
# representation impresa or an XML worth delivering: a request without stamp has
# no fiscal validity and the PDF would not be reproducible by the PAC.
DELIVERABLE_STATUSES = ("stamped", "cancelled")


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


def _member_invoice(invoice: Invoice, expires_at_epoch: int) -> MemberInvoiceItem:
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
