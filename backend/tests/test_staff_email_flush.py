"""The cron entry that drains the staff email queue.

``flush_staff_email.py`` sends the deliveries a crashed process left ``pending``
and never retries ``failed`` rows. These tests cover the flags, the missing
database URL, the club switch, an unreachable database and the simulated pass
in preview mode.
"""

import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from app.modules import identity, memberships, notifications  # noqa: F401
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications.models import StaffNotificationDelivery
from app.modules.notifications.service import create_staff_notification
from app.modules.staffing.service import get_staffing_settings

FLUSH = Path(__file__).resolve().parents[1] / "flush_staff_email.py"

spec = importlib.util.spec_from_file_location("flush_staff_email", FLUSH)
flush_staff_email = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(flush_staff_email)


@pytest.fixture(autouse=True)
def _restore_preview_env() -> Iterator[None]:
    before = os.environ.get("PREVIEW_MODE")
    yield
    if before is None:
        os.environ.pop("PREVIEW_MODE", None)
    else:
        os.environ["PREVIEW_MODE"] = before


def _seed_pending(tmp_path: Path, *, email_enabled: bool = True) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'gym_preview.db').as_posix()}")
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            ensure_default_access_control(session)
            user = register_user(
                session,
                email="trainer@example.com",
                password="trainer-strong-password",
                role_codes=("trainer",),
            )
            create_staff_notification(
                session,
                user_id=user.id,
                kind="workout_pending_review",
                title="Rutina por revisar",
                body="La rutina de Ana espera tu revisión.",
            )
            session.commit()
            if not email_enabled:
                settings = get_staffing_settings(session)
                settings.attendance_email_enabled = False
                session.add(settings)
                session.commit()
    finally:
        engine.dispose()


def test_preview_creates_the_database_and_reports_an_empty_queue(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    code = flush_staff_email.main(["--preview"])

    printed = capsys.readouterr().out
    assert code == 0
    assert "Base de vista previa" in printed
    assert "0 intentos" in printed
    assert "Entregas pendientes que quedan: 0." in printed
    assert (tmp_path / "gym_preview.db").is_file()


def test_preview_sends_the_pending_delivery_as_simulated(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _seed_pending(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = flush_staff_email.main(["--preview"])

    printed = capsys.readouterr().out
    assert code == 0
    assert "1 intentos" in printed
    assert "simulados 1" in printed
    engine = create_engine(f"sqlite:///{(tmp_path / 'gym_preview.db').as_posix()}")
    try:
        with Session(engine) as session:
            delivery = session.exec(select(StaffNotificationDelivery)).one()
            assert delivery.status == "simulated"
    finally:
        engine.dispose()


def test_club_switch_off_keeps_the_delivery_pending(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _seed_pending(tmp_path, email_enabled=False)
    monkeypatch.chdir(tmp_path)

    code = flush_staff_email.main(["--preview"])

    printed = capsys.readouterr().out
    assert code == 0
    assert "El correo del personal está apagado" in printed
    assert "Entregas pendientes que quedan: 1." in printed
    engine = create_engine(f"sqlite:///{(tmp_path / 'gym_preview.db').as_posix()}")
    try:
        with Session(engine) as session:
            delivery = session.exec(select(StaffNotificationDelivery)).one()
            assert delivery.status == "pending"
    finally:
        engine.dispose()


def test_preview_and_database_url_cannot_be_combined(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        flush_staff_email.main(["--preview", "--database-url", "sqlite:///otra.db"])

    assert error.value.code == 2
    assert "no ambos" in capsys.readouterr().err


@pytest.mark.parametrize("limit", [0, 101])
def test_limit_out_of_range_is_rejected(
    limit: int, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        flush_staff_email.main(["--limit", str(limit)])

    assert error.value.code == 2
    assert "--limit" in capsys.readouterr().err


def test_missing_database_url_exits_with_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = flush_staff_email.main([])

    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_unreachable_database_exits_with_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PREVIEW_MODE", raising=False)

    code = flush_staff_email.main(
        ["--database-url", f"sqlite:///{(tmp_path / 'missing' / 'gym.db').as_posix()}"]
    )

    assert code == 1
    assert "Error al enviar la cola de correo del personal" in capsys.readouterr().err
