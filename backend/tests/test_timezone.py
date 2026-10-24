"""The club calendar is the single source for day boundaries and folio dates."""

from datetime import date, datetime, timezone

from app.timezone import (
    DEFAULT_TIMEZONE,
    club_date,
    club_day_stamp,
    club_timezone,
    local_midnight,
    to_club_timezone,
)


def test_known_zone_resolves_and_unknown_falls_back_to_utc() -> None:
    assert club_timezone("America/Mexico_City").key == "America/Mexico_City"
    assert club_timezone("Not/AZone").key == "UTC"


def test_default_zone_is_the_club_one(monkeypatch) -> None:
    monkeypatch.delenv("APP_TIMEZONE", raising=False)
    assert club_timezone().key == DEFAULT_TIMEZONE


def test_app_timezone_env_overrides_the_default(monkeypatch) -> None:
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    assert club_timezone().key == "UTC"


def test_local_midnight_is_the_start_of_the_local_day() -> None:
    # Mexico is UTC-6, so its 18th starts six hours after UTC midnight.
    start = local_midnight(date(2026, 10, 18), club_timezone("America/Mexico_City"))
    assert start == datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
    assert local_midnight(date(2026, 10, 18), club_timezone("UTC")) == datetime(
        2026, 10, 18, tzinfo=timezone.utc
    )


def test_club_day_stamp_uses_the_local_day_and_tolerates_naive_values() -> None:
    # 20:00 local on the 18th is already the 19th in UTC.
    instant = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)
    assert club_day_stamp(instant, timezone_name="America/Mexico_City") == "20261018"
    assert club_date(instant, timezone_name="America/Mexico_City") == date(2026, 10, 18)
    # A naive value (SQLite drops tzinfo on reload) is read as UTC.
    naive = datetime(2026, 10, 19, 2, 0)
    assert club_day_stamp(naive, timezone_name="America/Mexico_City") == "20261018"
    assert to_club_timezone(naive, timezone_name="UTC") == instant
