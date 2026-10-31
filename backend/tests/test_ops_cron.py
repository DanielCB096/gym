"""The operations cron block installed by ``ops_cron.py``.

The block schedules the two daily purges and the Expo receipts pass, keeps
unrelated crontab lines untouched, and reinstalling replaces the old block
instead of adding a second copy.
"""

from dataclasses import replace
import importlib.util
from pathlib import Path
import shlex
import sys

import pytest

OPS_CRON = Path(__file__).resolve().parents[1] / "ops_cron.py"

spec = importlib.util.spec_from_file_location("ops_cron", OPS_CRON)
ops_cron = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ops_cron)

DATABASE_URL = "postgresql+psycopg://gym:p@ss#word@db:5432/gym"
BASE = ops_cron.OpsCronConfig(
    app_dir=Path("/srv/gimnasio/backend"),
    python=Path("/srv/gimnasio/backend/.venv/bin/python"),
    database_url=DATABASE_URL,
    log_dir=Path("/var/log/gimnasio"),
)


def _block(**overrides: object) -> str:
    return ops_cron.build_block(replace(BASE, **overrides))


def test_block_schedules_the_three_jobs_in_order() -> None:
    lines = _block().splitlines()
    assert lines[0] == ops_cron.BEGIN_MARKER
    assert lines[-1] == ops_cron.END_MARKER

    access = next(line for line in lines if "purge_access_data.py" in line)
    email = next(line for line in lines if "purge_email_receipts.py" in line)
    receipts = next(line for line in lines if "sync_push_receipts.py" in line)

    assert access.startswith("15 3 * * * ")
    assert email.startswith("45 3 * * * ")
    assert receipts.startswith("*/30 * * * * ")
    assert lines.index(access) < lines.index(email)
    assert "--limit 200" in receipts
    for line in (access, email, receipts):
        assert "cd " in line
        assert "DATABASE_URL=" in line
        assert ">> " in line
        assert line.endswith("2>&1")


def test_commands_quote_the_url_and_paths() -> None:
    block = _block()
    assert f"DATABASE_URL={shlex.quote(DATABASE_URL)}" in block
    assert "DATABASE_URL=postgresql" not in block
    assert shlex.quote("sync_push_receipts.py") in block or "sync_push_receipts.py" in block


def test_logs_are_named_per_job() -> None:
    block = _block()
    assert "purge-access.log" in block
    assert "purge-email.log" in block
    assert "push-receipts.log" in block


def test_daily_schedule_wraps_midnight() -> None:
    block = _block(daily_at="23:50")
    access = next(line for line in block.splitlines() if "purge_access_data.py" in line)
    email = next(line for line in block.splitlines() if "purge_email_receipts.py" in line)
    assert access.startswith("50 23 * * * ")
    assert email.startswith("20 0 * * * ")


def test_receipts_schedule_accepts_steps_and_hourly() -> None:
    assert ops_cron.receipts_schedule(15) == "*/15 * * * *"
    assert ops_cron.receipts_schedule(59) == "*/59 * * * *"
    assert ops_cron.receipts_schedule(60) == "0 * * * *"


@pytest.mark.parametrize(
    "overrides",
    [
        {"receipts_every": 4},
        {"receipts_every": 61},
        {"daily_at": "24:00"},
        {"daily_at": "3:5"},
        {"daily_at": "noche"},
        {"push_limit": 0},
        {"push_limit": 1001},
        {"database_url": "   "},
        {"database_url": "postgresql://gym\nrm -rf /"},
    ],
)
def test_invalid_configuration_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _block(**overrides)


def test_replace_block_is_idempotent_and_preserves_other_lines() -> None:
    block = _block()
    current = (
        "MAILTO=ops@example.test\n"
        "0 1 * * * /usr/local/bin/backup\n"
        f"{ops_cron.BEGIN_MARKER}\n"
        "viejo bloque\n"
        f"{ops_cron.END_MARKER}\n"
        "\n"
        "30 2 * * * /usr/local/bin/otra\n"
    )

    once = ops_cron.replace_block(current, block)
    twice = ops_cron.replace_block(once, block)

    assert once == twice
    assert "MAILTO=ops@example.test" in once
    assert "/usr/local/bin/backup" in once
    assert "/usr/local/bin/otra" in once
    assert "viejo bloque" not in once
    assert once.count(ops_cron.BEGIN_MARKER) == 1


def test_replace_block_without_end_marker_discards_the_rest() -> None:
    block = _block()
    current = f"0 1 * * * /usr/local/bin/backup\n{ops_cron.BEGIN_MARKER}\nmedia línea rota\n"
    result = ops_cron.replace_block(current, block)
    assert "/usr/local/bin/backup" in result
    assert "media línea rota" not in result
    assert result.count(ops_cron.BEGIN_MARKER) == 1


