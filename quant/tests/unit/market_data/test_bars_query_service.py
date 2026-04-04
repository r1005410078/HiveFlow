from __future__ import annotations

import pytest

from application.market_data.bars_query_service import BarsQueryService


class _FakeBarStore:
    def __init__(self, storage_rows: list[dict] | None = None):
        self.storage_rows = storage_rows or []
        self.list_bars_calls: list[dict] = []
        self.list_storage_calls: list[dict] = []

    def list_bars(self, symbols=None, timeframe=None, start_date=None, end_date=None, limit=None):
        self.list_bars_calls.append(
            {
                "symbols": symbols,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            }
        )
        return []

    def list_storage_bars(
        self,
        symbols=None,
        storage_timeframe="1m",
        start_date=None,
        end_date=None,
        limit=None,
        order="asc",
    ):
        self.list_storage_calls.append(
            {
                "symbols": symbols,
                "storage_timeframe": storage_timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
                "order": order,
            }
        )
        return list(self.storage_rows)

    def list_symbols_with_min_bars_in_window(
        self,
        *,
        storage_timeframe: str,
        start_date: str,
        end_date: str,
        min_bars: int,
        after_symbol: str | None,
        limit: int,
    ):
        del storage_timeframe, start_date, end_date, min_bars, after_symbol, limit
        return ([], False)


def _two_minutes_same_trading_day() -> list[dict]:
    return [
        {
            "symbol": "600519.SH",
            "timeframe": "1m",
            "bar_time": "2026-04-01T09:31:00+08:00",
            "open": 1450.0,
            "high": 1452.0,
            "low": 1449.0,
            "close": 1451.0,
            "volume": 100.0,
            "amount": 1000.0,
            "adj_factor": 1.0,
            "data_source": "tencent",
        },
        {
            "symbol": "600519.SH",
            "timeframe": "1m",
            "bar_time": "2026-04-01T09:32:00+08:00",
            "open": 1451.0,
            "high": 1455.0,
            "low": 1450.0,
            "close": 1454.0,
            "volume": 80.0,
            "amount": 900.0,
            "adj_factor": 1.0,
            "data_source": "tencent",
        },
    ]


def test_query_1d_uses_list_storage_1m_and_aggregates() -> None:
    store = _FakeBarStore(_two_minutes_same_trading_day())
    svc = BarsQueryService(bar_store=store)

    out = svc.query(
        symbols=["600519.SH"],
        timeframe="1d",
        start_date="2026-04-01",
        end_date="2026-04-01",
        limit=200,
    )

    assert len(store.list_storage_calls) == 1
    sc = store.list_storage_calls[0]
    assert sc["storage_timeframe"] == "1m"
    assert sc["order"] == "asc"
    assert sc["symbols"] == ["600519.SH"]
    assert "items" in out
    assert len(out["items"]) == 1
    row = out["items"][0]
    assert row["timeframe"] == "1d"
    assert row["symbol"] == "600519.SH"
    assert row["bar_time"] == "2026-04-01T15:00:00+08:00"
    assert row["open"] == 1450.0
    assert row["close"] == 1454.0
    assert row["high"] == 1455.0
    assert row["low"] == 1449.0
    assert out["next_cursor_bar_time"] is None
    assert out["next_cursor_symbol"] is None


def test_next_cursor_when_more_rows_than_limit_1m_desc() -> None:
    day = "2026-04-01"
    rows = []
    for minute in (33, 32, 31):
        rows.append(
            {
                "symbol": "600519.SH",
                "timeframe": "1m",
                "bar_time": f"{day}T09:{minute:02d}:00+08:00",
                "open": float(minute),
                "high": float(minute),
                "low": float(minute),
                "close": float(minute),
                "volume": 1.0,
                "amount": 1.0,
                "adj_factor": 1.0,
                "data_source": "x",
            }
        )
    store = _FakeBarStore(rows)
    svc = BarsQueryService(bar_store=store)
    out = svc.query(
        symbols=["600519.SH"],
        timeframe="1m",
        start_date=day,
        end_date=day,
        limit=2,
    )
    assert len(out["items"]) == 2
    assert "09:33" in out["items"][0]["bar_time"]
    assert out["next_cursor_bar_time"] == out["items"][-1]["bar_time"]
    assert out["next_cursor_symbol"] == "600519.SH"


