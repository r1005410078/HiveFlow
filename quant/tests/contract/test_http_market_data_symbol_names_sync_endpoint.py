from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_symbol_names_sync_service


def test_post_market_data_symbol_names_sync_returns_summary() -> None:
    app = create_app()

    def _stub_merge(*, universes, provider):
        assert universes == ["csi300"]
        assert provider == "akshare"
        return {
            "provider": provider,
            "universes": universes,
            "per_universe_symbols": {"csi300": 3},
            "symbol_names_path": "/tmp/quant/config/universes/symbol_names.json",
            "updated_at": "2026-04-04T00:00:00+00:00",
        }

    app.dependency_overrides[get_market_data_symbol_names_sync_service] = lambda: _stub_merge
    client = TestClient(app)

    resp = client.post(
        "/v1/market-data/universes/symbol-names/sync",
        json={"universes": ["csi300"], "provider": "akshare"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["universes"] == ["csi300"]
    assert payload["per_universe_symbols"]["csi300"] == 3


def test_post_market_data_symbol_names_sync_default_body() -> None:
    app = create_app()
    called: dict = {}

    def _stub_merge(*, universes, provider):
        called["universes"] = universes
        called["provider"] = provider
        return {
            "provider": provider,
            "universes": ["csi300", "zz500", "all_a"],
            "per_universe_symbols": {},
            "symbol_names_path": None,
            "updated_at": "2026-04-04T00:00:00+00:00",
        }

    app.dependency_overrides[get_market_data_symbol_names_sync_service] = lambda: _stub_merge
    client = TestClient(app)

    resp = client.post("/v1/market-data/universes/symbol-names/sync", json={"provider": "akshare"})
    assert resp.status_code == 200
    assert called["universes"] is None
