"""Grant reception the attendance.manage permission.

The documented role matrix (docs/02-modulos/personal-y-roles.md) lets the
recepcionista register staff attendance, but the original RBAC seed migration
only granted ``attendance.read``. Production roles come exclusively from the
migrations (``ensure_default_access_control`` only runs in preview mode), so the
missing grant is corrected here. Trainers are intentionally left read-only.

Revision ID: 20261016_0003
Revises: 20261015_0002
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op

revision = "20261016_0003"
down_revision = "20261015_0002"
branch_labels = None
depends_on = None

# (role code, permission code) pairs to add.
GRANTS = (("reception", "attendance.manage"),)


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    for role_code, permission_code in GRANTS:
        role_id = _stable_id("role", role_code)
        permission_id = _stable_id("permission", permission_code)
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            f"VALUES ('{role_id}'::uuid, '{permission_id}'::uuid) "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        )


def downgrade() -> None:
    for role_code, permission_code in GRANTS:
        role_id = _stable_id("role", role_code)
        permission_id = _stable_id("permission", permission_code)
        op.execute(
            "DELETE FROM role_permissions "
            f"WHERE role_id = '{role_id}'::uuid AND permission_id = '{permission_id}'::uuid"
        )
