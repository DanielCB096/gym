"""The cron entry that closes the physiotherapy day.

``close_physio_day.py`` applies the same rule as the panel's «Cerrar día»: a
pending appointment of a finished day becomes ``no_show`` and no money or
credit moves. These tests cover the day filter, the status filter, the
not-ended guard, the default of yesterday, preview mode and the exit codes.
"""

import importlib.util
import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules import physio  # noqa: F401
from app.modules.identity.models import Employee
from app.modules.memberships.models import Member
from app.modules.physio.models import PhysioAppointment, PhysioService
from app.timezone import club_date, club_timezone, local_midnight

CLOSE = Path(__file__).resolve().parents[1] / "close_physio_day.py"

spec = importlib.util.spec_from_file_location("close_physio_day", CLOSE)
close_physio_day_script = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(close_physio_day_script)


@pytest.fixture(autouse=True)
def _restore_preview_env() -> Iterator[None]:
    before = os.environ.get("PREVIEW_MODE")
    yield
    if before is None:
        os.environ.pop("PREVIEW_MODE", None)
    else:
        os.environ["PREVIEW_MODE"] = before


def _at(day, hours: int, minutes: int = 0) -> datetime:
    return local_midnight(day, club_timezone()) + timedelta(
        hours=hours, minutes=minutes
    )


def _seed(db_path: Path) -> dict[str, object]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            member = Member(first_name="Ana", last_name="Prueba", status="active")
            therapist = Employee(
                employee_number=f"EMP-{uuid4().hex[:8]}",
                first_name="Tere",
                last_name="Fisio",
                job_title="Fisioterapeuta",
                status="active",
            )
            service = PhysioService(
                code="DESCARGA",
                name="Descarga muscular",
                duration_minutes=30,
                price_cents=50000,
            )
            session.add_all([member, therapist, service])
            session.commit()
            session.refresh(member)
            session.refresh(therapist)
            session.refresh(service)
            ids = {
                "member_id": member.id,
                "therapist_id": therapist.id,
                "service_id": service.id,
            }
    finally:
        engine.dispose()
    return ids


def _appointment(
    db_path: Path,
    ids: dict[str, object],
    *,
    starts_at: datetime,
    status: str = "scheduled",
) -> None:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with Session(engine) as session:
            session.add(
                PhysioAppointment(
                    member_id=ids["member_id"],
                    service_id=ids["service_id"],
                    therapist_employee_id=ids["therapist_id"],
                    starts_at=starts_at.astimezone(timezone.utc),
                    ends_at=(starts_at + timedelta(minutes=30)).astimezone(timezone.utc),
                    status=status,
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _statuses(db_path: Path) -> dict[datetime, str]:
    """Map each stored start (naive UTC, as SQLite returns it) to its status."""

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with Session(engine) as session:
            rows = session.exec(select(PhysioAppointment)).all()
            return {row.starts_at: row.status for row in rows}
    finally:
        engine.dispose()


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def test_closes_only_the_pending_appointments_of_the_chosen_day(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db_path = tmp_path / "gym_test.db"
    ids = _seed(db_path)
    day = club_date(datetime.now(timezone.utc)) - timedelta(days=2)
    pending = _at(day, 9)
    attended = _at(day, 11)
    cancelled = _at(day, 13)
    other_day = _at(day - timedelta(days=1), 9)
    _appointment(db_path, ids, starts_at=pending)
    _appointment(db_path, ids, starts_at=attended, status="attended")
    _appointment(db_path, ids, starts_at=cancelled, status="cancelled")
    _appointment(db_path, ids, starts_at=other_day)

    code = close_physio_day_script.main(
        ["--database-url", f"sqlite:///{db_path.as_posix()}", "--date", day.isoformat()]
    )

    printed = capsys.readouterr().out
    assert code == 0
    assert f"{day.isoformat()} — 1 cita marcada como inasistencia." in printed
    starts = _statuses(db_path)
    assert starts[_naive_utc(pending)] == "no_show"
    assert starts[_naive_utc(attended)] == "attended"
    assert starts[_naive_utc(cancelled)] == "cancelled"
    assert starts[_naive_utc(other_day)] == "scheduled"


def test_does_not_close_an_appointment_that_has_not_ended(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db_path = tmp_path / "gym_test.db"
    ids = _seed(db_path)
    today = club_date(datetime.now(timezone.utc))
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    _appointment(db_path, ids, starts_at=future)

    code = close_physio_day_script.main(
        [
            "--database-url",
            f"sqlite:///{db_path.as_posix()}",
            "--date",
            today.isoformat(),
        ]
    )

    printed = capsys.readouterr().out
    assert code == 0
    assert "sin citas pendientes" in printed
    assert next(iter(_statuses(db_path).values())) == "scheduled"


def test_default_day_is_yesterday_and_the_run_is_idempotent(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db_path = tmp_path / "gym_test.db"
    ids = _seed(db_path)
    yesterday = club_date(datetime.now(timezone.utc)) - timedelta(days=1)
    _appointment(db_path, ids, starts_at=_at(yesterday, 10))
    arguments = ["--database-url", f"sqlite:///{db_path.as_posix()}"]

    first = close_physio_day_script.main(arguments)
    first_output = capsys.readouterr().out
    second = close_physio_day_script.main(arguments)
    second_output = capsys.readouterr().out

    assert first == 0
    assert f"{yesterday.isoformat()} — 1 cita marcada como inasistencia." in first_output
    assert second == 0
    assert "sin citas pendientes" in second_output
    assert next(iter(_statuses(db_path).values())) == "no_show"


def test_preview_creates_the_database_and_reports_an_empty_day(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    code = close_physio_day_script.main(["--preview"])

    printed = capsys.readouterr().out
    assert code == 0
    assert "Base de vista previa" in printed
    assert "sin citas pendientes" in printed
    assert (tmp_path / "gym_preview.db").is_file()


def test_preview_and_database_url_cannot_be_combined(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        close_physio_day_script.main(
            ["--preview", "--database-url", "sqlite:///otra.db"]
        )

    assert error.value.code == 2
    assert "no ambos" in capsys.readouterr().err


def test_invalid_date_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        close_physio_day_script.main(["--preview", "--date", "31-10-2026"])

    assert error.value.code == 2
    assert "AAAA-MM-DD" in capsys.readouterr().err


def test_missing_database_url_exits_with_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = close_physio_day_script.main([])

    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_unreachable_database_exits_with_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PREVIEW_MODE", raising=False)

    code = close_physio_day_script.main(
        ["--database-url", f"sqlite:///{(tmp_path / 'missing' / 'gym.db').as_posix()}"]
    )

    assert code == 1
    assert "Error al cerrar el día de fisioterapia" in capsys.readouterr().err
