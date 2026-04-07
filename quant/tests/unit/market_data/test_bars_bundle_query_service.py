from __future__ import annotations

import pytest

from application.market_data.bars_query_service import BarsQueryService


class _FakeBarStore:
    def __init__(
        self,
        storage_rows: list[dict] | None = None,
        *,
        by_timeframe: dict[str, list[dict]] | None = None,
    ):
        self.by_tf: dict[str, list[dict]] = {}
        if storage_rows is not None:
            self.by_tf["1m"] = storage_rows
        if by_timeframe:
            self.by_tf.update(by_timeframe)
        self.list_storage_calls: list[dict] = []

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
        return list(self.by_tf.get(storage_timeframe, []))


def _two_minutes_600519() -> list[dict]:
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


def test_query_bundle_single_list_storage_multiple_timeframes() -> None:
    store = _FakeBarStore(_two_minutes_600519())
    svc = BarsQueryService(bar_store=store)

    out = svc.query_bundle(
        symbols=["600519.SH"],
        timeframes=["1m", "1d"],
        start_date="2026-04-01",
        end_date="2026-04-01",
        limit_per_timeframe=100,
    )

    assert len(store.list_storage_calls) == 2
    tfs = {c["storage_timeframe"] for c in store.list_storage_calls}
    assert tfs == {"1m", "15m"}
    assert all(c["symbols"] == ["600519.SH"] for c in store.list_storage_calls)
    assert out["schema_version"] == "1.0.0"
    assert "generated_at" in out
    assert out["producer_version"] == "hiveflow-quant-bars-bundle-1.0.0"
    assert "by_timeframe" in out
    btf = out["by_timeframe"]
    assert "1m" in btf and "1d" in btf
    assert btf["1m"]["has_more"] is False
    assert len(btf["1m"]["items"]) == 2
    assert all(r["timeframe"] == "1m" for r in btf["1m"]["items"])
    assert len(btf["1d"]["items"]) == 1
    assert btf["1d"]["items"][0]["timeframe"] == "1d"
    assert btf["1d"]["items"][0]["close"] == 1454.0


def test_query_bundle_empty_symbols_raises() -> None:
    svc = BarsQueryService(bar_store=_FakeBarStore([]))
    with pytest.raises(ValueError, match="BARS_BUNDLE_SYMBOLS_REQUIRED"):
        svc.query_bundle(symbols=[], timeframes=["1d"])


def test_query_bundle_empty_timeframes_raises() -> None:
    svc = BarsQueryService(bar_store=_FakeBarStore([]))
    with pytest.raises(ValueError, match="BARS_BUNDLE_TIMEFRAMES_REQUIRED"):
        svc.query_bundle(symbols=["600519.SH"], timeframes=[])
