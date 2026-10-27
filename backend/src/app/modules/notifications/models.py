"""Member notification inbox.

The club acts on the member (a trainer reviews a workout, reception cancels a
goal, a spot opens in a class, the membership is about to expire). Until now the
member only found that out by opening each screen. This table is the push-free
equivalent: every domain event that changes something the member owns appends a
short Spanish message here, and the app shows it in one inbox.

The row is a snapshot of the message, not a pointer to live data, so a
notification keeps making sense after the referenced record is edited or
deleted. ``ref_id`` is an untyped reference used only to deep-link.

Notifications are append-only from the point of view of the member: the portal
can create them (through the domain events) and mark them read, never edit or
delete them.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


NOTIFICATION_KINDS = (
    "workout_reviewed",
    "goal_achieved",
    "goal_cancelled_by_staff",
    "goal_updated_by_staff",
    "class_waitlist_promoted",
    "membership_expiring",
)
MAX_TITLE_CHARS = 140
MAX_BODY_CHARS = 500
MAX_DEDUPE_CHARS = 120


class MemberNotification(SQLModel, table=True):
    __tablename__ = "member_notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring')",
            name="ck_member_notifications_kind",
        ),
        CheckConstraint(
            f"length(title) BETWEEN 1 AND {MAX_TITLE_CHARS}",
            name="ck_member_notifications_title_length",
        ),
        CheckConstraint(
            f"length(body) BETWEEN 1 AND {MAX_BODY_CHARS}",
            name="ck_member_notifications_body_length",
        ),
        Index("ix_member_notifications_member_time", "member_id", "created_at"),
        Index("ix_member_notifications_member_unread", "member_id", "read_at"),
        Index(
            "ix_member_notifications_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
            sqlite_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    kind: str = Field(max_length=40)
    title: str = Field(max_length=MAX_TITLE_CHARS)
    body: str = Field(sa_column=Column(String(length=MAX_BODY_CHARS), nullable=False))
    ref_id: UUID | None = Field(default=None, sa_column=Column(Uuid(as_uuid=True)))
    dedupe_key: str | None = Field(
        default=None, sa_column=Column(String(length=MAX_DEDUPE_CHARS))
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
