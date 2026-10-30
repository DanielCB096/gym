"""Link an approved attendance request to the event it wrote.

Approving a request applies the change through the regular correction or
annulment path, so until now the only way to tell a request-driven change from a
panel one was to cross ``staff_attendance_requests.decided_at`` with the event's
``occurred_at``. This revision stores the link on the event itself:
``staff_attendance_events.attendance_request_id`` (nullable, ``ON DELETE SET
NULL`` so removing a request keeps the mark history). A NULL means the change came
straight from the panel.

No backfill: the old rows stay unlinked rather than guessing by timestamp, which
would be ambiguous when a supervisor decided two requests in the same instant.

Revision ID: 20261031_0063
Revises: 20261031_0062
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0063"
down_revision = "20261031_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff_attendance_events",
        sa.Column("attendance_request_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_staff_attendance_events_request_link",
        "staff_attendance_events",
        "staff_attendance_requests",
        ["attendance_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_staff_attendance_events_request_link",
        "staff_attendance_events",
        ["attendance_request_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    linked = bind.execute(
        sa.text(
            "SELECT count(*) FROM staff_attendance_events "
            "WHERE attendance_request_id IS NOT NULL"
        )
    ).scalar()
    if linked:
        raise RuntimeError(
            "No se puede revertir mientras existan eventos enlazados a una "
            f"solicitud ({linked}); se perdería el vínculo"
        )

    op.drop_index(
        "ix_staff_attendance_events_request_link",
        table_name="staff_attendance_events",
    )
    op.drop_constraint(
        "fk_staff_attendance_events_request_link",
        "staff_attendance_events",
        type_="foreignkey",
    )
    op.drop_column("staff_attendance_events", "attendance_request_id")
