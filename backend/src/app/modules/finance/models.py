"""Bank accounts, statement lines and their reconciliation trail.

The club does not store a second ledger of money: a declared transfer, card
charge or refund already has its own row (``payments``, ``sales``,
``member_account_payments`` or ``sale_returns``). A ``bank_movements`` row is
one line of the bank statement; a live match points at that existing internal
movement and never duplicates or overwrites it.

One internal movement can be matched to one bank line at most: the partial
unique index on ``(matched_source, matched_id)`` prevents two statement lines
from claiming the same payment. Unmatching clears the pointers, so the line can
be matched again with the correct one.

Everything that happens to a statement line is appended to
``bank_movement_events``; the movement itself only keeps the current state.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel

BANK_ACCOUNT_STATUSES = ("active", "inactive")

BANK_MOVEMENT_STATUSES = ("pending", "reconciled", "difference", "reviewing")

# Internal rows that can satisfy a bank line. Cash never appears in the bank,
# so only the electronic tenders (card, transfer, SPEI) are candidates.
BANK_MOVEMENT_SOURCES = (
    "membership_payment",
    "sale",
    "member_account_payment",
    "sale_return",
    "invoice_payment",
)

BANK_MOVEMENT_EVENT_TYPES = ("imported", "matched", "unmatched", "flagged", "reopened")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BankAccount(SQLModel, table=True):
    """A bank account whose statement lines are reconciled in the panel.

    It is a catalogue row, not a ledger: the balance shown by the panel is the
    sum of the imported statement lines, which is only as complete as the
    statements the operator imports.
    """

    __tablename__ = "bank_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive')", name="ck_bank_accounts_status"
        ),
        Index("uq_bank_accounts_name_lower", text("lower(name)"), unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=120)
    bank_name: str = Field(max_length=80)
    account_last4: str = Field(max_length=4)
    currency: str = Field(
        default="MXN",
        sa_column=Column(String(3), nullable=False, server_default=text("'MXN'")),
    )
    status: str = Field(
        default="active",
        sa_column=Column(String(16), nullable=False, server_default=text("'active'")),
    )
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
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


class BankMovement(SQLModel, table=True):
    """One line of a bank statement, signed as the bank sees it.

    A deposit is positive and a withdrawal (a refund or a bank fee) is
    negative. ``difference_cents`` is only set when the operator links the line
    to an internal movement whose amount does not match exactly; the line then
    keeps the ``difference`` status until someone reviews it.
    """

    __tablename__ = "bank_movements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'reconciled', 'difference', 'reviewing')",
            name="ck_bank_movements_status",
        ),
        CheckConstraint("amount_cents <> 0", name="ck_bank_movements_amount_nonzero"),
        CheckConstraint(
            "(matched_source IS NULL AND matched_id IS NULL) OR "
            "(matched_source IS NOT NULL AND matched_id IS NOT NULL)",
            name="ck_bank_movements_match_pair",
        ),
        CheckConstraint(
            "status <> 'reconciled' OR matched_id IS NOT NULL",
            name="ck_bank_movements_reconciled_match",
        ),
        CheckConstraint(
            "matched_id IS NOT NULL OR difference_cents IS NULL",
            name="ck_bank_movements_unmatched_difference",
        ),
        CheckConstraint(
            "difference_cents IS NULL OR (difference_cents <> 0 AND status = 'difference')",
            name="ck_bank_movements_difference_value",
        ),
        UniqueConstraint(
            "bank_account_id", "import_hash", name="uq_bank_movements_import_hash"
        ),
        Index("ix_bank_movements_account_date", "bank_account_id", "occurred_on"),
        Index("ix_bank_movements_status", "status"),
        Index("ix_bank_movements_date", "occurred_on"),
        Index(
            "uq_bank_movements_match",
            "matched_source",
            "matched_id",
            unique=True,
            postgresql_where=text("matched_id IS NOT NULL"),
            sqlite_where=text("matched_id IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    bank_account_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("bank_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    occurred_on: date = Field(sa_column=Column(Date, nullable=False))
    amount_cents: int = Field(sa_type=BigInteger)
    currency: str = Field(
        default="MXN",
        sa_column=Column(String(3), nullable=False, server_default=text("'MXN'")),
    )
    reference: str = Field(
        default="",
        sa_column=Column(
            String(120), nullable=False, server_default=text("''")
        ),
    )
    description: str | None = Field(default=None, max_length=240)
    status: str = Field(
        default="pending",
        sa_column=Column(String(16), nullable=False, server_default=text("'pending'")),
    )
    matched_source: str | None = Field(default=None, max_length=24)
    matched_id: UUID | None = Field(default=None, sa_type=Uuid(as_uuid=True))
    matched_label: str | None = Field(default=None, max_length=240)
    difference_cents: int | None = Field(default=None, sa_type=BigInteger)
    note: str | None = Field(default=None, max_length=300)
    import_hash: str = Field(max_length=64)
    imported_by: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    imported_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    reconciled_by: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    reconciled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    reviewed_by: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    reviewed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class BankMovementEvent(SQLModel, table=True):
    """Append-only trail of a statement line: import, match, difference, reopen."""

    __tablename__ = "bank_movement_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('imported', 'matched', 'unmatched', 'flagged', 'reopened')",
            name="ck_bank_movement_events_type",
        ),
        Index("ix_bank_movement_events_movement_time", "movement_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    movement_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("bank_movements.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    event_type: str = Field(max_length=24)
    detail: str = Field(max_length=400)
    actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


__all__ = [
    "BANK_ACCOUNT_STATUSES",
    "BANK_MOVEMENT_EVENT_TYPES",
    "BANK_MOVEMENT_SOURCES",
    "BANK_MOVEMENT_STATUSES",
    "BankAccount",
    "BankMovement",
    "BankMovementEvent",
    "utc_now",
]
