from fastapi.testclient import TestClient

from application.market_data.instruments_list_service import InstrumentsListService
from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_instruments_list_service


def test_get_instruments_universe_stub() -> None:
    app = create_app()
    captured: dict[str, object] = {}

    def _stub(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "items": [{"symbol": "600519.SH", "symbol_name_zh": "贵州茅台"}],
            "has_more": False,
            "next_cursor_symbol": None,
        }

    app.dependency_overrides[get_market_data_instruments_list_service] = lambda: _stub
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/instruments",
        params={"mode": "universe", "universe": "csi300", "limit": 50},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["symbol"] == "600519.SH"
    assert captured["kwargs"]["mode"] == "universe"
    assert captured["kwargs"]["universe"] == "csi300"


def test_get_instruments_422_when_universe_missing() -> None:
    app = create_app()
    svc = InstrumentsListService(bar_store=None)
    app.dependency_overrides[get_market_data_instruments_list_service] = lambda: svc.list_instruments
    client = TestClient(app)

    resp = client.get("/v1/market-data/instruments", params={"mode": "universe"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "INSTRUMENTS_UNIVERSE_REQUIRED"


def test_get_instruments_503_db_mode_without_store() -> None:
    app = create_app()
    svc = InstrumentsListService(bar_store=None)
    app.dependency_overrides[get_market_data_instruments_list_service] = lambda: svc.list_instruments
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/instruments",
        params={"mode": "db", "start_date": "2026-04-01", "end_date": "2026-04-01"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "INSTRUMENTS_DB_UNAVAILABLE"
