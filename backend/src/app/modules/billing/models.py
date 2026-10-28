"""Fiscal data, CFDI invoices and their audit trail.

The data-model document separates ``ClienteFiscal``, ``SolicitudFacturacion``,
``ComprobanteFiscal`` and ``EventoFiscal``. For this first increment the request
and the resulting comprobante live in one ``invoices`` row: the status tells
whether it is only a request (``requested``), a failed attempt (``failed``), a
stamped comprobante (``stamped``) or a cancelled one (``cancelled``), and every
attempt or state change is appended to ``invoice_events``. That keeps a single
identity per invoice without duplicating the request/result pair, and it can be
split later if the PAC needs several comprobantes per request.

An invoice never stores the card data or the PAC credentials: only the fiscal
snapshot, the SAT references, the resulting UUID/XML/status and the operator.
"""

from datetime import date, datetime, timezone
from typing import Any
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
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# A CFDI bills one sale, one confirmed membership payment, one monthly batch of
# walk-in sales to the public in general or one credit note (CFDI de egreso)
# linked to a previous invoice. Other origins (account payments, PPD
# complements) are added by later migrations that widen this check.
INVOICE_ORIGIN_TYPES = ("sale", "membership_payment", "global", "credit_note")

INVOICE_STATUSES = ("requested", "failed", "stamped", "cancelled")

# A payment complement (CFDI tipo P, complemento de pago 2.0) records one
# partiality of an invoice issued with MétodoPago PPD. It is a fiscal document
# of its own: it has its own folio, UUID and cancellation, and the income
# invoice keeps its original total untouched.
PAYMENT_COMPLEMENT_STATUSES = ("requested", "failed", "stamped", "cancelled")

