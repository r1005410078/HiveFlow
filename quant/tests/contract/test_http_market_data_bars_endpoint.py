from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_get_market_data_bars_returns_items() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/bars",
        params={"symbols": "600519.SH", "timeframe": "1d", "start_date": "2026-04-01", "end_date": "2026-04-01"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload
    assert isinstance(payload["items"], list)
    if payload["items"]:
        first = payload["items"][0]
        assert "symbol" in first
        assert "bar_time" in first
        assert "close" in first
