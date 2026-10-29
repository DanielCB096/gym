"""Widen ``member_notifications.kind`` with class cancellation and reschedule.

A cancelled or moved class leaves the member with a seat that no longer means
what it did when they booked it. The inbox now carries both facts: one notice
per affected member when the session is cancelled, and one per move with the
old and the new slot when the time changes. The waitlisted are included,
because a queue waiting for a class that will not happen (or moved) is stuck
on the wrong schedule.

PostgreSQL stores a CHECK constraint as a single expression, so widening the
allowed list means dropping and re-adding it under the same name.

Revision ID: 20261029_0053
Revises: 20261029_0052
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0053"
down_revision = "20261029_0052"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
    "'invoice_cancelled', 'class_reminder', 'class_reserved'"
)
NEW_KINDS = OLD_KINDS + ", 'class_cancelled', 'class_rescheduled'"


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
            "('class_cancelled', 'class_rescheduled')"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan avisos de clase cancelada o "
            f"reprogramada ({remaining} filas); bórralos primero si de verdad "
            "quieres retirar los tipos"
        )
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )
