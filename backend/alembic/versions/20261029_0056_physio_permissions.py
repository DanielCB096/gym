"""Add the physiotherapy permissions.

The room is operated from reception: consulting the catalog, the agenda and the
member balances is one permission (``physio.read``) and operating them —
selling packs, booking, moving, cancelling and marking attendance — is another
(``physio.manage``). Charging does not get a third permission: the charge rides
on ``physio.manage``, exactly like a premium class charge rides on
``classes.manage``, and still needs an open register shift.

Revision ID: 20261029_0056
Revises: 20261029_0055
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op

revision = "20261029_0056"
down_revision = "20261029_0055"
branch_labels = None
depends_on = None

PERMISSIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "physio.read",
        "Consultar fisioterapia, agenda y saldos",
        ("owner", "manager", "reception", "trainer"),
    ),
    (
        "physio.manage",
        "Administrar fisioterapia, paquetes y citas",
        ("owner", "manager", "reception"),
    ),
)


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
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


def downgrade() -> None:
    for code, _description, role_codes in PERMISSIONS:
        for role_code in role_codes:
            op.execute(
                "DELETE FROM role_permissions USING roles, permissions "
                "WHERE role_permissions.role_id = roles.id "
                "AND role_permissions.permission_id = permissions.id "
                f"AND roles.code = '{role_code}' AND permissions.code = '{code}'"
            )
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")
