"""Member self-service login with one-time email codes.

Revision ID: 20261027_0031
Revises: 20261025_0030
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_0031"
down_revision = "20261025_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_login_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("attempts >= 0", name="ck_member_login_codes_attempts"),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_member_login_codes_expiry_order",
        ),
    )
    op.create_index(
        "ix_member_login_codes_member_created",
        "member_login_codes",
        ["member_id", "created_at"],
    )

    op.create_table(
        "member_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_member_sessions_expiry_order",
        ),
        sa.UniqueConstraint("token_sha256", name="uq_member_sessions_token_hash"),
    )
    op.create_index(
        "ix_member_sessions_member_expiry",
        "member_sessions",
        ["member_id", "expires_at", "revoked_at"],
    )

    op.create_table(
        "member_auth_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "result IN ('success', 'failure')",
            name="ck_member_auth_events_result",
        ),
    )
    op.create_index(
        "ix_member_auth_events_member_time",
        "member_auth_events",
        ["member_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_member_auth_events_member_time", table_name="member_auth_events")
    op.drop_table("member_auth_events")
    op.drop_index("ix_member_sessions_member_expiry", table_name="member_sessions")
    op.drop_table("member_sessions")
    op.drop_index("ix_member_login_codes_member_created", table_name="member_login_codes")
    op.drop_table("member_login_codes")
