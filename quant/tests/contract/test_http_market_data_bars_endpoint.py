from fastapi.testclient import TestClient

from application.market_data.bars_query_service import BarsQueryService
from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_bars_query_service


class _EmptyBarStore:
    def list_bars(self, **kwargs):
        return []

    def list_storage_bars(self, **kwargs):
        return []


def test_get_market_data_bars_returns_items() -> None:
    app = create_app()

    captured: dict[str, object] = {}

    def _stub_query(
        *,
        symbols,
        timeframe,
        start_date,
        end_date,
        limit,
        session_date=None,
        cursor_bar_time=None,
        cursor_symbol=None,
    ):
        captured["args"] = {
            "symbols": symbols,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "session_date": session_date,
            "cursor_bar_time": cursor_bar_time,
            "cursor_symbol": cursor_symbol,
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
            ],
            "next_cursor_bar_time": None,
            "next_cursor_symbol": None,
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
    assert payload.get("next_cursor_bar_time") is None
    assert payload.get("next_cursor_symbol") is None
    assert captured["args"] == {
        "symbols": ["600519.SH", "000001.SZ"],
        "timeframe": "1d",
        "start_date": "2026-04-01",
        "end_date": "2026-04-01",
        "limit": 200,
        "session_date": None,
        "cursor_bar_time": None,
        "cursor_symbol": None,
    }
    if payload["items"]:
        first = payload["items"][0]
        assert "symbol" in first
        assert "bar_time" in first
        assert "close" in first
        assert "symbol_name_zh" in first


def test_get_market_data_bars_passes_session_and_cursor_to_service() -> None:
    app = create_app()
    captured: dict[str, object] = {}

    def _stub_query(**kwargs):
        captured["kwargs"] = kwargs
        return {"items": [], "next_cursor_bar_time": None, "next_cursor_symbol": None}

    app.dependency_overrides[get_market_data_bars_query_service] = lambda: _stub_query
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/bars",
        params={
            "symbols": ["600519.SH"],
            "timeframe": "1m",
            "session_date": "2026-01-05",
            "cursor_bar_time": "2026-01-05T09:35:00+08:00",
            "cursor_symbol": "600519.SH",
            "limit": 100,
        },
    )
    assert resp.status_code == 200
    assert captured["kwargs"]["session_date"] == "2026-01-05"
    assert captured["kwargs"]["cursor_bar_time"] == "2026-01-05T09:35:00+08:00"
    assert captured["kwargs"]["cursor_symbol"] == "600519.SH"


def test_get_market_data_bars_422_on_timeframe_finer_than_storage() -> None:
    app = create_app()
    store = _EmptyBarStore()
    svc = BarsQueryService(store)
    app.dependency_overrides[get_market_data_bars_query_service] = lambda: svc.query
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/bars",
        params={"symbols": ["600519.SH"], "timeframe": "1s"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "TIMEFRAME_FINER_THAN_STORAGE"
