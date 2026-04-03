from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_universe_sync_service


def test_post_market_data_universe_sync_maps_provider_error_to_503() -> None:
    app = create_app()

    def _raise_provider_error(*, universe, provider):
        del universe, provider
        raise RuntimeError("provider unavailable")

    app.dependency_overrides[get_market_data_universe_sync_service] = lambda: _raise_provider_error
    client = TestClient(app)

    resp = client.post("/v1/market-data/universes/sync", json={"universe": "csi300", "provider": "akshare"})

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["detail"]["code"] == "UNIVERSE_SYNC_PROVIDER_ERROR"
