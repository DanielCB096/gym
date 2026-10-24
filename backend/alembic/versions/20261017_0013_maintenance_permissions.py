"""Add the ``maintenance.report`` permission.

``maintenance.read`` / ``maintenance.manage`` already exist from the identity
RBAC seed. Reporting a fault is a different job from repairing it: reception and
trainers must be able to flag a broken machine and take it out of service, but
they do not resolve tickets, assign technicians or approve costs. This revision
adds ``maintenance.report`` for them and widens ``maintenance.read`` to
reception and trainers so the front desk can answer "is that machine working?".

Revision ID: 20261017_0013
Revises: 20261017_0012
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op

revision = "20261017_0013"
down_revision = "20261017_0012"
branch_labels = None
depends_on = None

PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("maintenance.report", "Reportar fallas y poner equipos fuera de servicio"),
)

# ``maintenance.read`` is granted here to roles that did not have it; the
# existing owner/manager/maintenance grants are left untouched.
ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "owner": ("maintenance.report",),
    "manager": ("maintenance.report",),
    "maintenance": ("maintenance.report",),
    "reception": ("maintenance.read", "maintenance.report"),
    "trainer": ("maintenance.read", "maintenance.report"),
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
    for role_code, role_codes in ROLE_GRANTS.items():
        for code in role_codes:
            op.execute(
                "DELETE FROM role_permissions USING roles, permissions "
                "WHERE role_permissions.role_id = roles.id "
                "AND role_permissions.permission_id = permissions.id "
                f"AND roles.code = '{role_code}' AND permissions.code = '{code}'"
            )
    for code, _description in PERMISSIONS:
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")
