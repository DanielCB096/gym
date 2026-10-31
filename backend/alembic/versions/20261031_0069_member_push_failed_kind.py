"""Alert the staff when a member push runs out of attempts.

Until now a push that failed three times stayed ``failed`` in the panel queue
and nobody was told: the notice was in the member's inbox, the phone never rang
and the club only found out by opening the card. This revision adds the
``member_push_failed`` staff notice kind, which the push pass writes for every
account that operates the queue.

Revision ID: 20261031_0069
Revises: 20261031_0068
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20261031_0069"
down_revision = "20261031_0068"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring', "
    "'attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
    "'attendance_request_approved', 'attendance_request_rejected', "
    "'attendance_request_overdue'"
)
NEW_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring', "
    "'attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
    "'attendance_request_approved', 'attendance_request_rejected', "
    "'attendance_request_overdue', 'member_push_failed'"
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
                "WHERE kind = 'member_push_failed'"
            )
        ).scalar()
        if alerts:
            raise RuntimeError(
                "No se puede revertir mientras existan avisos de push sin entregar "
                f"({alerts}); bórralos primero"
            )

    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind",
        "staff_notifications",
        f"kind IN ({OLD_KINDS})",
    )
