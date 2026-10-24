"""Add employees, user sessions, and role-based permissions."""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261015_0002"
down_revision = "20261015_0001"
branch_labels = None
depends_on = None

ROLE_PERMISSIONS = {
    "owner": (
        "dashboard.read", "members.read", "members.manage", "access.read", "access.manual_override",
        "staff.read", "staff.manage", "roles.manage", "attendance.read", "attendance.manage",
        "classes.read", "classes.manage", "inventory.read", "inventory.manage", "maintenance.read",
        "maintenance.manage", "payroll.read", "payroll.manage", "finance.read", "settings.manage",
    ),
    "manager": (
        "dashboard.read", "members.read", "members.manage", "access.read", "access.manual_override",
        "staff.read", "staff.manage", "attendance.read", "attendance.manage", "classes.read",
        "classes.manage", "inventory.read", "inventory.manage", "maintenance.read", "maintenance.manage",
        "payroll.read", "finance.read",
    ),
    "reception": (
        "dashboard.read", "members.read", "members.manage", "access.read", "access.manual_override",
        "attendance.read", "inventory.read",
    ),
    "trainer": ("dashboard.read", "classes.read", "classes.manage", "attendance.read", "members.read"),
    "maintenance": ("dashboard.read", "maintenance.read", "maintenance.manage", "inventory.read"),
    "accountant": ("dashboard.read", "finance.read", "payroll.read"),
}

ROLE_NAMES = {
    "owner": ("Dueño", "Administración completa del gimnasio."),
    "manager": ("Gerente", "Operación diaria y supervisión de la sucursal."),
    "reception": ("Recepción", "Atención a socios y operación de acceso."),
    "trainer": ("Entrenador", "Clases, agenda y seguimiento de socios."),
    "maintenance": ("Mantenimiento", "Equipos e instalaciones asignados."),
    "accountant": ("Contador", "Consulta financiera y de nómina."),
}

PERMISSION_DESCRIPTIONS = {
    "dashboard.read": "Consultar panel operativo",
    "members.read": "Consultar socios",
    "members.manage": "Crear y actualizar socios",
    "access.read": "Consultar bitácora de accesos",
    "access.manual_override": "Autorizar accesos manuales",
    "staff.read": "Consultar personal",
    "staff.manage": "Administrar expedientes de personal",
    "roles.manage": "Administrar roles y permisos",
    "attendance.read": "Consultar asistencias",
    "attendance.manage": "Registrar y corregir asistencias",
    "classes.read": "Consultar clases",
    "classes.manage": "Administrar clases y reservas",
    "inventory.read": "Consultar inventario",
    "inventory.manage": "Administrar inventario",
    "maintenance.read": "Consultar mantenimiento",
    "maintenance.manage": "Administrar mantenimiento",
    "payroll.read": "Consultar nómina",
    "payroll.manage": "Administrar nómina",
    "finance.read": "Consultar reportes financieros",
    "settings.manage": "Administrar configuración del gimnasio",
}


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_number", sa.String(length=40), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("job_title", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("hired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'inactive', 'terminated')", name="ck_employees_status"),
        sa.UniqueConstraint("employee_number", name="uq_employees_employee_number"),
    )
    op.create_index(
        "uq_employees_email_lower",
        "employees",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_table(
        "app_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_app_users_status"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("employee_id", name="uq_app_users_employee"),
    )
    op.create_index("uq_app_users_email_lower", "app_users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_table(
        "user_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > assigned_at",
            name="ck_user_role_assignments_expiry_order",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_user_role_assignments_active",
        "user_role_assignments",
        ["user_id", "role_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_user_role_assignments_user_expiry",
        "user_role_assignments",
        ["user_id", "expires_at", "revoked_at"],
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_user_sessions_expiry_order"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("token_sha256", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_user_expiry", "user_sessions", ["user_id", "expires_at", "revoked_at"])
    op.create_table(
        "auth_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("result IN ('success', 'failure')", name="ck_auth_events_result"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_auth_events_user_time", "auth_events", ["user_id", "occurred_at"])

    roles = [
        {"id": _stable_id("role", code), "code": code, "name": name, "description": description, "is_system": True}
        for code, (name, description) in ROLE_NAMES.items()
    ]
    permissions = [
        {"id": _stable_id("permission", code), "code": code, "description": description}
        for code, description in PERMISSION_DESCRIPTIONS.items()
    ]
    role_permissions = [
        {"role_id": _stable_id("role", role_code), "permission_id": _stable_id("permission", permission_code)}
        for role_code, permission_codes in ROLE_PERMISSIONS.items()
        for permission_code in permission_codes
    ]
    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("code", sa.String()),
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("is_system", sa.Boolean()),
        ),
        roles,
    )
    op.bulk_insert(
        sa.table(
            "permissions",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("code", sa.String()),
            sa.column("description", sa.Text()),
        ),
        permissions,
    )
    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role_id", postgresql.UUID(as_uuid=True)),
            sa.column("permission_id", postgresql.UUID(as_uuid=True)),
        ),
        role_permissions,
    )


def downgrade() -> None:
    op.drop_index("ix_auth_events_user_time", table_name="auth_events")
    op.drop_table("auth_events")
    op.drop_index("ix_user_sessions_user_expiry", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_user_role_assignments_user_expiry", table_name="user_role_assignments")
    op.drop_index("uq_user_role_assignments_active", table_name="user_role_assignments")
    op.drop_table("user_role_assignments")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_index("uq_app_users_email_lower", table_name="app_users")
    op.drop_table("app_users")
    op.drop_index("uq_employees_email_lower", table_name="employees")
    op.drop_table("employees")