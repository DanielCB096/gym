"""Widen ``member_notifications.kind`` with the reservation confirmation.

A reservation is a commitment with a date and an hour. The member who books in
the app sees the confirmation screen once and then has no record of it, and a
seat booked at the counter or by phone would never be announced at all. The
inbox now writes ``class_reserved`` when a seat is held (never when the member
lands on the waitlist, which has its own promotion notice and a visible
position).

PostgreSQL stores a CHECK constraint as a single expression, so widening the
allowed list means dropping and re-adding it under the same name.

Revision ID: 20261029_0052
Revises: 20261029_0051
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0052"
down_revision = "20261029_0051"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
    "'invoice_cancelled', 'class_reminder'"
)
NEW_KINDS = OLD_KINDS + ", 'class_reserved'"


def upgrade() -> None:
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notifications WHERE kind IN ('class_reserved')"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan confirmaciones de reserva "
            f"({remaining} filas); bórralas primero si de verdad quieres retirar el tipo"
        )
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )
