"""Credit notes (CFDI de egreso) linked to a stamped income invoice.

Widens ``invoices.origin_type`` with ``credit_note`` and stores the relation to
the adjusted invoice, the reason and an optional operator note. A credit note
always points to an existing invoice (self foreign key restricted on delete), so
a comprobante with live notes cannot be removed.

The live-origin unique index excludes credit notes: one income invoice accepts
several partial notes. The remaining balance is enforced in the service, which
locks the original row before adding a note.

Revision ID: 20261025_0026
Revises: 20261024_0025
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261025_0026"
down_revision = "20261024_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column(
            "related_invoice_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "invoices", sa.Column("credit_note_reason", sa.String(length=24), nullable=True)
    )
    op.add_column(
        "invoices", sa.Column("credit_note_note", sa.String(length=300), nullable=True)
    )
    op.create_foreign_key(
        "fk_invoices_related_invoice",
        "invoices",
        "invoices",
        ["related_invoice_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("ck_invoices_origin_type", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_origin_type",
        "invoices",
        "origin_type IN ('sale', 'membership_payment', 'global', 'credit_note')",
    )
    op.create_check_constraint(
        "ck_invoices_credit_note",
        "invoices",
        "(origin_type = 'credit_note' AND related_invoice_id IS NOT NULL "
        "AND credit_note_reason IS NOT NULL) OR "
        "(origin_type <> 'credit_note' AND related_invoice_id IS NULL "
        "AND credit_note_reason IS NULL AND credit_note_note IS NULL)",
    )
    op.create_index("ix_invoices_related", "invoices", ["related_invoice_id"])

    op.drop_index("uq_invoices_active_origin", table_name="invoices")
    op.create_index(
        "uq_invoices_active_origin",
        "invoices",
        ["origin_type", "origin_id"],
        unique=True,
        postgresql_where=sa.text(
            "status <> 'cancelled' AND origin_type <> 'credit_note'"
        ),
        sqlite_where=sa.text("status <> 'cancelled' AND origin_type <> 'credit_note'"),
    )


def downgrade() -> None:
    has_credit_note = op.get_bind().execute(
        sa.text("SELECT 1 FROM invoices WHERE origin_type = 'credit_note' LIMIT 1")
    ).first()
    if has_credit_note is not None:
        raise RuntimeError(
            "No se puede revertir la migración mientras existan notas de crédito."
        )
    op.drop_index("uq_invoices_active_origin", table_name="invoices")
    op.create_index(
        "uq_invoices_active_origin",
        "invoices",
        ["origin_type", "origin_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
        sqlite_where=sa.text("status <> 'cancelled'"),
    )
    op.drop_index("ix_invoices_related", table_name="invoices")
    op.drop_constraint("ck_invoices_credit_note", "invoices", type_="check")
    op.drop_constraint("ck_invoices_origin_type", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_origin_type",
        "invoices",
        "origin_type IN ('sale', 'membership_payment', 'global')",
    )
    op.drop_constraint("fk_invoices_related_invoice", "invoices", type_="foreignkey")
    op.drop_column("invoices", "credit_note_note")
    op.drop_column("invoices", "credit_note_reason")
    op.drop_column("invoices", "related_invoice_id")
