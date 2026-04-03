from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_universe_sync_service


def test_post_market_data_universe_sync_returns_summary() -> None:
    app = create_app()

    def _stub_sync(*, universe, provider):
        assert universe == "csi300"
        assert provider == "akshare"
        return {
            "universe": universe,
            "provider": provider,
            "symbols_count": 300,
            "file_path": "/tmp/csi300.txt",
            "updated_at": "2026-04-03T00:00:00+00:00",
        }

    app.dependency_overrides[get_market_data_universe_sync_service] = lambda: _stub_sync
    client = TestClient(app)

    resp = client.post("/v1/market-data/universes/sync", json={"universe": "csi300", "provider": "akshare"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["universe"] == "csi300"
    assert payload["provider"] == "akshare"
    assert payload["symbols_count"] == 300