def test_remove_block_leaves_the_other_entries() -> None:
    current = (
        f"MAILTO=ops@example.test\n{_block()}\n0 1 * * * /usr/local/bin/backup\n"
    )
    result = ops_cron.remove_block(current)
    assert result == "MAILTO=ops@example.test\n\n0 1 * * * /usr/local/bin/backup\n"


def test_remove_block_empties_a_crontab_with_only_the_block() -> None:
    assert ops_cron.remove_block(_block()) == ""


def test_cli_print_does_not_touch_the_crontab(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setattr(
        ops_cron, "read_crontab", lambda: pytest.fail("no debe leer el crontab")
    )
    monkeypatch.setattr(
        ops_cron, "write_crontab", lambda text: pytest.fail("no debe escribir el crontab")
    )

    code = ops_cron.main(
        [
            "--print",
            "--app-dir",
            str(tmp_path),
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    printed = capsys.readouterr().out
    assert code == 0
    assert ops_cron.BEGIN_MARKER in printed
    assert "sync_push_receipts.py" in printed
    assert "purge_access_data.py" in printed


def test_cli_install_replaces_the_block_and_creates_the_log_dir(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for script in ops_cron._SCRIPTS:
        (tmp_path / script).write_text("", encoding="utf-8")
    written: list[str] = []
    monkeypatch.setattr(ops_cron, "read_crontab", lambda: "0 1 * * * /usr/local/bin/backup\n")
    monkeypatch.setattr(ops_cron, "write_crontab", written.append)

    code = ops_cron.main(
        [
            "--install",
            "--app-dir",
            str(tmp_path),
            "--database-url",
            DATABASE_URL,
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    assert code == 0
    assert (tmp_path / "logs").is_dir()
    assert len(written) == 1
    assert "/usr/local/bin/backup" in written[0]
    assert ops_cron.BEGIN_MARKER in written[0]
    assert written[0].count(ops_cron.BEGIN_MARKER) == 1
    assert "Bloque instalado" in capsys.readouterr().out


def test_cli_install_requires_every_script(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    (tmp_path / "purge_access_data.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        ops_cron, "write_crontab", lambda text: pytest.fail("no debe escribir")
    )

    code = ops_cron.main(
        [
            "--install",
            "--app-dir",
            str(tmp_path),
            "--database-url",
            DATABASE_URL,
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    assert code == 2
    assert "sync_push_receipts.py" in capsys.readouterr().err


def test_cli_uninstall_removes_only_the_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    written: list[str] = []
    current = f"0 1 * * * /usr/local/bin/backup\n{_block()}"
    monkeypatch.setattr(ops_cron, "read_crontab", lambda: current)
    monkeypatch.setattr(ops_cron, "write_crontab", written.append)

    code = ops_cron.main(["--uninstall"])

    assert code == 0
    assert written == ["0 1 * * * /usr/local/bin/backup\n"]


def test_cli_requires_the_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    code = ops_cron.main(["--print", "--app-dir", str(tmp_path)])
    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cli_reports_a_crontab_that_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for script in ops_cron._SCRIPTS:
        (tmp_path / script).write_text("", encoding="utf-8")

    def fail() -> str:
        raise ops_cron.OpsCronError("sin crontab")

    monkeypatch.setattr(ops_cron, "read_crontab", fail)

    code = ops_cron.main(
        [
            "--install",
            "--app-dir",
            str(tmp_path),
            "--database-url",
            DATABASE_URL,
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    assert code == 1
    assert "sin crontab" in capsys.readouterr().err


def test_cli_install_reports_missing_crontab_without_claiming_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    for script in ops_cron._SCRIPTS:
        (tmp_path / script).write_text("", encoding="utf-8")

    def missing_crontab(*_args: object, **_kwargs: object):
        raise FileNotFoundError("crontab")

    monkeypatch.setattr(ops_cron.subprocess, "run", missing_crontab)

    code = ops_cron.main(
        [
            "--install",
            "--app-dir",
            str(tmp_path),
            "--database-url",
            DATABASE_URL,
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "No se encontró el comando crontab" in captured.err
    assert "instala cron" in captured.err
    assert "Bloque instalado" not in captured.out


def test_cli_install_reports_crontab_write_failure_without_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    for script in ops_cron._SCRIPTS:
        (tmp_path / script).write_text("", encoding="utf-8")

    def fail_write(arguments: list[str], *, stdin: str | None = None):
        if arguments == ["-l"]:
            return ops_cron.subprocess.CompletedProcess(
                ["crontab", "-l"], 0, "MAILTO=ops@example.test\n", ""
            )
        assert arguments == ["-"]
        assert stdin is not None
        return ops_cron.subprocess.CompletedProcess(
            ["crontab", "-"], 1, "", "permiso denegado"
        )

    monkeypatch.setattr(ops_cron, "_run_crontab", fail_write)

    code = ops_cron.main(
        [
            "--install",
            "--app-dir",
            str(tmp_path),
            "--database-url",
            DATABASE_URL,
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "No se pudo escribir el crontab: permiso denegado" in captured.err
    assert "Bloque instalado" not in captured.out