# Only an individual income invoice with a known receptor can receive payment
# complements. The global invoice is paid at sale time and a credit note is
# already a fiscal adjustment.
PAYMENT_COMPLEMENT_SOURCE_TYPES = frozenset({"sale", "membership_payment"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemberFiscalProfile(SQLModel, table=True):
    """The fiscal data a member gave to receive invoices.

    It is only a convenience to prefill the next request: every invoice keeps
    its own receptor snapshot, so editing the profile never rewrites an already
    stamped comprobante.
    """

    __tablename__ = "member_fiscal_profiles"
    __table_args__ = (
        UniqueConstraint("member_id", name="uq_member_fiscal_profiles_member"),
        CheckConstraint("length(rfc) BETWEEN 12 AND 13", name="ck_member_fiscal_profiles_rfc"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    rfc: str = Field(max_length=13)
    legal_name: str = Field(max_length=254)
    tax_regime: str = Field(max_length=3)
    postal_code: str = Field(max_length=5)
    cfdi_use: str = Field(max_length=3)
    email: str | None = Field(default=None, max_length=254)
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


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "origin_type IN ('sale', 'membership_payment', 'global', 'credit_note')",
            name="ck_invoices_origin_type",
        ),
        CheckConstraint(
            "status IN ('requested', 'failed', 'stamped', 'cancelled')",
            name="ck_invoices_status",
        ),
        # The monthly global invoice keeps its period so the XML can be rebuilt
        # after stamping and a cancelled month can be identified in the history.
        CheckConstraint(
            "(origin_type = 'global' AND global_year IS NOT NULL "
            "AND global_month BETWEEN 1 AND 12) OR "
            "(origin_type <> 'global' AND global_year IS NULL "
            "AND global_month IS NULL)",
            name="ck_invoices_global_period",
        ),
        # A credit note always points to the invoice it adjusts and records why;
        # no other invoice type may carry those fields.
        CheckConstraint(
            "(origin_type = 'credit_note' AND related_invoice_id IS NOT NULL "
            "AND credit_note_reason IS NOT NULL) OR "
            "(origin_type <> 'credit_note' AND related_invoice_id IS NULL "
            "AND credit_note_reason IS NULL AND credit_note_note IS NULL)",
            name="ck_invoices_credit_note",
        ),
        CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0 "
            "AND subtotal_cents + tax_cents = total_cents",
            name="ck_invoices_totals",
        ),
        CheckConstraint("total_cents > 0", name="ck_invoices_total_positive"),
        CheckConstraint("tax_rate_percent >= 0", name="ck_invoices_tax_rate"),
        CheckConstraint("folio > 0", name="ck_invoices_folio_positive"),
        UniqueConstraint("series", "folio", name="uq_invoices_series_folio"),
        UniqueConstraint("idempotency_key", name="uq_invoices_idempotency_key"),
        UniqueConstraint("uuid", name="uq_invoices_uuid"),
        Index("ix_invoices_origin", "origin_type", "origin_id"),
        Index("ix_invoices_status_created", "status", "created_at"),
        Index("ix_invoices_member_created", "member_id", "created_at"),
        Index("ix_invoices_related", "related_invoice_id"),
        # At most one live (not cancelled) invoice per origin. A cancelled
        # invoice keeps its folio and history but frees the origin for a new
        # one, which is how a replacement comprobante is issued. Credit notes
        # are excluded: an invoice accepts several partial notes, and its
        # remaining balance is validated in the service instead.
        Index(
            "uq_invoices_active_origin",
            "origin_type",
            "origin_id",
            unique=True,
            postgresql_where=text(
                "status <> 'cancelled' AND origin_type <> 'credit_note'"
            ),
            sqlite_where=text(
                "status <> 'cancelled' AND origin_type <> 'credit_note'"
            ),
        ),
        # At most one live global invoice per month. Cancelling one frees the
        # month for a replacement while both batches stay traceable.
        Index(
            "uq_invoices_active_global_period",
            "global_year",
            "global_month",
            unique=True,
            postgresql_where=text(
                "origin_type = 'global' AND status <> 'cancelled'"
            ),
            sqlite_where=text("origin_type = 'global' AND status <> 'cancelled'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    series: str = Field(default="A", max_length=10)
    folio: int
    status: str = Field(
        default="requested",
        sa_column=Column(String(16), nullable=False, server_default=text("'requested'")),
    )
    origin_type: str = Field(max_length=24)
    origin_id: UUID = Field(sa_column=Column(Uuid(as_uuid=True), nullable=False))
    # Human reference of the origin (sale folio ``V-…`` or payment id) copied at
    # request time so the listing shows it without querying each origin.
    origin_reference: str = Field(max_length=64)
    # Club-local calendar month of a global invoice; NULL for individual CFDI.
    global_year: int | None = Field(default=None)
    global_month: int | None = Field(default=None)
    member_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT")),
    )
    # Credit note (CFDI de egreso) linkage and reason. ``origin_id`` also points
    # to the related invoice, but this FK keeps the relation enforced and lets
    # the database reject deleting a credited comprobante.
    related_invoice_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    credit_note_reason: str | None = Field(default=None, max_length=24)
    credit_note_note: str | None = Field(default=None, max_length=300)

    # Receptor snapshot (CFDI 4.0). It is copied into the invoice so a later
    # change to the member profile cannot alter an issued comprobante.
    receptor_rfc: str = Field(max_length=13)
    receptor_name: str = Field(max_length=254)
    receptor_tax_regime: str = Field(max_length=3)
    receptor_postal_code: str = Field(max_length=5)
    receptor_cfdi_use: str = Field(max_length=3)
    receptor_email: str | None = Field(default=None, max_length=254)

    currency: str = Field(
        default="MXN",
        sa_column=Column(String(3), nullable=False, server_default=text("'MXN'")),
    )
    subtotal_cents: int = Field(sa_type=BigInteger)
    tax_cents: int = Field(sa_type=BigInteger)
    total_cents: int = Field(sa_type=BigInteger)
    tax_rate_percent: int = Field(default=16)
    payment_form: str = Field(max_length=2)
    payment_method: str = Field(default="PUE", max_length=3)

    # Result of the stamping request.
    uuid: str | None = Field(default=None, max_length=36)
    is_simulated: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    provider: str | None = Field(default=None, max_length=40)
    provider_reference: str | None = Field(default=None, max_length=160)
    xml_content: str | None = Field(default=None, sa_column=Column(Text))
    issued_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    stamped_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    cancellation_reason_code: str | None = Field(default=None, max_length=2)
    cancellation_replacement_uuid: str | None = Field(default=None, max_length=36)
    cancellation_note: str | None = Field(default=None, max_length=300)
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    # A 202 from the PAC leaves the request in process at the SAT: the invoice
    # stays ``stamped`` and these columns hold the request until it resolves,
    # so the operator can query it again instead of sending a blind retry.
    cancellation_requested_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    cancellation_checked_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )

    idempotency_key: str = Field(max_length=128)
    request_fingerprint: str = Field(max_length=64)
    created_by: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    stamped_by: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    cancelled_by: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
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


class InvoiceItem(SQLModel, table=True):
    """A concept of the comprobante, with the amounts split for CFDI."""

    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint("position > 0", name="ck_invoice_items_position_positive"),
        CheckConstraint("quantity > 0", name="ck_invoice_items_quantity_positive"),
        CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0 "
            "AND subtotal_cents + tax_cents = total_cents",
            name="ck_invoice_items_totals",
        ),
        UniqueConstraint("invoice_id", "position", name="uq_invoice_items_position"),
        Index("ix_invoice_items_invoice", "invoice_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    position: int
    description: str = Field(max_length=300)
    sat_product_code: str = Field(max_length=8)
    sat_unit_code: str = Field(max_length=3)
    unit_name: str = Field(max_length=30)
    quantity: int
    unit_price_cents: int = Field(sa_type=BigInteger)
    subtotal_cents: int = Field(sa_type=BigInteger)
    tax_cents: int = Field(sa_type=BigInteger)
    total_cents: int = Field(sa_type=BigInteger)

    product_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    sale_item_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))


