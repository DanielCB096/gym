"""Record staff-collected membership payments and link them to the cash shift.

The first version activated a plan without charging. This migration adds the
fields needed to turn the existing ``payments`` table into a complete manual
payment receipt: the period it covers, the cash session that collected it, the
operator and an optional note. It also relaxes the card-method check so a
front-desk card payment can be declared without a gateway token.

Revision ID: 20261021_0023
Revises: 20261021_0022
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261021_0023"
down_revision = "20261021_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("period_starts_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("period_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("cash_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("collected_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("payments", sa.Column("note", sa.String(length=200), nullable=True))
    op.create_index(
        "ix_payments_cash_session",
        "payments",
        ["cash_session_id"],
    )
    op.drop_constraint(
        "ck_payment_attempts_card_method_required",
        "payment_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_payment_attempts_card_method_required",
        "payment_attempts",
        "method <> 'card' OR payment_method_id IS NOT NULL OR provider IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_payment_attempts_card_method_required",
        "payment_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_payment_attempts_card_method_required",
        "payment_attempts",
        "method <> 'card' OR payment_method_id IS NOT NULL",
    )
    op.drop_index("ix_payments_cash_session", table_name="payments")
    op.drop_column("payments", "note")
    op.drop_column("payments", "collected_by")
    op.drop_column("payments", "cash_session_id")
    op.drop_column("payments", "period_ends_at")
    op.drop_column("payments", "period_starts_at")
