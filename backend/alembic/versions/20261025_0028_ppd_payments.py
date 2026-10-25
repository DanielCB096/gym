"""Payment complements (CFDI tipo P) for invoices issued with PPD.

An income invoice billed as PPD does not record a payment: each partiality is
a separate payment complement with its own folio, UUID and cancellation. The
balances are snapshotted when the complement is stamped and the invoice totals
never change. The relation is restricted on delete so a comprobante with
complements cannot disappear.

Revision ID: 20261025_0028
Revises: 20261025_0027
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261025_0028"
down_revision = "20261025_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "series",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'P'"),
        ),
        sa.Column("folio", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'requested'"),
        ),
        sa.Column("partiality_number", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'MXN'"),
        ),
        sa.Column("payment_form", sa.String(length=2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("prior_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("outstanding_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "tax_rate_percent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("16"),
        ),
        sa.Column("uuid", sa.String(length=36), nullable=True),
        sa.Column(
            "is_simulated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("xml_content", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stamped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason_code", sa.String(length=2), nullable=True),
        sa.Column("cancellation_note", sa.String(length=300), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stamped_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("series", "folio", name="uq_invoice_payments_series_folio"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_invoice_payments_idempotency_key"
        ),
        sa.UniqueConstraint("uuid", name="uq_invoice_payments_uuid"),
        sa.CheckConstraint(
            "status IN ('requested', 'failed', 'stamped', 'cancelled')",
            name="ck_invoice_payments_status",
        ),
        sa.CheckConstraint("folio > 0", name="ck_invoice_payments_folio_positive"),
        sa.CheckConstraint(
            "partiality_number > 0", name="ck_invoice_payments_partiality_positive"
        ),
        sa.CheckConstraint(
            "amount_cents > 0", name="ck_invoice_payments_amount_positive"
        ),
        sa.CheckConstraint(
            "prior_balance_cents > 0 AND amount_cents <= prior_balance_cents "
            "AND outstanding_balance_cents = prior_balance_cents - amount_cents",
            name="ck_invoice_payments_balances",
        ),
    )
    op.create_index(
        "ix_invoice_payments_invoice_time",
        "invoice_payments",
        ["invoice_id", "created_at"],
    )
    op.create_index(
        "ix_invoice_payments_invoice_partiality",
        "invoice_payments",
        ["invoice_id", "partiality_number"],
    )
    op.create_index(
        "ix_invoice_payments_status_created",
        "invoice_payments",
        ["status", "created_at"],
    )

    op.create_table(
        "invoice_payment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoice_payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_invoice_payment_events_payment_time",
        "invoice_payment_events",
        ["payment_id", "occurred_at"],
    )


def downgrade() -> None:
    has_payments = op.get_bind().execute(
        sa.text("SELECT 1 FROM invoice_payments LIMIT 1")
    ).first()
    if has_payments is not None:
        raise RuntimeError(
            "No se puede revertir la migración mientras existan complementos de pago."
        )
    op.drop_index(
        "ix_invoice_payment_events_payment_time",
        table_name="invoice_payment_events",
    )
    op.drop_table("invoice_payment_events")
    op.drop_index(
        "ix_invoice_payments_status_created", table_name="invoice_payments"
    )
    op.drop_index(
        "ix_invoice_payments_invoice_partiality", table_name="invoice_payments"
    )
    op.drop_index(
        "ix_invoice_payments_invoice_time", table_name="invoice_payments"
    )
    op.drop_table("invoice_payments")
