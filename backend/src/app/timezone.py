"""Club-local time helpers.

Every timestamp is stored in UTC, but the club reads and writes in its own
calendar: ``APP_TIMEZONE`` (``America/Mexico_City`` by default). This is the
single place that resolves that zone, so the access log, the reports, the point
of sale and maintenance all agree on which calendar day a sale, a refund, a
ticket or a "today" window belongs to.

The day boundaries and the folio dates are the club's, not UTC's: a sale rung up
at 20:00 in Mexico is already the next day in UTC, but it stays on the club's
local day everywhere the operator looks.
"""

import os
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "America/Mexico_City"


def club_timezone(name: str | None = None) -> ZoneInfo:
    """Resolve ``timezone_name`` (or ``APP_TIMEZONE``), falling back to UTC.

    An unknown zone name never crashes a read: the club's calendar degrades to
    UTC, which is the same convention the access summary already used.
    """

    try:
        return ZoneInfo(name or os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    """UTC instant at which ``day`` starts in ``tz``."""

    return datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)


def to_club_timezone(moment: datetime, *, timezone_name: str | None = None) -> datetime:
    """Move an instant to the club's timezone, treating a naive value as UTC.

    Naive values happen when SQLite reloads a row and drops ``tzinfo``.
    """

    if moment.tzinfo is None or moment.utcoffset() is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(club_timezone(timezone_name))


def club_date(moment: datetime, *, timezone_name: str | None = None) -> date:
    """The club-local calendar day of an instant."""

    return to_club_timezone(moment, timezone_name=timezone_name).date()


def club_day_stamp(moment: datetime, *, timezone_name: str | None = None) -> str:
    """The club-local calendar day as ``YYYYMMDD`` (used in folios)."""

    return club_date(moment, timezone_name=timezone_name).strftime("%Y%m%d")
