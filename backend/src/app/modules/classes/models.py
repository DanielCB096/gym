"""Class schedule and reservations.

First increment of the classes module. A *class session* is one scheduled
occurrence (type + room + instructor + time window + capacity). Reservations
carry the whole member lifecycle in a single row: a member is ``waitlist`` while
the session is full, ``reserved`` once they hold a seat, and then ``attended``,
``no_show`` or ``cancelled``. This keeps attendance 1:1 with the reservation
(the module spec lists ``AsistenciaClase`` and ``ListaEsperaClase`` as separate
entities; here they are modelled as states of ``class_reservations``) while the
capacity checks stay in one place.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
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

SESSION_STATUSES = ("scheduled", "cancelled")
RESERVATION_STATUSES = ("waitlist", "reserved", "attended", "no_show", "cancelled")
ACCESS_TYPES = ("included", "premium")
RESERVATION_ORIGINS = ("app", "reception", "web")

# Statuses that still hold the member on the roster: they count against the
# capacity checks and block a second reservation for the same session.
ACTIVE_RESERVATION_STATUSES = ("waitlist", "reserved", "attended")
SEATED_RESERVATION_STATUSES = ("reserved", "attended")

DEFAULT_CANCEL_WINDOW_HOURS = 4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ClassType(SQLModel, table=True):
    """Kind of class, e.g. Spinning, Yoga, Funcional."""

    __tablename__ = "class_types"
    __table_args__ = (Index("uq_class_types_name_lower", text("lower(name)"), unique=True),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=120)
    description: str | None = Field(default=None, sa_column=Column(Text))
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ClassRoom(SQLModel, table=True):
    """Physical room where a class happens."""

    __tablename__ = "class_rooms"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_class_rooms_capacity_positive"),
        Index("uq_class_rooms_name_lower", text("lower(name)"), unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=120)
    capacity: int = Field(sa_type=Integer)
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ClassSession(SQLModel, table=True):
    """One scheduled occurrence of a class."""

    __tablename__ = "class_sessions"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_class_sessions_time_order"),
        CheckConstraint("capacity > 0", name="ck_class_sessions_capacity_positive"),
        CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_class_sessions_status"),
        CheckConstraint("access_type IN ('included', 'premium')", name="ck_class_sessions_access_type"),
        CheckConstraint("extra_price_cents >= 0", name="ck_class_sessions_price_nonnegative"),
        CheckConstraint("cancel_window_hours >= 0", name="ck_class_sessions_window_nonnegative"),
        Index("ix_class_sessions_start", "starts_at"),
        Index("ix_class_sessions_status_start", "status", "starts_at"),
        Index("ix_class_sessions_room_start", "room_id", "starts_at"),
        Index("ix_class_sessions_instructor_start", "instructor_id", "starts_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(max_length=160)
    class_type_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("class_types.id", ondelete="RESTRICT"), nullable=False)
    )
    room_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("class_rooms.id", ondelete="RESTRICT")),
    )
    instructor_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT")),
    )
    starts_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    ends_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    capacity: int = Field(sa_type=Integer)
    status: str = Field(
        default="scheduled",
        sa_column=Column(String(16), nullable=False, server_default=text("'scheduled'")),
    )
    access_type: str = Field(
        default="included",
        sa_column=Column(String(16), nullable=False, server_default=text("'included'")),
    )
    extra_price_cents: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
    )
    waitlist_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    cancel_window_hours: int = Field(
        default=DEFAULT_CANCEL_WINDOW_HOURS,
        sa_column=Column(Integer, nullable=False, server_default=text("4")),
    )
    notes: str | None = Field(default=None, sa_column=Column(Text))
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    cancelled_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
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


class ClassReservation(SQLModel, table=True):
    """A member on a class roster (seat, waitlist, attendance or cancellation)."""

    __tablename__ = "class_reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('waitlist', 'reserved', 'attended', 'no_show', 'cancelled')",
            name="ck_class_reservations_status",
        ),
        CheckConstraint("origin IN ('app', 'reception', 'web')", name="ck_class_reservations_origin"),
        CheckConstraint(
            "waitlist_position IS NULL OR waitlist_position > 0",
            name="ck_class_reservations_position_positive",
        ),
        # A member can hold at most one live reservation per session; cancelled
        # (and no_show) rows stay for history without blocking a new booking.
        Index(
            "uq_class_reservations_active",
            "session_id",
            "member_id",
            unique=True,
            postgresql_where=text("status IN ('waitlist', 'reserved', 'attended')"),
            sqlite_where=text("status IN ('waitlist', 'reserved', 'attended')"),
        ),
        Index("ix_class_reservations_session_status", "session_id", "status"),
        Index("ix_class_reservations_member_time", "member_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True), ForeignKey("class_sessions.id", ondelete="RESTRICT"), nullable=False
        )
    )
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    status: str = Field(
        default="reserved",
        sa_column=Column(String(16), nullable=False, server_default=text("'reserved'")),
    )
    origin: str = Field(
        default="reception",
        sa_column=Column(String(16), nullable=False, server_default=text("'reception'")),
    )
    waitlist_position: int | None = Field(default=None, sa_type=Integer)
    late_cancellation: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    note: str | None = Field(default=None, max_length=200)
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    cancelled_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    marked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    marked_by: UUID | None = Field(
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
