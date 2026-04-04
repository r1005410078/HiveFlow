"""Pure-domain OHLC aggregation and A-share session bucketing (Asia/Shanghai).

Implements §5.1–§5.2 of ``2026-04-04-market-data-lazy-list-aggregate-design``:
single-bucket OHLC merge, 1m→1d on SSE calendar, intraday session filter, multiframe
minute buckets, and daily→weekly/monthly/yearly rollups. No HTTP/DB imports.

Extra row keys (e.g. ``symbol``, ``data_source``) are taken from the **chronologically
first** row in each output bucket after sorting by ``bar_time``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from domain.market_data.sse_calendar import is_sse_trading_day, iter_sse_trading_days

SHANGHAI = ZoneInfo("Asia/Shanghai")

_TIMEFRAME_TO_DELTA: dict[str, int] = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
}


def _parse_bar_time(bar_time: str) -> datetime:
    """Parse ISO bar_time (``Z`` or ``+08:00`` / offset) to aware datetime."""
    s = bar_time.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"bar_time must be timezone-aware, got {bar_time!r}")
    return dt


def _shanghai_local(dt: datetime) -> datetime:
    return dt.astimezone(SHANGHAI)


def _shanghai_date_str(dt: datetime) -> str:
    return _shanghai_local(dt).date().isoformat()


def _day_close_anchor(trading_day_yyyy_mm_dd: str) -> datetime:
    d = date.fromisoformat(trading_day_yyyy_mm_dd)
    return datetime.combine(d, time(15, 0), tzinfo=SHANGHAI)


def _in_open_call_auction_local(local_dt: datetime) -> bool:
    """SSE open call auction minutes 09:15–09:25 (minute starts, Shanghai)."""
    return local_dt.hour == 9 and 15 <= local_dt.minute <= 25


def _in_close_call_auction_local(local_dt: datetime) -> bool:
    """SSE closing call auction window 14:57–15:00 (Shanghai)."""
    if local_dt.hour == 14 and local_dt.minute >= 57:
        return True
    return local_dt.hour == 15 and local_dt.minute == 0


def _in_continuous_morning_local(local_dt: datetime) -> bool:
    """§5.2.2 morning continuous auction [09:30, 11:30) (left-closed right-open)."""
    t = local_dt.time()
    return time(9, 30) <= t < time(11, 30)


def _in_continuous_afternoon_local(local_dt: datetime) -> bool:
    """§5.2.2 afternoon continuous auction [13:00, 15:00)."""
    t = local_dt.time()
    return time(13, 0) <= t < time(15, 0)


def _keep_intraday_row_local(local_dt: datetime, session_day: date) -> bool:
    if local_dt.date() != session_day:
        return False
    return (
        _in_continuous_morning_local(local_dt)
        or _in_continuous_afternoon_local(local_dt)
        or _in_open_call_auction_local(local_dt)
        or _in_close_call_auction_local(local_dt)
    )


def _numeric_or_none(row: dict[str, Any], key: str) -> float | None:
    if key not in row:
        return None
    v = row[key]
    if v is None:
        return None
    return float(v)


def merge_ohlc_sequence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge ordered OHLC rows (§5.1). Volume/amount: None sums as 0; all missing → None."""
    if not rows:
        raise ValueError("merge_ohlc_sequence requires at least one row")

    first = rows[0]
    last = rows[-1]
    highs = [_numeric_or_none(r, "high") for r in rows]
    lows = [_numeric_or_none(r, "low") for r in rows]

    def _finite(xs: Iterable[float | None]) -> list[float]:
        return [x for x in xs if x is not None]

    hi_vals = _finite(highs)
    lo_vals = _finite(lows)
    if not hi_vals or not lo_vals:
        raise ValueError("high/low must be present on each row")

    out: dict[str, Any] = {
        "open": first["open"],
        "high": max(hi_vals),
        "low": min(lo_vals),
        "close": last["close"],
    }

    for field in ("volume", "amount"):
        present = False
        total = 0.0
        for r in rows:
            if field not in r or r[field] is None:
                continue
            present = True
            total += float(r[field])
        out[field] = total if present else None

    return out


