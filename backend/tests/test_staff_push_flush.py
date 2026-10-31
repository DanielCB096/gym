"""The cron entry that drains the staff Web Push queue.

``flush_staff_push.py`` sends the deliveries a crashed process left ``pending``
and never retries ``failed`` rows. These tests cover the flags, the missing
database URL, an unreachable database and the simulated pass in preview mode.
"""

import base64
import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlmodel import SQLModel, Session, create_engine, select

from app.modules import identity, memberships, notifications  # noqa: F401
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.notifications.models import StaffPushDelivery
from app.modules.notifications.service import create_staff_notification
from app.modules.notifications.webpush import register_staff_push_subscription

FLUSH = Path(__file__).resolve().parents[1] / "flush_staff_push.py"

spec = importlib.util.spec_from_file_location("flush_staff_push", FLUSH)
flush_staff_push = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(flush_staff_push)


@pytest.fixture(autouse=True)
def _restore_preview_env() -> Iterator[None]:
    before = os.environ.get("PREVIEW_MODE")
    yield
    if before is None:
        os.environ.pop("PREVIEW_MODE", None)
    else:
        os.environ["PREVIEW_MODE"] = before


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _keys() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    p256dh = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return _base64url(p256dh), _base64url(os.urandom(16))


def _seed_pending(tmp_path: Path) -> None:
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
            p256dh, auth = _keys()
            register_staff_push_subscription(
                session,
                user.id,
                endpoint="https://push.example.com/send/abc123ABCdef",
                p256dh=p256dh,
                auth=auth,
            )
            create_staff_notification(
                session,
                user_id=user.id,
                kind="workout_pending_review",
                title="Rutina por revisar",
                body="La rutina de Ana espera tu revisión.",
            )
            session.commit()
    finally:
        engine.dispose()


def test_preview_creates_the_database_and_reports_an_empty_queue(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    code = flush_staff_push.main(["--preview"])

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

    code = flush_staff_push.main(["--preview"])

    printed = capsys.readouterr().out
    assert code == 0
    assert "1 intentos" in printed
    assert "simulados 1" in printed
    engine = create_engine(f"sqlite:///{(tmp_path / 'gym_preview.db').as_posix()}")
    try:
        with Session(engine) as session:
            delivery = session.exec(select(StaffPushDelivery)).one()
            assert delivery.status == "simulated"
    finally:
        engine.dispose()


def test_preview_and_database_url_cannot_be_combined(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        flush_staff_push.main(["--preview", "--database-url", "sqlite:///otra.db"])

    assert error.value.code == 2
    assert "no ambos" in capsys.readouterr().err


@pytest.mark.parametrize("limit", [0, 101])
def test_limit_out_of_range_is_rejected(
    limit: int, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        flush_staff_push.main(["--limit", str(limit)])

    assert error.value.code == 2
    assert "--limit" in capsys.readouterr().err


def test_missing_database_url_exits_with_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = flush_staff_push.main([])

    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_unreachable_database_exits_with_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PREVIEW_MODE", raising=False)

    code = flush_staff_push.main(
        ["--database-url", f"sqlite:///{(tmp_path / 'missing' / 'gym.db').as_posix()}"]
    )

    assert code == 1
    assert "Error al enviar la cola del push del personal" in capsys.readouterr().err
