from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_bars_query_service


def test_get_market_data_bars_returns_items() -> None:
    app = create_app()

    captured: dict[str, object] = {}

    def _stub_query(*, symbols, timeframe, start_date, end_date, limit):
        captured["args"] = {
            "symbols": symbols,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        return {
            "items": [
                {
                    "symbol": "600519.SH",
                    "timeframe": timeframe,
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
        }

    app.dependency_overrides[get_market_data_bars_query_service] = lambda: _stub_query
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/bars",
        params={
            "symbols": ["600519.SH", "000001.SZ"],
            "timeframe": "1d",
            "start_date": "2026-04-01",
            "end_date": "2026-04-01",
            "limit": 200,
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload
    assert isinstance(payload["items"], list)
    assert captured["args"] == {
        "symbols": ["600519.SH", "000001.SZ"],
        "timeframe": "1d",
        "start_date": "2026-04-01",
        "end_date": "2026-04-01",
        "limit": 200,
    }
    if payload["items"]:
        first = payload["items"][0]
        assert "symbol" in first
        assert "bar_time" in first
        assert "close" in first
