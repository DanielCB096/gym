"""Audit the member account statements sent by email.

Exporting a statement is read-only, but *sending* it leaves the club's systems
and needs an audit trail: who sent it, to which address, with which format, for
which cut-off date, and whether the SMTP transport actually ran. The new
``member_account_statement_deliveries`` table stores that attempt. The account
balance is still computed from the sales, returns and payments, so this table
never becomes a second ledger.

Preview mode records ``simulated`` deliveries and never contacts a real SMTP
server. A failed transport is recorded as ``failed`` with the error, even though
the API returns an error to the caller.

Revision ID: 20261019_0020
Revises: 20261019_0019
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_0020"
down_revision = "20261019_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_account_statement_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "channel IN ('email')",
            name="ck_member_account_statement_deliveries_channel",
        ),
        sa.CheckConstraint(
            "format IN ('pdf', 'csv')",
            name="ck_member_account_statement_deliveries_format",
        ),
        sa.CheckConstraint(
            "status IN ('sent', 'simulated', 'failed')",
            name="ck_member_account_statement_deliveries_status",
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_member_account_statement_deliveries_member_created",
        "member_account_statement_deliveries",
        ["member_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_member_account_statement_deliveries_member_created",
        table_name="member_account_statement_deliveries",
    )
    op.drop_table("member_account_statement_deliveries")
