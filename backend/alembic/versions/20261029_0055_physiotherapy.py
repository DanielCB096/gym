"""Open the physiotherapy room: catalog, prepaid packs and agenda.

The room sells two things: a single session and a prepaid pack of sessions.
Both are ordinary service sales in the existing ledger (SKU ``FISIO``), which
keeps the register shift, the member account, the revenue report and invoicing
working without a parallel ledger. The pack is the balance the sale bought;
the appointment is the slot, and it grows a nullable link from ``sales`` so the
single session charged at attendance can be found (and refunded) from its own
appointment.

Revision ID: 20261029_0055
Revises: 20261029_0054
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261029_0055"
down_revision = "20261029_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "physio_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "duration_minutes > 0", name="ck_physio_services_duration_positive"
        ),
        sa.CheckConstraint(
            "price_cents >= 0", name="ck_physio_services_price_nonnegative"
        ),
    )
    op.create_index(
        "uq_physio_services_code_lower",
        "physio_services",
        [sa.text("lower(code)")],
        unique=True,
    )

    op.create_table(
        "physio_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physio_services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("list_price_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "validity_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("31"),
        ),
        sa.Column(
            "payment_mode",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'single'"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("sessions >= 1", name="ck_physio_offers_sessions_positive"),
        sa.CheckConstraint(
            "price_cents >= 0", name="ck_physio_offers_price_nonnegative"
        ),
        sa.CheckConstraint(
            "list_price_cents >= price_cents",
            name="ck_physio_offers_discount_nonnegative",
        ),
        sa.CheckConstraint(
            "validity_days > 0", name="ck_physio_offers_validity_positive"
        ),
        sa.CheckConstraint(
            "payment_mode IN ('single')", name="ck_physio_offers_payment_mode"
        ),
    )
    op.create_index(
        "uq_physio_offers_name_lower",
        "physio_offers",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_index("ix_physio_offers_service", "physio_offers", ["service_id"])

    op.create_table(
        "physio_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "offer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physio_offers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sessions_total", sa.Integer(), nullable=False),
        sa.Column(
            "sessions_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "purchased_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "sessions_total > 0", name="ck_physio_packs_total_positive"
        ),
        sa.CheckConstraint(
            "sessions_used >= 0 AND sessions_used <= sessions_total",
            name="ck_physio_packs_used_range",
        ),
        sa.CheckConstraint(
            "price_cents >= 0", name="ck_physio_packs_price_nonnegative"
        ),
        sa.UniqueConstraint("sale_id", name="uq_physio_packs_sale"),
    )
    op.create_index(
        "ix_physio_packs_member_validity",
        "physio_packs",
        ["member_id", "valid_until"],
    )

    op.create_table(
        "physio_appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physio_services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "pack_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physio_packs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "therapist_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("room", sa.String(length=80), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'scheduled'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "booked_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "marked_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_by",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'attended', 'no_show', 'cancelled')",
            name="ck_physio_appointments_status",
        ),
        sa.CheckConstraint(
            "ends_at > starts_at", name="ck_physio_appointments_time_range"
        ),
    )
    op.create_index(
        "uq_physio_appointments_therapist_start",
        "physio_appointments",
        ["therapist_employee_id", "starts_at"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.create_index(
        "ix_physio_appointments_starts_at", "physio_appointments", ["starts_at"]
    )
    op.create_index(
        "ix_physio_appointments_member",
        "physio_appointments",
        ["member_id", "starts_at"],
    )
    op.create_index(
        "ix_physio_appointments_pack", "physio_appointments", ["pack_id"]
    )

    op.add_column(
        "sales",
        sa.Column("physio_appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sales_physio_appointment",
        "sales",
        "physio_appointments",
        ["physio_appointment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sales_physio_appointment", "sales", ["physio_appointment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_sales_physio_appointment", table_name="sales")
    op.drop_constraint("fk_sales_physio_appointment", "sales", type_="foreignkey")
    op.drop_column("sales", "physio_appointment_id")

    op.drop_index(
        "ix_physio_appointments_pack", table_name="physio_appointments"
    )
    op.drop_index(
        "ix_physio_appointments_member", table_name="physio_appointments"
    )
    op.drop_index(
        "ix_physio_appointments_starts_at", table_name="physio_appointments"
    )
    op.drop_index(
        "uq_physio_appointments_therapist_start", table_name="physio_appointments"
    )
    op.drop_table("physio_appointments")

    op.drop_index(
        "ix_physio_packs_member_validity", table_name="physio_packs"
    )
    op.drop_table("physio_packs")

    op.drop_index("ix_physio_offers_service", table_name="physio_offers")
    op.drop_index("uq_physio_offers_name_lower", table_name="physio_offers")
    op.drop_table("physio_offers")

    op.drop_index("uq_physio_services_code_lower", table_name="physio_services")
    op.drop_table("physio_services")
