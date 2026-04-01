from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_get_market_data_sync_runs_returns_items() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/v1/market-data/sync-runs", params={"days": 5, "timeframe": "1d"})

    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload
    assert isinstance(payload["items"], list)
