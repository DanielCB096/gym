"""Add the attendance.self permission and grant it to every base role.

Employees mark their own attendance from the staff app, which is a different
capability from ``attendance.manage`` (reception/manager registering or
correcting attendance for others). The permission is granted to every base role
because any employee with an account may self-register.

The inserts look roles and permissions up by code (instead of assuming the seed
ids) so the migration stays correct even where a preview seed already created
the permission with a different id.

Revision ID: 20261016_0007
Revises: 20261016_0006
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op

revision = "20261016_0007"
down_revision = "20261016_0006"
branch_labels = None
depends_on = None

PERMISSION_CODE = "attendance.self"
PERMISSION_DESCRIPTION = "Marcar la propia asistencia"

ROLE_CODES = ("owner", "manager", "reception", "trainer", "maintenance", "accountant")


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    permission_id = _stable_id("permission", PERMISSION_CODE)
    op.execute(
        "INSERT INTO permissions (id, code, description) "
        f"SELECT '{permission_id}'::uuid, '{PERMISSION_CODE}', '{PERMISSION_DESCRIPTION}' "
        f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{PERMISSION_CODE}')"
    )
    for role_code in ROLE_CODES:
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT roles.id, permissions.id FROM roles, permissions "
            f"WHERE roles.code = '{role_code}' AND permissions.code = '{PERMISSION_CODE}' "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions USING roles, permissions "
        "WHERE role_permissions.role_id = roles.id AND role_permissions.permission_id = permissions.id "
        f"AND roles.code IN {ROLE_CODES!r} AND permissions.code = '{PERMISSION_CODE}'"
    )
    op.execute(f"DELETE FROM permissions WHERE code = '{PERMISSION_CODE}'")
