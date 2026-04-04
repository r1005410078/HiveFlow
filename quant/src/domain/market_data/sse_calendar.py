"""SSE (XSHG) trading calendar helpers for A-share daily alignment.

Uses ``exchange_calendars`` calendar ``XSHG`` (Shanghai). Data is bundled with
the library; no runtime network calls.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import exchange_calendars as ecals
import pandas as pd
from exchange_calendars import ExchangeCalendar

_CALENDAR_NAME = "XSHG"
_calendar: ExchangeCalendar | None = None


def _get_xshg_calendar() -> ExchangeCalendar:
    global _calendar
    if _calendar is None:
        _calendar = ecals.get_calendar(_CALENDAR_NAME)
    return _calendar


def _parse_yyyy_mm_dd(date_str: str) -> pd.Timestamp:
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"expected YYYY-MM-DD, got {date_str!r}") from exc
    return pd.Timestamp(parsed.date())


def is_sse_trading_day(date_str: str) -> bool:
    """Return True if ``date_str`` (YYYY-MM-DD) is an XSHG session day."""
    cal = _get_xshg_calendar()
    ts = _parse_yyyy_mm_dd(date_str)
    return bool(cal.is_session(ts))


def iter_sse_trading_days(start: str, end: str) -> Iterator[str]:
    """Yield YYYY-MM-DD for each XSHG session from ``start`` through ``end`` (inclusive).

    If ``end`` is before ``start``, yields nothing.
    """
    start_ts = _parse_yyyy_mm_dd(start)
    end_ts = _parse_yyyy_mm_dd(end)
    if end_ts < start_ts:
        return
    cal = _get_xshg_calendar()
    sessions = cal.sessions_in_range(start_ts, end_ts)
    for ts in sessions:
        yield ts.strftime("%Y-%m-%d")
