"""Widen ``member_notifications.kind`` with the upcoming-class reminder.

The member books a class and then only sees it again by reopening the classes
screen. The inbox now writes a reminder when the class is 24 hours away and
again when it is 2 hours away; like the membership notice it is materialised on
read, because the project still has no scheduler.

PostgreSQL stores a CHECK constraint as a single expression, so widening the
allowed list means dropping and re-adding it. The constraint keeps its name so
the application code, the preview database and production stay in sync.

Revision ID: 20261029_0051
Revises: 20261029_0050
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0051"
down_revision = "20261029_0050"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
    "'invoice_cancelled'"
)
NEW_KINDS = OLD_KINDS + ", 'class_reminder'"


def upgrade() -> None:
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notifications WHERE kind IN ('class_reminder')"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan recordatorios de clase "
            f"({remaining} filas); bórralos primero si de verdad quieres retirar el tipo"
        )
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )
