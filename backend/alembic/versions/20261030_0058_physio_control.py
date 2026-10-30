"""Add the room control layer: rooms, specialties, therapist profiles and pack
adjustments, plus the reminder kind.

Increment 3 closes the loop around the room without changing how money moves:
the prepaid pack can be extended or voided (never refunded), the therapist can
be described with an optional specialty and default room, the appointment can
point at the room catalog, and the member gets a notice 24 hours before a
session. A new permission, ``physio.adjust``, guards the pack adjustments so
reception keeps operating the agenda while a manager decides about balances.

Revision ID: 20261030_0058
Revises: 20261029_0057
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261030_0058"
down_revision = "20261029_0057"
branch_labels = None
depends_on = None

OLD_KINDS = (
    "'workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
    "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
    "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
    "'invoice_cancelled', 'class_reminder', 'class_reserved', "
    "'class_cancelled', 'class_rescheduled', 'physio_appointment_scheduled', "
    "'physio_appointment_cancelled', 'physio_appointment_rescheduled'"
)

PERMISSIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "physio.adjust",
        "Extender o anular paquetes de fisioterapia",
        ("owner", "manager"),
    ),
)


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    op.create_table(
        "physio_rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
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
    )
    op.create_index(
        "uq_physio_rooms_name_lower",
        "physio_rooms",
        [sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "physio_specialties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
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
    )
    op.create_index(
        "uq_physio_specialties_name_lower",
        "physio_specialties",
        [sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "physio_therapist_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "specialty_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physio_specialties.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physio_rooms.id", ondelete="RESTRICT"),
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
        sa.UniqueConstraint(
            "employee_id", name="uq_physio_therapist_profiles_employee"
        ),
    )
    op.create_index(
        "ix_physio_therapist_profiles_specialty",
        "physio_therapist_profiles",
        ["specialty_id"],
    )
    op.create_index(
        "ix_physio_therapist_profiles_room",
        "physio_therapist_profiles",
        ["room_id"],
    )

    op.create_table(
        "physio_pack_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pack_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("physio_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("days", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column(
            "actor_id",
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
        sa.CheckConstraint(
            "kind IN ('extension', 'void')", name="ck_physio_pack_adjustments_kind"
        ),
        sa.CheckConstraint(
            "days IS NULL OR days > 0", name="ck_physio_pack_adjustments_days"
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 300",
            name="ck_physio_pack_adjustments_reason",
        ),
    )
    op.create_index(
        "ix_physio_pack_adjustments_pack_time",
        "physio_pack_adjustments",
        ["pack_id", "created_at"],
    )

    op.add_column(
        "physio_packs",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "physio_packs",
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_physio_packs_voided_by",
        "physio_packs",
        "app_users",
        ["voided_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "physio_packs",
        sa.Column("void_reason", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "physio_packs",
        sa.Column(
            "voided_sessions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_physio_packs_voided_range",
        "physio_packs",
        "voided_sessions >= 0 AND voided_sessions <= sessions_total",
    )

    op.add_column(
        "physio_appointments",
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_physio_appointments_room",
        "physio_appointments",
        "physio_rooms",
        ["room_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_physio_appointments_room", "physio_appointments", ["room_id"]
    )

    for code, description, role_codes in PERMISSIONS:
        permission_id = _stable_id("permission", code)
        op.execute(
            "INSERT INTO permissions (id, code, description) "
            f"SELECT '{permission_id}'::uuid, '{code}', '{description}' "
            f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{code}')"
        )
        for role_code in role_codes:
            op.execute(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT roles.id, permissions.id FROM roles, permissions "
                f"WHERE roles.code = '{role_code}' AND permissions.code = '{code}' "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            )

    op.drop_constraint(
        "ck_member_notifications_kind", "member_notifications", type_="check"
    )
    op.create_check_constraint(
        "ck_member_notifications_kind",
        "member_notifications",
        f"kind IN ({OLD_KINDS}, 'physio_reminder')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    remaining = bind.execute(
        sa.text(
            "SELECT count(*) FROM member_notifications WHERE kind = 'physio_reminder'"
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "No se puede revertir mientras existan recordatorios de fisioterapia "
            f"({remaining} filas); bórralos primero si de verdad quieres retirar el tipo"
        )
    op.drop_constraint(
        "ck_member_notifications_kind", "member_notifications", type_="check"
    )
    op.create_check_constraint(
        "ck_member_notifications_kind", "member_notifications", f"kind IN ({OLD_KINDS})"
    )

    for code, _description, role_codes in PERMISSIONS:
        for role_code in role_codes:
            op.execute(
                "DELETE FROM role_permissions USING roles, permissions "
                "WHERE role_permissions.role_id = roles.id "
                "AND role_permissions.permission_id = permissions.id "
                f"AND roles.code = '{role_code}' AND permissions.code = '{code}'"
            )
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")

    op.drop_index("ix_physio_appointments_room", table_name="physio_appointments")
    op.drop_constraint(
        "fk_physio_appointments_room", "physio_appointments", type_="foreignkey"
    )
    op.drop_column("physio_appointments", "room_id")

    op.drop_constraint(
        "ck_physio_packs_voided_range", "physio_packs", type_="check"
    )
    op.drop_column("physio_packs", "voided_sessions")
    op.drop_column("physio_packs", "void_reason")
    op.drop_constraint("fk_physio_packs_voided_by", "physio_packs", type_="foreignkey")
    op.drop_column("physio_packs", "voided_by")
    op.drop_column("physio_packs", "voided_at")

    op.drop_index(
        "ix_physio_pack_adjustments_pack_time", table_name="physio_pack_adjustments"
    )
    op.drop_table("physio_pack_adjustments")

    op.drop_index(
        "ix_physio_therapist_profiles_room", table_name="physio_therapist_profiles"
    )
    op.drop_index(
        "ix_physio_therapist_profiles_specialty",
        table_name="physio_therapist_profiles",
    )
    op.drop_table("physio_therapist_profiles")

    op.drop_index(
        "uq_physio_specialties_name_lower", table_name="physio_specialties"
    )
    op.drop_table("physio_specialties")

    op.drop_index("uq_physio_rooms_name_lower", table_name="physio_rooms")
    op.drop_table("physio_rooms")
