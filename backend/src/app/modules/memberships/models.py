from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Member(SQLModel, table=True):
    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'active', 'inactive')", name="ck_members_status"),
        CheckConstraint(
            "credit_limit_cents IS NULL OR credit_limit_cents >= 0",
            name="ck_members_credit_limit",
        ),
        Index(
            "uq_members_email_lower",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
            sqlite_where=text("email IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    credit_limit_cents: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    status: str = Field(
        default="pending",
        sa_column=Column(String(20), nullable=False, server_default=text("'pending'")),
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


class Plan(SQLModel, table=True):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("duration_days > 0", name="ck_plans_duration_positive"),
        CheckConstraint("price_cents >= 0", name="ck_plans_price_nonnegative"),
        CheckConstraint(
            "billing_interval_days IS NULL OR billing_interval_days > 0",
            name="ck_plans_billing_interval_positive",
        ),
        UniqueConstraint("code", name="uq_plans_code"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=50)
    name: str = Field(max_length=120)
    duration_days: int
    price_cents: int = Field(sa_type=BigInteger)
    currency: str = Field(
        default="MXN",
        sa_column=Column(String(3), nullable=False, server_default=text("'MXN'")),
    )
    billing_interval_days: int | None = None
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


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_payment', 'active', 'frozen', 'suspended', 'cancelled', 'expired')",
            name="ck_memberships_status",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_memberships_period_valid"),
        Index("ix_memberships_member_status_ends", "member_id", "status", "ends_at"),
        Index(
            "uq_memberships_one_nonterminal_per_member",
            "member_id",
            unique=True,
            postgresql_where=text("status IN ('pending_payment', 'active', 'frozen', 'suspended')"),
            sqlite_where=text("status IN ('pending_payment', 'active', 'frozen', 'suspended')"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    plan_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False)
    )
    status: str = Field(max_length=24)
    starts_at: datetime = Field(sa_type=DateTime(timezone=True))
    ends_at: datetime = Field(sa_type=DateTime(timezone=True))
    auto_renew: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
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


class MemberConsent(SQLModel, table=True):
    __tablename__ = "member_consents"
    __table_args__ = (
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= accepted_at",
            name="ck_member_consents_revocation_order",
        ),
        Index("ix_member_consents_member_type", "member_id", "consent_type", "accepted_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    consent_type: str = Field(max_length=50)
    document_version: str = Field(max_length=80)
    evidence_digest: str | None = Field(default=None, max_length=64)
    accepted_at: datetime = Field(sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class PaymentMethod(SQLModel, table=True):
    __tablename__ = "payment_methods"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_payment_methods_status"),
        UniqueConstraint("provider", "provider_method_id", name="uq_payment_methods_provider_method"),
        Index(
            "uq_payment_methods_default_active",
            "member_id",
            unique=True,
            postgresql_where=text("is_default AND status = 'active'"),
            sqlite_where=text("is_default AND status = 'active'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    provider: str = Field(max_length=40)
    provider_customer_id: str | None = Field(default=None, max_length=160)
    provider_method_id: str = Field(max_length=160)
    encrypted_provider_token: bytes = Field(sa_type=LargeBinary)
    status: str = Field(
        default="active",
        sa_column=Column(String(16), nullable=False, server_default=text("'active'")),
    )
    is_default: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
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


class PaymentAttempt(SQLModel, table=True):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        CheckConstraint("method IN ('card', 'spei', 'cash', 'transfer')", name="ck_payment_attempts_method"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed', 'unknown', 'cancelled')",
            name="ck_payment_attempts_status",
        ),
        CheckConstraint("attempt_number > 0", name="ck_payment_attempts_number_positive"),
        CheckConstraint("amount_cents > 0", name="ck_payment_attempts_amount_positive"),
        CheckConstraint(
            "method <> 'card' OR payment_method_id IS NOT NULL OR provider IS NULL",
            name="ck_payment_attempts_card_method_required",
        ),
        UniqueConstraint("idempotency_key", name="uq_payment_attempts_idempotency_key"),
        UniqueConstraint("membership_id", "due_at", "attempt_number", name="uq_payment_attempts_cycle_number"),
        UniqueConstraint("provider", "provider_reference", name="uq_payment_attempts_provider_reference"),
        Index("ix_payment_attempts_status_due", "status", "due_at"),
        Index("ix_payment_attempts_membership_due", "membership_id", "due_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    membership_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False)
    )
    payment_method_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("payment_methods.id", ondelete="RESTRICT")),
    )
    method: str = Field(max_length=16)
    provider: str | None = Field(default=None, max_length=40)
    provider_reference: str | None = Field(default=None, max_length=160)
    idempotency_key: str = Field(max_length=128)
    request_fingerprint: str = Field(max_length=64)
    attempt_number: int
    amount_cents: int = Field(sa_type=BigInteger)
    currency: str = Field(
        default="MXN",
        sa_column=Column(String(3), nullable=False, server_default=text("'MXN'")),
    )
    status: str = Field(max_length=16)
    due_at: datetime = Field(sa_type=DateTime(timezone=True))
    requested_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    failure_code: str | None = Field(default=None, max_length=80)


class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_payments_amount_positive"),
        UniqueConstraint("payment_attempt_id", name="uq_payments_attempt"),
        Index("ix_payments_member_paid", "member_id", "paid_at"),
        Index("ix_payments_membership_paid", "membership_id", "paid_at"),
        Index("ix_payments_cash_session", "cash_session_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    payment_attempt_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("payment_attempts.id", ondelete="RESTRICT"), nullable=False)
    )
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    membership_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False)
    )
    amount_cents: int = Field(sa_type=BigInteger)
    currency: str = Field(max_length=3)
    method: str = Field(max_length=16)
    paid_at: datetime = Field(sa_type=DateTime(timezone=True))
    period_starts_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    period_ends_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    cash_session_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    collected_by: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    note: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ProviderWebhookEvent(SQLModel, table=True):
    __tablename__ = "provider_webhook_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'ignored')",
            name="ck_provider_webhook_events_status",
        ),
        UniqueConstraint("provider", "provider_event_id", name="uq_provider_webhook_events_external_id"),
        Index("ix_provider_webhook_events_attempt", "payment_attempt_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    provider: str = Field(max_length=40)
    provider_event_id: str = Field(max_length=160)
    event_type: str = Field(max_length=100)
    payload_sha256: str = Field(max_length=64)
    payment_attempt_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("payment_attempts.id", ondelete="RESTRICT")),
    )
    status: str = Field(
        default="received",
        sa_column=Column(String(16), nullable=False, server_default=text("'received'")),
    )
    received_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    processed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    error_code: str | None = Field(default=None, max_length=80)


