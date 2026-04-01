from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_sync_service


def test_post_market_data_sync_maps_empty_result_to_422() -> None:
    app = create_app()

    def _raise_empty(*, days, end_date, timeframe, symbols, universe, request_id):
        del days, end_date, timeframe, symbols, universe, request_id
        raise ValueError("no market data fetched for requested scope")

    app.dependency_overrides[get_market_data_sync_service] = lambda: _raise_empty
    client = TestClient(app)

    resp = client.post(
        "/v1/market-data/sync",
        json={"days": 1, "end_date": "2026-04-01", "timeframe": "1d"},
    )

    assert resp.status_code == 422
    payload = resp.json()
    assert payload["detail"]["code"] == "MARKET_DATA_EMPTY"
