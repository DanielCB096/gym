from dataclasses import dataclass
from datetime import datetime, time, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Uuid, func
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