"""Add the member account ("cuenta del socio") and charge-on-account tender.

A sale can now be tendered with ``payment_method = "account"``: the member takes
the goods and owes the club. A return of such a sale is credited back to the
account with ``refund_method = "account"`` (money was never collected, so it can
never be refunded in cash). The new ``member_account_payments`` table records the
money the member later pays; the balance is computed as
``charges - account credits - payments`` and is never stored.

The same ``sales.read`` / ``sales.manage`` permissions operate the account, so no
new RBAC row is created.

Revision ID: 20261019_0017
Revises: 20261018_0016
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_0017"
down_revision = "20261018_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_sales_payment_method", "sales", type_="check")
    op.create_check_constraint(
        "ck_sales_payment_method",
        "sales",
        "payment_method IN ('cash', 'card', 'transfer', 'account')",
    )

    op.drop_constraint("ck_sale_returns_method", "sale_returns", type_="check")
    op.create_check_constraint(
        "ck_sale_returns_method",
        "sale_returns",
        "refund_method IN ('cash', 'card', 'transfer', 'account')",
    )

    op.create_table(
        "member_account_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cash_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "method IN ('cash', 'card', 'transfer')",
            name="ck_member_account_payments_method",
        ),
        sa.CheckConstraint(
            "amount_cents > 0", name="ck_member_account_payments_amount_positive"
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cash_session_id"], ["cash_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_member_account_payments_member_paid",
        "member_account_payments",
        ["member_id", "paid_at"],
    )
    op.create_index(
        "ix_member_account_payments_cash_session",
        "member_account_payments",
        ["cash_session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_member_account_payments_cash_session",
        table_name="member_account_payments",
    )
    op.drop_index(
        "ix_member_account_payments_member_paid",
        table_name="member_account_payments",
    )
    op.drop_table("member_account_payments")

    op.drop_constraint("ck_sale_returns_method", "sale_returns", type_="check")
    op.create_check_constraint(
        "ck_sale_returns_method",
        "sale_returns",
        "refund_method IN ('cash', 'card', 'transfer')",
    )

    op.drop_constraint("ck_sales_payment_method", "sales", type_="check")
    op.create_check_constraint(
        "ck_sales_payment_method",
        "sales",
        "payment_method IN ('cash', 'card', 'transfer')",
    )
