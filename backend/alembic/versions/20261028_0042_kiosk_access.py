"""Rotating member access codes and reception kiosks.

The member app shows a six-digit code that the tablet at the front desk
validates. Three tables carry that flow: ``member_access_codes`` (HMAC digest,
expiry, single use), ``kiosk_devices`` (SHA-256 token digest, one per tablet)
and ``kiosk_attempts`` (feed for the per-device rate limit). Access decisions
keep landing in ``access_events``, so this migration adds no columns there.

Revision ID: 20261028_0042
Revises: 20261028_0041
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261028_0042"
down_revision = "20261028_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kiosk_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')", name="ck_kiosk_devices_status"
        ),
        sa.UniqueConstraint("token_sha256", name="uq_kiosk_devices_token"),
    )

    op.create_table(
        "member_access_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_member_access_codes_expiry_order"
        ),
    )
    op.create_index(
        "ix_member_access_codes_member_created",
        "member_access_codes",
        ["member_id", "created_at"],
    )
    op.create_index(
        "ix_member_access_codes_hash", "member_access_codes", ["code_hash"]
    )

    op.create_table(
        "kiosk_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kiosk_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "result IN ('authorized', 'denied', 'invalid')",
            name="ck_kiosk_attempts_result",
        ),
    )
    op.create_index(
        "ix_kiosk_attempts_device_occurred",
        "kiosk_attempts",
        ["device_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_kiosk_attempts_device_occurred", table_name="kiosk_attempts")
    op.drop_table("kiosk_attempts")
    op.drop_index("ix_member_access_codes_hash", table_name="member_access_codes")
    op.drop_index(
        "ix_member_access_codes_member_created", table_name="member_access_codes"
    )
    op.drop_table("member_access_codes")
    op.drop_table("kiosk_devices")
