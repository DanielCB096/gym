"""Add the member credit limit and the sales.credit permission.

A member can carry store credit ("cuenta del socio"). Until now the account had
no ceiling: the only rule was that the member existed and was active. The new
``members.credit_limit_cents`` is nullable so existing installations keep the
old behavior (``NULL`` = no limit); ``0`` means the member cannot charge
anything, and any positive value caps the outstanding balance.

The aging report does not need a new table: it is computed from the account
sales, returns and payments every time the account is read, applying credits
and payments FIFO to the oldest charges.

Setting a credit limit is a policy decision, not a counter operation, so it gets
its own ``sales.credit`` permission granted to the owner and manager roles only
(reception keeps ``sales.read`` / ``sales.manage`` for the register).

Revision ID: 20261019_0019
Revises: 20261019_0018
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = "20261019_0019"
down_revision = "20261019_0018"
branch_labels = None
depends_on = None

PERMISSION_CODE = "sales.credit"
PERMISSION_DESCRIPTION = "Administrar límites de crédito de socios"
ROLE_GRANTS = ("owner", "manager")


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    op.add_column(
        "members",
        sa.Column("credit_limit_cents", sa.BigInteger(), nullable=True),
    )
    op.create_check_constraint(
        "ck_members_credit_limit",
        "members",
        "credit_limit_cents IS NULL OR credit_limit_cents >= 0",
    )

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

    op.drop_constraint("ck_members_credit_limit", "members", type_="check")
    op.drop_column("members", "credit_limit_cents")
