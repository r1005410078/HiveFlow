from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_query_service


def test_get_market_data_sync_runs_returns_items() -> None:
    app = create_app()

    captured: dict[str, object] = {}

    def _stub_query(*, days, timeframe, status, request_id, limit):
        captured["args"] = {
            "days": days,
            "timeframe": timeframe,
            "status": status,
            "request_id": request_id,
            "limit": limit,
        }
        return {
            "items": [
                {
                    "run_id": "run-001",
                    "request_id": request_id,
                    "status": status,
                    "days": days,
                    "end_date": "2026-04-01",
                    "timeframe": timeframe,
                    "selection_mode": "symbols",
                    "symbols_hash": "abc123",
                    "effective_symbols_count": 2,
                    "written_rows": 4,
                    "manifest_ids": ["mf_001"],
                    "started_at": "2026-04-01T09:30:00+08:00",
                    "finished_at": "2026-04-01T09:31:00+08:00",
                    "error_code": None,
                    "error_message": None,
                }
            ]
        }

    app.dependency_overrides[get_market_data_query_service] = lambda: _stub_query
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/sync-runs",
        params={"days": 5, "timeframe": "1d", "status": "success", "request_id": "req-123", "limit": 20},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload
    assert isinstance(payload["items"], list)
    assert captured["args"] == {
        "days": 5,
        "timeframe": "1d",
        "status": "success",
        "request_id": "req-123",
        "limit": 20,
    }
    if payload["items"]:
        first = payload["items"][0]
        assert "run_id" in first
        assert "status" in first
        assert "effective_symbols_count" in first
        assert "close" not in first
