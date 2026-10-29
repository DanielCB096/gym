"""Kiosk token expiry notices in the staff inbox.

The kiosk token lives 90 days and is rotated from the panel, but nothing warned
the people who can rotate it before the tablet stopped working. The new
``kiosk_token_expiring`` kind is emitted lazily when the inbox is read, because
the project still has no scheduler; the CHECK has to allow the value.

Revision ID: 20261029_0046
Revises: 20261028_0045
"""

from alembic import op

revision = "20261029_0046"
down_revision = "20261028_0045"
branch_labels = None
depends_on = None

OLD_KINDS = "kind IN ('workout_pending_review', 'maintenance_ticket_assigned')"
NEW_KINDS = (
    "kind IN ('workout_pending_review', 'maintenance_ticket_assigned', "
    "'kiosk_token_expiring')"
)


def upgrade() -> None:
    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind", "staff_notifications", NEW_KINDS
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM staff_notifications WHERE kind = 'kiosk_token_expiring'"
    )
    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind", "staff_notifications", OLD_KINDS
    )