class PaymentAttemptEvent(SQLModel, table=True):
    __tablename__ = "payment_attempt_events"
    __table_args__ = (
        CheckConstraint("source IN ('api', 'webhook', 'worker', 'operator')", name="ck_payment_attempt_events_source"),
        Index("ix_payment_attempt_events_attempt_time", "payment_attempt_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    payment_attempt_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("payment_attempts.id", ondelete="RESTRICT"), nullable=False)
    )
    webhook_event_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("provider_webhook_events.id", ondelete="RESTRICT")),
    )
    event_type: str = Field(max_length=60)
    from_status: str | None = Field(default=None, max_length=16)
    to_status: str = Field(max_length=16)
    source: str = Field(max_length=20)
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class MembershipEvent(SQLModel, table=True):
    __tablename__ = "membership_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('member', 'employee', 'system', 'provider')",
            name="ck_membership_events_actor_type",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="ck_membership_events_metadata_object",
        ).ddl_if(dialect="postgresql"),
        Index("ix_membership_events_membership_time", "membership_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    membership_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False)
    )
    event_type: str = Field(max_length=60)
    from_status: str | None = Field(default=None, max_length=24)
    to_status: str | None = Field(default=None, max_length=24)
    actor_type: str = Field(max_length=20)
    actor_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    correlation_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    event_metadata: dict[str, Any] = Field(
        sa_column=Column(
            "metadata",
            JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        )
    )
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )