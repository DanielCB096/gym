"""Persist hosted provider checkout details on payment attempts."""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0075"
down_revision = "20261031_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_attempts",
        sa.Column("provider_order_id", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "payment_attempts",
        sa.Column("checkout_url", sa.String(length=2048), nullable=True),
    )
    op.create_unique_constraint(
        "uq_payment_attempts_provider_order",
        "payment_attempts",
        ["provider", "provider_order_id"],
    )
    op.drop_constraint(
        "ck_payment_attempts_card_method_required",
        "payment_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_payment_attempts_card_method_required",
        "payment_attempts",
        "method <> 'card' OR payment_method_id IS NOT NULL OR provider IS NULL "
        "OR provider = 'conekta'",
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
        "method <> 'card' OR payment_method_id IS NOT NULL OR provider IS NULL",
    )
    op.drop_constraint(
        "uq_payment_attempts_provider_order",
        "payment_attempts",
        type_="unique",
    )
    op.drop_column("payment_attempts", "checkout_url")
    op.drop_column("payment_attempts", "provider_order_id")
