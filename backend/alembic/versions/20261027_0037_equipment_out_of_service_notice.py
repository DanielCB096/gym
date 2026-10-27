"""Widen ``member_notifications.kind`` with the equipment outage notice.

A machine going out of service is not a maintenance-module event only: every
member whose live routine version contains an exercise bound to that machine
loses a step of their plan, and today nobody tells them. The notice is one row
per affected member, so the inbox stays the single place the app reads.

PostgreSQL stores a CHECK constraint as a single expression, so widening the
allowed list means dropping and re-adding it. The constraint keeps its name so
the application code, the preview database and production stay in sync.

Revision ID: 20261027_0037
Revises: 20261027_0036
"""

from alembic import op
import sqlalchemy as sa

revision = "20261027_0037"
down_revision = "20261027_0036"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring'"
)
NEW_KINDS = OLD_KINDS + ", 'equipment_out_of_service'"


def upgrade() -> None:
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notifications WHERE kind = 'equipment_out_of_service'"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan avisos de equipo fuera de servicio "
            f"({remaining} filas); bórralos primero si de verdad quieres retirar el tipo"
        )
    op.drop_constraint("ck_member_notifications_kind", "member_notifications", type_="check")
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )
