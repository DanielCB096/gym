"""Let the mail provider acknowledge the staff emails.

The queue records what the SMTP server answered, which is all the club can know
on its own: the server accepted the message. What happened afterwards is only
known by the provider, so this revision prepares the return path —the message
identifier the delivery left with and an append-only table of provider events—
before a signed webhook starts filling it. Receipts never rewrite the transport
status: a ``sent`` row keeps meaning "the server accepted it".

Revision ID: 20261031_0066
Revises: 20261031_0065
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0066"
down_revision = "20261031_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff_notification_deliveries",
        sa.Column("message_id", sa.String(length=320), nullable=True),
    )
    op.create_index(
        "ix_staff_notification_deliveries_message_id",
        "staff_notification_deliveries",
        ["message_id"],
        unique=True,
    )

    op.create_table(
        "staff_notification_delivery_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
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
            ["staff_notification_deliveries.id"],
            name="fk_staff_notification_delivery_receipts_delivery",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "provider_event_id",
            name="uq_staff_notification_delivery_receipts_event",
        ),
        sa.CheckConstraint(
            "event_type IN ('delivered', 'bounced', 'complained')",
            name="ck_staff_notification_delivery_receipts_event",
        ),
    )
    op.create_index(
        "ix_staff_notification_delivery_receipts_delivery_time",
        "staff_notification_delivery_receipts",
        ["delivery_id", "received_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    receipts = bind.execute(
        sa.text("SELECT count(*) FROM staff_notification_delivery_receipts")
    ).scalar()
    if receipts:
        raise RuntimeError(
            "No se puede revertir mientras existan acuses del proveedor "
            f"({receipts}); se perdería la trazabilidad de las entregas"
        )

    op.drop_index(
        "ix_staff_notification_delivery_receipts_delivery_time",
        table_name="staff_notification_delivery_receipts",
    )
    op.drop_table("staff_notification_delivery_receipts")
    op.drop_index(
        "ix_staff_notification_deliveries_message_id",
        table_name="staff_notification_deliveries",
    )
    op.drop_column("staff_notification_deliveries", "message_id")
