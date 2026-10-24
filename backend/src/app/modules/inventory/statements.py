"""Render and deliver a member account statement.

The statement is a **snapshot** of the events already recorded in the account:
the balance is still computed from the sales, returns and payments, never from
this module. Here we only turn that snapshot into a printable PDF, a CSV for a
spreadsheet, or an email attachment.

The email transport is deliberately small (stdlib ``smtplib``): the club's SMTP
account is configured through environment variables and preview mode simulates
the delivery instead of contacting a real server. Every attempt is appended to
``member_account_statement_deliveries`` so the club can audit who sent what.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
import csv
import io
import os
import re
import smtplib
import ssl
import unicodedata
from uuid import UUID
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func
from sqlmodel import Session, select

from app.modules.identity.models import AppUser
from app.modules.inventory.models import (
    MEMBER_ACCOUNT_STATEMENT_FORMATS,
    MEMBER_ACCOUNT_STATEMENT_PURPOSES,
    MemberAccountStatementDelivery,
    utc_now,
)
from app.modules.inventory.service import (
    InventoryError,
    MAX_PAGE_SIZE,
    MemberAccountStatement,
    MemberAccountSummary,
    MemberUnavailable,
    member_account_statement,
)
from app.modules.memberships.models import Member
from app.timezone import to_club_timezone

DEFAULT_GYM_NAME = "Centro Fit"
DEFAULT_STATEMENT_DELIVERY_PAGE_SIZE = 20
# A collection reminder is a follow-up for charges that are already 31 days old
# or more. Current debt is not chased: the member may still be inside the normal
# billing window.
STATEMENT_REMINDER_MIN_OVERDUE_DAYS = 31
STATEMENT_REMINDER_COOLDOWN_DAYS = 7
STATEMENT_REMINDER_BATCH_LIMIT = 50
# A failed attempt never reached the member and a preview attempt never left the
# server, so both can be retried. A real ``sent`` delivery is not retried from
# the history to avoid duplicate financial emails; that needs a separate resend
# flow with an explicit confirmation and frequency control.
RETRYABLE_STATEMENT_DELIVERY_STATUSES = ("failed", "simulated")
METHOD_LABELS = {
    "cash": "Efectivo",
    "card": "Tarjeta",
    "transfer": "Transferencia",
    "account": "Cuenta del socio",
}
KIND_LABELS = {
    "charge": "Cargo",
    "credit": "Devolución",
    "payment": "Pago",
}
STATUS_LABELS = {
    "active": "Activo",
    "pending": "Pendiente",
    "frozen": "Congelado",
    "inactive": "Inactivo",
}


class StatementError(InventoryError):
    pass


class InvalidStatementFormat(StatementError):
    pass


class InvalidStatementPurpose(StatementError):
    pass


class StatementRecipientMissing(StatementError):
    pass


class StatementEmailNotConfigured(StatementError):
    pass


class StatementDeliveryFailed(StatementError):
    pass


class StatementReminderNotAllowed(StatementError):
    pass


class StatementDeliveryNotFound(StatementError):
    pass


class StatementDeliveryRetryNotAllowed(StatementError):
    pass


@dataclass(frozen=True)
class StatementDeliveryView:
    id: UUID
    member_id: UUID
    actor_id: UUID | None
    actor_email: str | None
    recipient: str
    format: str
    purpose: str
    status: str
    as_of: date
    error: str | None
    retry_of_id: UUID | None
    created_at: datetime


@dataclass(frozen=True)
class StatementDeliveryList:
    items: list[StatementDeliveryView]
    total: int
    page: int
    page_size: int
    pages: int


@dataclass(frozen=True)
class StatementReminderResult:
    """Outcome of one member inside a reminder batch.

    ``skipped`` covers business reasons (no overdue balance, no email, cooldown);
    ``failed`` means the transport was attempted and the audit row records the
    error. The batch never aborts because one member cannot be contacted.
    """

    member_id: UUID
    member_name: str | None
    status: str
    reason: str | None
    balance_cents: int
    overdue_cents: int
    delivery: StatementDeliveryView | None


@dataclass(frozen=True)
class StatementReminderBatch:
    requested: int
    sent: int
    simulated: int
    skipped: int
    failed: int
    results: list[StatementReminderResult]


def _money(cents: int) -> str:
    """Signed money for a human-readable document."""

    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _overdue_cents(summary: MemberAccountSummary) -> int:
    """Amount older than 30 days, using the same FIFO aging as the account."""

    aging = summary.aging
    return (
        aging.days_31_60_cents
        + aging.days_61_90_cents
        + aging.over_90_cents
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _decimal(cents: int) -> str:
    """Money for CSV cells, without a currency symbol."""

    return f"{cents / 100:.2f}"


def _csv_text(value: str | None) -> str:
    """Keep spreadsheet text from being interpreted as a formula.

    Excel treats a leading ``=``, ``+``, ``-``, ``@``, tab or carriage return as
    a formula. A leading apostrophe forces text without changing the visible
    value in the spreadsheet.
    """

    text = value or ""
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def _local_date(moment: datetime) -> str:
    return to_club_timezone(moment).date().isoformat()


def _local_datetime(moment: datetime) -> str:
    return to_club_timezone(moment).strftime("%d/%m/%Y %H:%M")


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()


def statement_filename(statement: MemberAccountStatement, extension: str) -> str:
    name = _slug(statement.summary.member_name) or "socio"
    return f"estado-cuenta-{name}-{statement.as_of.isoformat()}.{extension}"


def build_member_account_statement_csv(statement: MemberAccountStatement) -> bytes:
    """Flatten the statement into a spreadsheet-friendly UTF-8 CSV.

    The BOM at the beginning lets Excel for Windows detect UTF-8, so the accents
    in "Devolución" and "Límite" survive a double click.
    """

    summary = statement.summary
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["Estado de cuenta"])
    writer.writerow(["Socio", _csv_text(summary.member_name)])
    writer.writerow(["Correo", _csv_text(summary.email)])
    writer.writerow(["Teléfono", _csv_text(summary.phone)])
    writer.writerow(["Corte", statement.as_of.isoformat()])
    writer.writerow([])
    writer.writerow(["Resumen"])
    writer.writerow(["Cargos", _decimal(summary.charges_cents)])
    writer.writerow(["Abonos", _decimal(summary.payments_cents)])
    writer.writerow(["Devoluciones", _decimal(summary.credits_cents)])
    writer.writerow(["Saldo", _decimal(summary.balance_cents)])
    writer.writerow(
        [
            "Límite de crédito",
            "" if summary.credit_limit_cents is None else _decimal(summary.credit_limit_cents),
        ]
    )
    writer.writerow(
        [
            "Crédito disponible",
            ""
            if summary.credit_available_cents is None
            else _decimal(summary.credit_available_cents),
        ]
    )
    writer.writerow(["Sobre el límite", "Sí" if summary.over_limit else "No"])
    writer.writerow([])
    writer.writerow(["Antigüedad del saldo"])
    writer.writerow(["0-30 días", _decimal(summary.aging.current_cents)])
    writer.writerow(["31-60 días", _decimal(summary.aging.days_31_60_cents)])
    writer.writerow(["61-90 días", _decimal(summary.aging.days_61_90_cents)])
    writer.writerow(["+90 días", _decimal(summary.aging.over_90_cents)])
    writer.writerow([])
    writer.writerow(["Movimientos (del más antiguo al más reciente)"])
    writer.writerow(["Fecha", "Tipo", "Movimiento", "Referencia", "Forma", "Importe", "Saldo"])
    for entry in reversed(statement.entries):
        writer.writerow(
            [
                _local_date(entry.occurred_at),
                KIND_LABELS.get(entry.kind, entry.kind),
                _csv_text(entry.description),
                _csv_text(entry.reference),
                _csv_text(METHOD_LABELS.get(entry.method or "", entry.method or "")),
                _decimal(entry.amount_cents),
                _decimal(entry.balance_cents),
            ]
        )
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def build_member_account_statement_pdf(statement: MemberAccountStatement) -> bytes:
    """Render the statement as a printable letter-size PDF."""

    summary = statement.summary
    buffer = io.BytesIO()
    gym_name = os.getenv("GYM_NAME", DEFAULT_GYM_NAME).strip() or DEFAULT_GYM_NAME
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=19 * mm,
        title=f"Estado de cuenta - {summary.member_name}",
        author=gym_name,
        subject="Estado de cuenta del socio",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StatementTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=21,
        textColor=colors.HexColor("#16322d"),
        alignment=0,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "StatementSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#6b7a70"),
    )
    section_style = ParagraphStyle(
        "StatementSection",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#23509a"),
        spaceBefore=8,
        spaceAfter=4,
    )
    small_style = ParagraphStyle(
        "StatementSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#26332c"),
    )
    small_right_style = ParagraphStyle(
        "StatementSmallRight",
        parent=small_style,
        alignment=2,
    )
    label_style = ParagraphStyle(
        "StatementLabel",
        parent=small_style,
        textColor=colors.HexColor("#6b7a70"),
    )

    def header_table() -> Table:
        rows = [
            [
                Paragraph("Socio", label_style),
                Paragraph(f"<b>{escape(summary.member_name)}</b>", small_style),
                Paragraph("Corte", label_style),
                Paragraph(statement.as_of.strftime("%d/%m/%Y"), small_style),
            ],
            [
                Paragraph("Correo", label_style),
                Paragraph(escape(summary.email or "Sin correo"), small_style),
                Paragraph("Teléfono", label_style),
                Paragraph(escape(summary.phone or "Sin teléfono"), small_style),
            ],
            [
                Paragraph("Estado", label_style),
                Paragraph(
                    escape(STATUS_LABELS.get(summary.member_status, summary.member_status)),
                    small_style,
                ),
                Paragraph("Movimientos", label_style),
                Paragraph(str(len(statement.entries)), small_style),
            ],
        ]
        table = Table(rows, colWidths=[20 * mm, 76 * mm, 22 * mm, 56 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return table

    def summary_table() -> Table:
        data = [
            ["Cargos", "Abonos", "Devoluciones", "Saldo"],
            [
                _money(summary.charges_cents),
                _money(summary.payments_cents),
                _money(summary.credits_cents),
                _money(summary.balance_cents),
            ],
        ]
        table = Table(data, colWidths=[43 * mm, 43 * mm, 43 * mm, 45 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4f1")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#567168")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#16322d")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dce7e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table

    def limit_table() -> Table:
        limit = "Sin límite" if summary.credit_limit_cents is None else _money(summary.credit_limit_cents)
        available = (
            "No aplica"
            if summary.credit_available_cents is None
            else _money(summary.credit_available_cents)
        )
        data = [
            [
                Paragraph("Límite de crédito", label_style),
                Paragraph(limit, small_style),
                Paragraph("Crédito disponible", label_style),
                Paragraph(available, small_style),
                Paragraph("Estado del crédito", label_style),
                Paragraph(
                    "Excedido" if summary.over_limit else "Dentro del límite",
                    small_style,
                ),
            ]
        ]
        table = Table(data, colWidths=[30 * mm, 24 * mm, 32 * mm, 24 * mm, 30 * mm, 34 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table

    def aging_table() -> Table:
        data = [
            ["0-30 días", "31-60 días", "61-90 días", "+90 días"],
            [
                _money(summary.aging.current_cents),
                _money(summary.aging.days_31_60_cents),
                _money(summary.aging.days_61_90_cents),
                _money(summary.aging.over_90_cents),
            ],
        ]
        table = Table(data, colWidths=[43 * mm, 43 * mm, 43 * mm, 45 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f7faf7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#567168")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e3ebe6")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def movements_table() -> Table:
        header = [
            Paragraph("<b>Fecha</b>", small_style),
            Paragraph("<b>Tipo</b>", small_style),
            Paragraph("<b>Movimiento</b>", small_style),
            Paragraph("<b>Referencia</b>", small_style),
            Paragraph("<b>Forma</b>", small_style),
            Paragraph("<b>Importe</b>", small_right_style),
            Paragraph("<b>Saldo</b>", small_right_style),
        ]
        rows: list[list[object]] = [header]
        for entry in reversed(statement.entries):
            rows.append(
                [
                    Paragraph(_local_datetime(entry.occurred_at), small_style),
                    Paragraph(escape(KIND_LABELS.get(entry.kind, entry.kind)), small_style),
                    Paragraph(escape(entry.description), small_style),
                    Paragraph(escape(entry.reference), small_style),
                    Paragraph(
                        escape(METHOD_LABELS.get(entry.method or "", entry.method or "")),
                        small_style,
                    ),
                    Paragraph(_money(entry.amount_cents), small_right_style),
                    Paragraph(_money(entry.balance_cents), small_right_style),
                ]
            )
        if len(rows) == 1:
            rows.append(
                [
                    Paragraph("Sin movimientos registrados.", small_style),
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
            colWidths=[21 * mm, 16 * mm, 48 * mm, 30 * mm, 21 * mm, 21 * mm, 21 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16322d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e3ebe6")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8faf8")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def draw_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dfe7e1"))
        canvas.line(18 * mm, 14 * mm, letter[0] - 18 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#6b7a70"))
        canvas.drawString(
            18 * mm,
            9.5 * mm,
            f"{gym_name} · Estado de cuenta · Corte {statement.as_of.strftime('%d/%m/%Y')}",
        )
        canvas.drawRightString(letter[0] - 18 * mm, 9.5 * mm, f"Página {doc.page}")
        canvas.restoreState()

    story = [
        Paragraph(escape(gym_name), subtitle_style),
        Paragraph("Estado de cuenta", title_style),
        Paragraph(
            "Documento informativo de la cuenta del socio. Los saldos se calculan "
            "con los movimientos registrados.",
            subtitle_style,
        ),
        Spacer(1, 8),
        header_table(),
        Spacer(1, 10),
        summary_table(),
        Spacer(1, 6),
        limit_table(),
        Paragraph("Antigüedad del saldo", section_style),
        aging_table(),
        Paragraph("Movimientos", section_style),
        movements_table(),
        Spacer(1, 8),
        Paragraph(
            "Pagos y devoluciones se aplican al cargo más antiguo (FIFO). "
            "Un saldo negativo representa un saldo a favor del socio.",
            subtitle_style,
        ),
    ]
    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _send_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    attachment: bytes,
    filename: str,
    document_format: str,
) -> str:
    """Send the email and return ``sent`` or ``simulated``.

    Preview mode never contacts a real SMTP server, even when ``SMTP_HOST`` is
    configured: it records a ``simulated`` delivery so the panel and the audit
    trail behave exactly like a production send without sending private
    financial data during a demo.
    """

    if _env_bool("PREVIEW_MODE", False):
        return "simulated"

    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        raise StatementEmailNotConfigured(
            "El envío de estados de cuenta no está configurado (SMTP_HOST)."
        )

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        timeout = float(os.getenv("SMTP_TIMEOUT", "20"))
    except ValueError as error:
        raise StatementEmailNotConfigured(
            "SMTP_PORT o SMTP_TIMEOUT no tienen un número válido."
        ) from error
    use_ssl = _env_bool("SMTP_USE_SSL", False)
    use_tls = _env_bool("SMTP_USE_TLS", True)
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip() or username or "no-reply@localhost"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    maintype, subtype = ("application", "pdf") if document_format == "pdf" else ("text", "csv")
    message.add_attachment(attachment, maintype=maintype, subtype=subtype, filename=filename)

    context = ssl.create_default_context()
    try:
        if use_ssl:
            connection = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            connection = smtplib.SMTP(host, port, timeout=timeout)
        with connection as server:
            if use_tls and not use_ssl:
                server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as error:
        detail = str(error).strip() or error.__class__.__name__
        raise StatementDeliveryFailed(
            f"No se pudo enviar el estado de cuenta: {detail}"
        ) from error
    return "sent"


def _delivery_view(
    record: MemberAccountStatementDelivery, actor_email: str | None = None
) -> StatementDeliveryView:
    return StatementDeliveryView(
        id=record.id,
        member_id=record.member_id,
        actor_id=record.actor_id,
        actor_email=actor_email,
        recipient=record.recipient,
        format=record.format,
        purpose=record.purpose,
        status=record.status,
        as_of=record.as_of,
        error=record.error,
        retry_of_id=record.retry_of_id,
        created_at=record.created_at,
    )


def list_member_account_statement_deliveries(
    session: Session,
    member_id: UUID,
    *,
    page: int = 1,
    page_size: int = DEFAULT_STATEMENT_DELIVERY_PAGE_SIZE,
) -> StatementDeliveryList:
    """Return the delivery attempts for one member, newest first."""

    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    page_size = min(page_size, MAX_PAGE_SIZE)
    if session.get(Member, member_id) is None:
        raise MemberUnavailable("Socio no encontrado")

    condition = MemberAccountStatementDelivery.member_id == member_id
    total = session.exec(
        select(func.count())
        .select_from(MemberAccountStatementDelivery)
        .where(condition)
    ).one()
    records = session.exec(
        select(MemberAccountStatementDelivery)
        .where(condition)
        .order_by(
            MemberAccountStatementDelivery.created_at.desc(),
            MemberAccountStatementDelivery.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    actor_ids = {record.actor_id for record in records if record.actor_id is not None}
    actor_emails: dict[UUID, str] = {}
    if actor_ids:
        actors = session.exec(select(AppUser).where(AppUser.id.in_(actor_ids))).all()
        actor_emails = {actor.id: actor.email for actor in actors}
    pages = (int(total) + page_size - 1) // page_size if total > 0 else 0
    return StatementDeliveryList(
        items=[
            _delivery_view(record, actor_emails.get(record.actor_id))
            for record in records
        ],
        total=int(total),
        page=page,
        page_size=page_size,
        pages=pages,
    )


def retry_member_account_statement_delivery(
    session: Session,
    member_id: UUID,
    delivery_id: UUID,
    *,
    actor_id: UUID | None = None,
    today: date | None = None,
) -> StatementDeliveryView:
    """Retry the original recipient and format, appending a new audit row.

    The source row is never mutated: the history keeps the failed/simulated
    attempt and the new attempt points back to it with ``retry_of_id``.
    """

    record = session.get(MemberAccountStatementDelivery, delivery_id)
    if record is None or record.member_id != member_id:
        raise StatementDeliveryNotFound("No se encontró el envío del estado de cuenta.")
    if record.status not in RETRYABLE_STATEMENT_DELIVERY_STATUSES:
        raise StatementDeliveryRetryNotAllowed(
            "Solo se pueden reintentar envíos fallidos o simulados."
        )
    return send_member_account_statement(
        session,
        member_id,
        recipient=record.recipient,
        document_format=record.format,
        purpose=record.purpose,
        actor_id=actor_id,
        retry_of_id=record.id,
        today=today if today is not None else record.as_of,
    )


def send_member_account_statement(
    session: Session,
    member_id: UUID,
    *,
    recipient: str | None = None,
    document_format: str = "pdf",
    purpose: str = "statement",
    actor_id: UUID | None = None,
    retry_of_id: UUID | None = None,
    today: date | None = None,
) -> StatementDeliveryView:
    """Send a statement or collection reminder and append the attempt.

    The delivery record is written even when the transport fails, with
    ``status = "failed"`` and the error, so a manager can see why a member did
    not receive the document. The account balance is never mutated here.

    A reminder is only valid while the account still has a positive balance with
    charges older than 30 days. This is checked again here, not only in the batch
    selector, so a retry cannot send an outdated collection notice after payment.
    """

    if document_format not in MEMBER_ACCOUNT_STATEMENT_FORMATS:
        raise InvalidStatementFormat("El formato debe ser PDF o CSV.")
    if purpose not in MEMBER_ACCOUNT_STATEMENT_PURPOSES:
        raise InvalidStatementPurpose("El tipo de envío no es válido.")
    statement = member_account_statement(session, member_id, today=today)
    summary = statement.summary
    overdue_cents = _overdue_cents(summary)
    if purpose == "reminder":
        if summary.balance_cents <= 0:
            raise StatementReminderNotAllowed(
                "El socio ya no tiene saldo pendiente."
            )
        if overdue_cents <= 0:
            raise StatementReminderNotAllowed(
                "El saldo pendiente todavía no tiene cargos con más de "
                f"{STATEMENT_REMINDER_MIN_OVERDUE_DAYS - 1} días."
            )
    address = (recipient or summary.email or "").strip()
    if not address:
        raise StatementRecipientMissing(
            "El socio no tiene correo registrado; agrega uno o indica un destinatario."
        )

    if document_format == "pdf":
        content = build_member_account_statement_pdf(statement)
    else:
        content = build_member_account_statement_csv(statement)
    filename = statement_filename(statement, document_format)
    if purpose == "reminder":
        subject = (
            f"Recordatorio de saldo pendiente de {summary.member_name} "
            f"al {statement.as_of.strftime('%d/%m/%Y')}"
        )
        body = (
            f"Hola {summary.member_name},\n\n"
            f"Te recordamos que tu cuenta del socio tiene un saldo pendiente de "
            f"{_money(summary.balance_cents)} al "
            f"{statement.as_of.strftime('%d/%m/%Y')}.\n\n"
            f"Del total, {_money(overdue_cents)} corresponde a cargos con más de "
            f"{STATEMENT_REMINDER_MIN_OVERDUE_DAYS - 1} días de antigüedad.\n"
            f"31 a 60 días: {_money(summary.aging.days_31_60_cents)}\n"
            f"61 a 90 días: {_money(summary.aging.days_61_90_cents)}\n"
            f"Más de 90 días: {_money(summary.aging.over_90_cents)}\n\n"
            "Adjuntamos tu estado de cuenta para que revises los movimientos. "
            "Si ya realizaste el pago, ignora este mensaje o comparte el "
            "comprobante con la recepción del gimnasio.\n\n"
            "Este correo se generó automáticamente.\n"
        )
    else:
        subject = (
            f"Estado de cuenta de {summary.member_name} "
            f"al {statement.as_of.strftime('%d/%m/%Y')}"
        )
        balance_label = "Saldo a favor" if summary.balance_cents < 0 else "Saldo"
        body = (
            f"Hola {summary.member_name},\n\n"
            f"Adjuntamos el estado de cuenta de tu cuenta del socio "
            f"al {statement.as_of.strftime('%d/%m/%Y')}.\n\n"
            f"{balance_label}: {_money(abs(summary.balance_cents))}\n"
            f"Cargos: {_money(summary.charges_cents)}\n"
            f"Abonos: {_money(summary.payments_cents)}\n"
            f"Devoluciones: {_money(summary.credits_cents)}\n\n"
            "Si tienes dudas sobre algún movimiento, contacta a la recepción del gimnasio.\n\n"
            "Este correo se generó automáticamente.\n"
        )

    record = MemberAccountStatementDelivery(
        member_id=member_id,
        actor_id=actor_id,
        channel="email",
        recipient=address,
        format=document_format,
        purpose=purpose,
        status="failed",
        as_of=statement.as_of,
        retry_of_id=retry_of_id,
        created_at=utc_now(),
    )
    try:
        status = _send_email(
            recipient=address,
            subject=subject,
            body=body,
            attachment=content,
            filename=filename,
            document_format=document_format,
        )
    except StatementError as error:
        record.error = str(error)[:500]
        session.add(record)
        session.commit()
        session.refresh(record)
        raise
    record.status = status
    record.error = None
    session.add(record)
    session.commit()
    session.refresh(record)
    return _delivery_view(record)


def send_member_account_reminders(
    session: Session,
    member_ids: list[UUID],
    *,
    document_format: str = "pdf",
    actor_id: UUID | None = None,
    today: date | None = None,
) -> StatementReminderBatch:
    """Send collection reminders to several members, one audit row each.

    The batch is deliberately best-effort: a missing email, a paid account or an
    SMTP failure for one member never prevents the other reminders from being
    attempted. Every member in the response has an explicit ``status`` and, when
    skipped, a human-readable reason.

    A member is skipped when they still have no balance, when no charge is older
    than 30 days, or when a successful reminder was already recorded in the last
    seven days. Failed reminders do not start the cooldown, so the panel can
    retry them from the delivery history.
    """

    if document_format not in MEMBER_ACCOUNT_STATEMENT_FORMATS:
        raise InvalidStatementFormat("El formato debe ser PDF o CSV.")

    unique_ids: list[UUID] = []
    seen: set[UUID] = set()
    for member_id in member_ids:
        if member_id in seen:
            continue
        seen.add(member_id)
        unique_ids.append(member_id)
    if not unique_ids:
        raise ValueError("Debes seleccionar al menos un socio.")
    if len(unique_ids) > STATEMENT_REMINDER_BATCH_LIMIT:
        raise ValueError(
            f"Un lote de recordatorios admite hasta "
            f"{STATEMENT_REMINDER_BATCH_LIMIT} socios."
        )

    members = {
        member.id: member
        for member in session.exec(
            select(Member).where(Member.id.in_(unique_ids))
        ).all()
    }
    recent_reminders = session.exec(
        select(MemberAccountStatementDelivery)
        .where(
            MemberAccountStatementDelivery.member_id.in_(unique_ids),
            MemberAccountStatementDelivery.purpose == "reminder",
            MemberAccountStatementDelivery.status.in_(("sent", "simulated")),
        )
        .order_by(
            MemberAccountStatementDelivery.created_at.desc(),
            MemberAccountStatementDelivery.id.desc(),
        )
    ).all()
    latest_reminder: dict[UUID, MemberAccountStatementDelivery] = {}
    for record in recent_reminders:
        latest_reminder.setdefault(record.member_id, record)

    results: list[StatementReminderResult] = []
    now = utc_now()
    cooldown = timedelta(days=STATEMENT_REMINDER_COOLDOWN_DAYS)
    for member_id in unique_ids:
        member = members.get(member_id)
        if member is None:
            results.append(
                StatementReminderResult(
                    member_id=member_id,
                    member_name=None,
                    status="skipped",
                    reason="Socio no encontrado.",
                    balance_cents=0,
                    overdue_cents=0,
                    delivery=None,
                )
            )
            continue

        try:
            statement = member_account_statement(session, member_id, today=today)
        except InventoryError as error:
            results.append(
                StatementReminderResult(
                    member_id=member_id,
                    member_name=f"{member.first_name} {member.last_name}".strip(),
                    status="failed",
                    reason=str(error),
                    balance_cents=0,
                    overdue_cents=0,
                    delivery=None,
                )
            )
            continue

        summary = statement.summary
        overdue_cents = _overdue_cents(summary)
        result_base = {
            "member_id": member_id,
            "member_name": summary.member_name,
            "balance_cents": summary.balance_cents,
            "overdue_cents": overdue_cents,
        }

        skip_reason: str | None = None
        if summary.balance_cents <= 0:
            skip_reason = "Sin saldo pendiente."
        elif overdue_cents <= 0:
            skip_reason = (
                "El saldo no tiene cargos con más de "
                f"{STATEMENT_REMINDER_MIN_OVERDUE_DAYS - 1} días."
            )
        elif not (summary.email or "").strip():
            skip_reason = "El socio no tiene correo registrado."
        else:
            previous = latest_reminder.get(member_id)
            if previous is not None:
                elapsed = now - _as_utc(previous.created_at)
                if elapsed < cooldown:
                    skip_reason = (
                        "Ya se envió un recordatorio en los últimos "
                        f"{STATEMENT_REMINDER_COOLDOWN_DAYS} días."
                    )

        if skip_reason is not None:
            results.append(
                StatementReminderResult(
                    **result_base,
                    status="skipped",
                    reason=skip_reason,
                    delivery=None,
                )
            )
            continue

        try:
            delivery = send_member_account_statement(
                session,
                member_id,
                recipient=summary.email,
                document_format=document_format,
                purpose="reminder",
                actor_id=actor_id,
                today=statement.as_of,
            )
        except StatementReminderNotAllowed as error:
            results.append(
                StatementReminderResult(
                    **result_base,
                    status="skipped",
                    reason=str(error),
                    delivery=None,
                )
            )
        except InventoryError as error:
            results.append(
                StatementReminderResult(
                    **result_base,
                    status="failed",
                    reason=str(error),
                    delivery=None,
                )
            )
        else:
            results.append(
                StatementReminderResult(
                    **result_base,
                    status=delivery.status,
                    reason=None,
                    delivery=delivery,
                )
            )

    return StatementReminderBatch(
        requested=len(unique_ids),
        sent=sum(1 for result in results if result.status == "sent"),
        simulated=sum(1 for result in results if result.status == "simulated"),
        skipped=sum(1 for result in results if result.status == "skipped"),
        failed=sum(1 for result in results if result.status == "failed"),
        results=results,
    )


__all__ = [
    "DEFAULT_STATEMENT_DELIVERY_PAGE_SIZE",
    "InvalidStatementFormat",
    "InvalidStatementPurpose",
    "KIND_LABELS",
    "METHOD_LABELS",
    "RETRYABLE_STATEMENT_DELIVERY_STATUSES",
    "STATEMENT_REMINDER_BATCH_LIMIT",
    "STATEMENT_REMINDER_COOLDOWN_DAYS",
    "STATEMENT_REMINDER_MIN_OVERDUE_DAYS",
    "StatementDeliveryFailed",
    "StatementDeliveryList",
    "StatementDeliveryNotFound",
    "StatementDeliveryRetryNotAllowed",
    "StatementDeliveryView",
    "StatementEmailNotConfigured",
    "StatementError",
    "StatementRecipientMissing",
    "StatementReminderBatch",
    "StatementReminderNotAllowed",
    "StatementReminderResult",
    "build_member_account_statement_csv",
    "build_member_account_statement_pdf",
    "list_member_account_statement_deliveries",
    "retry_member_account_statement_delivery",
    "send_member_account_reminders",
    "send_member_account_statement",
    "statement_filename",
]
