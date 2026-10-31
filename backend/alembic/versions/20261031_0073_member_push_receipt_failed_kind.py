"""Alert the staff when Expo answers a push receipt with an error.

ADR-062 stored the receipt beside the queue but left an ``error`` answer visible
only to whoever opened the panel. This revision adds the
``member_push_receipt_failed`` staff notice kind, written by the receipt pass for
every account that operates the queue when the phone did not get the message for
a reason other than the device being gone.

Revision ID: 20261031_0073
Revises: 20261031_0072
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20261031_0073"
down_revision = "20261031_0072"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring', "
    "'attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
    "'attendance_request_approved', 'attendance_request_rejected', "
    "'attendance_request_overdue', 'member_push_failed'"
)
NEW_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring', "
    "'attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
    "'attendance_request_approved', 'attendance_request_rejected', "
    "'attendance_request_overdue', 'member_push_failed', "
    "'member_push_receipt_failed'"
)


def upgrade() -> None:
    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind",
        "staff_notifications",
        f"kind IN ({NEW_KINDS})",
    )


def downgrade() -> None:
    # Offline SQL generation has no connection, so there are no rows to count.
    if not context.is_offline_mode():
        alerts = op.get_bind().execute(
            sa.text(
                "SELECT count(*) FROM staff_notifications "
                "WHERE kind = 'member_push_receipt_failed'"
            )
        ).scalar()
        if alerts:
            raise RuntimeError(
                "No se puede revertir mientras existan avisos de acuse con error "
                f"({alerts}); bórralos primero"
            )

    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind",
        "staff_notifications",
        f"kind IN ({OLD_KINDS})",
    )
