from __future__ import annotations

from datetime import date

import pytest

from domain.market_data.bars_aggregate import (
    aggregate_1m_to_session_multiframe,
    aggregate_daily_to_monthly,
    aggregate_daily_to_weekly,
    aggregate_storage_rows,
    filter_intraday_session_minutes,
    merge_ohlc_sequence,
)


def test_merge_ohlc_sequence_three_bars_volume_none_middle() -> None:
    rows = [
        {"open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100.0},
        {"open": 10.5, "high": 12.0, "low": 10.0, "close": 11.0, "volume": None},
        {"open": 11.0, "high": 11.5, "low": 10.8, "close": 11.2, "volume": 50.0},
    ]
    got = merge_ohlc_sequence(rows)
    assert got["open"] == 10.0
    assert got["high"] == 12.0
    assert got["low"] == 9.5
    assert got["close"] == 11.2
    assert got["volume"] == pytest.approx(150.0)


def test_filter_intraday_keeps_0931_drops_premarket_and_lunch() -> None:
    session = "2026-01-05"
    rows = [
        {"bar_time": "2026-01-05T08:00:00+08:00", "open": 1, "high": 1, "low": 1, "close": 1},
        {"bar_time": "2026-01-05T09:31:00+08:00", "open": 2, "high": 2, "low": 2, "close": 2},
        {"bar_time": "2026-01-05T12:00:00+08:00", "open": 3, "high": 3, "low": 3, "close": 3},
    ]
    got = filter_intraday_session_minutes(rows, session)
    assert len(got) == 1
    assert "09:31" in got[0]["bar_time"]


def test_multiframe_5m_first_bucket_anchor_monday_sse_day() -> None:
    """§5.2.3: first 5m morning bucket ends at 09:35+08."""
    day = "2026-01-05"
    rows = []
    for minute in range(30, 35):
        rows.append(
            {
                "bar_time": f"{day}T09:{minute:02d}:00+08:00",
                "open": float(minute),
                "high": float(minute) + 0.5,
                "low": float(minute) - 0.5,
                "close": float(minute) + 0.1,
                "volume": 10.0,
            }
        )
    got = aggregate_1m_to_session_multiframe(rows, 5)
    assert got, "expected at least one bucket"
    assert got[0]["bar_time"] == "2026-01-05T09:35:00+08:00"


def test_aggregate_daily_to_monthly_two_days_same_month() -> None:
    daily = [
        {
            "bar_time": "2026-01-05T15:00:00+08:00",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
            "symbol": "TEST.SH",
        },
        {
            "bar_time": "2026-01-08T15:00:00+08:00",
            "open": 104.0,
            "high": 110.0,
            "low": 102.0,
            "close": 108.0,
            "symbol": "TEST.SH",
        },
    ]
    got = aggregate_daily_to_monthly(daily)
    assert len(got) == 1
    assert got[0]["open"] == 100.0
    assert got[0]["close"] == 108.0
    assert got[0]["high"] == 110.0
    assert got[0]["low"] == 99.0
    last_sse_jan_2026 = "2026-01-30"
    assert got[0]["bar_time"] == f"{last_sse_jan_2026}T15:00:00+08:00"


def test_aggregate_daily_to_weekly_iso_week_boundary_splits_groups() -> None:
    """2025-12-26 is ISO week 52 of 2025; 2025-12-29 starts ISO week 1 of 2026."""
    assert date(2025, 12, 26).isocalendar()[:2] == (2025, 52)
    assert date(2025, 12, 29).isocalendar()[:2] == (2026, 1)

    daily = [
        {
            "bar_time": "2025-12-26T15:00:00+08:00",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
        },
        {
            "bar_time": "2025-12-29T15:00:00+08:00",
            "open": 2.0,
            "high": 3.0,
            "low": 1.5,
            "close": 2.5,
        },
    ]
    got = aggregate_daily_to_weekly(daily)
    assert len(got) == 2
    anchors = sorted(r["bar_time"] for r in got)
    # ISO week 52/2025 ends 2025-12-26; ISO week 1/2026 ends 2025-12-31 (calendar still December).
    assert anchors[0] == "2025-12-26T15:00:00+08:00"
    assert anchors[1] == "2025-12-31T15:00:00+08:00"


def test_aggregate_storage_rows_1q_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        aggregate_storage_rows("1Q", [])
