"""Training routines and progress tracking.

This module covers the trainer side of the routine lifecycle:

* ``exercises`` is the reusable library (muscle group, category and the
  equipment the movement needs) that both routines and workouts draw from;
* ``routines`` are templates owned by a trainer. Editing the plan *never*
  rewrites history: every change publishes a new ``version`` and keeps the
  previous ``routine_items`` rows, so an assignment can be traced back to the
  exact plan the member trained;
* ``routine_assignments`` bind a routine (and the version active at the time)
  to a member, with dates, weekly frequency and status;
* ``workout_logs`` record a performed session against an assignment;
* ``body_measurements`` store the member's weight and girths as an
  append-only history (the spec forbids replacing an earlier measurement).

Workout detail per set (``DetalleEntrenamiento``), goals, progress photos and
trainer-member messaging are deliberately out of this first increment; they are
tracked in ``docs/deuda-tecnica.md``.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel

ROUTINE_STATUSES = ("draft", "active", "archived")
ASSIGNMENT_STATUSES = ("active", "completed", "cancelled")
WORKOUT_STATUSES = ("logged", "reviewed")

MIN_WEEKLY_FREQUENCY = 1
MAX_WEEKLY_FREQUENCY = 7
MIN_EFFORT = 1
MAX_EFFORT = 10


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Exercise(SQLModel, table=True):
    """Reusable movement in the exercise library."""

    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_exercises_name_nonempty"),
        CheckConstraint("length(trim(muscle_group)) > 0", name="ck_exercises_muscle_nonempty"),
        CheckConstraint("length(trim(category)) > 0", name="ck_exercises_category_nonempty"),
        Index("uq_exercises_name_lower", text("lower(name)"), unique=True),
        Index("ix_exercises_muscle_group", "muscle_group"),
        Index("ix_exercises_category", "category"),
        Index("ix_exercises_equipment", "equipment_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=160)
    muscle_group: str = Field(max_length=60)
    category: str = Field(max_length=60)
    equipment_name: str | None = Field(default=None, max_length=120)
    # Optional link to the maintenance fleet so a plan can be flagged when the
    # machine it needs is out of service. ``equipment_name`` stays as the plain
    # text description used when there is no linked unit.
    equipment_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL")
        ),
    )
    description: str | None = Field(default=None, sa_column=Column(Text))
    video_url: str | None = Field(default=None, max_length=300)
    image_url: str | None = Field(default=None, max_length=300)
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
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


class Routine(SQLModel, table=True):
    """Trainer-owned routine template; ``version`` points at the live plan."""

    __tablename__ = "routines"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_routines_name_nonempty"),
        CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_routines_status"),
        CheckConstraint("version > 0", name="ck_routines_version_positive"),
        Index("ix_routines_status", "status"),
        Index("ix_routines_trainer", "trainer_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=160)
    trainer_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT")),
    )
    objective: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, sa_column=Column(Text))
    status: str = Field(
        default="active",
        sa_column=Column(String(16), nullable=False, server_default=text("'active'")),
    )
    version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    archived_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
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


class RoutineItem(SQLModel, table=True):
    """One line of a routine version (exercise + sets/reps/rest + order)."""

    __tablename__ = "routine_items"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_routine_items_version_positive"),
        CheckConstraint("position > 0", name="ck_routine_items_position_positive"),
        CheckConstraint("sets > 0", name="ck_routine_items_sets_positive"),
        CheckConstraint(
            "rest_seconds IS NULL OR rest_seconds >= 0", name="ck_routine_items_rest_nonnegative"
        ),
        Index("uq_routine_items_line", "routine_id", "version", "position", unique=True),
        Index("ix_routine_items_version", "routine_id", "version"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    routine_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("routines.id", ondelete="RESTRICT"), nullable=False
        )
    )
    version: int = Field(sa_type=Integer)
    position: int = Field(sa_type=Integer)
    exercise_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False
        )
    )
    sets: int = Field(sa_type=Integer)
    reps: str = Field(max_length=20)
    rest_seconds: int | None = Field(default=None, sa_type=Integer)
    load_note: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=200)


class RoutineRevision(SQLModel, table=True):
    """Change log for a routine: which version and why it was published."""

    __tablename__ = "routine_revisions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_routine_revisions_version_positive"),
        CheckConstraint("item_count > 0", name="ck_routine_revisions_item_count_positive"),
        Index("uq_routine_revisions_version", "routine_id", "version", unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    routine_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("routines.id", ondelete="RESTRICT"), nullable=False
        )
    )
    version: int = Field(sa_type=Integer)
    reason: str | None = Field(default=None, max_length=300)
    item_count: int = Field(sa_type=Integer)
    changed_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class RoutineAssignment(SQLModel, table=True):
    """A routine version assigned to a member for a date range."""

    __tablename__ = "routine_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')", name="ck_routine_assignments_status"
        ),
        CheckConstraint("routine_version > 0", name="ck_routine_assignments_version_positive"),
        CheckConstraint(
            "frequency_per_week IS NULL OR (frequency_per_week >= 1 AND frequency_per_week <= 7)",
            name="ck_routine_assignments_frequency_range",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_routine_assignments_date_order"
        ),
        # A member follows one live assignment per routine at a time.
        Index(
            "uq_routine_assignments_active",
            "member_id",
            "routine_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_routine_assignments_member_status", "member_id", "status"),
        Index("ix_routine_assignments_routine", "routine_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    routine_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("routines.id", ondelete="RESTRICT"), nullable=False
        )
    )
    routine_version: int = Field(sa_type=Integer)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False
        )
    )
    trainer_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT")),
    )
    assigned_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    start_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date | None = Field(default=None, sa_column=Column(Date))
    frequency_per_week: int | None = Field(default=None, sa_type=Integer)
    status: str = Field(
        default="active",
        sa_column=Column(String(16), nullable=False, server_default=text("'active'")),
    )
    notes: str | None = Field(default=None, sa_column=Column(Text))
    ended_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
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


class WorkoutLog(SQLModel, table=True):
    """A performed training session logged against an assignment."""

    __tablename__ = "workout_logs"
    __table_args__ = (
        CheckConstraint("status IN ('logged', 'reviewed')", name="ck_workout_logs_status"),
        CheckConstraint("routine_version > 0", name="ck_workout_logs_version_positive"),
        CheckConstraint(
            "perceived_effort IS NULL OR (perceived_effort >= 1 AND perceived_effort <= 10)",
            name="ck_workout_logs_effort_range",
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes >= 0",
            name="ck_workout_logs_duration_nonnegative",
        ),
        Index("ix_workout_logs_assignment_date", "assignment_id", "performed_at"),
        Index("ix_workout_logs_member_date", "member_id", "performed_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    assignment_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("routine_assignments.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False
        )
    )
    routine_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("routines.id", ondelete="RESTRICT"), nullable=False
        )
    )
    routine_version: int = Field(sa_type=Integer)
    performed_at: date = Field(sa_column=Column(Date, nullable=False))
    duration_minutes: int | None = Field(default=None, sa_type=Integer)
    perceived_effort: int | None = Field(default=None, sa_type=Integer)
    notes: str | None = Field(default=None, sa_column=Column(Text))
    status: str = Field(
        default="logged",
        sa_column=Column(String(16), nullable=False, server_default=text("'logged'")),
    )
    logged_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    reviewed_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    reviewed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
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


class BodyMeasurement(SQLModel, table=True):
    """Append-only body measurement history for a member."""

    __tablename__ = "body_measurements"
    __table_args__ = (
        CheckConstraint("weight_kg IS NULL OR weight_kg > 0", name="ck_body_measurements_weight"),
        CheckConstraint("waist_cm IS NULL OR waist_cm > 0", name="ck_body_measurements_waist"),
        CheckConstraint("chest_cm IS NULL OR chest_cm > 0", name="ck_body_measurements_chest"),
        CheckConstraint(
            "body_fat_percent IS NULL OR (body_fat_percent >= 0 AND body_fat_percent <= 100)",
            name="ck_body_measurements_fat_range",
        ),
        Index("ix_body_measurements_member_date", "member_id", "measured_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False
        )
    )
    measured_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    weight_kg: float | None = Field(default=None, sa_column=Column(Numeric(5, 2)))
    waist_cm: float | None = Field(default=None, sa_column=Column(Numeric(5, 2)))
    chest_cm: float | None = Field(default=None, sa_column=Column(Numeric(5, 2)))
    body_fat_percent: float | None = Field(default=None, sa_column=Column(Numeric(4, 1)))
    notes: str | None = Field(default=None, max_length=300)
    measured_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
