from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_post_market_data_sync_returns_run_id() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/v1/market-data/sync",
        json={"days": 5, "end_date": "2026-04-01", "timeframe": "1d"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "success"
    assert payload["timeframe"] == "1d"
    assert payload["days"] == 5
    assert "run_id" in payload
