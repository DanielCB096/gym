"""Persistence for idempotent scheduled report email delivery."""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid as SQLAlchemyUuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel

from app.constraints import sql_in_list

# The reports the panel can schedule. This tuple is the vocabulary: the delivery
# ``CHECK``, the envelope labels, the per-recipient columns and the request
# ``Literal`` all have to agree with it.
REPORT_NAMES = ("overview", "revenue", "memberships", "operations", "maintenance", "inventory")

REPORT_FREQUENCIES = ("daily", "weekly", "monthly")


class ScheduledReportDelivery(SQLModel, table=True):
    __tablename__ = "scheduled_report_deliveries"
    __table_args__ = (
        Index(
            "ix_scheduled_report_deliveries_status_claimed",
            "status",
            "claimed_at",
        ),
        UniqueConstraint("idempotency_key", name="uq_scheduled_report_delivery_key"),
        CheckConstraint(
            f"report_name IN {sql_in_list(REPORT_NAMES)}",
            name="ck_scheduled_report_deliveries_report_name",
        ),
        CheckConstraint(
            f"frequency IN {sql_in_list(REPORT_FREQUENCIES)}",
            name="ck_scheduled_report_deliveries_frequency",
        ),
        CheckConstraint(
            "status IN ('sending', 'sent', 'simulated', 'failed')",
            name="ck_scheduled_report_deliveries_status",
        ),
        CheckConstraint(
            "attempts >= 1",
            name="ck_scheduled_report_deliveries_attempts",
        ),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(SQLAlchemyUuid(as_uuid=True), primary_key=True),
    )
    idempotency_key: str = Field(sa_column=Column(String(64), nullable=False))
    report_name: str = Field(sa_column=Column(String(16), nullable=False))
    frequency: str = Field(sa_column=Column(String(8), nullable=False))
    date_from: date = Field(sa_column=Column(Date, nullable=False))
    date_to: date = Field(sa_column=Column(Date, nullable=False))
    recipient_hash: str = Field(sa_column=Column(String(64), nullable=False))
    status: str = Field(
        default="sending",
        sa_column=Column(
            String(16), nullable=False, server_default=text("'sending'")
        ),
    )
    attempts: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )
    error: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    claimed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    sent_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )


class ScheduledReportConfiguration(SQLModel, table=True):
    """Singleton marker for settings saved from the administration panel."""

    __tablename__ = "scheduled_report_configurations"

    id: int = Field(default=1, primary_key=True)
    updated_by: UUID | None = Field(
        default=None,
        sa_column=Column(
            SQLAlchemyUuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )


class ScheduledReportRecipient(SQLModel, table=True):
    """Current report subscriptions; inactive rows retain stable identities."""

    __tablename__ = "scheduled_report_recipients"
    __table_args__ = (
        UniqueConstraint("email_key", name="uq_scheduled_report_recipient_email_key"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(SQLAlchemyUuid(as_uuid=True), primary_key=True),
    )
    email: str = Field(sa_column=Column(String(254), nullable=False))
    email_key: str = Field(sa_column=Column(String(254), nullable=False))
    overview_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    revenue_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    memberships_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    operations_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    maintenance_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    inventory_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )


class ScheduledReportConfigurationEvent(SQLModel, table=True):
    """Append-only change record with hashed addresses, never plain emails."""

    __tablename__ = "scheduled_report_configuration_events"
    __table_args__ = (Index("ix_scheduled_report_configuration_events_changed", "changed_at"),)

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(SQLAlchemyUuid(as_uuid=True), primary_key=True),
    )
    actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            SQLAlchemyUuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    previous_snapshot: str = Field(sa_column=Column(Text, nullable=False))
    next_snapshot: str = Field(sa_column=Column(Text, nullable=False))
    changed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
