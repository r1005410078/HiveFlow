from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_sync_service


def test_post_market_data_sync_returns_existing_run_for_request_id() -> None:
    app = create_app()

    def _stub_sync(*, days, end_date, timeframe, symbols, universe, request_id):
        del days, end_date, timeframe, symbols, universe
        assert request_id == "req-123"
        return {
            "status": "success",
            "run_id": "run-existing",
            "request_id": request_id,
            "timeframe": "1d",
            "days": 5,
            "end_date": "2026-04-01",
            "effective_symbols_count": 1,
            "selection_mode": "symbols",
            "symbols_hash": "abc123",
            "written_rows": 9,
            "manifest_ids": ["mf_stored_abc"],
            "generated_at": "2026-04-01T00:00:00+00:00",
        }

    app.dependency_overrides[get_market_data_sync_service] = lambda: _stub_sync
    client = TestClient(app)

    resp = client.post(
        "/v1/market-data/sync",
        json={
            "days": 5,
            "end_date": "2026-04-01",
            "timeframe": "1d",
            "request_id": "req-123",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "success"
    assert payload["request_id"] == "req-123"
    assert payload["run_id"] == "run-existing"
    assert payload["selection_mode"] == "symbols"
    assert payload["written_rows"] == 9
    assert payload["manifest_ids"] == ["mf_stored_abc"]
    assert {
        "status",
        "run_id",
        "request_id",
        "timeframe",
        "days",
        "end_date",
        "effective_symbols_count",
        "selection_mode",
        "symbols_hash",
        "written_rows",
        "manifest_ids",
        "generated_at",
    }.issubset(payload.keys())
