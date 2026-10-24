"""Equipment and facility maintenance.

First increment of the maintenance module. The spec (``docs/02-modulos/mantenimiento-equipo.md``)
lists a dozen draft entities (brand, category, location, supplier, purchase
order, cost...). Here they collapse into four tables plus columns:

* ``equipment`` is the fleet registry. Brand, category and location are plain
  columns (the spec models them as catalogues; a first increment does not need
  separate tables), and ``status`` carries the service state the members see.
  Equipment is never deleted: a unit that leaves service is *retired* so its
  history survives.
* ``maintenance_tickets`` are reported faults or scheduled preventives, with a
  lifecycle ``open -> assigned -> in_progress -> resolved`` (or ``cancelled``).
  A critical ticket blocks the equipment (status ``out_of_service``) and the
  prior status is kept in ``previous_status`` so resolving restores it.
* ``maintenance_records`` are the append-only technical history: every executed
  job (preventive, corrective, inspection, cleaning, calibration) is a new row.
  A record may optionally point back at the ticket that triggered it.
* ``maintenance_checklists`` record the cleaning/inspection rounds per area.

Suppliers, purchase orders and replacement budgeting are deliberately out of
this first increment (they belong with purchasing); they are tracked in
``docs/deuda-tecnica.md``.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel

EQUIPMENT_STATUSES = ("operational", "maintenance", "out_of_service", "inspection", "retired")
# Anything but ``retired`` still counts as part of the working fleet.
LIVE_EQUIPMENT_STATUSES = ("operational", "maintenance", "out_of_service", "inspection")
# Equipment members cannot use right now (drives the service status per area).
UNAVAILABLE_EQUIPMENT_STATUSES = ("maintenance", "out_of_service")

TICKET_STATUSES = ("open", "assigned", "in_progress", "resolved", "cancelled")
OPEN_TICKET_STATUSES = ("open", "assigned", "in_progress")
TICKET_KINDS = ("corrective", "preventive")
TICKET_SEVERITIES = ("low", "medium", "high", "critical")
# Severities that take the equipment out of service on report.
BLOCKING_SEVERITIES = ("critical",)

RECORD_KINDS = ("preventive", "corrective", "inspection", "cleaning", "calibration")
CHECKLIST_RESULTS = ("ok", "observation", "pending")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Equipment(SQLModel, table=True):
    """One physical machine or installation in the fleet."""

    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_equipment_name_nonempty"),
        CheckConstraint(
            "status IN ('operational', 'maintenance', 'out_of_service', 'inspection', 'retired')",
            name="ck_equipment_status",
        ),
        CheckConstraint("purchase_cost_cents >= 0", name="ck_equipment_cost_nonnegative"),
        CheckConstraint(
            "useful_life_months IS NULL OR useful_life_months > 0",
            name="ck_equipment_useful_life_positive",
        ),
        # A serial number identifies one unit; two units cannot share it.
        Index(
            "uq_equipment_serial",
            "serial_number",
            unique=True,
            postgresql_where=text("serial_number IS NOT NULL AND serial_number <> ''"),
            sqlite_where=text("serial_number IS NOT NULL AND serial_number <> ''"),
        ),
        Index("ix_equipment_status", "status"),
        Index("ix_equipment_category", "category"),
        Index("ix_equipment_location", "location"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=160)
    category: str = Field(max_length=60)
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    serial_number: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=80)
    acquired_on: date | None = Field(default=None, sa_column=Column(Date))
    useful_life_months: int | None = Field(default=None, sa_type=Integer)
    purchase_cost_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    status: str = Field(
        default="operational",
        sa_column=Column(String(20), nullable=False, server_default=text("'operational'")),
    )
    next_preventive_due: date | None = Field(default=None, sa_column=Column(Date))
    notes: str | None = Field(default=None, sa_column=Column(Text))
    retired_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class MaintenanceTicket(SQLModel, table=True):
    """A reported fault or a scheduled preventive job."""

    __tablename__ = "maintenance_tickets"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_maintenance_tickets_title_nonempty"),
        CheckConstraint("kind IN ('corrective', 'preventive')", name="ck_maintenance_tickets_kind"),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_maintenance_tickets_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'assigned', 'in_progress', 'resolved', 'cancelled')",
            name="ck_maintenance_tickets_status",
        ),
        CheckConstraint("cost_cents >= 0", name="ck_maintenance_tickets_cost_nonnegative"),
        # A resolved ticket must explain what was done.
        CheckConstraint(
            "status <> 'resolved' OR (resolution_notes IS NOT NULL AND length(trim(resolution_notes)) > 0)",
            name="ck_maintenance_tickets_resolution_required",
        ),
        Index("uq_maintenance_tickets_code", "code", unique=True),
        Index("ix_maintenance_tickets_equipment_status", "equipment_id", "status"),
        Index("ix_maintenance_tickets_status_created", "status", "created_at"),
        Index("ix_maintenance_tickets_severity", "severity"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=24)
    equipment_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
        )
    )
    kind: str = Field(
        default="corrective",
        sa_column=Column(String(16), nullable=False, server_default=text("'corrective'")),
    )
    severity: str = Field(
        default="medium",
        sa_column=Column(String(16), nullable=False, server_default=text("'medium'")),
    )
    title: str = Field(max_length=160)
    description: str | None = Field(default=None, sa_column=Column(Text))
    status: str = Field(
        default="open",
        sa_column=Column(String(16), nullable=False, server_default=text("'open'")),
    )
    reported_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    reported_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    assigned_to: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT")),
    )
    assigned_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    scheduled_for: date | None = Field(default=None, sa_column=Column(Date))
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    resolution_notes: str | None = Field(default=None, sa_column=Column(Text))
    cost_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    blocked_equipment: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    # Equipment status before this ticket blocked it, so resolving can restore it.
    previous_status: str | None = Field(default=None, max_length=20)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class MaintenanceRecord(SQLModel, table=True):
    """Append-only technical history entry for an equipment."""

    __tablename__ = "maintenance_records"
    __table_args__ = (
        CheckConstraint("length(trim(summary)) > 0", name="ck_maintenance_records_summary_nonempty"),
        CheckConstraint(
            "kind IN ('preventive', 'corrective', 'inspection', 'cleaning', 'calibration')",
            name="ck_maintenance_records_kind",
        ),
        CheckConstraint("cost_cents >= 0", name="ck_maintenance_records_cost_nonnegative"),
        Index("ix_maintenance_records_equipment_performed", "equipment_id", "performed_at"),
        Index("ix_maintenance_records_kind_performed", "kind", "performed_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipment_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
        )
    )
    ticket_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("maintenance_tickets.id", ondelete="RESTRICT")
        ),
    )
    kind: str = Field(sa_column=Column(String(16), nullable=False))
    summary: str = Field(max_length=200)
    notes: str | None = Field(default=None, sa_column=Column(Text))
    performed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    cost_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    technician_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT")),
    )
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class MaintenanceChecklist(SQLModel, table=True):
    """Cleaning / inspection round for one area."""

    __tablename__ = "maintenance_checklists"
    __table_args__ = (
        CheckConstraint("length(trim(area)) > 0", name="ck_maintenance_checklists_area_nonempty"),
        CheckConstraint(
            "result IN ('ok', 'observation', 'pending')", name="ck_maintenance_checklists_result"
        ),
        # An observation must be written down.
        CheckConstraint(
            "result <> 'observation' OR (observations IS NOT NULL AND length(trim(observations)) > 0)",
            name="ck_maintenance_checklists_observation_required",
        ),
        Index("ix_maintenance_checklists_area_performed", "area", "performed_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    area: str = Field(max_length=80)
    result: str = Field(sa_column=Column(String(16), nullable=False))
    observations: str | None = Field(default=None, sa_column=Column(Text))
    performed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    performed_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
