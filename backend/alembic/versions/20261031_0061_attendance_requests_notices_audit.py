"""Attendance change requests, employee notices and policy audit.

Three gaps close here. The employee now hears about a mark that was corrected
or voided on their behalf, so the staff inbox gains two informational kinds and
three more for the request cycle. The employee can also *ask* for a change
instead of only receiving one: ``staff_attendance_requests`` keeps the
justification and the supervisor's decision, while the applied change still goes
through the regular correction/annulment path. Finally,
``staffing_settings_events`` records who changed the club attendance policy and
the previous values, which ``updated_at`` alone could not tell.

Revision ID: 20261031_0061
Revises: 20261030_0060
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261031_0061"
down_revision = "20261030_0060"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring'"
)
NEW_KINDS = (
    "'workout_pending_review', 'maintenance_ticket_assigned', 'kiosk_token_expiring', "
    "'attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
    "'attendance_request_approved', 'attendance_request_rejected'"
)


def upgrade() -> None:
    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind",
        "staff_notifications",
        f"kind IN ({NEW_KINDS})",
    )

    op.create_table(
        "staff_attendance_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attendance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_attendance.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("mark", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("justification", sa.String(length=500), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column(
            "decided_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "mark IN ('check_in', 'check_out')", name="ck_staff_attendance_requests_mark"
        ),
        sa.CheckConstraint(
            "action IN ('correct', 'void')", name="ck_staff_attendance_requests_action"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_staff_attendance_requests_status",
        ),
        sa.CheckConstraint(
            "(action = 'correct' AND proposed_at IS NOT NULL) OR "
            "(action = 'void' AND proposed_at IS NULL)",
            name="ck_staff_attendance_requests_proposed",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND decided_by IS NULL AND decided_at IS NULL) OR "
            "(status <> 'pending' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_staff_attendance_requests_decision",
        ),
    )
    op.create_index(
        "ix_staff_attendance_requests_status_time",
        "staff_attendance_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_staff_attendance_requests_employee_time",
        "staff_attendance_requests",
        ["employee_id", "created_at"],
    )
    op.create_index(
        "uq_staff_attendance_requests_pending",
        "staff_attendance_requests",
        ["attendance_id", "mark", "action"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "staffing_settings_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "previous_check_in_early_grace_minutes", sa.Integer(), nullable=False
        ),
        sa.Column("previous_lateness_tolerance_minutes", sa.Integer(), nullable=False),
        sa.Column("check_in_early_grace_minutes", sa.Integer(), nullable=False),
        sa.Column("lateness_tolerance_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_staffing_settings_events_changed", "staffing_settings_events", ["changed_at"]
    )

    op.create_index(
        "ix_staff_attendance_events_type_time",
        "staff_attendance_events",
        ["event_type", "occurred_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    requests = bind.execute(sa.text("SELECT count(*) FROM staff_attendance_requests")).scalar()
    if requests:
        raise RuntimeError(
            "No se puede revertir mientras existan solicitudes de cambio de asistencia "
            f"({requests}); bórralas primero"
        )
    notices = bind.execute(
        sa.text(
            "SELECT count(*) FROM staff_notifications WHERE kind IN "
            "('attendance_corrected', 'attendance_voided', 'attendance_request_pending', "
            "'attendance_request_approved', 'attendance_request_rejected')"
        )
    ).scalar()
    if notices:
        raise RuntimeError(
            "No se puede revertir mientras existan avisos de asistencia en la bandeja "
            f"({notices}); bórralos primero"
        )

    op.drop_index("ix_staff_attendance_events_type_time", table_name="staff_attendance_events")
    op.drop_index("ix_staffing_settings_events_changed", table_name="staffing_settings_events")
    op.drop_table("staffing_settings_events")
    op.drop_index(
        "uq_staff_attendance_requests_pending", table_name="staff_attendance_requests"
    )
    op.drop_index(
        "ix_staff_attendance_requests_employee_time", table_name="staff_attendance_requests"
    )
    op.drop_index(
        "ix_staff_attendance_requests_status_time", table_name="staff_attendance_requests"
    )
    op.drop_table("staff_attendance_requests")

    op.drop_constraint("ck_staff_notifications_kind", "staff_notifications", type_="check")
    op.create_check_constraint(
        "ck_staff_notifications_kind",
        "staff_notifications",
        f"kind IN ({OLD_KINDS})",
    )