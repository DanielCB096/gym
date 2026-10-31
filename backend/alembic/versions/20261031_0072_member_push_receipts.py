"""Keep Expo's ticket and the receipt it later answers.

The delivery row records that Expo accepted the push; the receipt says whether
the phone got it. This revision stores the ticket on the delivery (it is the
handle of the later question) and creates the table where the answer lands, one
receipt per delivery.

Revision ID: 20261031_0072
Revises: 20261031_0071
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0072"
down_revision = "20261031_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "member_push_deliveries",
        sa.Column("expo_ticket_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "member_push_deliveries",
        sa.Column("receipt_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "member_push_delivery_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["member_push_deliveries.id"],
            name="fk_member_push_delivery_receipts_delivery",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "delivery_id",
            name="uq_member_push_delivery_receipts_delivery",
        ),
        sa.UniqueConstraint(
            "ticket_id",
            name="uq_member_push_delivery_receipts_ticket",
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'expired')",
            name="ck_member_push_delivery_receipts_status",
        ),
    )
    op.create_index(
        "ix_member_push_delivery_receipts_received",
        "member_push_delivery_receipts",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_member_push_delivery_receipts_received",
        table_name="member_push_delivery_receipts",
    )
    op.drop_table("member_push_delivery_receipts")
    op.drop_column("member_push_deliveries", "receipt_checked_at")
    op.drop_column("member_push_deliveries", "expo_ticket_id")
