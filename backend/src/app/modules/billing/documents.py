"""Printable representation (representación impresa) of a CFDI invoice.

This PDF is a courtesy copy for the member and the club's files: the XML is the
fiscal document. It repeats the receptor snapshot, the SAT references and the
totals already stored in the invoice, and marks simulated or cancelled
comprobantes so they are never mistaken for a valid stamp.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import io
import os
from typing import Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.billing.cfdi import IssuerConfig
from app.modules.billing.models import Invoice, InvoiceItem
from app.timezone import to_club_timezone

STATUS_LABELS = {
    "requested": "Solicitada",
    "failed": "Timbrado fallido",
    "stamped": "Timbrada",
    "cancelled": "Cancelada",
}
ORIGIN_LABELS = {
    "sale": "Venta",
    "membership_payment": "Pago de membresía",
    "global": "Factura global",
}
PAYMENT_FORM_LABELS = {
    "01": "Efectivo",
    "02": "Cheque nominativo",
    "03": "Transferencia electrónica",
    "04": "Tarjeta de crédito",
    "05": "Monedero electrónico",
    "06": "Dinero electrónico",
    "08": "Vales de despensa",
    "12": "Dación en pago",
    "13": "Pago por subrogación",
    "14": "Pago por consignación",
    "15": "Condonación",
    "17": "Compensación",
    "23": "Novación",
    "24": "Confusión",
    "25": "Remisión de deuda",
    "26": "Prescripción o caducidad",
    "27": "A satisfacción del acreedor",
    "28": "Tarjeta de débito",
    "29": "Tarjeta de servicios",
    "30": "Aplicación de anticipos",
    "31": "Intermediario pagos",
    "99": "Por definir",
}
CFDI_USE_LABELS = {
    "G01": "Adquisición de mercancías",
    "G02": "Devoluciones, descuentos o bonificaciones",
    "G03": "Gastos en general",
    "D01": "Honorarios médicos y gastos hospitalarios",
    "D02": "Gastos médicos por incapacidad o discapacidad",
    "D03": "Gastos funerales",
    "D04": "Donativos",
    "D05": "Intereses reales pagados por créditos hipotecarios",
    "D06": "Aportaciones voluntarias al SAR",
    "D07": "Primas por seguros de gastos médicos",
    "D08": "Gastos de transportación escolar obligatoria",
    "D09": "Depósitos en cuentas para el ahorro",
    "D10": "Pagos por servicios educativos",
    "I01": "Construcciones",
    "I02": "Mobiliario y equipo de oficina",
    "I03": "Equipo de transporte",
    "I04": "Equipo de cómputo y accesorios",
    "I05": "Dados, troqueles, moldes, matrices y herramental",
    "I06": "Comunicaciones telefónicas",
    "I07": "Comunicaciones satelitales",
    "I08": "Otra maquinaria y equipo",
    "S01": "Sin efectos fiscales",
    "CP01": "Pagos",
    "CN01": "Nómina",
}
CANCELLATION_REASON_LABELS = {
    "01": "Comprobante emitido con errores con relación",
    "02": "Comprobante emitido con errores sin relación",
    "03": "No se llevó a cabo la operación",
    "04": "Operación nominativa relacionada en la factura global",
}
DEFAULT_GYM_NAME = "Centro Fit"
INK = colors.HexColor("#16322d")
MUTED = colors.HexColor("#6b7a70")
ACCENT = colors.HexColor("#23509a")
LINE = colors.HexColor("#dce7e1")
SOFT = colors.HexColor("#eef4f1")


def _money(cents: int) -> str:
    value = (Decimal(cents) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"${value:,.2f}"


def _unit_price(subtotal_cents: int, quantity: int) -> str:
    value = (Decimal(subtotal_cents) / Decimal(100) / Decimal(quantity)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return f"${value:,.4f}"


def _local_datetime(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    return to_club_timezone(moment).strftime("%d/%m/%Y %H:%M")


def invoice_pdf_filename(invoice: Invoice) -> str:
    suffix = "-simulada" if invoice.is_simulated else ""
    return f"CFDI-{invoice.series}-{invoice.folio:06d}{suffix}.pdf"


def build_invoice_pdf(
    *,
    invoice: Invoice,
    items: Sequence[InvoiceItem],
    issuer: IssuerConfig,
) -> bytes:
    """Render the stamped invoice as a letter-size PDF."""

    buffer = io.BytesIO()
    gym_name = (
        os.getenv("GYM_NAME", "").strip()
        or issuer.legal_name
        or DEFAULT_GYM_NAME
    )
    folio_label = f"{invoice.series}-{invoice.folio:06d}"
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=19 * mm,
        title=f"CFDI {folio_label} - {invoice.receptor_name}",
        author=gym_name,
        subject="Representación impresa de CFDI",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        textColor=INK,
        alignment=0,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "InvoiceSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=MUTED,
    )
    section_style = ParagraphStyle(
        "InvoiceSection",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=ACCENT,
        spaceBefore=8,
        spaceAfter=4,
    )
    small_style = ParagraphStyle(
        "InvoiceSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#26332c"),
    )
    small_right_style = ParagraphStyle(
        "InvoiceSmallRight",
        parent=small_style,
        alignment=2,
    )
    label_style = ParagraphStyle(
        "InvoiceLabel",
        parent=small_style,
        textColor=MUTED,
        fontSize=6.8,
        leading=8.5,
    )
    value_style = ParagraphStyle(
        "InvoiceValue",
        parent=small_style,
        fontSize=8,
        leading=10,
    )
    party_style = ParagraphStyle(
        "InvoiceParty",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=INK,
        spaceAfter=3,
    )
    note_style = ParagraphStyle(
        "InvoiceNote",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#8a3b12"),
    )
    final_note_style = ParagraphStyle(
        "InvoiceFinalNote",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9.5,
        textColor=MUTED,
        alignment=1,
    )

    status_label = STATUS_LABELS.get(invoice.status, invoice.status)
    payment_form = invoice.payment_form
    payment_form_label = PAYMENT_FORM_LABELS.get(payment_form, "Forma de pago")
    cancellation_reason = CANCELLATION_REASON_LABELS.get(
        invoice.cancellation_reason_code or "", invoice.cancellation_reason_code or "—"
    )

    def parties_table() -> Table:
        receptor_rows = [
            ("RFC", invoice.receptor_rfc),
            ("Razón social", invoice.receptor_name),
            ("Régimen fiscal", invoice.receptor_tax_regime),
            ("Código postal", invoice.receptor_postal_code),
            (
                "Uso del CFDI",
                f"{invoice.receptor_cfdi_use} · "
                f"{CFDI_USE_LABELS.get(invoice.receptor_cfdi_use, 'Uso registrado')}",
            ),
            ("Correo", invoice.receptor_email or "Sin correo"),
        ]
        issuer_rows = [
            ("RFC", issuer.rfc),
            ("Razón social", issuer.legal_name),
            ("Régimen fiscal", issuer.tax_regime),
            ("Código postal", issuer.postal_code),
            ("", ""),
            ("", ""),
        ]
        data: list[list[object]] = [
            [
                Paragraph("Emisor", party_style),
                "",
                Paragraph("Receptor", party_style),
                "",
            ]
        ]
        for (issuer_label, issuer_value), (receptor_label, receptor_value) in zip(
            issuer_rows, receptor_rows
        ):
            data.append(
                [
                    Paragraph(issuer_label, label_style),
                    Paragraph(escape(issuer_value), value_style),
                    Paragraph(receptor_label, label_style),
                    Paragraph(escape(receptor_value), value_style),
                ]
            )
        table = Table(data, colWidths=[22 * mm, 68 * mm, 22 * mm, 68 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (1, 0)),
                    ("SPAN", (2, 0), (3, 0)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return table

    def status_table() -> Table:
        data = [
            [
                Paragraph("FOLIO", label_style),
                Paragraph("ESTADO", label_style),
                Paragraph("FECHA DE EMISIÓN", label_style),
                Paragraph("TOTAL", label_style),
            ],
            [
                Paragraph(f"<b>{folio_label}</b>", value_style),
                Paragraph(f"<b>{escape(status_label)}</b>", value_style),
                Paragraph(_local_datetime(invoice.issued_at or invoice.created_at), value_style),
                Paragraph(f"<b>{_money(invoice.total_cents)}</b>", value_style),
            ],
        ]
        table = Table(data, colWidths=[36 * mm, 42 * mm, 54 * mm, 48 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                    ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def facts_table() -> Table:
        rows = [
            ("FORMA DE PAGO", f"{payment_form} · {payment_form_label}", "MÉTODO", "PUE · Pago en una sola exhibición"),
            ("MONEDA", invoice.currency, "LUGAR DE EXPEDICIÓN", issuer.postal_code),
            ("OPERACIÓN", f"{ORIGIN_LABELS.get(invoice.origin_type, invoice.origin_type)} · {invoice.origin_reference}", "PAC", invoice.provider or "—"),
            ("REFERENCIA PAC", invoice.provider_reference or "—", "TIPO", "Ingreso · CFDI 4.0"),
        ]
        if invoice.origin_type == "global" and invoice.global_year and invoice.global_month:
            operations = sum(item.quantity for item in items)
            rows.append(
                (
                    "PERIODO GLOBAL",
                    f"{invoice.global_month:02d}/{invoice.global_year} · Mensual",
                    "OPERACIONES",
                    f"{operations} ventas al público en general",
                )
            )
        data = [
            [
                Paragraph(label_a, label_style),
                Paragraph(escape(value_a), value_style),
                Paragraph(label_b, label_style),
                Paragraph(escape(value_b), value_style),
            ]
            for label_a, value_a, label_b, value_b in rows
        ]
        table = Table(data, colWidths=[29 * mm, 62 * mm, 34 * mm, 55 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ]
            )
        )
        return table

    def concepts_table() -> Table:
        header = [
            Paragraph("<b>Clave SAT</b>", small_style),
            Paragraph("<b>Descripción</b>", small_style),
            Paragraph("<b>Cant.</b>", small_style),
            Paragraph("<b>Unidad</b>", small_style),
            Paragraph("<b>Valor unitario</b>", small_right_style),
            Paragraph("<b>Importe</b>", small_right_style),
            Paragraph("<b>IVA</b>", small_right_style),
            Paragraph("<b>Total</b>", small_right_style),
        ]
        rows: list[list[object]] = [header]
        for item in items:
            rows.append(
                [
                    Paragraph(item.sat_product_code, small_style),
                    Paragraph(
                        f"{escape(item.description)}<br/><font size=6.5 color='#6b7a70'>"
                        f"{item.sat_unit_code} · {escape(item.unit_name)}</font>",
                        small_style,
                    ),
                    Paragraph(str(item.quantity), small_style),
                    Paragraph(escape(item.unit_name), small_style),
                    Paragraph(_unit_price(item.subtotal_cents, item.quantity), small_right_style),
                    Paragraph(_money(item.subtotal_cents), small_right_style),
                    Paragraph(_money(item.tax_cents), small_right_style),
                    Paragraph(_money(item.total_cents), small_right_style),
                ]
            )
        if len(rows) == 1:
            rows.append(
                [
                    Paragraph("Sin conceptos registrados.", small_style),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
        table = Table(
            rows,
            colWidths=[18 * mm, 55 * mm, 11 * mm, 16 * mm, 22 * mm, 20 * mm, 17 * mm, 21 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8faf8")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def totals_table() -> Table:
        data = [
            [Paragraph("Subtotal", small_style), Paragraph(_money(invoice.subtotal_cents), small_right_style)],
            [
                Paragraph(f"IVA ({invoice.tax_rate_percent}%)", small_style),
                Paragraph(_money(invoice.tax_cents), small_right_style),
            ],
            [Paragraph("<b>Total</b>", value_style), Paragraph(f"<b>{_money(invoice.total_cents)}</b>", value_style)],
        ]
        table = Table(data, colWidths=[40 * mm, 32 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.25, LINE),
                    ("LINEBELOW", (0, 1), (-1, 1), 0.25, LINE),
                    ("BACKGROUND", (0, 2), (-1, 2), SOFT),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def note_box(text: str) -> Table:
        table = Table(
            [[Paragraph(escape(text), note_style)]],
            colWidths=[180 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4e5")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0a35b")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def cancellation_section() -> list[object]:
        if invoice.status != "cancelled":
            return []
        rows = [
            ("MOTIVO SAT", f"{invoice.cancellation_reason_code or '—'} · {cancellation_reason}"),
            ("FECHA DE CANCELACIÓN", _local_datetime(invoice.cancelled_at)),
            ("UUID DE SUSTITUCIÓN", invoice.cancellation_replacement_uuid or "—"),
            ("NOTA", invoice.cancellation_note or "—"),
        ]
        data = [
            [Paragraph(label, label_style), Paragraph(escape(value), value_style)]
            for label, value in rows
        ]
        table = Table(data, colWidths=[45 * mm, 135 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fdeceb")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#efd4d1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return [
            Paragraph("Cancelación", section_style),
            table,
        ]

    watermark = None
    if invoice.status == "cancelled":
        watermark = "CANCELADA"
    elif invoice.is_simulated:
        watermark = "SIMULADA"

    def draw_page(canvas, doc) -> None:
        canvas.saveState()
        if watermark is not None:
            canvas.saveState()
            canvas.setFillColor(colors.HexColor("#b3261e"))
            canvas.setFillAlpha(0.09)
            canvas.setFont("Helvetica-Bold", 64)
            canvas.translate(letter[0] / 2, letter[1] / 2)
            canvas.rotate(38)
            canvas.drawCentredString(0, 0, watermark)
            canvas.restoreState()
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 14 * mm, letter[0] - 18 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            18 * mm,
            9.5 * mm,
            f"{gym_name} · RFC {issuer.rfc} · CFDI {folio_label}",
        )
        canvas.drawRightString(letter[0] - 18 * mm, 9.5 * mm, f"Página {doc.page}")
        canvas.restoreState()

    story: list[object] = [
        Paragraph(escape(gym_name), subtitle_style),
        Paragraph("Representación impresa de CFDI", title_style),
        Paragraph(
            f"Emisor {escape(issuer.legal_name)} · RFC {issuer.rfc} · "
            f"Régimen {issuer.tax_regime} · CP {issuer.postal_code}",
            subtitle_style,
        ),
        Spacer(1, 8),
    ]
    if invoice.is_simulated:
        story.extend(
            [
                note_box(
                    "SIMULACIÓN: comprobante generado con el PAC simulado de la vista "
                    "previa. No está timbrado ante el SAT y no tiene validez fiscal."
                ),
                Spacer(1, 8),
            ]
        )
    if invoice.status == "cancelled":
        story.extend(
            [
                note_box("COMPROBANTE CANCELADO: esta representación impresa ya no ampara la operación."),
                Spacer(1, 8),
            ]
        )

    story.extend(
        [
            status_table(),
            Spacer(1, 6),
            Paragraph(
                f"<b>UUID SAT:</b> {escape(invoice.uuid or 'Sin UUID (comprobante simulado)')}",
                small_style,
            ),
            Spacer(1, 4),
            facts_table(),
            Paragraph("Emisor y receptor", section_style),
            parties_table(),
            Paragraph("Conceptos", section_style),
            concepts_table(),
            Spacer(1, 6),
            totals_table(),
        ]
    )

    cancellation = cancellation_section()
    if cancellation:
        story.extend(cancellation)

    story.extend(
        [
            Spacer(1, 14),
            Paragraph(
                "Este documento es una representación impresa de un CFDI. "
                "El archivo XML timbrado es el comprobante fiscal válido.",
                final_note_style,
            ),
        ]
    )
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()


__all__ = [
    "build_invoice_pdf",
    "invoice_pdf_filename",
]
