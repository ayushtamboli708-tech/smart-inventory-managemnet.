from __future__ import annotations

from datetime import date, datetime, timedelta

from core.time import (
    format_local,
    local_date_to_utc,
    local_day_bounds_utc,
    local_days_ago_utc,
    to_local,
    utc_now,
)


def test_day_bounds_cover_exactly_24_hours() -> None:
    start, end = local_day_bounds_utc(date(2026, 11, 5))
    assert end - start == timedelta(days=1)


def test_kolkata_bounds_are_utc_shifted() -> None:
    start, _ = local_day_bounds_utc(date(2026, 11, 5))
    assert start == datetime(2026, 11, 4, 18, 30)


def test_local_date_round_trip_keeps_selected_day() -> None:
    utc_value = local_date_to_utc(date(2026, 11, 5))
    assert to_local(utc_value).date() == date(2026, 11, 5)


def test_days_ago_is_in_the_past_and_naive_utc() -> None:
    value = local_days_ago_utc(7)
    assert value.tzinfo is None
    assert value < utc_now()


def test_format_local_handles_missing_value() -> None:
    assert format_local(None) == "N/A"
