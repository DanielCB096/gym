"""Allow the member inbox to announce equipment returning to service.

Revision ID: 20261031_0077
Revises: 20261031_0075
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0077"
down_revision = "20261031_0075"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
    "'invoice_cancelled', 'class_reminder', 'class_reserved', 'class_cancelled', "
    "'class_rescheduled', 'physio_appointment_scheduled', "
    "'physio_appointment_cancelled', 'physio_appointment_rescheduled', "
    "'physio_reminder'"
)
NEW_KINDS = OLD_KINDS + ", 'equipment_back_in_service'"


def upgrade() -> None:
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notifications "
            "WHERE kind = 'equipment_back_in_service'"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan avisos de regreso de equipo "
            f"({remaining} filas); bórralos primero si de verdad quieres retirar el tipo"
        )
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )
