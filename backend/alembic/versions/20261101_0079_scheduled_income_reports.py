"""Track scheduled income report delivery idempotently.

Revision ID: 20261101_0079
Revises: 20261031_0078
"""

from alembic import op
import sqlalchemy as sa

revision = "20261101_0079"
down_revision = "20261031_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_report_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("frequency", sa.String(length=8), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("recipient_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'sending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "frequency IN ('daily', 'weekly', 'monthly')",
            name="ck_scheduled_report_deliveries_frequency",
        ),
        sa.CheckConstraint(
            "status IN ('sending', 'sent', 'simulated', 'failed')",
            name="ck_scheduled_report_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempts >= 1",
            name="ck_scheduled_report_deliveries_attempts",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_scheduled_report_delivery_key"
        ),
    )
    op.create_index(
        "ix_scheduled_report_deliveries_status_claimed",
        "scheduled_report_deliveries",
        ["status", "claimed_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    delivery_count = bind.execute(
        sa.text("SELECT count(*) FROM scheduled_report_deliveries")
    ).scalar()
    if delivery_count:
        raise RuntimeError(
            "No se puede retirar el registro de entregas programadas mientras "
            f"conserve {delivery_count} fila(s); archívalas primero."
        )
    op.drop_index(
        "ix_scheduled_report_deliveries_status_claimed",
        table_name="scheduled_report_deliveries",
    )
    op.drop_table("scheduled_report_deliveries")
