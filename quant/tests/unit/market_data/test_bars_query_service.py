from application.market_data.bars_query_service import BarsQueryService


class _FakeBarStore:
    def list_bars(self, symbols=None, timeframe=None, start_date=None, end_date=None, limit=None):
        self.call_args = {
            "symbols": symbols,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        return [
            {
                "symbol": "600519.SH",
                "timeframe": "1d",
                "bar_time": "2026-04-01T15:00:00+08:00",
                "open": 1450.0,
                "high": 1468.0,
                "low": 1442.0,
                "close": 1459.44,
                "volume": 29125.0,
                "amount": 4256185472.0,
                "adj_factor": 1.0,
                "data_source": "tencent",
            }
        ]


def test_bars_query_service_returns_bar_items() -> None:
    store = _FakeBarStore()
    svc = BarsQueryService(bar_store=store)

    out = svc.query(
        symbols=["600519.SH"],
        timeframe="1d",
        start_date="2026-04-01",
        end_date="2026-04-01",
        limit=200,
    )

    assert "items" in out
    assert store.call_args == {
        "symbols": ["600519.SH"],
        "timeframe": "1d",
        "start_date": "2026-04-01",
        "end_date": "2026-04-01",
        "limit": 200,
    }
    assert out["items"][0]["symbol"] == "600519.SH"
    assert out["items"][0]["close"] == 1459.44
