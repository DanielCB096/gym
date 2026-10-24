"""Create the membership and recurring billing foundation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261015_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'inactive')",
            name="ck_members_status",
        ),
    )
    op.create_index(
        "uq_members_email_lower",
        "members",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="MXN", nullable=False),
        sa.Column("billing_interval_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("duration_days > 0", name="ck_plans_duration_positive"),
        sa.CheckConstraint("price_cents >= 0", name="ck_plans_price_nonnegative"),
        sa.CheckConstraint(
            "billing_interval_days IS NULL OR billing_interval_days > 0",
            name="ck_plans_billing_interval_positive",
        ),
        sa.UniqueConstraint("code", name="uq_plans_code"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_payment', 'active', 'frozen', 'suspended', 'cancelled', 'expired')",
            name="ck_memberships_status",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_memberships_period_valid"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_memberships_member_status_ends", "memberships", ["member_id", "status", "ends_at"])
    op.create_index(
        "uq_memberships_one_nonterminal_per_member",
        "memberships",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_payment', 'active', 'frozen', 'suspended')"),
    )

    op.create_table(
        "member_consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=50), nullable=False),
        sa.Column("document_version", sa.String(length=80), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= accepted_at",
            name="ck_member_consents_revocation_order",
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_member_consents_member_type", "member_consents", ["member_id", "consent_type", "accepted_at"])

    op.create_table(
        "payment_methods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=160), nullable=True),
        sa.Column("provider_method_id", sa.String(length=160), nullable=False),
        sa.Column("encrypted_provider_token", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_payment_methods_status"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider", "provider_method_id", name="uq_payment_methods_provider_method"),
    )
    op.create_index(
        "uq_payment_methods_default_active",
        "payment_methods",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("is_default AND status = 'active'"),
    )

    op.create_table(
        "payment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_method_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="MXN", nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.CheckConstraint("method IN ('card', 'spei', 'cash', 'transfer')", name="ck_payment_attempts_method"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed', 'unknown', 'cancelled')",
            name="ck_payment_attempts_status",
        ),
        sa.CheckConstraint("attempt_number > 0", name="ck_payment_attempts_number_positive"),
        sa.CheckConstraint("amount_cents > 0", name="ck_payment_attempts_amount_positive"),
        sa.CheckConstraint(
            "method <> 'card' OR payment_method_id IS NOT NULL",
            name="ck_payment_attempts_card_method_required",
        ),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_method_id"], ["payment_methods.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_attempts_idempotency_key"),
        sa.UniqueConstraint(
            "membership_id",
            "due_at",
            "attempt_number",
            name="uq_payment_attempts_cycle_number",
        ),
        sa.UniqueConstraint("provider", "provider_reference", name="uq_payment_attempts_provider_reference"),
    )
    op.create_index("ix_payment_attempts_status_due", "payment_attempts", ["status", "due_at"])
    op.create_index("ix_payment_attempts_membership_due", "payment_attempts", ["membership_id", "due_at"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_payments_amount_positive"),
        sa.ForeignKeyConstraint(["payment_attempt_id"], ["payment_attempts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("payment_attempt_id", name="uq_payments_attempt"),
    )
    op.create_index("ix_payments_member_paid", "payments", ["member_id", "paid_at"])
    op.create_index("ix_payments_membership_paid", "payments", ["membership_id", "paid_at"])

    op.create_table(
        "provider_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="received", nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'ignored')",
            name="ck_provider_webhook_events_status",
        ),
        sa.ForeignKeyConstraint(["payment_attempt_id"], ["payment_attempts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_provider_webhook_events_external_id"),
    )
    op.create_index("ix_provider_webhook_events_attempt", "provider_webhook_events", ["payment_attempt_id"])

    op.create_table(
        "payment_attempt_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source IN ('api', 'webhook', 'worker', 'operator')", name="ck_payment_attempt_events_source"),
        sa.ForeignKeyConstraint(["payment_attempt_id"], ["payment_attempts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["webhook_event_id"], ["provider_webhook_events.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_payment_attempt_events_attempt_time",
        "payment_attempt_events",
        ["payment_attempt_id", "occurred_at"],
    )

    op.create_table(
        "membership_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('member', 'employee', 'system', 'provider')",
            name="ck_membership_events_actor_type",
        ),
        sa.CheckConstraint("jsonb_typeof(metadata) = 'object'", name="ck_membership_events_metadata_object"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_membership_events_membership_time", "membership_events", ["membership_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_membership_events_membership_time", table_name="membership_events")
    op.drop_table("membership_events")
    op.drop_index("ix_payment_attempt_events_attempt_time", table_name="payment_attempt_events")
    op.drop_table("payment_attempt_events")
    op.drop_index("ix_provider_webhook_events_attempt", table_name="provider_webhook_events")
    op.drop_table("provider_webhook_events")
    op.drop_index("ix_payments_membership_paid", table_name="payments")
    op.drop_index("ix_payments_member_paid", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_payment_attempts_membership_due", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_status_due", table_name="payment_attempts")
    op.drop_table("payment_attempts")
    op.drop_index("uq_payment_methods_default_active", table_name="payment_methods")
    op.drop_table("payment_methods")
    op.drop_index("ix_member_consents_member_type", table_name="member_consents")
    op.drop_table("member_consents")
    op.drop_index("uq_memberships_one_nonterminal_per_member", table_name="memberships")
    op.drop_index("ix_memberships_member_status_ends", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("plans")
    op.drop_index("uq_members_email_lower", table_name="members")
    op.drop_table("members")