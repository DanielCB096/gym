"""Distinguish statements from collection reminders in the delivery log.

The reminder reuses the statement snapshot and the same append-only audit table,
but it has its own purpose so the seven-day frequency rule only looks at
reminders and the panel can label each attempt correctly.

Revision ID: 20261021_0022
Revises: 20261019_0021
"""

from alembic import op
import sqlalchemy as sa

revision = "20261021_0022"
down_revision = "20261019_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "member_account_statement_deliveries",
        sa.Column(
            "purpose",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'statement'"),
        ),
    )
    op.create_check_constraint(
        "ck_member_account_statement_deliveries_purpose",
        "member_account_statement_deliveries",
        "purpose IN ('statement', 'reminder')",
    )
    op.create_index(
        "ix_member_account_statement_deliveries_member_purpose_created",
        "member_account_statement_deliveries",
        ["member_id", "purpose", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_member_account_statement_deliveries_member_purpose_created",
        table_name="member_account_statement_deliveries",
    )
    op.drop_constraint(
        "ck_member_account_statement_deliveries_purpose",
        "member_account_statement_deliveries",
        type_="check",
    )
    op.drop_column("member_account_statement_deliveries", "purpose")
