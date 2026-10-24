"""Add the routines permissions and grant them to owner, manager and trainer.

Routines are the trainer's working surface: the library, the plans, the
assignments and the progress record. ``routines.read`` covers consulting them
and ``routines.manage`` covers creating/editing plans and assigning or logging.
Reception, maintenance and accounting do not get either permission (the module
spec gives them no routines role).

The inserts look roles and permissions up by code (instead of assuming the seed
ids) so the migration stays correct where a preview seed already created the
permission with a different id.

Revision ID: 20261017_0011
Revises: 20261017_0010
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op

revision = "20261017_0011"
down_revision = "20261017_0010"
branch_labels = None
depends_on = None

PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("routines.read", "Consultar rutinas y progreso"),
    ("routines.manage", "Administrar rutinas, asignaciones y progreso"),
)

ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "owner": ("routines.read", "routines.manage"),
    "manager": ("routines.read", "routines.manage"),
    "trainer": ("routines.read", "routines.manage"),
}


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    for code, description in PERMISSIONS:
        permission_id = _stable_id("permission", code)
        op.execute(
            "INSERT INTO permissions (id, code, description) "
            f"SELECT '{permission_id}'::uuid, '{code}', '{description}' "
            f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{code}')"
        )
    for role_code, codes in ROLE_GRANTS.items():
        for code in codes:
            op.execute(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT roles.id, permissions.id FROM roles, permissions "
                f"WHERE roles.code = '{role_code}' AND permissions.code = '{code}' "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            )


def downgrade() -> None:
    codes = tuple(code for code, _ in PERMISSIONS)
    for role_code, role_codes in ROLE_GRANTS.items():
        for code in role_codes:
            op.execute(
                "DELETE FROM role_permissions USING roles, permissions "
                "WHERE role_permissions.role_id = roles.id "
                "AND role_permissions.permission_id = permissions.id "
                f"AND roles.code = '{role_code}' AND permissions.code = '{code}'"
            )
    for code in codes:
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")
