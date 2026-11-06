"""UTC-first time helpers.

The database stores naive UTC datetimes. Conversion to the shop's local time
happens only at the presentation edge, which removes the old mix of Python
``date.today()`` and SQL ``CURDATE()``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from core.config import TIMEZONE


def utc_now() -> datetime:
    """Current UTC time as a naive datetime suitable for MySQL DATETIME."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_today() -> date:
    return utc_now().date()


def local_zone() -> ZoneInfo:
    return ZoneInfo(TIMEZONE)


def local_today() -> date:
    return datetime.now(local_zone()).date()


def to_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(local_zone())


def format_local(value: datetime | None, fmt: str = "%d %b %Y, %I:%M %p") -> str:
    local = to_local(value)
    return local.strftime(fmt) if local else "N/A"


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Return the UTC half-open range covering a local calendar day."""
    start_local = datetime.combine(day, time.min, tzinfo=local_zone())
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def local_days_ago_utc(days: int) -> datetime:
    """UTC instant corresponding to local midnight ``days`` ago."""
    start_local = datetime.combine(
        local_today() - timedelta(days=days), time.min, tzinfo=local_zone()
    )
    return start_local.astimezone(timezone.utc).replace(tzinfo=None)


def local_date_to_utc(day: date, at_hour: int = 12) -> datetime:
    """Turn a chosen local calendar date into a stable UTC timestamp."""
    local = datetime.combine(day, time(hour=at_hour), tzinfo=local_zone())
    return local.astimezone(timezone.utc).replace(tzinfo=None)
