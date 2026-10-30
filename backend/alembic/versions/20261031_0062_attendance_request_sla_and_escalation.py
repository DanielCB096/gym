"""Deadline and escalation for pending attendance change requests.

A request used to stay pending forever: the partial unique index blocked the mark
indefinitely and nobody above the supervisor was told. This revision gives the
club a term (``staffing_settings.attendance_request_sla_hours``, zero meaning no
term), freezes it on each request as ``due_at`` so a later policy change does not
re-time what is already waiting, and adds the ``attendance_request_overdue``
notice kind that escalates an expired request to the owner.

Pending requests that already existed at upgrade time get the default 24-hour
term measured from their creation, because they had been waiting with no term at
all. Decided requests keep ``due_at`` NULL: nothing is pending for them.

Revision ID: 20261031_0062
Revises: 20261031_0061
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0062"
down_revision = "20261031_0061"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring', "
    "'attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
    "'attendance_request_approved', 'attendance_request_rejected'"
)
NEW_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring', "
    "'attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
    "'attendance_request_approved', 'attendance_request_rejected', "
    "'attendance_request_overdue'"
)


def upgrade() -> None:
    op.add_column(
        "staffing_settings",
        sa.Column(
            "attendance_request_sla_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
    )
    op.create_check_constraint(
        "ck_staffing_settings_request_sla",
        "staffing_settings",
        "attendance_request_sla_hours >= 0 AND attendance_request_sla_hours <= 720",
    )

    op.add_column(
        "staffing_settings_events",
        sa.Column(
            "previous_attendance_request_sla_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
    )
    op.add_column(
        "staffing_settings_events",
        sa.Column(
            "attendance_request_sla_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
    )

    op.add_column(
        "staff_attendance_requests",
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE staff_attendance_requests "
        "SET due_at = created_at + interval '24 hours' "
        "WHERE status = 'pending' AND due_at IS NULL"
    )
    op.create_index(
        "ix_staff_attendance_requests_status_due",
        "staff_attendance_requests",
        ["status", "due_at"],
    )

    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind",
        "staff_notifications",
        f"kind IN ({NEW_KINDS})",
    )


def downgrade() -> None:
    bind = op.get_bind()
    overdue = bind.execute(
        sa.text(
            "SELECT count(*) FROM staff_notifications "
            "WHERE kind = 'attendance_request_overdue'"
        )
    ).scalar()
    if overdue:
        raise RuntimeError(
            "No se puede revertir mientras existan avisos de solicitud vencida "
            f"({overdue}); bórralos primero"
        )

    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind",
        "staff_notifications",
        f"kind IN ({OLD_KINDS})",
    )

    op.drop_index(
        "ix_staff_attendance_requests_status_due", table_name="staff_attendance_requests"
    )
    op.drop_column("staff_attendance_requests", "due_at")
    op.drop_column("staffing_settings_events", "attendance_request_sla_hours")
    op.drop_column("staffing_settings_events", "previous_attendance_request_sla_hours")
    op.drop_constraint(
        "ck_staffing_settings_request_sla", "staffing_settings", type_="check"
    )
    op.drop_column("staffing_settings", "attendance_request_sla_hours")