"""Add the sessions.manage permission and grant it to the owner role.

Session administration is a security/audit action, so it gets its own permission
instead of overloading ``roles.manage``. Production roles come exclusively from
the migrations, so the permission and the owner grant are added here.

The inserts look up roles and permissions by code (instead of assuming the stable
seed ids) so the migration stays correct even where a preview seed already
created the permission with a different id.

Revision ID: 20261016_0006
Revises: 20261016_0005
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op

revision = "20261016_0006"
down_revision = "20261016_0005"
branch_labels = None
depends_on = None

PERMISSION_CODE = "sessions.manage"
PERMISSION_DESCRIPTION = "Administrar sesiones activas"


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    permission_id = _stable_id("permission", PERMISSION_CODE)
    op.execute(
        "INSERT INTO permissions (id, code, description) "
        f"SELECT '{permission_id}'::uuid, '{PERMISSION_CODE}', '{PERMISSION_DESCRIPTION}' "
        f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{PERMISSION_CODE}')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT roles.id, permissions.id FROM roles, permissions "
        f"WHERE roles.code = 'owner' AND permissions.code = '{PERMISSION_CODE}' "
        "ON CONFLICT (role_id, permission_id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions USING roles, permissions "
        f"WHERE role_permissions.role_id = roles.id AND role_permissions.permission_id = permissions.id "
        f"AND roles.code = 'owner' AND permissions.code = '{PERMISSION_CODE}'"
    )
    op.execute(f"DELETE FROM permissions WHERE code = '{PERMISSION_CODE}'")
