"""Let an already registered staff mark be corrected with an audit trail.

The employee's own marks stay immutable from self-service, but reception
sometimes needs to fix a wrong time. The attendance row keeps the current
value and the append-only event log gains two event types for the corrections,
so the original punch and the corrected one remain in the history with the
operator and the reason. The event type column widens to fit the new values.

Revision ID: 20261030_0059
Revises: 20261030_0058
"""

from alembic import op
import sqlalchemy as sa

revision = "20261030_0059"
down_revision = "20261030_0058"
branch_labels = None
depends_on = None

OLD_TYPES = "'check_in', 'check_out'"
NEW_TYPES = "'check_in', 'check_out', 'check_in_correction', 'check_out_correction'"


def upgrade() -> None:
    op.alter_column(
        "staff_attendance_events",
        "event_type",
        type_=sa.String(length=32),
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )
    op.drop_constraint("ck_staff_attendance_events_type", "staff_attendance_events", type_="check")
    op.create_check_constraint(
        "ck_staff_attendance_events_type",
        "staff_attendance_events",
        f"event_type IN ({NEW_TYPES})",
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM staff_attendance_events WHERE event_type IN "
            "('check_in_correction', 'check_out_correction')"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan correcciones de asistencia "
            f"({remaining} filas); bórralas primero si de verdad quieres retirar los tipos"
        )
    op.drop_constraint("ck_staff_attendance_events_type", "staff_attendance_events", type_="check")
    op.create_check_constraint(
        "ck_staff_attendance_events_type",
        "staff_attendance_events",
        f"event_type IN ({OLD_TYPES})",
    )
    op.alter_column(
        "staff_attendance_events",
        "event_type",
        type_=sa.String(length=16),
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
