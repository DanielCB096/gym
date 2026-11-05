from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlmodel import Session

from app.mailer import (
    EmailAttachment,
    MailDeliveryFailed,
    MailNotConfigured,
    send_email,
)
from app.modules.inventory.service import InventoryError, SaleItemView
from app.modules.memberships.models import Member


class TicketError(InventoryError):
    pass


class TicketRecipientMissing(TicketError):
    pass


class TicketEmailNotConfigured(TicketError):
    pass


class TicketDeliveryFailed(TicketError):
    pass


def build_sale_ticket_pdf(sale: SaleItemView) -> bytes:
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    left = 24 * mm
    right = width - 24 * mm
    top = height - 28 * mm

    page.setTitle(f"Ticket {sale.folio}")
    page.setFont("Helvetica-Bold", 18)
    page.drawCentredString(width / 2, top, "GIMNASIO")
    page.setFont("Helvetica-Bold", 12)
    page.drawCentredString(width / 2, top - 8 * mm, f"Ticket {sale.folio}")
    page.setFont("Helvetica", 9)
    page.drawCentredString(width / 2, top - 14 * mm, sale.sold_at.strftime("%d/%m/%Y %H:%M"))

    y = top - 24 * mm
    if sale.member_name:
        page.drawString(left, y, f"Socio: {sale.member_name}")
        y -= 6 * mm
    if sale.cashier_email:
        page.drawString(left, y, f"Atendio: {sale.cashier_email}")
        y -= 8 * mm

    page.setFont("Helvetica-Bold", 9)
    page.drawString(left, y, "Concepto")
    page.drawRightString(right, y, "Importe")
    y -= 5 * mm
    page.line(left, y, right, y)
    y -= 6 * mm
    page.setFont("Helvetica", 9)
    for line in sale.lines:
        if y < 35 * mm:
            page.showPage()
            y = top
            page.setFont("Helvetica-Bold", 9)
            page.drawString(left, y, "Concepto")
            page.drawRightString(right, y, "Importe")
            y -= 5 * mm
            page.line(left, y, right, y)
            y -= 6 * mm
            page.setFont("Helvetica", 9)
        page.drawString(left, y, f"{line.quantity} x {line.product_name}")
        page.drawRightString(right, y, _money(line.line_total_cents))
        y -= 6 * mm

    if y < 55 * mm:
        page.showPage()
        y = top
    y -= 2 * mm
    page.line(left, y, right, y)
    y -= 7 * mm
    page.setFont("Helvetica", 10)
    page.drawString(left, y, "Subtotal")
    page.drawRightString(right, y, _money(sale.subtotal_cents))
    y -= 6 * mm
    if sale.discount_cents:
        page.drawString(left, y, "Descuento")
        page.drawRightString(right, y, _money(sale.discount_cents))
        y -= 6 * mm
    if sale.tax_cents:
        page.drawString(left, y, "IVA")
        page.drawRightString(right, y, _money(sale.tax_cents))
        y -= 6 * mm
    page.setFont("Helvetica-Bold", 12)
    page.drawString(left, y, "TOTAL")
    page.drawRightString(right, y, _money(sale.total_cents))
    y -= 8 * mm
    page.setFont("Helvetica", 9)
    page.drawString(left, y, f"Forma de pago: {_payment_method(sale.payment_method)}")
    y -= 7 * mm
    page.setFont("Helvetica-Oblique", 9)
    page.drawCentredString(width / 2, 22 * mm, "Gracias por su compra")
    page.showPage()
    page.save()
    return output.getvalue()


def send_sale_ticket_email(
    session: Session,
    sale: SaleItemView,
    recipient: str | None = None,
) -> str:
    destination = (recipient or "").strip()
    if not destination and sale.member_id is not None:
        member = session.get(Member, sale.member_id)
        destination = (member.email if member is not None else "") or ""
    destination = destination.strip()
    if not destination:
        raise TicketRecipientMissing(
            "El socio no tiene correo registrado y no se indico un destinatario."
        )

    pdf = build_sale_ticket_pdf(sale)
    try:
        return send_email(
            recipient=destination,
            subject=f"Ticket {sale.folio}",
            body="Adjuntamos el ticket de su compra. Este documento no sustituye una factura CFDI.",
            attachments=[
                EmailAttachment(
                    content=pdf,
                    filename=f"{sale.folio}.pdf",
                    maintype="application",
                    subtype="pdf",
                )
            ],
            not_configured_message="El envio de tickets por correo no esta configurado (SMTP_HOST).",
            failure_label="No se pudo enviar el ticket",
        )
    except MailNotConfigured as error:
        raise TicketEmailNotConfigured(str(error)) from error
    except MailDeliveryFailed as error:
        raise TicketDeliveryFailed(str(error)) from error


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    pesos, remainder = divmod(absolute, 100)
    return f"{sign}${pesos:,}.{remainder:02d}"


def _payment_method(method: str) -> str:
    return {
        "cash": "Efectivo",
        "card": "Tarjeta",
        "transfer": "Transferencia",
        "account": "Cuenta del socio",
    }.get(method, method)
