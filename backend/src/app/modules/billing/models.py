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

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
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

# The first increment bills one sale or one confirmed membership payment. Other
# origins (account payments, global invoice batches) are added by later
# migrations that widen this check.
INVOICE_ORIGIN_TYPES = ("sale", "membership_payment")

INVOICE_STATUSES = ("requested", "failed", "stamped", "cancelled")


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
            "origin_type IN ('sale', 'membership_payment')",
            name="ck_invoices_origin_type",
        ),
        CheckConstraint(
            "status IN ('requested', 'failed', 'stamped', 'cancelled')",
            name="ck_invoices_status",
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
        # At most one live (not cancelled) invoice per origin. A cancelled
        # invoice keeps its folio and history but frees the origin for a new
        # one, which is how a replacement comprobante is issued.
        Index(
            "uq_invoices_active_origin",
            "origin_type",
            "origin_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
            sqlite_where=text("status <> 'cancelled'"),
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
    member_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT")),
    )

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


__all__ = [
    "INVOICE_ORIGIN_TYPES",
    "INVOICE_STATUSES",
    "Invoice",
    "InvoiceEvent",
    "InvoiceItem",
    "MemberFiscalProfile",
    "utc_now",
]
