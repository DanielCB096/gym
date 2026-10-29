from dataclasses import dataclass
from datetime import datetime, time, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccessDirection(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"


class AccessReason(StrEnum):
    ENTRY_ALLOWED = "entry_allowed"
    EXIT_ALLOWED = "exit_allowed"
    SNAPSHOT_MISSING = "snapshot_missing"
    SNAPSHOT_EXPIRED = "snapshot_expired"
    MEMBERSHIP_NOT_ACTIVE = "membership_not_active"
    MEMBERSHIP_NOT_STARTED = "membership_not_started"
    MEMBERSHIP_EXPIRED = "membership_expired"
    BLOCKING_DEBT = "blocking_debt"
    OUTSIDE_ALLOWED_HOURS = "outside_allowed_hours"
    ANTIPASSBACK = "antipassback"
    DAILY_LIMIT = "daily_limit"
    OCCUPANCY_FULL = "occupancy_full"
    MANUAL_OVERRIDE = "manual_override"


@dataclass(frozen=True)
class AccessWindow:
    weekday: int
    starts_at: time
    ends_at: time


@dataclass(frozen=True)
class AccessSnapshot:
    member_id: UUID
    membership_status: str
    membership_starts_at: datetime
    membership_ends_at: datetime
    blocking_debt: bool
    cached_at: datetime
    valid_until: datetime
    allowed_windows: tuple[AccessWindow, ...] | None = None
    daily_entry_limit: int | None = None
    entries_today: int = 0
    antipassback_seconds: int = 60


@dataclass(frozen=True)
class AccessRequest:
    event_id: UUID
    member_id: UUID
    reader_id: str
    direction: AccessDirection
    occurred_at: datetime
    current_occupancy: int
    max_occupancy: int
    offline: bool


@dataclass(frozen=True)
class AccessDecision:
    event_id: UUID
    member_id: UUID
    authorized: bool
    reason: AccessReason
    direction: AccessDirection
    occurred_at: datetime
    offline: bool


class DuplicateAccessEventConflict(Exception):
    pass


class AccessMemberNotFound(Exception):
    pass


class AccessEvent(SQLModel, table=True):
    """Persisted access decision, online record of a reader or manual check.

    ``event_id`` is the device-side event identifier and is unique so that
    re-sending the same decision (offline sync, retries) stays idempotent.
    """

    __tablename__ = "access_events"
    __table_args__ = (
        CheckConstraint("direction IN ('entry', 'exit')", name="ck_access_events_direction"),
        CheckConstraint("source IN ('reader', 'manual')", name="ck_access_events_source"),
        Index("ix_access_events_occurred_at", "occurred_at"),
        Index("ix_access_events_member_occurred", "member_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_id: UUID = Field(sa_column=Column(Uuid(as_uuid=True), nullable=False, unique=True))
    member_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT")),
    )
    reader_id: str = Field(max_length=80)
    direction: str = Field(max_length=16)
    authorized: bool
    reason: str = Field(max_length=40)
    note: str | None = Field(default=None, max_length=200)
    source: str = Field(default="reader", max_length=16)
    occurred_at: datetime = Field(sa_type=DateTime(timezone=True))
    offline: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class AccessSettings(SQLModel, table=True):
    """Single-row club policy for access rules that do not belong to a member.

    ``antipassback_seconds`` is the minimum gap between two authorized entries
    of the same member; ``0`` disables the rule. The row is created with id 1
    by the migration and lazily by the service when a preview database starts
    empty.
    """

    __tablename__ = "access_settings"
    __table_args__ = (
        CheckConstraint(
            "antipassback_seconds >= 0 AND antipassback_seconds <= 3600",
            name="ck_access_settings_antipassback_range",
        ),
    )

    id: int = Field(default=1, primary_key=True)
    antipassback_seconds: int = Field(default=0)
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )


class KioskDevice(SQLModel, table=True):
    """Tablet at the front desk that validates member check-in codes.

    Only the SHA-256 digest of the device token is stored, mirroring staff and
    member sessions: the raw token is shown once when the device is created.
    """

    __tablename__ = "kiosk_devices"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_kiosk_devices_status"),
        UniqueConstraint("token_sha256", name="uq_kiosk_devices_token"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    label: str = Field(max_length=80)
    token_sha256: str = Field(max_length=64)
    status: str = Field(default="active", max_length=16)
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_seen_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )


class MemberAccessCode(SQLModel, table=True):
    """Short-lived six-digit check-in code issued to one member.

    The code is stored as an HMAC digest. Issuing a new code invalidates the
    previous unconsumed ones so only the code on screen can open the door.
    """

    __tablename__ = "member_access_codes"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at", name="ck_member_access_codes_expiry_order"
        ),
        Index("ix_member_access_codes_member_created", "member_id", "created_at"),
        Index("ix_member_access_codes_hash", "code_hash"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    code_hash: str = Field(max_length=64)
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    consumed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class KioskAttempt(SQLModel, table=True):
    """One check-in attempt per kiosk, used for the per-device rate limit."""

    __tablename__ = "kiosk_attempts"
    __table_args__ = (
        CheckConstraint(
            "result IN ('authorized', 'denied', 'invalid')",
            name="ck_kiosk_attempts_result",
        ),
        Index("ix_kiosk_attempts_device_occurred", "device_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    device_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("kiosk_devices.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    result: str = Field(max_length=16)
    occurred_at: datetime = Field(sa_type=DateTime(timezone=True))