def test_session_date_intraday_1m_sorted_asc() -> None:
    day = "2026-01-05"
    rows = [
        {
            "symbol": "600519.SH",
            "timeframe": "1m",
            "bar_time": f"{day}T10:00:00+08:00",
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
            "amount": 1.0,
            "adj_factor": 1.0,
            "data_source": "x",
        },
        {
            "symbol": "600519.SH",
            "timeframe": "1m",
            "bar_time": f"{day}T09:31:00+08:00",
            "open": 2.0,
            "high": 2.0,
            "low": 2.0,
            "close": 2.0,
            "volume": 1.0,
            "amount": 1.0,
            "adj_factor": 1.0,
            "data_source": "x",
        },
    ]
    store = _FakeBarStore(rows)
    svc = BarsQueryService(bar_store=store)

    out = svc.query(
        symbols=["600519.SH"],
        timeframe="1m",
        session_date=day,
        limit=50,
    )

    assert store.list_storage_calls[0]["start_date"] == day
    assert store.list_storage_calls[0]["end_date"] == day
    times = [r["bar_time"] for r in out["items"]]
    assert times == sorted(times)
    assert "09:31" in times[0]
    assert "10:00" in times[1]
    assert out["next_cursor_bar_time"] is None


def test_cursor_with_multi_symbol_raises() -> None:
    store = _FakeBarStore([])
    svc = BarsQueryService(bar_store=store)
    with pytest.raises(ValueError, match="BARS_CURSOR_MULTI_SYMBOL"):
        svc.query(
            symbols=["600519.SH", "000001.SZ"],
            timeframe="1d",
            cursor_bar_time="2026-04-01T15:00:00+08:00",
        )


def test_cursor_without_single_symbol_raises() -> None:
    store = _FakeBarStore([])
    svc = BarsQueryService(bar_store=store)
    with pytest.raises(ValueError, match="BARS_CURSOR_SINGLE_SYMBOL_ONLY"):
        svc.query(
            symbols=None,
            timeframe="1d",
            cursor_bar_time="2026-04-01T15:00:00+08:00",
        )


def test_timeframe_1s_raises() -> None:
    store = _FakeBarStore([])
    svc = BarsQueryService(bar_store=store)
    with pytest.raises(ValueError, match="TIMEFRAME_FINER_THAN_STORAGE"):
        svc.query(symbols=["600519.SH"], timeframe="1s")


def test_session_date_not_trading_day_raises() -> None:
    store = _FakeBarStore([])
    svc = BarsQueryService(bar_store=store)
    with pytest.raises(ValueError, match="SESSION_DATE_NOT_TRADING_DAY"):
        svc.query(
            symbols=["600519.SH"],
            timeframe="1m",
            session_date="2026-01-01",
        )


def test_timeframe_1q_not_implemented() -> None:
    store = _FakeBarStore(_two_minutes_same_trading_day())
    svc = BarsQueryService(bar_store=store)
    with pytest.raises(ValueError, match="TIMEFRAME_NOT_IMPLEMENTED"):
        svc.query(symbols=["600519.SH"], timeframe="1Q", start_date="2026-04-01", end_date="2026-04-01")


def test_cursor_symbol_mismatch_raises() -> None:
    store = _FakeBarStore([])
    svc = BarsQueryService(bar_store=store)
    with pytest.raises(ValueError, match="BARS_CURSOR_SYMBOL_MISMATCH"):
        svc.query(
            symbols=["600519.SH"],
            timeframe="1d",
            cursor_bar_time="2026-04-01T15:00:00+08:00",
            cursor_symbol="000001.SZ",
        )
