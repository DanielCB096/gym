"""The member email recovery script validates configuration and reports results."""

import importlib.util
import os
from pathlib import Path

import pytest

from app.modules.notifications.member_email import MemberEmailPass

FLUSH = Path(__file__).resolve().parents[1] / "flush_member_email.py"
spec = importlib.util.spec_from_file_location("flush_member_email", FLUSH)
flush_member_email = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(flush_member_email)


def test_preview_drains_in_simulation_and_reports_counts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    preview_db = tmp_path / "gym_preview.db"
    monkeypatch.setattr(
        flush_member_email,
        "PREVIEW_DATABASE_URL",
        f"sqlite:///{preview_db.as_posix()}",
    )
    result = MemberEmailPass(
        attempted=2,
        sent=0,
        simulated=1,
        failed=1,
        cancelled=0,
        remaining=1,
    )
    calls: list[tuple[object, int]] = []

    def fake_send(engine, *, limit: int):
        assert os.getenv("PREVIEW_MODE") == "1"
        calls.append((engine, limit))
        return result

    monkeypatch.setattr(
        flush_member_email.member_email,
        "send_pending_member_notification_emails_from_engine",
        fake_send,
    )

    code = flush_member_email.main(["--preview", "--limit", "3"])

    output = capsys.readouterr().out
    assert code == 0
    assert preview_db.exists()
    assert calls[0][1] == 3
    assert "simulados 1" in output
    assert "fallidos 1" in output
    assert "Entregas pendientes o con reintento programado: 1" in output
    assert os.getenv("PREVIEW_MODE") is None


def test_missing_database_url_returns_configuration_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = flush_member_email.main([])

    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err
