"""The six places that know the member notice kinds have to say the same thing.

Adding a kind is a six-file change: the tuple and the ``CHECK`` in the model, the
category that silences it, the ``CHECK_UPGRADES`` chain that lifts a preview
database to today's list, the panel label, the app label and the screen the app
opens when the notice is tapped. Nothing in the code links those files, so a
missed one stays invisible until a member reads a raw ``invoice_foo`` in the
inbox, a switch silences nothing or a notice lands in the tray instead of its
screen.

The app is TypeScript, so the two last maps are read as text instead of
executed: the assertions parse what they need and nothing else. The routing
rules are collected in source order, exactly like ``notificationDestination``
evaluates them, and each category names the screen it has to open here, so a
notice cannot quietly start landing in the tray after a refactor.
"""

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint

from app.modules.notifications.models import (
    MEMBER_EMAIL_NOTIFICATION_CATEGORIES,
    MEMBER_NOTIFICATION_CATEGORIES,
    NOTIFICATION_CATEGORY_BY_KIND,
    NOTIFICATION_KINDS,
    STAFF_NOTIFICATION_KINDS,
    MemberNotification,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
NOTIFICATIONS_SERVICE = BACKEND_DIR / "src" / "app" / "modules" / "notifications" / "service.py"
WEB_PANEL = REPO_DIR / "web" / "src" / "app" / "page.tsx"
MOBILE_FORMAT = REPO_DIR / "mobile" / "src" / "format.ts"
MOBILE_ROUTING = REPO_DIR / "mobile" / "src" / "notificationRouting.ts"

# The app has no Equipment or Membership screen of its own: a notice about a
# machine opens the section that shows the routine that uses it, and an
# expiring membership opens the home where the plan card lives.
EXPECTED_DESTINATION_BY_CATEGORY = {
    "membership": "home",
    "classes": "classes",
    "training": "routines",
    "billing": "invoices",
    "equipment": "routines",
    "physio": "physio",
}

# Only the sets notificationRouting.ts expands by name are worth reading; the
# app may declare other sets for its own use.
ROUTING_SETS = ("CLASS_KINDS", "PHYSIO_KINDS", "ROUTINE_KINDS")


def _read(path: Path) -> str:
    assert path.exists(), f"falta el archivo {path}"
    return path.read_text(encoding="utf-8")


def _kinds_from_check(clause: str) -> set[str]:
    match = re.search(r"kind IN \((.*?)\)", clause, re.S)
    assert match, f"no se encontró la lista de tipos en {clause!r}"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def _model_check_kinds() -> set[str]:
    for constraint in MemberNotification.__table__.constraints:
        if (
            isinstance(constraint, CheckConstraint)
            and constraint.name == "ck_member_notifications_kind"
        ):
            return _kinds_from_check(str(constraint.sqltext))
    pytest.fail("member_notifications perdió su CHECK ck_member_notifications_kind")


def _preview_patch():
    path = BACKEND_DIR / "preview_patch.py"
    spec = importlib.util.spec_from_file_location("preview_patch", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record_keys(source: str, declaration: str) -> set[str]:
    """The keys of a ``Record<string, string>`` literal, read as text.

    Both label maps list one quoted line per kind, so the keys are the lines
    that start an entry.
    """
    match = re.search(
        rf"const {re.escape(declaration)}: Record<string, string> = \{{(.*?)^\}};",
        source,
        re.S | re.M,
    )
    assert match, f"no se encontró el mapa {declaration}"
    return set(re.findall(r"^\s*([a-z_]+):", match.group(1), re.M))


def _set_members(source: str, name: str) -> set[str]:
    match = re.search(rf"const {re.escape(name)} = new Set\(\[(.*?)\]\);", source, re.S)
    assert match, f"no se encontró el conjunto {name}"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def _destination_rules(source: str) -> list[dict[str, object]]:
    """The ladder of ``notificationDestination``, in the order the app tests it.

    Each rule matches a kind by exact name, by prefix or by set membership and
    returns one screen. The trailing ``return "notifications"`` is the fallback
    the app keeps for kinds it does not know, so it is deliberately not a rule:
    a kind no rule claims is the bug this file is here to catch.
    """
    start = source.index("export function notificationDestination")
    body = source[start : source.index("\n}", start)]
    rules: list[tuple[int, dict[str, object]]] = []
    patterns = (
        (r'if \(kind === "([a-z_]+)"\) \{\s*return "([a-z]+)";', "equals"),
        (r'if \(kind\.startsWith\("([a-z_]+)"\)\) \{\s*return "([a-z]+)";', "prefix"),
    )
    for pattern, key in patterns:
        for match in re.finditer(pattern, body, re.S):
            rules.append(
                (
                    match.start(),
                    {key: match.group(1), "destination": match.group(2)},
                )
            )
    for name in ROUTING_SETS:
        for match in re.finditer(
            rf'if \({re.escape(name)}\.has\(kind\)\) \{{\s*return "([a-z]+)";',
            body,
            re.S,
        ):
            rules.append(
                (
                    match.start(),
                    {"members": _set_members(source, name), "destination": match.group(1)},
                )
            )
    assert rules, "notificationRouting.ts cambió de forma y este archivo ya no la lee"
    return [rule for _, rule in sorted(rules)]


def _destination_of(kind: str, rules: list[dict[str, object]]) -> str | None:
    for rule in rules:
        if kind in rule.get("equals", ""):
            return str(rule["destination"])
        prefix = rule.get("prefix", "")
        if prefix and kind.startswith(str(prefix)):
            return str(rule["destination"])
        if kind in rule.get("members", ()):
            return str(rule["destination"])
    return None


def test_notification_kinds_are_unique():
    assert len(NOTIFICATION_KINDS) == len(set(NOTIFICATION_KINDS)), (
        "NOTIFICATION_KINDS tiene tipos duplicados"
    )


def test_model_check_accepts_exactly_the_declared_kinds():
    assert _model_check_kinds() == set(NOTIFICATION_KINDS), (
        "el CHECK ck_member_notifications_kind y NOTIFICATION_KINDS dicen cosas distintas: "
        "un tipo aceptado por la base pero no declarado, o declarado y rechazado al insertar"
    )


def test_preview_patch_lifts_the_check_to_the_current_kinds():
    chain = _preview_patch().CHECK_UPGRADES["member_notifications"]
    assert _kinds_from_check(chain[-1][1]) == set(NOTIFICATION_KINDS), (
        "la última sustitución de CHECK_UPGRADES deja la base de vista previa con otra "
        "lista de tipos; hay que añadir el tramo que falte"
    )


def test_category_map_is_exhaustive():
    assert set(NOTIFICATION_CATEGORY_BY_KIND) == set(NOTIFICATION_KINDS), (
        "NOTIFICATION_CATEGORY_BY_KIND y NOTIFICATION_KINDS tienen tipos distintos: "
        "ningún aviso nuevo puede quedarse sin interruptor que lo calle"
    )
    unknown = set(NOTIFICATION_CATEGORY_BY_KIND.values()) - set(MEMBER_NOTIFICATION_CATEGORIES)
    assert not unknown, f"categorías de aviso fuera de MEMBER_NOTIFICATION_CATEGORIES: {unknown}"
    for category in MEMBER_NOTIFICATION_CATEGORIES:
        assert category in NOTIFICATION_CATEGORY_BY_KIND.values(), (
            f"la categoría {category} no silencia ningún tipo"
        )


def test_email_categories_are_switches_the_app_can_offer():
    assert set(MEMBER_EMAIL_NOTIFICATION_CATEGORIES) <= set(MEMBER_NOTIFICATION_CATEGORIES), (
        "una categoría de correo no existe entre las categorías de aviso"
    )
    for category in MEMBER_EMAIL_NOTIFICATION_CATEGORIES:
        silenced = [
            kind
            for kind, kind_category in NOTIFICATION_CATEGORY_BY_KIND.items()
            if kind_category == category
        ]
        assert silenced, f"el correo de {category} no cubriría ningún aviso"


def test_panel_labels_cover_every_kind():
    labels = _record_keys(_read(WEB_PANEL), "MEMBER_NOTIFICATION_KIND_LABELS")
    assert labels == set(NOTIFICATION_KINDS), (
        f"las etiquetas del panel y los tipos declarados difieren: "
        f"faltan {sorted(set(NOTIFICATION_KINDS) - labels)}, "
        f"sobran {sorted(labels - set(NOTIFICATION_KINDS))}"
    )


def test_app_labels_cover_every_kind():
    labels = _record_keys(_read(MOBILE_FORMAT), "NOTIFICATION_KIND_LABELS")
    assert labels == set(NOTIFICATION_KINDS), (
        f"las etiquetas de la app y los tipos declarados difieren: "
        f"faltan {sorted(set(NOTIFICATION_KINDS) - labels)}, "
        f"sobran {sorted(labels - set(NOTIFICATION_KINDS))}"
    )


def test_app_routes_every_kind_to_the_screen_of_its_category():
    rules = _destination_rules(_read(MOBILE_ROUTING))
    for kind in NOTIFICATION_KINDS:
        destination = _destination_of(kind, rules)
        expected = EXPECTED_DESTINATION_BY_CATEGORY[NOTIFICATION_CATEGORY_BY_KIND[kind]]
        assert destination is not None, (
            f"el aviso {kind} no tiene pantalla: caería a la bandeja, "
            "el sitio donde la app sólo deja los tipos que aún no conoce"
        )
        assert destination == expected, (
            f"el aviso {kind} abre {destination} y su categoría {expected}"
        )


def test_app_routing_sets_do_not_overlap():
    members = {name: _set_members(_read(MOBILE_ROUTING), name) for name in ROUTING_SETS}
    for name, kinds in members.items():
        assert kinds <= set(NOTIFICATION_KINDS), (
            f"{name} menciona tipos que ya no existen: {sorted(kinds - set(NOTIFICATION_KINDS))}"
        )
    names = list(members)
    for index, name in enumerate(names):
        for other in names[index + 1 :]:
            assert not members[name] & members[other], (
                f"{name} y {other} reclaman {sorted(members[name] & members[other])}: "
                "un tipo en dos conjuntos se resuelve por orden y el mapa deja de ser explícito"
            )


def test_every_kind_is_emitted_and_no_emitter_invents_a_kind():
    source = _read(NOTIFICATIONS_SERVICE)
    emitted = set(re.findall(r'kind\s*=\s*"([a-z_]+)"', source))
    declared = set(NOTIFICATION_KINDS) | set(STAFF_NOTIFICATION_KINDS)
    assert emitted <= declared, (
        f"notifications/service.py emite tipos no declarados: {sorted(emitted - declared)}"
    )
    missing = sorted(set(NOTIFICATION_KINDS) - emitted)
    assert not missing, (
        f"ningún aviso de la app escribe estos tipos: {missing}; "
        "o se perdió el emisor o el tipo sobra del inventario"
    )
