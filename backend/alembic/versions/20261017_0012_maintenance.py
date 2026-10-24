"""Create the equipment and maintenance tables.

Adds the fleet registry (``equipment``), the fault/preventive tickets
(``maintenance_tickets``), the append-only technical history
(``maintenance_records``) and the cleaning/inspection rounds
(``maintenance_checklists``).

Equipment is never deleted (retiring is a status), and every ticket/record
references the unit with ``ondelete="RESTRICT"`` so the history survives. A
critical ticket blocks the unit and stores the previous status so resolving can
restore it.

The ``maintenance.report`` permission and its grants are seeded by the
following revision (``20261017_0013``); the ``exercises.equipment_id`` link is
added by ``20261017_0014``.

Revision ID: 20261017_0012
Revises: 20261017_0011
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261017_0012"
down_revision = "20261017_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("serial_number", sa.String(length=80), nullable=True),
        sa.Column("location", sa.String(length=80), nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=True),
        sa.Column("useful_life_months", sa.Integer(), nullable=True),
        sa.Column(
            "purchase_cost_cents", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("status", sa.String(length=20), server_default="operational", nullable=False),
        sa.Column("next_preventive_due", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_equipment_name_nonempty"),
        sa.CheckConstraint(
            "status IN ('operational', 'maintenance', 'out_of_service', 'inspection', 'retired')",
            name="ck_equipment_status",
        ),
        sa.CheckConstraint("purchase_cost_cents >= 0", name="ck_equipment_cost_nonnegative"),
        sa.CheckConstraint(
            "useful_life_months IS NULL OR useful_life_months > 0",
            name="ck_equipment_useful_life_positive",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_equipment_serial",
        "equipment",
        ["serial_number"],
        unique=True,
        postgresql_where=sa.text("serial_number IS NOT NULL AND serial_number <> ''"),
        sqlite_where=sa.text("serial_number IS NOT NULL AND serial_number <> ''"),
    )
    op.create_index("ix_equipment_status", "equipment", ["status"])
    op.create_index("ix_equipment_category", "equipment", ["category"])
    op.create_index("ix_equipment_location", "equipment", ["location"])

    op.create_table(
        "maintenance_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="corrective", nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="medium", nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("reported_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_for", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("cost_cents", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("blocked_equipment", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("previous_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_maintenance_tickets_title_nonempty"),
        sa.CheckConstraint("kind IN ('corrective', 'preventive')", name="ck_maintenance_tickets_kind"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_maintenance_tickets_severity"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'assigned', 'in_progress', 'resolved', 'cancelled')",
            name="ck_maintenance_tickets_status",
        ),
        sa.CheckConstraint("cost_cents >= 0", name="ck_maintenance_tickets_cost_nonnegative"),
        sa.CheckConstraint(
            "status <> 'resolved' OR (resolution_notes IS NOT NULL AND length(trim(resolution_notes)) > 0)",
            name="ck_maintenance_tickets_resolution_required",
        ),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reported_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to"], ["employees.id"], ondelete="RESTRICT"),
    )
    op.create_index("uq_maintenance_tickets_code", "maintenance_tickets", ["code"], unique=True)
    op.create_index(
        "ix_maintenance_tickets_equipment_status",
        "maintenance_tickets",
        ["equipment_id", "status"],
    )
    op.create_index(
        "ix_maintenance_tickets_status_created", "maintenance_tickets", ["status", "created_at"]
    )
    op.create_index("ix_maintenance_tickets_severity", "maintenance_tickets", ["severity"])

    op.create_table(
        "maintenance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cost_cents", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("technician_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(summary)) > 0", name="ck_maintenance_records_summary_nonempty"),
        sa.CheckConstraint(
            "kind IN ('preventive', 'corrective', 'inspection', 'cleaning', 'calibration')",
            name="ck_maintenance_records_kind",
        ),
        sa.CheckConstraint("cost_cents >= 0", name="ck_maintenance_records_cost_nonnegative"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["maintenance_tickets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technician_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_maintenance_records_equipment_performed",
        "maintenance_records",
        ["equipment_id", "performed_at"],
    )
    op.create_index(
        "ix_maintenance_records_kind_performed", "maintenance_records", ["kind", "performed_at"]
    )

    op.create_table(
        "maintenance_checklists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("area", sa.String(length=80), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(area)) > 0", name="ck_maintenance_checklists_area_nonempty"),
        sa.CheckConstraint(
            "result IN ('ok', 'observation', 'pending')", name="ck_maintenance_checklists_result"
        ),
        sa.CheckConstraint(
            "result <> 'observation' OR (observations IS NOT NULL AND length(trim(observations)) > 0)",
            name="ck_maintenance_checklists_observation_required",
        ),
        sa.ForeignKeyConstraint(["performed_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_maintenance_checklists_area_performed",
        "maintenance_checklists",
        ["area", "performed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_checklists_area_performed", table_name="maintenance_checklists")
    op.drop_table("maintenance_checklists")
    op.drop_index("ix_maintenance_records_kind_performed", table_name="maintenance_records")
    op.drop_index("ix_maintenance_records_equipment_performed", table_name="maintenance_records")
    op.drop_table("maintenance_records")
    op.drop_index("ix_maintenance_tickets_severity", table_name="maintenance_tickets")
    op.drop_index("ix_maintenance_tickets_status_created", table_name="maintenance_tickets")
    op.drop_index("ix_maintenance_tickets_equipment_status", table_name="maintenance_tickets")
    op.drop_index("uq_maintenance_tickets_code", table_name="maintenance_tickets")
    op.drop_table("maintenance_tickets")
    op.drop_index("ix_equipment_location", table_name="equipment")
    op.drop_index("ix_equipment_category", table_name="equipment")
    op.drop_index("ix_equipment_status", table_name="equipment")
    op.drop_index("uq_equipment_serial", table_name="equipment")
    op.drop_table("equipment")
