from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_sync_service


def test_post_market_data_sync_returns_run_id() -> None:
    app = create_app()

    def _stub_sync(*, days, end_date, timeframe, symbols, universe, request_id):
        del symbols, universe, request_id
        return {
            "status": "success",
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "timeframe": timeframe,
            "days": days,
            "end_date": end_date,
            "effective_symbols_count": 1,
            "selection_mode": "symbols",
            "symbols_hash": "abc123",
            "written_rows": 1,
            "manifest_ids": ["mf_stub_001"],
            "generated_at": "2026-04-01T00:00:00+00:00",
        }

    app.dependency_overrides[get_market_data_sync_service] = lambda: _stub_sync
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
