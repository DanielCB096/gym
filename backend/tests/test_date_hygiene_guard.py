"""Custodia de la higiene de fechas en las pruebas del backend.

El dictamen de 2026-11-01 (en `docs/07-pruebas/plan-de-pruebas.md`) encontró
cuatro pruebas que sembraban con una fecha congelada mientras la producción
comparaba contra el reloj real del proceso: pasaban el día que se escribieron y
se ponían rojas semanas después, sin que nadie tocara la regla.

La custodia congela el acuerdo al que se llegó después de ese barrido:

    si el servicio acepta `now=`, pásalo; si la ruta, el script o el CLI leen el
    reloj de la sala, siembra con el reloj de la sala.

La forma estática de romper ese acuerdo es mezclar los dos mundos dentro de una
misma función de prueba: una siembra con instante congelado y una lectura del
reloj real. Aquí esa mezcla está prohibida salvo que esté registrada en `ALLOWED`
con un motivo escrito, así que quien la introduzca tiene que decidir —y dejar
constancia de por qué la suya no caduca— en lugar de heredársela al calendario.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SELF_NAME = Path(__file__).name

# Lecturas del reloj de la sala: el instante que consulta el proceso, no el que la
# prueba le pasa al servicio.
CLOCK_READ = re.compile(r"datetime\.now\(|utc_now\(\)|date\.today\(|time\.time\(")

# Instantes congelados: una llamada `datetime(2026, …)`/`date(2026, …)` o una
# cadena ISO con año de cuatro dígitos.
FROZEN_CALL = re.compile(r"(?:datetime|date)\(\s*(?:19|20)\d\d\b")
FROZEN_ISO = re.compile(r"""\b(?:19|20)\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b""")

# Mezclas ya dictaminadas: la función lee el reloj real y siembra con un instante
# congelado, y se comprobó que la comparación no depende del calendario.
ALLOWED: dict[str, str] = {
    "test_routines_api.py::test_assignments_and_workouts": (
        "`PAST` viaja como payload válido —un pasado siempre es pasado— y `date.today()` "
        "se usa a propósito para probar que un entrenamiento no puede ser anterior a su "
        "asignación, que empieza en el centinela 2030-01-01. Las dos mitades están "
        "ancladas la una a la otra."
    ),
}


def _without_comments(source: str) -> list[str]:
    """Las líneas del archivo sin sus comentarios, para no leer fechas del relato."""
    lines = source.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return [line.split("#", 1)[0] for line in lines]
    commented = {token.start[0] for token in tokens if token.type == tokenize.COMMENT}
    return [
        (line.split("#", 1)[0] if number in commented else line)
        for number, line in enumerate(lines, start=1)
    ]


def _module_frozen_names(lines: list[str]) -> set[str]:
    """Nombres de módulo que congelan un instante.

    Cuenta el literal directo (`START = datetime(2026, …)`) y todo lo que se
    derive de él (`VOIDED_AT = START + timedelta(days=30)`): una constante hija
    sigue siendo la misma fecha congelada con otro nombre. Se itera hasta que no
    crece porque una hija puede estar escrita antes que su madre.
    """
    tree = ast.parse("\n".join(lines))
    assignments: list[tuple[set[str], set[str], bool]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        segment = "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno)])
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        sources = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        frozen_literal = bool(FROZEN_CALL.search(segment) or FROZEN_ISO.search(segment))
        assignments.append((targets, sources, frozen_literal))

    names = {name for targets, _, literal in assignments if literal for name in targets}
    while True:
        grown = set(names)
        for targets, sources, _ in assignments:
            if sources & names:
                grown |= targets
        if grown == names:
            return names
        names = grown


def _body(lines: list[str], function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return "\n".join(lines[function.lineno - 1 : (function.end_lineno or function.lineno)])


def _mixes(path: Path) -> list[tuple[str, int]]:
    lines = _without_comments(path.read_text(encoding="utf-8"))
    tree = ast.parse("\n".join(lines))
    frozen_names = _module_frozen_names(lines)
    found: list[tuple[str, int]] = []
    for function in (
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ):
        body = _body(lines, function)
        if not CLOCK_READ.search(body):
            continue
        references_frozen = bool(FROZEN_CALL.search(body)) or bool(FROZEN_ISO.search(body)) or any(
            re.search(rf"\b{re.escape(name)}\b", body) for name in frozen_names
        )
        if references_frozen:
            found.append((function.name, function.lineno))
    return found


def test_no_test_mixes_a_frozen_seed_with_a_real_clock_read() -> None:
    files = sorted(p for p in TESTS_DIR.glob("test_*.py") if p.name != SELF_NAME)
    assert files, f"No se leyó ningún archivo de prueba en {TESTS_DIR}"

    offences: list[str] = []
    mixes: set[str] = set()
    for path in files:
        for name, lineno in _mixes(path):
            key = f"{path.name}::{name}"
            mixes.add(key)
            if key not in ALLOWED:
                offences.append(f"{path.name}:{lineno} {name}")

    assert not offences, (
        "Estas pruebas siembran con un instante congelado y a la vez leen el reloj real: "
        "una de las dos caduca con el calendario. O pasas el mismo `now=` al servicio, o "
        "siembras con el reloj de la sala; si la mezcla es segura, regístrala en ALLOWED "
        "con su motivo.\n  " + "\n  ".join(offences)
    )

    stale = sorted(set(ALLOWED) - mixes)
    assert not stale, (
        "Estas entradas de ALLOWED ya no corresponden a ninguna mezcla: quítalas, porque "
        "una lista de permitidos que nadie revisa deja de proteger.\n  " + "\n  ".join(stale)
    )


def test_every_allowed_mix_explains_itself() -> None:
    thin = {key: reason for key, reason in ALLOWED.items() if len(reason.strip()) < 60}
    assert not thin, (
        "Cada mezcla permitida necesita un motivo que resista la lectura de otra "
        f"persona, no una etiqueta: {', '.join(sorted(thin))}"
    )
    malformed = [
        key
        for key in ALLOWED
        if key.count("::") != 1
        or not key.split("::")[0].endswith(".py")
        or not key.split("::")[1].startswith("test_")
    ]
    assert not malformed, (
        "Las entradas de ALLOWED se escriben 'archivo.py::funcion_de_prueba': "
        f"{', '.join(sorted(malformed))}"
    )
