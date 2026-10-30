"""Configurable attendance policy and annulment of a registered mark.

The club decides how early a check-in opens and how many minutes after the
start still count as on time, so both live in a single-row ``staffing_settings``
table instead of the service constant. A mark recorded by mistake can now be
voided with a reason: the attendance row keeps its history but stops occupying
the shift, which is why its one-attendance-per-shift rule becomes a partial
unique index. The event log gains the two annulment types.

Revision ID: 20261030_0060
Revises: 20261030_0059
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261030_0060"
down_revision = "20261030_0059"
branch_labels = None
depends_on = None

OLD_TYPES = "'check_in', 'check_out', 'check_in_correction', 'check_out_correction'"
NEW_TYPES = (
    "'check_in', 'check_out', 'check_in_correction', 'check_out_correction', "
    "'check_out_voided', 'attendance_voided'"
)


def upgrade() -> None:
    op.create_table(
        "staffing_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "check_in_early_grace_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("15"),
        ),
        sa.Column(
            "lateness_tolerance_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "check_in_early_grace_minutes >= 0 AND check_in_early_grace_minutes <= 240",
            name="ck_staffing_settings_early_grace",
        ),
        sa.CheckConstraint(
            "lateness_tolerance_minutes >= 0 AND lateness_tolerance_minutes <= 240",
            name="ck_staffing_settings_lateness",
        ),
    )

    op.add_column(
        "staff_attendance", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "staff_attendance",
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_staff_attendance_voided_by",
        "staff_attendance",
        "app_users",
        ["voided_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "staff_attendance", sa.Column("void_reason", sa.String(length=300), nullable=True)
    )

    op.drop_constraint("uq_staff_attendance_shift", "staff_attendance", type_="unique")
    op.create_index(
        "uq_staff_attendance_shift",
        "staff_attendance",
        ["shift_id"],
        unique=True,
        postgresql_where=sa.text("voided_at IS NULL"),
    )

    op.drop_constraint("ck_staff_attendance_events_type", "staff_attendance_events", type_="check")
    op.create_check_constraint(
        "ck_staff_attendance_events_type",
        "staff_attendance_events",
        f"event_type IN ({NEW_TYPES})",
    )


def downgrade() -> None:
    bind = op.get_bind()
    voided = bind.execute(
        sa.text("SELECT count(*) FROM staff_attendance WHERE voided_at IS NOT NULL")
    ).scalar()
    events = bind.execute(
        sa.text(
            "SELECT count(*) FROM staff_attendance_events WHERE event_type IN "
            "('check_out_voided', 'attendance_voided')"
        )
    ).scalar()
    if voided or events:
        raise RuntimeError(
            "No se puede revertir mientras existan marcas anuladas "
            f"({voided} asistencias, {events} eventos); bórralas primero"
        )

    op.drop_constraint("ck_staff_attendance_events_type", "staff_attendance_events", type_="check")
    op.create_check_constraint(
        "ck_staff_attendance_events_type",
        "staff_attendance_events",
        f"event_type IN ({OLD_TYPES})",
    )

    op.drop_index("uq_staff_attendance_shift", table_name="staff_attendance")
    op.create_unique_constraint(
        "uq_staff_attendance_shift", "staff_attendance", ["shift_id"]
    )

    op.drop_column("staff_attendance", "void_reason")
    op.drop_constraint("fk_staff_attendance_voided_by", "staff_attendance", type_="foreignkey")
    op.drop_column("staff_attendance", "voided_by")
    op.drop_column("staff_attendance", "voided_at")

    op.drop_table("staffing_settings")
