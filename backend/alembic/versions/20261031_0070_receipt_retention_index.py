"""Index the receipts by reception so the retention purge stays cheap.

The provider receipts are append-only and grow with every acknowledgement. A
retention task deletes them by ``received_at`` (ADR-058), which the existing
``(delivery_id, received_at)`` index cannot serve: this revision adds a plain
index on the date the club stored the report.

Revision ID: 20261031_0070
Revises: 20261031_0069
"""

from alembic import op

revision = "20261031_0070"
down_revision = "20261031_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_staff_notification_delivery_receipts_received",
        "staff_notification_delivery_receipts",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staff_notification_delivery_receipts_received",
        table_name="staff_notification_delivery_receipts",
    )
