from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemberLoginCode(SQLModel, table=True):
    """One-time code sent to the member's registered email.

    Only the HMAC digest of the code is stored; the code itself never touches
    the database or the logs.
    """

    __tablename__ = "member_login_codes"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_member_login_codes_attempts"),
        CheckConstraint("expires_at > created_at", name="ck_member_login_codes_expiry_order"),
        Index("ix_member_login_codes_member_created", "member_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    code_hash: str = Field(max_length=64)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    consumed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )


class MemberSession(SQLModel, table=True):
    __tablename__ = "member_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_member_sessions_expiry_order"),
        UniqueConstraint("token_sha256", name="uq_member_sessions_token_hash"),
        Index("ix_member_sessions_member_expiry", "member_id", "expires_at", "revoked_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    token_sha256: str = Field(max_length=64)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    last_seen_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class MemberAuthEvent(SQLModel, table=True):
    __tablename__ = "member_auth_events"
    __table_args__ = (
        CheckConstraint("result IN ('success', 'failure')", name="ck_member_auth_events_result"),
        Index("ix_member_auth_events_member_time", "member_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT")),
    )
    event_type: str = Field(max_length=40)
    result: str = Field(max_length=16)
    reason_code: str | None = Field(default=None, max_length=80)
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
