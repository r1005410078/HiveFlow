"""Unit tests for SSE (XSHG) trading calendar helpers."""

import exchange_calendars as ecals
import pandas as pd
import pytest

from domain.market_data.sse_calendar import is_sse_trading_day, iter_sse_trading_days


def test_new_year_2026_is_not_trading() -> None:
    """China New Year's Day 2026-01-01 is not an XSHG session."""
    assert is_sse_trading_day("2026-01-01") is False


def test_known_weekday_trading_day_matches_exchange_calendars() -> None:
    """A normal session day matches ``exchange_calendars`` XSHG directly."""
    day = "2026-01-05"
    cal = ecals.get_calendar("XSHG")
    expected = cal.is_session(pd.Timestamp(day))
    assert is_sse_trading_day(day) == expected
    assert expected is True


def test_iter_sse_trading_days_matches_sessions_in_range() -> None:
    start, end = "2026-01-05", "2026-01-09"
    cal = ecals.get_calendar("XSHG")
    expected = [
        ts.strftime("%Y-%m-%d")
        for ts in cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    ]
    assert list(iter_sse_trading_days(start, end)) == expected


def test_iter_excludes_weekend_in_range() -> None:
    """Range spanning Sat–Sun yields only Thu/Fri sessions before the weekend."""
    # 2026-01-08 Thu, 2026-01-09 Fri, 2026-01-10 Sat, 2026-01-11 Sun
    cal = ecals.get_calendar("XSHG")
    expected = [
        ts.strftime("%Y-%m-%d")
        for ts in cal.sessions_in_range(
            pd.Timestamp("2026-01-08"), pd.Timestamp("2026-01-11")
        )
    ]
    assert expected == ["2026-01-08", "2026-01-09"]
    assert list(iter_sse_trading_days("2026-01-08", "2026-01-11")) == expected


def test_iter_empty_when_end_before_start() -> None:
    assert list(iter_sse_trading_days("2026-01-10", "2026-01-05")) == []


def test_invalid_date_format_raises() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        is_sse_trading_day("20260101")
