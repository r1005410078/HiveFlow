"""Contract tests for async sync endpoints: 202, GET run, cancel, retry-failed."""

from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_sync_service, get_market_data_universe_sync_service


def _stub_sync(*, days, end_date, timeframe, symbols=None, universe=None, request_id=None):
    return {
        "status": "success",
        "run_id": "run-stub-001",
        "timeframe": timeframe,
        "days": days,
        "end_date": end_date,
        "effective_symbols_count": 1,
        "selection_mode": "symbols",
        "symbols_hash": "stub",
        "written_rows": 1,
        "manifest_ids": ["mf_stub_001"],
        "generated_at": "2026-04-01T00:00:00+00:00",
    }


def _make_client():
    app = create_app()
    app.dependency_overrides[get_market_data_sync_service] = lambda: _stub_sync
    return TestClient(app)


def test_post_sync_returns_200_in_no_db_mode():
    """Without DB (InMemoryBarStore + worker=None), POST /sync falls through to sync service."""
    client = _make_client()
    resp = client.post(
        "/v1/market-data/sync",
        json={"days": 3, "end_date": "2026-04-01", "timeframe": "1d"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "success"


def test_get_sync_run_detail_404_in_no_db_mode():
    """GET /sync-runs/{run_id} returns 404 for non-existent run (stub bar store)."""
    client = _make_client()
    resp = client.get("/v1/market-data/sync-runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "SYNC_RUN_NOT_FOUND"


def test_post_cancel_404_for_nonexistent_run():
    """POST cancel returns 404 when run doesn't exist."""
    client = _make_client()
    resp = client.post("/v1/market-data/sync-runs/00000000-0000-0000-0000-000000000000/cancel")
    assert resp.status_code == 404


def test_post_retry_failed_without_worker():
    """retry-failed requires async worker; no-DB mode returns 404 or 501."""
    client = _make_client()
    resp = client.post("/v1/market-data/sync-runs/00000000-0000-0000-0000-000000000000/retry-failed")
    assert resp.status_code in (404, 501)


def test_get_sync_runs_list_still_works():
    """GET /sync-runs listing remains functional (uses query service dependency)."""
    app = create_app()
    from interfaces.http.dependencies import get_market_data_query_service
    app.dependency_overrides[get_market_data_query_service] = lambda: (
        lambda **kw: {"items": []}
    )
    client = TestClient(app)
    resp = client.get("/v1/market-data/sync-runs?days=7")
    assert resp.status_code == 200


def test_post_universe_sync_returns_in_no_db_mode():
    """Without DB, POST /universes/sync falls back to inline execution via dependency override."""
    app = create_app()
    app.dependency_overrides[get_market_data_universe_sync_service] = lambda: (
        lambda universe, provider: {"universe": universe, "provider": provider, "symbols_count": 0}
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/market-data/universes/sync",
        json={"universe": "csi300", "provider": "akshare"},
    )
    assert resp.status_code == 200
