"""Extend the member notification kinds with the physiotherapy appointments.

Booking, moving and cancelling a physiotherapy appointment from reception append
a notice to the member's inbox. The three kinds reuse the same table and CHECK as
the rest of the inbox, so the constraint is widened in place; the downgrade
refuses to run while any row of the new kinds exists instead of deleting them.

Revision ID: 20261029_0057
Revises: 20261029_0056
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0057"
down_revision = "20261029_0056"
branch_labels = None
depends_on = None

NEW_KINDS = (
    "'physio_appointment_scheduled', 'physio_appointment_cancelled', "
    "'physio_appointment_rescheduled'"
)
OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
    "'invoice_cancelled', 'class_reminder', 'class_reserved', "
    "'class_cancelled', 'class_rescheduled'"
)


def upgrade() -> None:
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind",
        "member_notifications",
        f"kind IN ({OLD_KINDS}, {NEW_KINDS})",
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notifications WHERE kind IN "
            "('physio_appointment_scheduled', 'physio_appointment_cancelled', "
            "'physio_appointment_rescheduled')"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan avisos de citas de fisioterapia "
            f"({remaining} filas); bórralos primero si de verdad quieres retirar los "
            "tipos"
        )
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )
