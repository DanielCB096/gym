"""CFDI 4.0 invoicing: fiscal profiles, invoices, concepts and audit trail.

Creates the first slice of the billing module:

* ``member_fiscal_profiles`` — the fiscal data a member gives to receive
  invoices. It is only a convenience to prefill the next request; each invoice
  keeps its own receptor snapshot.
* ``invoices`` — one row per invoice request/result, with the receptor snapshot,
  the VAT breakdown, the SAT references (series/folio/payment form) and the
  stamping result. Cancelling keeps the row: nothing fiscal is deleted.
* ``invoice_items`` — the concepts of the comprobante with their VAT split.
* ``invoice_events`` — append-only trail of requests, stamp attempts and
  cancellations.

The request and the comprobante share a row for this increment; the audit trail
keeps every attempt. ``docs/02-modulos/facturacion-y-reportes.md`` records the
limits (global invoice, credit notes, PPD complement) that stay out.

Permissions are separate from the operator ones because asking for an invoice
and stamping/cancelling it are different responsibilities: reception captures
requests, the accountant (or manager/owner) stamps and cancels.

Revision ID: 20261023_0024
Revises: 20261021_0023
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261023_0024"
down_revision = "20261021_0023"
branch_labels = None
depends_on = None

PERMISSIONS = (
    (
        "billing.read",
        "Consultar facturas y datos fiscales",
        ("owner", "manager", "accountant", "reception"),
    ),
    (
        "billing.request",
        "Solicitar facturas y capturar datos fiscales",
        ("owner", "manager", "accountant", "reception"),
    ),
    (
        "billing.manage",
        "Timbrar y cancelar facturas",
        ("owner", "manager", "accountant"),
    ),
)


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    op.create_table(
        "member_fiscal_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rfc", sa.String(length=13), nullable=False),
        sa.Column("legal_name", sa.String(length=254), nullable=False),
        sa.Column("tax_regime", sa.String(length=3), nullable=False),
        sa.Column("postal_code", sa.String(length=5), nullable=False),
        sa.Column("cfdi_use", sa.String(length=3), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
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
        sa.UniqueConstraint("member_id", name="uq_member_fiscal_profiles_member"),
        sa.CheckConstraint(
            "length(rfc) BETWEEN 12 AND 13",
            name="ck_member_fiscal_profiles_rfc",
        ),
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("series", sa.String(length=10), nullable=False),
        sa.Column("folio", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'requested'"),
        ),
        sa.Column("origin_type", sa.String(length=24), nullable=False),
        sa.Column("origin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_reference", sa.String(length=64), nullable=False),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("receptor_rfc", sa.String(length=13), nullable=False),
        sa.Column("receptor_name", sa.String(length=254), nullable=False),
        sa.Column("receptor_tax_regime", sa.String(length=3), nullable=False),
        sa.Column("receptor_postal_code", sa.String(length=5), nullable=False),
        sa.Column("receptor_cfdi_use", sa.String(length=3), nullable=False),
        sa.Column("receptor_email", sa.String(length=254), nullable=True),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'MXN'"),
        ),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "tax_rate_percent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("16"),
        ),
        sa.Column("payment_form", sa.String(length=2), nullable=False),
        sa.Column(
            "payment_method",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'PUE'"),
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
        sa.Column("cancellation_replacement_uuid", sa.String(length=36), nullable=True),
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
        sa.UniqueConstraint("series", "folio", name="uq_invoices_series_folio"),
        sa.UniqueConstraint("idempotency_key", name="uq_invoices_idempotency_key"),
        sa.UniqueConstraint("uuid", name="uq_invoices_uuid"),
        sa.CheckConstraint(
            "origin_type IN ('sale', 'membership_payment')",
            name="ck_invoices_origin_type",
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'failed', 'stamped', 'cancelled')",
            name="ck_invoices_status",
        ),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0 "
            "AND subtotal_cents + tax_cents = total_cents",
            name="ck_invoices_totals",
        ),
        sa.CheckConstraint("total_cents > 0", name="ck_invoices_total_positive"),
        sa.CheckConstraint("tax_rate_percent >= 0", name="ck_invoices_tax_rate"),
        sa.CheckConstraint("folio > 0", name="ck_invoices_folio_positive"),
    )
    op.create_index("ix_invoices_origin", "invoices", ["origin_type", "origin_id"])
    op.create_index("ix_invoices_status_created", "invoices", ["status", "created_at"])
    op.create_index("ix_invoices_member_created", "invoices", ["member_id", "created_at"])
    op.create_index(
        "uq_invoices_active_origin",
        "invoices",
        ["origin_type", "origin_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )

    op.create_table(
        "invoice_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("sat_product_code", sa.String(length=8), nullable=False),
        sa.Column("sat_unit_code", sa.String(length=3), nullable=False),
        sa.Column("unit_name", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sale_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("invoice_id", "position", name="uq_invoice_items_position"),
        sa.CheckConstraint("position > 0", name="ck_invoice_items_position_positive"),
        sa.CheckConstraint("quantity > 0", name="ck_invoice_items_quantity_positive"),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0 "
            "AND subtotal_cents + tax_cents = total_cents",
            name="ck_invoice_items_totals",
        ),
    )
    op.create_index("ix_invoice_items_invoice", "invoice_items", ["invoice_id"])

    op.create_table(
        "invoice_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
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
        "ix_invoice_events_invoice_time",
        "invoice_events",
        ["invoice_id", "occurred_at"],
    )

    for code, description, role_codes in PERMISSIONS:
        permission_id = _stable_id("permission", code)
        op.execute(
            "INSERT INTO permissions (id, code, description) "
            f"SELECT '{permission_id}'::uuid, '{code}', '{description}' "
            f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{code}')"
        )
        for role_code in role_codes:
            op.execute(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT roles.id, permissions.id FROM roles, permissions "
                f"WHERE roles.code = '{role_code}' AND permissions.code = '{code}' "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            )


def downgrade() -> None:
    for code, _description, _role_codes in PERMISSIONS:
        op.execute(
            "DELETE FROM role_permissions USING roles, permissions "
            "WHERE role_permissions.role_id = roles.id "
            "AND role_permissions.permission_id = permissions.id "
            f"AND permissions.code = '{code}'"
        )
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")

    op.drop_index("ix_invoice_events_invoice_time", table_name="invoice_events")
    op.drop_table("invoice_events")
    op.drop_index("ix_invoice_items_invoice", table_name="invoice_items")
    op.drop_table("invoice_items")
    op.drop_index("uq_invoices_active_origin", table_name="invoices")
    op.drop_index("ix_invoices_member_created", table_name="invoices")
    op.drop_index("ix_invoices_status_created", table_name="invoices")
    op.drop_index("ix_invoices_origin", table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("member_fiscal_profiles")
