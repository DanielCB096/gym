"""The preview seed and the RBAC migrations must describe the same access matrix.

``ensure_default_access_control`` writes the roles, permissions and grants a
preview or test database gets, while production gets the same matrix from the
migrations in ``alembic/versions``. They were maintained apart and already
diverged once, and the panel reads its catalog from the database: a permission
missing from the seed is simply not grantable in preview, and one missing from a
migration is missing for the real club.

This module reads the grant data out of every migration that writes
``role_permissions`` and compares it with the seed, so a new migration that
nobody declared, a dropped grant, a renamed code or an edited label fails here.
The migrations are PostgreSQL-only (``::uuid`` casts, ``DELETE ... USING``), so
the data is read from the modules instead of replaying their SQL.
"""

import importlib.util
from pathlib import Path
import re
from typing import Callable

import pytest

from app.modules.identity.service import (
    DEFAULT_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    DEFAULT_ROLES,
)

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# A migration writes a grant either with an INSERT or with a bulk insert of the
# ``role_permissions`` table; ``op.drop_table("role_permissions")`` has no comma
# after the name, so it does not match.
GRANT_WRITES = re.compile(r'INSERT INTO role_permissions|"role_permissions",')
PERMISSION_WRITES = re.compile(r'INSERT INTO permissions|"permissions",')
REVOKES = re.compile(r"DELETE FROM role_permissions")
INLINE_ROLE = re.compile(r"roles\.code = '([a-z_.]+)'")


def _module(stem: str):
    path = VERSIONS / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_role(mapping: dict[str, tuple[str, ...]]) -> set[tuple[str, str]]:
    return {(role, code) for role, codes in mapping.items() for code in codes}


def _single_permission(module, roles_attribute: str) -> set[tuple[str, str]]:
    return {(role, module.PERMISSION_CODE) for role in getattr(module, roles_attribute)}


def _triples(module) -> set[tuple[str, str]]:
    return {
        (role, code) for code, _description, roles in module.PERMISSIONS for role in roles
    }


def _inline_owner_grant(stem: str, module) -> set[tuple[str, str]]:
    """Pairs from a migration that names its role inside the INSERT statement."""

    source = (VERSIONS / f"{stem}.py").read_text(encoding="utf-8")
    statement = source[source.index("INSERT INTO role_permissions") :]
    return {(role, module.PERMISSION_CODE) for role in INLINE_ROLE.findall(statement)}


# One entry per migration that grants, with the shape its data happens to have.
GRANT_MIGRATIONS: dict[str, Callable[..., set[tuple[str, str]]]] = {
    "20261015_0002_identity_rbac": lambda _stem, module: _by_role(module.ROLE_PERMISSIONS),
    "20261016_0003_reception_attendance_grant": lambda _stem, module: set(module.GRANTS),
    "20261016_0006_sessions_manage_permission": _inline_owner_grant,
    "20261016_0007_attendance_self_permission": lambda _stem, module: _single_permission(
        module, "ROLE_CODES"
    ),
    "20261017_0008_pos_inventory": lambda _stem, module: _by_role(module.ROLE_PERMISSIONS),
    "20261017_0011_routines_permissions": lambda _stem, module: _by_role(module.ROLE_GRANTS),
    "20261017_0013_maintenance_permissions": lambda _stem, module: _by_role(module.ROLE_GRANTS),
    "20261019_0019_credit_limits": lambda _stem, module: _single_permission(
        module, "ROLE_GRANTS"
    ),
    "20261023_0024_billing_cfdi": lambda _stem, module: _triples(module),
    "20261025_0027_bank_reconciliation": lambda _stem, module: _by_role(module.ROLE_GRANTS),
    "20261029_0050_service_refund_permission": lambda _stem, module: _single_permission(
        module, "ROLE_GRANTS"
    ),
    "20261029_0056_physio_permissions": lambda _stem, module: _triples(module),
    "20261030_0058_physio_control": lambda _stem, module: _triples(module),
}