def aggregate_storage_1m_to_daily(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bucket 1m storage rows by SSE trading day (Shanghai calendar); anchor 15:00+08."""
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        bt = _parse_bar_time(str(r["bar_time"]))
        day = _shanghai_date_str(bt)
        if not is_sse_trading_day(day):
            continue
        by_day[day].append(r)

    out: list[dict[str, Any]] = []
    for day in sorted(by_day.keys()):
        bucket = sorted(by_day[day], key=lambda x: _parse_bar_time(str(x["bar_time"])))
        merged = merge_ohlc_sequence(bucket)
        first = bucket[0]
        row_out = {k: v for k, v in first.items() if k not in {"open", "high", "low", "close", "volume", "amount"}}
        row_out.update(merged)
        row_out["bar_time"] = _day_close_anchor(day).isoformat()
        out.append(row_out)
    return out


def filter_intraday_session_minutes(
    rows: list[dict[str, Any]], session_date: str
) -> list[dict[str, Any]]:
    """§5.2.2 intraday subset for one session (Shanghai natural day + session windows)."""
    session_day = date.fromisoformat(session_date)
    kept: list[dict[str, Any]] = []
    for r in rows:
        bt = _parse_bar_time(str(r["bar_time"]))
        local = _shanghai_local(bt)
        if _keep_intraday_row_local(local, session_day):
            kept.append(r)
    kept.sort(key=lambda x: _parse_bar_time(str(x["bar_time"])))
    return kept


def _sorted_bucket_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda x: _parse_bar_time(str(x["bar_time"])))


def _merge_bucket_rows(bucket: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = _sorted_bucket_rows(bucket)
    merged = merge_ohlc_sequence(ordered)
    base = ordered[0]
    row_out = {k: v for k, v in base.items() if k not in {"open", "high", "low", "close", "volume", "amount"}}
    row_out.update(merged)
    return row_out


def _afternoon_bucket_rows(
    rows_sorted: list[dict[str, Any]],
    d: date,
    t: datetime,
    t_end: datetime,
    afternoon_end: datetime,
) -> list[dict[str, Any]]:
    bucket: list[dict[str, Any]] = []
    for r in rows_sorted:
        lt = _shanghai_local(_parse_bar_time(str(r["bar_time"])))
        if lt.date() != d:
            continue
        if t <= lt < t_end:
            bucket.append(r)
            continue
        if t_end == afternoon_end and _in_close_call_auction_local(lt):
            bucket.append(r)
    return bucket


def _morning_bucket_rows(
    rows_sorted: list[dict[str, Any]],
    d: date,
    t: datetime,
    t_end: datetime,
    include_open_auction: bool,
) -> list[dict[str, Any]]:
    bucket: list[dict[str, Any]] = []
    if include_open_auction:
        for r in rows_sorted:
            lt = _shanghai_local(_parse_bar_time(str(r["bar_time"])))
            if lt.date() != d:
                continue
            if _in_open_call_auction_local(lt):
                bucket.append(r)
    for r in rows_sorted:
        lt = _shanghai_local(_parse_bar_time(str(r["bar_time"])))
        if lt.date() != d:
            continue
        if t <= lt < t_end:
            bucket.append(r)
    return bucket


def aggregate_1m_to_session_multiframe(
    rows: list[dict[str, Any]], delta_minutes: int
) -> list[dict[str, Any]]:
    """§5.2.3 multiframe buckets per SSE day; anchor = right edge (+08)."""
    if delta_minutes <= 0:
        raise ValueError("delta_minutes must be positive")

    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        bt = _parse_bar_time(str(r["bar_time"]))
        day = _shanghai_date_str(bt)
        if not is_sse_trading_day(day):
            continue
        by_day[day].append(r)

    out: list[dict[str, Any]] = []
    for day_str in sorted(by_day.keys()):
        d = date.fromisoformat(day_str)
        filtered = filter_intraday_session_minutes(by_day[day_str], day_str)
        rows_sorted = _sorted_bucket_rows(filtered)
        morning_start = datetime.combine(d, time(9, 30), tzinfo=SHANGHAI)
        morning_end = datetime.combine(d, time(11, 30), tzinfo=SHANGHAI)
        afternoon_start = datetime.combine(d, time(13, 0), tzinfo=SHANGHAI)
        afternoon_end = datetime.combine(d, time(15, 0), tzinfo=SHANGHAI)

        t = morning_start
        first_morning = True
        while t < morning_end:
            t_end = min(t + timedelta(minutes=delta_minutes), morning_end)
            bucket = _morning_bucket_rows(rows_sorted, d, t, t_end, include_open_auction=first_morning)
            first_morning = False
            if bucket:
                row_out = _merge_bucket_rows(bucket)
                row_out["bar_time"] = t_end.isoformat()
                out.append(row_out)
            t = t_end

        t = afternoon_start
        while t < afternoon_end:
            t_end = min(t + timedelta(minutes=delta_minutes), afternoon_end)
            bucket = _afternoon_bucket_rows(rows_sorted, d, t, t_end, afternoon_end)
            if bucket:
                row_out = _merge_bucket_rows(bucket)
                row_out["bar_time"] = t_end.isoformat()
                out.append(row_out)
            t = t_end

    out.sort(key=lambda x: _parse_bar_time(str(x["bar_time"])))
    return out


def _last_sse_trading_day_in_range(start: date, end_exclusive: date) -> str | None:
    """Last YYYY-MM-DD session in [start, end_exclusive) (inclusive of start, exclusive of end)."""
    if end_exclusive <= start:
        return None
    last: str | None = None
    for s in iter_sse_trading_days(start.isoformat(), (end_exclusive - timedelta(days=1)).isoformat()):
        last = s
    return last


def _iso_week_bounds_shanghai(d: date) -> tuple[date, date]:
    """ISO week: Monday 00:00 to next Monday 00:00 (calendar dates in local sense)."""
    y, w, _ = d.isocalendar()
    monday = date.fromisocalendar(y, w, 1)
    next_monday = monday + timedelta(days=7)
    return monday, next_monday


def _month_bounds(d: date) -> tuple[date, date]:
    first = date(d.year, d.month, 1)
    if d.month == 12:
        next_first = date(d.year + 1, 1, 1)
    else:
        next_first = date(d.year, d.month + 1, 1)
    return first, next_first


def _year_bounds(d: date) -> tuple[date, date]:
    first = date(d.year, 1, 1)
    next_first = date(d.year + 1, 1, 1)
    return first, next_first


def _daily_trading_day_from_bar(row: dict[str, Any]) -> date:
    bt = _parse_bar_time(str(row["bar_time"]))
    local = _shanghai_local(bt)
    return local.date()


def aggregate_daily_to_weekly(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§5.2.4 ISO week (Shanghai calendar dates), anchor last SSE session 15:00+08 in that week."""
    if not daily_rows:
        return []

    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in daily_rows:
        d = _daily_trading_day_from_bar(r)
        y, w, _ = d.isocalendar()
        groups[(y, w)].append(r)

    out: list[dict[str, Any]] = []
    for key in sorted(groups.keys()):
        y, w = key
        bucket = _sorted_bucket_rows(groups[(y, w)])
        monday = date.fromisocalendar(y, w, 1)
        _, next_monday = _iso_week_bounds_shanghai(monday)
        anchor_day = _last_sse_trading_day_in_range(monday, next_monday)
        if anchor_day is None:
            continue
        merged = merge_ohlc_sequence(bucket)
        first = bucket[0]
        row_out = {k: v for k, v in first.items() if k not in {"open", "high", "low", "close", "volume", "amount"}}
        row_out.update(merged)
        row_out["bar_time"] = _day_close_anchor(anchor_day).isoformat()
        out.append(row_out)
    return out


def aggregate_daily_to_monthly(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§5.2.5 calendar month; anchor last SSE session 15:00+08 in that month."""
    if not daily_rows:
        return []

    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in daily_rows:
        d = _daily_trading_day_from_bar(r)
        groups[(d.year, d.month)].append(r)

    out: list[dict[str, Any]] = []
    for yr, mo in sorted(groups.keys()):
        bucket = _sorted_bucket_rows(groups[(yr, mo)])
        first_day = date(yr, mo, 1)
        _, next_first = _month_bounds(first_day)
        anchor_day = _last_sse_trading_day_in_range(first_day, next_first)
        if anchor_day is None:
            continue
        merged = merge_ohlc_sequence(bucket)
        first = bucket[0]
        row_out = {k: v for k, v in first.items() if k not in {"open", "high", "low", "close", "volume", "amount"}}
        row_out.update(merged)
        row_out["bar_time"] = _day_close_anchor(anchor_day).isoformat()
        out.append(row_out)
    return out


def aggregate_daily_to_yearly(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§5.2.5 calendar year; anchor last SSE session 15:00+08 in that year."""
    if not daily_rows:
        return []

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in daily_rows:
        d = _daily_trading_day_from_bar(r)
        groups[d.year].append(r)

    out: list[dict[str, Any]] = []
    for year in sorted(groups.keys()):
        bucket = _sorted_bucket_rows(groups[year])
        first_day = date(year, 1, 1)
        _, next_first = _year_bounds(first_day)
        anchor_day = _last_sse_trading_day_in_range(first_day, next_first)
        if anchor_day is None:
            continue
        merged = merge_ohlc_sequence(bucket)
        first = bucket[0]
        row_out = {k: v for k, v in first.items() if k not in {"open", "high", "low", "close", "volume", "amount"}}
        row_out.update(merged)
        row_out["bar_time"] = _day_close_anchor(anchor_day).isoformat()
        out.append(row_out)
    return out


def _trim_to_minute(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        bt = _parse_bar_time(str(r["bar_time"]))
        floored = bt.astimezone(SHANGHAI).replace(second=0, microsecond=0)
        rr = dict(r)
        rr["bar_time"] = floored.isoformat()
        out.append(rr)
    return out


def aggregate_storage_rows(
    output_timeframe: str,
    rows_1m_asc: list[dict[str, Any]],
    *,
    session_date: str | None = None,
) -> list[dict[str, Any]]:
    """Route 1m storage rows to the requested output timeframe (§5.1 table + §5.2)."""
    tf = output_timeframe.strip()
    if tf == "1Q":
        raise NotImplementedError("timeframe 1Q is not implemented yet")

    if tf == "1m":
        base = list(rows_1m_asc)
        if session_date is not None:
            return filter_intraday_session_minutes(base, session_date)
        return _trim_to_minute(base)

    if tf in _TIMEFRAME_TO_DELTA:
        delta = _TIMEFRAME_TO_DELTA[tf]
        if session_date is not None:
            day_rows = [r for r in rows_1m_asc if _shanghai_date_str(_parse_bar_time(str(r["bar_time"]))) == session_date]
            filtered = filter_intraday_session_minutes(day_rows, session_date)
            return aggregate_1m_to_session_multiframe(filtered, delta)
        return aggregate_1m_to_session_multiframe(rows_1m_asc, delta)

    if tf == "1d":
        return aggregate_storage_1m_to_daily(rows_1m_asc)

    if tf == "1w":
        daily = aggregate_storage_1m_to_daily(rows_1m_asc)
        return aggregate_daily_to_weekly(daily)

    if tf == "1M":
        daily = aggregate_storage_1m_to_daily(rows_1m_asc)
        return aggregate_daily_to_monthly(daily)

    if tf == "1y":
        daily = aggregate_storage_1m_to_daily(rows_1m_asc)
        return aggregate_daily_to_yearly(daily)

    raise ValueError(f"unsupported output_timeframe: {output_timeframe!r}")
