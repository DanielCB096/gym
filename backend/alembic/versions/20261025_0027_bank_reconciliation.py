"""Bank reconciliation: accounts, statement lines and their audit trail.

A bank line never creates or edits money: it only links to the payment, sale,
account payment or return that already recorded the operation. The partial
unique index on ``(matched_source, matched_id)`` keeps one internal movement
from being claimed by two statement lines.

Revision ID: 20261025_0027
Revises: 20261025_0026
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261025_0027"
down_revision = "20261025_0026"
branch_labels = None
depends_on = None

PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("finance.manage", "Conciliar pagos y administrar cuentas bancarias"),
)

ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "owner": ("finance.manage",),
    "accountant": ("finance.manage",),
}


def _stable_id(kind: str, code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ritmo-gym:{kind}:{code}")


def upgrade() -> None:
    op.create_table(
        "bank_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("bank_name", sa.String(length=80), nullable=False),
        sa.Column("account_last4", sa.String(length=4), nullable=False),
        sa.Column(
            "currency", sa.String(length=3), server_default=sa.text("'MXN'"), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name="ck_bank_accounts_status"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_bank_accounts_name_lower",
        "bank_accounts",
        [sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "bank_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency", sa.String(length=3), server_default=sa.text("'MXN'"), nullable=False
        ),
        sa.Column(
            "reference", sa.String(length=120), server_default=sa.text("''"), nullable=False
        ),
        sa.Column("description", sa.String(length=240), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("matched_source", sa.String(length=24), nullable=True),
        sa.Column("matched_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("matched_label", sa.String(length=240), nullable=True),
        sa.Column("difference_cents", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("import_hash", sa.String(length=64), nullable=False),
        sa.Column("imported_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reconciled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'reconciled', 'difference', 'reviewing')",
            name="ck_bank_movements_status",
        ),
        sa.CheckConstraint("amount_cents <> 0", name="ck_bank_movements_amount_nonzero"),
        sa.CheckConstraint(
            "(matched_source IS NULL AND matched_id IS NULL) OR "
            "(matched_source IS NOT NULL AND matched_id IS NOT NULL)",
            name="ck_bank_movements_match_pair",
        ),
        sa.CheckConstraint(
            "status <> 'reconciled' OR matched_id IS NOT NULL",
            name="ck_bank_movements_reconciled_match",
        ),
        sa.CheckConstraint(
            "matched_id IS NOT NULL OR difference_cents IS NULL",
            name="ck_bank_movements_unmatched_difference",
        ),
        sa.CheckConstraint(
            "difference_cents IS NULL OR (difference_cents <> 0 AND status = 'difference')",
            name="ck_bank_movements_difference_value",
        ),
        sa.ForeignKeyConstraint(
            ["bank_account_id"], ["bank_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["imported_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reconciled_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "bank_account_id", "import_hash", name="uq_bank_movements_import_hash"
        ),
    )
    op.create_index(
        "ix_bank_movements_account_date",
        "bank_movements",
        ["bank_account_id", "occurred_on"],
    )
    op.create_index("ix_bank_movements_status", "bank_movements", ["status"])
    op.create_index("ix_bank_movements_date", "bank_movements", ["occurred_on"])
    op.create_index(
        "uq_bank_movements_match",
        "bank_movements",
        ["matched_source", "matched_id"],
        unique=True,
        postgresql_where=sa.text("matched_id IS NOT NULL"),
        sqlite_where=sa.text("matched_id IS NOT NULL"),
    )

    op.create_table(
        "bank_movement_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("movement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("detail", sa.String(length=400), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('imported', 'matched', 'unmatched', 'flagged', 'reopened')",
            name="ck_bank_movement_events_type",
        ),
        sa.ForeignKeyConstraint(
            ["movement_id"], ["bank_movements.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_bank_movement_events_movement_time",
        "bank_movement_events",
        ["movement_id", "occurred_at"],
    )

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
    has_movements = op.get_bind().execute(
        sa.text("SELECT 1 FROM bank_movements LIMIT 1")
    ).first()
    if has_movements is not None:
        raise RuntimeError(
            "No se puede revertir la migración mientras existan movimientos bancarios."
        )
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
    op.drop_index(
        "ix_bank_movement_events_movement_time", table_name="bank_movement_events"
    )
    op.drop_table("bank_movement_events")
    op.drop_index("uq_bank_movements_match", table_name="bank_movements")
    op.drop_index("ix_bank_movements_date", table_name="bank_movements")
    op.drop_index("ix_bank_movements_status", table_name="bank_movements")
    op.drop_index("ix_bank_movements_account_date", table_name="bank_movements")
    op.drop_table("bank_movements")
    op.drop_index("uq_bank_accounts_name_lower", table_name="bank_accounts")
    op.drop_table("bank_accounts")
