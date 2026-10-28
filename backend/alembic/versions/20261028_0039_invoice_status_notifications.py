"""Widen ``member_notifications.kind`` with the invoice status notices.

The member can now request an invoice and download it, but the club stamps and
cancels it later. Until this migration the member only found out by reopening
the invoices screen. The billing service now writes one of three notices in the
same transaction that changes the invoice state.

PostgreSQL stores a CHECK constraint as a single expression, so widening the
allowed list means dropping and re-adding it. The constraint keeps its name so
the application code, the preview database and production stay in sync.

Revision ID: 20261028_0039
Revises: 20261027_0038
"""

from alembic import op
import sqlalchemy as sa

revision = "20261028_0039"
down_revision = "20261027_0038"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service'"
)
NEW_KINDS = OLD_KINDS + ", 'invoice_stamped', 'invoice_failed', 'invoice_cancelled'"


def upgrade() -> None:
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notifications WHERE kind IN "
            "('invoice_stamped', 'invoice_failed', 'invoice_cancelled')"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan avisos de estado de factura "
            f"({remaining} filas); bórralos primero si de verdad quieres retirar el tipo"
        )
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )
