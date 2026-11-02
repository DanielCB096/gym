"""Helpers shared by the module models.

The status and payment vocabularies live in one tuple per module and the database
CHECK constraints are rendered from that same tuple, so a value can never be
accepted by the service and refused by the schema (or the other way round) just
because somebody edited one of the two lists.
"""

from collections.abc import Sequence


def sql_in_list(values: Sequence[str]) -> str:
    """Render ``('a', 'b')`` for an ``IN (...)`` CHECK, in the order given.

    The values are in-code vocabularies, never user input, and the rendering is
    pinned by ``tests/test_catalog_single_source.py`` against the SQL the
    migrations already applied: changing a list changes the constraint text, and
    that needs a migration.
    """
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