class InvoiceEvent(SQLModel, table=True):
    """Append-only audit trail of every fiscal request, stamp and cancellation."""

    __tablename__ = "invoice_events"
    __table_args__ = (
        Index("ix_invoice_events_invoice_time", "invoice_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    event_type: str = Field(max_length=40)
    from_status: str | None = Field(default=None, max_length=16)
    to_status: str | None = Field(default=None, max_length=16)
    actor_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    detail: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class InvoicePayment(SQLModel, table=True):
    """One payment complement (partiality) for a PPD invoice.

    The income invoice keeps its original totals; the sum of the live stamped
    complements is the amount collected. ``prior_balance_cents``,
    ``amount_cents`` and ``outstanding_balance_cents`` are a snapshot taken when
    the complement was stamped, so the PDF and XML stay reproducible even if a
    later complement is cancelled.
    """

    __tablename__ = "invoice_payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'failed', 'stamped', 'cancelled')",
            name="ck_invoice_payments_status",
        ),
        CheckConstraint("folio > 0", name="ck_invoice_payments_folio_positive"),
        CheckConstraint(
            "partiality_number > 0", name="ck_invoice_payments_partiality_positive"
        ),
        CheckConstraint("amount_cents > 0", name="ck_invoice_payments_amount_positive"),
        CheckConstraint(
            "prior_balance_cents > 0 AND amount_cents <= prior_balance_cents "
            "AND outstanding_balance_cents = prior_balance_cents - amount_cents",
            name="ck_invoice_payments_balances",
        ),
        UniqueConstraint("series", "folio", name="uq_invoice_payments_series_folio"),
        UniqueConstraint("idempotency_key", name="uq_invoice_payments_idempotency_key"),
        UniqueConstraint("uuid", name="uq_invoice_payments_uuid"),
        Index("ix_invoice_payments_invoice_time", "invoice_id", "created_at"),
        Index("ix_invoice_payments_invoice_partiality", "invoice_id", "partiality_number"),
        Index("ix_invoice_payments_status_created", "status", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    series: str = Field(default="P", max_length=10)
    folio: int
    status: str = Field(
        default="requested",
        sa_column=Column(String(16), nullable=False, server_default=text("'requested'")),
    )
    partiality_number: int
    amount_cents: int = Field(sa_type=BigInteger)
    currency: str = Field(
        default="MXN",
        sa_column=Column(String(3), nullable=False, server_default=text("'MXN'")),
    )
    payment_form: str = Field(max_length=2)
    paid_on: date = Field(sa_type=Date)
    prior_balance_cents: int = Field(sa_type=BigInteger)
    outstanding_balance_cents: int = Field(sa_type=BigInteger)
    tax_rate_percent: int = Field(default=16)

    uuid: str | None = Field(default=None, max_length=36)
    is_simulated: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    provider: str | None = Field(default=None, max_length=40)
    provider_reference: str | None = Field(default=None, max_length=160)
    xml_content: str | None = Field(default=None, sa_column=Column(Text))
    issued_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    stamped_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    cancellation_reason_code: str | None = Field(default=None, max_length=2)
    cancellation_note: str | None = Field(default=None, max_length=300)
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    idempotency_key: str = Field(max_length=128)
    request_fingerprint: str = Field(max_length=64)
    created_by: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    stamped_by: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    cancelled_by: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
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


class InvoicePaymentEvent(SQLModel, table=True):
    """Append-only audit trail of a payment complement."""

    __tablename__ = "invoice_payment_events"
    __table_args__ = (
        Index("ix_invoice_payment_events_payment_time", "payment_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    payment_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("invoice_payments.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    event_type: str = Field(max_length=40)
    from_status: str | None = Field(default=None, max_length=16)
    to_status: str | None = Field(default=None, max_length=16)
    actor_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    detail: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class GlobalInvoiceSale(SQLModel, table=True):
    """A walk-in sale included in a monthly global invoice.

    The row is the traceability link required by the fiscal process: it keeps
    the sale reference and amount snapshot even if the sale is later refunded.
    A sale can appear again in a replacement batch when the previous global
    invoice is cancelled, but never in two live batches at once.
    """

    __tablename__ = "global_invoice_sales"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id", "sale_id", name="uq_global_invoice_sales_invoice_sale"
        ),
        CheckConstraint(
            "total_cents > 0", name="ck_global_invoice_sales_total_positive"
        ),
        Index("ix_global_invoice_sales_sale", "sale_id"),
        Index("ix_global_invoice_sales_invoice", "invoice_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    sale_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    sale_folio: str = Field(max_length=32)
    sold_at: datetime = Field(sa_type=DateTime(timezone=True))
    total_cents: int = Field(sa_type=BigInteger)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


__all__ = [
    "GlobalInvoiceSale",
    "INVOICE_ORIGIN_TYPES",
    "INVOICE_STATUSES",
    "Invoice",
    "InvoiceEvent",
    "InvoiceItem",
    "InvoicePayment",
    "InvoicePaymentEvent",
    "MemberFiscalProfile",
    "PAYMENT_COMPLEMENT_SOURCE_TYPES",
    "PAYMENT_COMPLEMENT_STATUSES",
    "utc_now",
]
