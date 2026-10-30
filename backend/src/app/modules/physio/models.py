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

DEFAULT_VALIDITY_DAYS = 31

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
