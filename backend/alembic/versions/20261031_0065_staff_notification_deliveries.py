"""Queue the attendance notices as email.

The attendance cycle only speaks through the panel bell: an employee whose mark
was corrected, a supervisor with a request waiting and an owner with an expired
one find out when they open the panel. This revision starts the email path with
the two pieces that must be transactional: one delivery row per staff notice
(written with the notice, unique per notice so a replay cannot queue twice) and
the club switch that decides whether the attendance notices are queued at all.
Sending, retry and the delivery view come in a later revision.

Revision ID: 20261031_0065
Revises: 20261031_0064
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0065"
down_revision = "20261031_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staffing_settings",
        sa.Column(
            "attendance_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "staffing_settings_events",
        sa.Column(
            "previous_attendance_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "staffing_settings_events",
        sa.Column(
            "attendance_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.create_table(
        "staff_notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notice_id", sa.Uuid(), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["notice_id"],
            ["staff_notifications.id"],
            name="fk_staff_notification_deliveries_notice",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "notice_id", name="uq_staff_notification_deliveries_notice"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed')",
            name="ck_staff_notification_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_staff_notification_deliveries_attempts"
        ),
    )
    op.create_index(
        "ix_staff_notification_deliveries_status_created",
        "staff_notification_deliveries",
        ["status", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    queued = bind.execute(
        sa.text("SELECT count(*) FROM staff_notification_deliveries")
    ).scalar()
    if queued:
        raise RuntimeError(
            "No se puede revertir mientras existan entregas encoladas "
            f"({queued}); se perdería la cola de correos"
        )

    op.drop_index(
        "ix_staff_notification_deliveries_status_created",
        table_name="staff_notification_deliveries",
    )
    op.drop_table("staff_notification_deliveries")
    op.drop_column("staffing_settings_events", "attendance_email_enabled")
    op.drop_column("staffing_settings_events", "previous_attendance_email_enabled")
    op.drop_column("staffing_settings", "attendance_email_enabled")
