"""Physiotherapy catalog, prepaid packs and the reception agenda.

The module is built around one rule: money moves only on attendance. A pack is
a prepaid balance of sessions, not a subscription, and a single session is
charged when the member shows up, never when the appointment is booked. A
no-show or a cancellation therefore leaves both the money and the balance
untouched.
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
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel

APPOINTMENT_STATUSES = ("scheduled", "attended", "no_show", "cancelled")
PAYMENT_MODES = ("single",)
PACK_ADJUSTMENT_KINDS = ("extension", "void")

DEFAULT_VALIDITY_DAYS = 31
MAX_ADJUSTMENT_REASON_CHARS = 300

# How long after an appointment ends the staff can still mark (or fix) its
# attendance. Outside the window the mark is final.
ATTENDANCE_GRACE_HOURS = 24


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PhysioService(SQLModel, table=True):
    """A service offered by the physiotherapy room; its price is the single one."""

    __tablename__ = "physio_services"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_physio_services_duration_positive"),
        CheckConstraint("price_cents >= 0", name="ck_physio_services_price_nonnegative"),
        Index("uq_physio_services_code_lower", text("lower(code)"), unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=160)
    description: str | None = Field(default=None, sa_column=Column(Text))
    duration_minutes: int = Field(sa_type=Integer)
    price_cents: int = Field(sa_type=BigInteger)
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
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


class PhysioOffer(SQLModel, table=True):
    """A prepaid pack of sessions sold at a discount.

    ``list_price_cents`` is the sum of the single prices at the moment the offer
    is created. It is stored, not derived: changing the single price later must
    not rewrite what an already sold pack saved.
    """

    __tablename__ = "physio_offers"
    __table_args__ = (
        CheckConstraint("sessions >= 1", name="ck_physio_offers_sessions_positive"),
        CheckConstraint("price_cents >= 0", name="ck_physio_offers_price_nonnegative"),
        CheckConstraint(
            "list_price_cents >= price_cents", name="ck_physio_offers_discount_nonnegative"
        ),
        CheckConstraint("validity_days > 0", name="ck_physio_offers_validity_positive"),
        CheckConstraint("payment_mode IN ('single')", name="ck_physio_offers_payment_mode"),
        Index("uq_physio_offers_name_lower", text("lower(name)"), unique=True),
        Index("ix_physio_offers_service", "service_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    service_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_services.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    name: str = Field(max_length=160)
    sessions: int = Field(sa_type=Integer)
    price_cents: int = Field(sa_type=BigInteger)
    list_price_cents: int = Field(sa_type=BigInteger)
    validity_days: int = Field(
        default=DEFAULT_VALIDITY_DAYS,
        sa_column=Column(Integer, nullable=False, server_default=text("31")),
    )
    payment_mode: str = Field(
        default="single",
        sa_column=Column(String(16), nullable=False, server_default=text("'single'")),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
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


class PhysioPack(SQLModel, table=True):
    """A prepaid balance bought by a member.

    There is no persisted status: whether a pack is active, used up or expired
    is derived from ``sessions_used``, ``sessions_total`` and ``valid_until``,
    so it can never drift from the truth.
    """

    __tablename__ = "physio_packs"
    __table_args__ = (
        CheckConstraint("sessions_total > 0", name="ck_physio_packs_total_positive"),
        CheckConstraint(
            "sessions_used >= 0 AND sessions_used <= sessions_total",
            name="ck_physio_packs_used_range",
        ),
        CheckConstraint("price_cents >= 0", name="ck_physio_packs_price_nonnegative"),
        CheckConstraint(
            "voided_sessions >= 0 AND voided_sessions <= sessions_total",
            name="ck_physio_packs_voided_range",
        ),
        UniqueConstraint("sale_id", name="uq_physio_packs_sale"),
        Index("ix_physio_packs_member_validity", "member_id", "valid_until"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    offer_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_offers.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    sale_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    sessions_total: int = Field(sa_type=Integer)
    sessions_used: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    price_cents: int = Field(sa_type=BigInteger)
    purchased_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    valid_until: datetime = Field(sa_type=DateTime(timezone=True))
    # A voided pack stops covering sessions and its remaining credits are
    # recorded, not silently marked as used. There is no refund: the club
    # extends the validity instead, and only a manager can void one.
    voided_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    voided_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    void_reason: str | None = Field(default=None, max_length=MAX_ADJUSTMENT_REASON_CHARS)
    voided_sessions: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class PhysioAppointment(SQLModel, table=True):
    """A slot in a therapist's agenda; the single place attendance lives."""

    __tablename__ = "physio_appointments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'attended', 'no_show', 'cancelled')",
            name="ck_physio_appointments_status",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_physio_appointments_time_range"),
        # The exact start of a therapist is unique while the appointment is
        # alive. A cancelled slot frees the hour again.
        Index(
            "uq_physio_appointments_therapist_start",
            "therapist_employee_id",
            "starts_at",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
            sqlite_where=text("status <> 'cancelled'"),
        ),
        Index("ix_physio_appointments_starts_at", "starts_at"),
        Index("ix_physio_appointments_member", "member_id", "starts_at"),
        Index("ix_physio_appointments_pack", "pack_id"),
        Index("ix_physio_appointments_room", "room_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    service_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_services.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    # The pack that covers this session. It is picked when the appointment is
    # booked and can be reassigned when the original pack runs out or expires
    # before the member shows up.
    pack_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_packs.id", ondelete="RESTRICT"),
        ),
    )
    therapist_employee_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    # The room catalog is optional: ``room`` keeps the name frozen for history
    # while ``room_id`` links to the current catalog entry when one was chosen.
    room_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_rooms.id", ondelete="RESTRICT"),
        ),
    )
    room: str | None = Field(default=None, max_length=80)
    starts_at: datetime = Field(sa_type=DateTime(timezone=True))
    ends_at: datetime = Field(sa_type=DateTime(timezone=True))
    status: str = Field(
        default="scheduled",
        sa_column=Column(String(16), nullable=False, server_default=text("'scheduled'")),
    )
    notes: str | None = Field(default=None, sa_column=Column(Text))
    booked_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    marked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    marked_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    cancelled_by: UUID | None = Field(
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


class PhysioRoom(SQLModel, table=True):
    """A physical room of the physiotherapy area (one is enough in practice)."""

    __tablename__ = "physio_rooms"
    __table_args__ = (Index("uq_physio_rooms_name_lower", text("lower(name)"), unique=True),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=80)
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
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


class PhysioSpecialty(SQLModel, table=True):
    """A therapist specialty, shown next to their name when booking."""

    __tablename__ = "physio_specialties"
    __table_args__ = (
        Index("uq_physio_specialties_name_lower", text("lower(name)"), unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=80)
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
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


class PhysioTherapistProfile(SQLModel, table=True):
    """Optional specialty and default room for an employee of the room.

    It complements ``employees`` instead of duplicating it: the schedule still
    points at the employee, and this row only adds what the clinic needs.
    """

    __tablename__ = "physio_therapist_profiles"
    __table_args__ = (
        UniqueConstraint("employee_id", name="uq_physio_therapist_profiles_employee"),
        Index("ix_physio_therapist_profiles_specialty", "specialty_id"),
        Index("ix_physio_therapist_profiles_room", "room_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    employee_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    specialty_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_specialties.id", ondelete="RESTRICT"),
        ),
    )
    room_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_rooms.id", ondelete="RESTRICT"),
        ),
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


class PhysioPackAdjustment(SQLModel, table=True):
    """Append-only audit row for an extension or a void of a pack.

    The pack itself keeps the resulting state (``valid_until`` or ``voided_*``);
    this table answers who changed it, when and why.
    """

    __tablename__ = "physio_pack_adjustments"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('extension', 'void')", name="ck_physio_pack_adjustments_kind"
        ),
        CheckConstraint(
            "days IS NULL OR days > 0", name="ck_physio_pack_adjustments_days"
        ),
        CheckConstraint(
            f"length(reason) BETWEEN 1 AND {MAX_ADJUSTMENT_REASON_CHARS}",
            name="ck_physio_pack_adjustments_reason",
        ),
        Index("ix_physio_pack_adjustments_pack_time", "pack_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    pack_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("physio_packs.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    kind: str = Field(max_length=16)
    days: int | None = Field(default=None, sa_type=Integer)
    reason: str = Field(max_length=MAX_ADJUSTMENT_REASON_CHARS)
    actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