# Permission codes created by a migration, with the label it stores for them.
CREATED_PERMISSIONS: dict[str, Callable[..., dict[str, str]]] = {
    "20261015_0002_identity_rbac": lambda _stem, module: dict(module.PERMISSION_DESCRIPTIONS),
    "20261016_0006_sessions_manage_permission": lambda _stem, module: {
        module.PERMISSION_CODE: module.PERMISSION_DESCRIPTION
    },
    "20261016_0007_attendance_self_permission": lambda _stem, module: {
        module.PERMISSION_CODE: module.PERMISSION_DESCRIPTION
    },
    "20261017_0008_pos_inventory": lambda _stem, module: dict(module.PERMISSIONS),
    "20261017_0011_routines_permissions": lambda _stem, module: dict(module.PERMISSIONS),
    "20261017_0013_maintenance_permissions": lambda _stem, module: dict(module.PERMISSIONS),
    "20261019_0019_credit_limits": lambda _stem, module: {
        module.PERMISSION_CODE: module.PERMISSION_DESCRIPTION
    },
    "20261023_0024_billing_cfdi": lambda _stem, module: {
        code: description for code, description, _roles in module.PERMISSIONS
    },
    "20261025_0027_bank_reconciliation": lambda _stem, module: dict(module.PERMISSIONS),
    "20261029_0050_service_refund_permission": lambda _stem, module: {
        module.PERMISSION_CODE: module.PERMISSION_DESCRIPTION
    },
    "20261029_0056_physio_permissions": lambda _stem, module: {
        code: description for code, description, _roles in module.PERMISSIONS
    },
    "20261030_0058_physio_control": lambda _stem, module: {
        code: description for code, description, _roles in module.PERMISSIONS
    },
}


def _migration_grants() -> set[tuple[str, str]]:
    return {
        pair for stem, extract in GRANT_MIGRATIONS.items() for pair in extract(stem, _module(stem))
    }


def _seed_grants() -> set[tuple[str, str]]:
    return {(role, code) for role, codes in DEFAULT_ROLE_PERMISSIONS.items() for code in codes}


def _writing_files(pattern: re.Pattern[str]) -> set[str]:
    return {
        path.stem
        for path in VERSIONS.glob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    }


def test_every_migration_that_grants_a_permission_is_declared() -> None:
    """A new grant migration has to join the custody, not slip past it."""

    writing = _writing_files(GRANT_WRITES)
    undeclared = writing - set(GRANT_MIGRATIONS)
    stale = set(GRANT_MIGRATIONS) - writing
    assert not undeclared, (
        f"{sorted(undeclared)} escribe en role_permissions y no está en "
        "GRANT_MIGRATIONS: declárala con su forma de leer los datos."
    )
    assert not stale, f"{sorted(stale)} ya no escribe en role_permissions."


def test_every_migration_that_creates_a_permission_is_declared() -> None:
    """Same for a migration that only registers a code: its label has to be read."""

    writing = _writing_files(PERMISSION_WRITES)
    assert not writing - set(CREATED_PERMISSIONS), (
        f"{sorted(writing - set(CREATED_PERMISSIONS))} crea permisos y no está en "
        "CREATED_PERMISSIONS."
    )
    assert not set(CREATED_PERMISSIONS) - writing


def test_seed_grants_equal_the_migration_grants() -> None:
    seed, migrated = _seed_grants(), _migration_grants()
    assert seed, "el seed RBAC quedó vacío"
    assert migrated == seed, (
        f"solo en migraciones: {sorted(migrated - seed)}; "
        f"solo en el seed: {sorted(seed - migrated)}"
    )


def test_seed_permission_labels_equal_the_migration_labels() -> None:
    migrated: dict[str, str] = {}
    for stem, extract in CREATED_PERMISSIONS.items():
        migrated.update(extract(stem, _module(stem)))
    assert set(migrated) == set(DEFAULT_PERMISSIONS)
    assert migrated == dict(DEFAULT_PERMISSIONS)


def test_migrations_only_grant_to_seeded_roles() -> None:
    """The roles of the matrix exist in the seed catalog and in the migrations."""

    assert set(DEFAULT_ROLE_PERMISSIONS) == set(DEFAULT_ROLES)
    assert {role for role, _code in _migration_grants()} == set(DEFAULT_ROLES)


@pytest.mark.parametrize("stem", sorted(GRANT_MIGRATIONS))
def test_no_migration_revokes_a_grant_on_upgrade(stem: str) -> None:
    """The union above is only valid while upgrades just add grants.

    A migration that deletes from ``role_permissions`` in ``upgrade()`` would make
    the order matter, and the custody would have to replay it instead of unioning.
    """

    source = (VERSIONS / f"{stem}.py").read_text(encoding="utf-8")
    upgrade = source[: source.index("def downgrade")]
    assert not REVOKES.search(upgrade), f"{stem} revoca en upgrade(); la unión ya no basta"
