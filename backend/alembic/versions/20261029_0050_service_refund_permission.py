"""Add the sales.service_refund permission.

The premium class charge is a service sale: nothing returns to stock and the
only record of the payout is the return row. The reservation flow refunds it
automatically, but a refund outside that flow (a comp, a duplicate charge, a
gesture) had no door in the panel. Refunding it from the register is a money
decision, not a counter operation, so it gets its own permission granted to the
owner and manager roles only; reception keeps ``sales.manage`` for products.

Revision ID: 20261029_0050
Revises: 20261029_0049
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op

revision = "20261029_0050"
down_revision = "20261029_0049"
branch_labels = None
depends_on = None

PERMISSION_CODE = "sales.service_refund"
PERMISSION_DESCRIPTION = "Reembolsar servicios cobrados (clases premium)"
ROLE_GRANTS = ("owner", "manager")


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    permission_id = _stable_id("permission", PERMISSION_CODE)
    op.execute(
        "INSERT INTO permissions (id, code, description) "
        f"SELECT '{permission_id}'::uuid, '{PERMISSION_CODE}', '{PERMISSION_DESCRIPTION}' "
        f"WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = '{PERMISSION_CODE}')"
    )
    for role_code in ROLE_GRANTS:
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT roles.id, permissions.id FROM roles, permissions "
            f"WHERE roles.code = '{role_code}' AND permissions.code = '{PERMISSION_CODE}' "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        )


def downgrade() -> None:
    for role_code in ROLE_GRANTS:
        op.execute(
            "DELETE FROM role_permissions USING roles, permissions "
            "WHERE role_permissions.role_id = roles.id "
            "AND role_permissions.permission_id = permissions.id "
            f"AND roles.code = '{role_code}' AND permissions.code = '{PERMISSION_CODE}'"
        )
    op.execute(f"DELETE FROM permissions WHERE code = '{PERMISSION_CODE}'")
