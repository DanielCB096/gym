"""Install the cron entries that keep the operations data fresh.

The application has no scheduler: the maintenance scripts run from the host's
cron (ADR-058, ADR-062, ADR-071, ADR-073, ADR-074, ADR-075, ADR-076). This
script renders the eight entries as one block delimited by markers, so
reinstalling after moving the app,
changing the database password or adjusting the schedule replaces the old block
instead of duplicating lines, and unrelated crontab entries are left untouched.

    DATABASE_URL=postgresql+psycopg://... .venv/bin/python ops_cron.py --print
    DATABASE_URL=postgresql+psycopg://... .venv/bin/python ops_cron.py --install
    python ops_cron.py --uninstall

``--print`` is the default and never touches the crontab; ``--install`` creates
the log directory and writes the block with ``crontab -``. The database URL is
stored in the user's crontab (readable only by that user); never paste the
output of ``--print`` with a real URL into a ticket or a chat.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shlex
import subprocess
import sys

BEGIN_MARKER = "# BEGIN gimnasio-ops"
END_MARKER = "# END gimnasio-ops"

DEFAULT_DAILY_AT = "03:15"
DEFAULT_PHYSIO_CLOSE_AT = "00:30"
DEFAULT_RECEIPTS_EVERY = 30
DEFAULT_STAFF_PUSH_EVERY = 15
DEFAULT_NOTICES_EVERY = 60
DEFAULT_PUSH_LIMIT = 200
MAX_PUSH_LIMIT = 1000
MIN_RECEIPTS_EVERY = 5
MIN_STAFF_PUSH_EVERY = 5
MIN_NOTICES_EVERY = 5
MAX_SCHEDULE_EVERY = 60
# The daily purges run one after the other, spaced by this many minutes.
PURGE_STAGGER_MINUTES = 30

_DAILY_AT = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_SCRIPTS = (
    "purge_access_data.py",
    "purge_email_receipts.py",
    "purge_push_data.py",
    "purge_inbox_data.py",
    "sync_push_receipts.py",
    "flush_staff_push.py",
    "emit_deferred_notices.py",
    "close_physio_day.py",
)


class OpsCronError(Exception):
    """The crontab could not be read or written, or a path is wrong."""


@dataclass(frozen=True)
class OpsCronConfig:
    app_dir: Path
    python: Path
    database_url: str
    log_dir: Path
    daily_at: str = DEFAULT_DAILY_AT
    physio_close_at: str = DEFAULT_PHYSIO_CLOSE_AT
    receipts_every: int = DEFAULT_RECEIPTS_EVERY
    staff_push_every: int = DEFAULT_STAFF_PUSH_EVERY
    notices_every: int = DEFAULT_NOTICES_EVERY
    push_limit: int = DEFAULT_PUSH_LIMIT


def parse_daily_at(value: str) -> tuple[int, int]:
    match = _DAILY_AT.match(value.strip())
    if match is None:
        raise ValueError("--daily-at debe tener la forma HH:MM (00:00 a 23:59).")
    return int(match.group(1)), int(match.group(2))


def _every_schedule(minutes: int, flag: str, minimum: int) -> str:
    if minimum <= minutes <= 59:
        return f"*/{minutes} * * * *"
    if minutes == MAX_SCHEDULE_EVERY:
        return "0 * * * *"
    raise ValueError(f"{flag} debe estar entre {minimum} y 59, o 60.")


def receipts_schedule(minutes: int) -> str:
    """Cron minute field for the receipts pass."""

    return _every_schedule(minutes, "--receipts-every", MIN_RECEIPTS_EVERY)


def staff_push_schedule(minutes: int) -> str:
    """Cron minute field for the staff push drain."""

    return _every_schedule(minutes, "--staff-push-every", MIN_STAFF_PUSH_EVERY)


def notices_schedule(minutes: int) -> str:
    """Cron minute field for the deferred-notices pass."""

    return _every_schedule(minutes, "--notices-every", MIN_NOTICES_EVERY)


def add_minutes(hour: int, minute: int, offset: int) -> tuple[int, int]:
    total = (hour * 60 + minute + offset) % (24 * 60)
    return total // 60, total % 60


def build_block(config: OpsCronConfig) -> str:
    """Render the marked crontab block for the eight maintenance jobs."""

    database_url = config.database_url.strip()
    if not database_url:
        raise ValueError("DATABASE_URL está vacía.")
    if "\n" in database_url or "\r" in database_url:
        raise ValueError("DATABASE_URL no puede contener saltos de línea.")
    if config.push_limit < 1 or config.push_limit > MAX_PUSH_LIMIT:
        raise ValueError(f"--limit debe estar entre 1 y {MAX_PUSH_LIMIT}.")

    hour, minute = parse_daily_at(config.daily_at)
    second_hour, second_minute = add_minutes(hour, minute, PURGE_STAGGER_MINUTES)
    third_hour, third_minute = add_minutes(
        hour, minute, PURGE_STAGGER_MINUTES * 2
    )
    fourth_hour, fourth_minute = add_minutes(
        hour, minute, PURGE_STAGGER_MINUTES * 3
    )
    close_hour, close_minute = parse_daily_at(config.physio_close_at)
    receipts = receipts_schedule(config.receipts_every)
    staff_push = staff_push_schedule(config.staff_push_every)
    notices = notices_schedule(config.notices_every)

    def command(script: str, extra: str, log_name: str) -> str:
        return (
            f"cd {shlex.quote(str(config.app_dir))} && "
            f"DATABASE_URL={shlex.quote(database_url)} "
            f"{shlex.quote(str(config.python))} {script}{extra} "
            f">> {shlex.quote(str(config.log_dir / log_name))} 2>&1"
        )

    lines = [
        BEGIN_MARKER,
        (
            "# Generado por backend/ops_cron.py: acuses cada "
            f"{config.receipts_every} min, push del personal cada "
            f"{config.staff_push_every} min, avisos diferidos con su push cada "
            f"{config.notices_every} min, cierre de fisioterapia a las "
            f"{close_hour:02d}:{close_minute:02d} y purgas diarias a las "
            f"{hour:02d}:{minute:02d}, {second_hour:02d}:{second_minute:02d}, "
            f"{third_hour:02d}:{third_minute:02d} y "
            f"{fourth_hour:02d}:{fourth_minute:02d}."
        ),
        (
            f"{close_minute} {close_hour} * * * "
            f"{command('close_physio_day.py', '', 'physio-close.log')}"
        ),
        f"{minute} {hour} * * * {command('purge_access_data.py', '', 'purge-access.log')}",
        (
            f"{second_minute} {second_hour} * * * "
            f"{command('purge_email_receipts.py', '', 'purge-email.log')}"
        ),
        (
            f"{third_minute} {third_hour} * * * "
            f"{command('purge_push_data.py', '', 'purge-push.log')}"
        ),
        (
            f"{fourth_minute} {fourth_hour} * * * "
            f"{command('purge_inbox_data.py', '', 'purge-inbox.log')}"
        ),
        (
            f"{receipts} "
            f"{command('sync_push_receipts.py', f' --limit {config.push_limit}', 'push-receipts.log')}"
        ),
        f"{staff_push} {command('flush_staff_push.py', '', 'staff-push.log')}",
        (
            f"{notices} "
            f"{command('emit_deferred_notices.py', '', 'deferred-notices.log')}"
        ),
        END_MARKER,
    ]
    return "\n".join(lines) + "\n"


def replace_block(current: str, block: str) -> str:
    """Replace the marked block in ``current``, preserving everything else.

    A missing end marker discards the rest of the file: a half-written block
    cannot be told apart from user lines, and leaving it would duplicate jobs.
    """

    kept: list[str] = []
    skipping = False
    for line in current.splitlines():
        stripped = line.strip()
        if stripped == BEGIN_MARKER:
            skipping = True
            continue
        if skipping:
            if stripped == END_MARKER:
                skipping = False
            continue
        kept.append(line)
    while kept and kept[-1].strip() == "":
        kept.pop()
    if kept:
        kept.append("")
    kept.extend(block.splitlines())
    return "\n".join(kept) + "\n"


def remove_block(current: str) -> str:
    """Remove the marked block, returning what is left."""

    kept: list[str] = []
    skipping = False
    for line in current.splitlines():
        stripped = line.strip()
        if stripped == BEGIN_MARKER:
            skipping = True
            continue
        if skipping:
            if stripped == END_MARKER:
                skipping = False
            continue
        kept.append(line)
    while kept and kept[-1].strip() == "":
        kept.pop()
    return "\n".join(kept) + "\n" if kept else ""


def _run_crontab(arguments: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["crontab", *arguments],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise OpsCronError(
            "No se encontró el comando crontab; instala cron o usa --print para "
            "copiar el bloque en el programador del servidor."
        ) from error


def read_crontab() -> str:
    result = _run_crontab(["-l"])
    if result.returncode == 0:
        return result.stdout
    message = (result.stderr or "").lower()
    if result.returncode == 1 and ("no crontab" in message or "no hay crontab" in message):
        return ""
    raise OpsCronError(f"No se pudo leer el crontab: {result.stderr.strip()}")


def write_crontab(text: str) -> None:
    result = _run_crontab(["-"], stdin=text)
    if result.returncode != 0:
        raise OpsCronError(f"No se pudo escribir el crontab: {result.stderr.strip()}")


def _config_from_args(args: argparse.Namespace) -> OpsCronConfig:
    database_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise OpsCronError(
            "Configura DATABASE_URL o pasa --database-url para el cron de operación."
        )
    app_dir = Path(args.app_dir).resolve() if args.app_dir else Path(__file__).resolve().parent
    return OpsCronConfig(
        app_dir=app_dir,
        python=Path(args.python).resolve() if args.python else Path(sys.executable),
        database_url=database_url,
        log_dir=Path(args.log_dir) if args.log_dir else app_dir / "logs",
        daily_at=args.daily_at,
        physio_close_at=args.physio_close_at,
        receipts_every=args.receipts_every,
        staff_push_every=args.staff_push_every,
        notices_every=args.notices_every,
        push_limit=args.limit,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera o instala el bloque de cron de las tareas de operación: "
            "cierre del día de fisioterapia, purga de accesos, purga de acuses "
            "de correo, purga de acuses y entregas del push, purga de la "
            "bandeja y de las entregas del personal, consulta de acuses del "
            "push, envío de la cola del push web del personal y emisión de los "
            "avisos diferidos."
        )
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--print",
        dest="print_block",
        action="store_true",
        help="imprime el bloque sin tocar el crontab (opción por defecto)",
    )
    action.add_argument(
        "--install",
        action="store_true",
        help="reemplaza el bloque en el crontab del usuario actual",
    )
    action.add_argument(
        "--uninstall",
        action="store_true",
        help="quita el bloque del crontab sin tocar otras entradas",
    )
    parser.add_argument(
        "--app-dir",
        default=None,
        help="carpeta del backend con los scripts (por defecto, la de este archivo)",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="intérprete que correrá los scripts (por defecto, el actual)",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL de SQLAlchemy; por defecto toma DATABASE_URL del entorno",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="carpeta de bitácoras (por defecto, <app-dir>/logs)",
    )
    parser.add_argument(
        "--daily-at",
        default=DEFAULT_DAILY_AT,
        help=f"hora local de la primera purga (por defecto {DEFAULT_DAILY_AT})",
    )
    parser.add_argument(
        "--physio-close-at",
        default=DEFAULT_PHYSIO_CLOSE_AT,
        help=(
            "hora local del cierre del día de fisioterapia "
            f"(por defecto {DEFAULT_PHYSIO_CLOSE_AT})"
        ),
    )
    parser.add_argument(
        "--receipts-every",
        type=int,
        default=DEFAULT_RECEIPTS_EVERY,
        help=(
            "minutos entre consultas de acuses del push "
            f"({MIN_RECEIPTS_EVERY} a 59, o 60; por defecto "
            f"{DEFAULT_RECEIPTS_EVERY})"
        ),
    )
    parser.add_argument(
        "--staff-push-every",
        type=int,
        default=DEFAULT_STAFF_PUSH_EVERY,
        help=(
            "minutos entre envíos de la cola del push web del personal "
            f"({MIN_STAFF_PUSH_EVERY} a 59, o 60; por defecto "
            f"{DEFAULT_STAFF_PUSH_EVERY})"
        ),
    )
    parser.add_argument(
        "--notices-every",
        type=int,
        default=DEFAULT_NOTICES_EVERY,
        help=(
            "minutos entre pasadas de avisos diferidos "
            f"({MIN_NOTICES_EVERY} a 59, o 60; por defecto "
            f"{DEFAULT_NOTICES_EVERY})"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_PUSH_LIMIT,
        help=f"tickets por corrida de acuses (1 a {MAX_PUSH_LIMIT}; por defecto {DEFAULT_PUSH_LIMIT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.uninstall:
            write_crontab(remove_block(read_crontab()))
            print("Bloque de operación retirado del crontab.")
            return 0

        config = _config_from_args(args)
        block = build_block(config)
    except (OpsCronError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    if not args.install:
        sys.stdout.write(block)
        return 0

    missing = [name for name in _SCRIPTS if not (config.app_dir / name).is_file()]
    if missing:
        print(
            f"Error: faltan scripts en {config.app_dir}: {', '.join(missing)}.",
            file=sys.stderr,
        )
        return 2
    try:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        write_crontab(replace_block(read_crontab(), block))
    except (OpsCronError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(
        f"Bloque instalado en el crontab: acuses cada {config.receipts_every} min, "
        f"push del personal cada {config.staff_push_every} min, avisos diferidos "
        f"cada {config.notices_every} min, cierre de fisioterapia a las "
        f"{config.physio_close_at} y cuatro purgas diarias desde las "
        f"{config.daily_at}. Revisa con: crontab -l"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
