import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.timezone import DEFAULT_TIMEZONE, club_timezone, validate_club_timezone


def test_validate_club_timezone_accepts_the_default():
    assert validate_club_timezone().key == DEFAULT_TIMEZONE


def test_validate_club_timezone_rejects_an_unknown_zone(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "America/Atlantis")

    with pytest.raises(ValueError, match="America/Atlantis"):
        validate_club_timezone()


def test_startup_refuses_to_run_with_an_unknown_zone(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "America/Atlantis")

    with pytest.raises(ValueError, match="APP_TIMEZONE"):
        with TestClient(app):
            pass


def test_club_timezone_still_degrades_to_utc_when_reading(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "America/Atlantis")

    assert club_timezone().key == "UTC"
