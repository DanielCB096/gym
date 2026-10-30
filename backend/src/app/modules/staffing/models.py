from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StaffShift(SQLModel, table=True):
    __tablename__ = "staff_shifts"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_staff_shifts_period_valid"),
        CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_staff_shifts_status"),
        Index("ix_staff_shifts_employee_start", "employee_id", "starts_at"),
        Index("ix_staff_shifts_start_status", "starts_at", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    employee_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    )
    starts_at: datetime = Field(sa_type=DateTime(timezone=True))
    ends_at: datetime = Field(sa_type=DateTime(timezone=True))
    status: str = Field(
        default="scheduled",
        sa_column=Column(String(16), nullable=False, server_default=text("'scheduled'")),
    )
    created_by: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
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


class StaffAttendance(SQLModel, table=True):
    __tablename__ = "staff_attendance"
    __table_args__ = (
        CheckConstraint("status IN ('present', 'late')", name="ck_staff_attendance_status"),
        CheckConstraint(
            "check_out_at IS NULL OR check_out_at >= check_in_at",
            name="ck_staff_attendance_checkout_order",
        ),
        # A voided row keeps its marks for the audit log but no longer occupies
        # the shift, so a new attendance can be recorded for it.
        Index(
            "uq_staff_attendance_shift",
            "shift_id",
            unique=True,
            sqlite_where=text("voided_at IS NULL"),
            postgresql_where=text("voided_at IS NULL"),
        ),
        Index("ix_staff_attendance_employee_checkin", "employee_id", "check_in_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    shift_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("staff_shifts.id", ondelete="RESTRICT"), nullable=False)
    )
    employee_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    )
    check_in_at: datetime = Field(sa_type=DateTime(timezone=True))
    check_in_source: str = Field(max_length=20)
    check_in_actor_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    )
    check_out_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    check_out_source: str | None = Field(default=None, max_length=20)
    check_out_actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    status: str = Field(max_length=16)
    voided_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    voided_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    void_reason: str | None = Field(default=None, max_length=300)
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


class StaffingSettings(SQLModel, table=True):
    """Single-row club policy for staff attendance.

    ``check_in_early_grace_minutes`` is how long before the shift start the
    self-service check-in opens; ``lateness_tolerance_minutes`` is how late an
    entry can be and still count as ``present`` instead of ``late``. Both are
    zero-or-positive minute counts and are edited from the panel.
    """

    __tablename__ = "staffing_settings"
    __table_args__ = (
        CheckConstraint(
            "check_in_early_grace_minutes >= 0 AND check_in_early_grace_minutes <= 240",
            name="ck_staffing_settings_early_grace",
        ),
        CheckConstraint(
            "lateness_tolerance_minutes >= 0 AND lateness_tolerance_minutes <= 240",
            name="ck_staffing_settings_lateness",
        ),
    )

    id: int = Field(default=1, primary_key=True)
    check_in_early_grace_minutes: int = Field(default=15)
    lateness_tolerance_minutes: int = Field(default=0)
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class AttendanceEvent(SQLModel, table=True):
    __tablename__ = "staff_attendance_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('check_in', 'check_out', 'check_in_correction', "
            "'check_out_correction', 'check_out_voided', 'attendance_voided')",
            name="ck_staff_attendance_events_type",
        ),
        CheckConstraint("source IN ('staff_app', 'manual', 'access_reader')", name="ck_staff_attendance_events_source"),
        UniqueConstraint("request_id", name="uq_staff_attendance_events_request"),
        Index("ix_staff_attendance_events_attendance_time", "attendance_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    request_id: UUID = Field(index=True)
    request_sha256: str = Field(max_length=64)
    attendance_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("staff_attendance.id", ondelete="RESTRICT"), nullable=False)
    )
    actor_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    )
    event_type: str = Field(max_length=32)
    source: str = Field(max_length=20)
    reason: str | None = Field(default=None, sa_type=Text)
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )