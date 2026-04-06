"""Contract tests for L5.5 pretrade HTTP endpoint."""

from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_pretrade_service


def _stub_ok() -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pretrade check",
        "run_id": "run_stub_001",
        "status": "ok",
        "generated_at": "2026-04-01T10:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "as_of": "2026-04-01",
            "notional": 1_000_000.0,
            "overall_tradable": True,
            "total_impact_bp": 5.5,
            "orders": [
                {
                    "symbol": "600519.SH",
                    "target_weight": 1.0,
                    "target_notional": 1_000_000.0,
                    "adv": 8e8,
                    "participation_rate": 0.00125,
                    "sigma": 0.18,
                    "impact_bp": 5.5,
                    "tradable": True,
                },
            ],
        },
        "warnings": [],
        "errors": [],
    }


def _stub_fallback_warning() -> dict:
    out = _stub_ok()
    out["warnings"] = [{
        "code": "PRETRADE_USING_FALLBACK_ADV",
        "message": "bar_store unavailable; using fallback ADV=1e9 and sigma=0.20",
    }]
    return out


def test_post_pretrade_check_ok() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_pretrade_service] = lambda: (
        lambda ao, tw, n: _stub_ok()
    )
    try:
        resp = client.post(
            "/api/v1/pretrade/check",
            json={"as_of": "2026-04-01", "target_weights": {"600519.SH": 1.0}},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["command"] == "hf pretrade check"
    assert payload["data"]["overall_tradable"] is True
    assert isinstance(payload["data"]["orders"], list)
    assert payload["data"]["orders"][0]["symbol"] == "600519.SH"


def test_post_pretrade_check_missing_weights_422() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_pretrade_service] = lambda: (
        lambda ao, tw, n: _stub_ok()
    )
    try:
        resp = client.post(
            "/api/v1/pretrade/check",
            json={"as_of": "2026-04-01"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422


def test_post_pretrade_check_fallback_warning_in_body() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_pretrade_service] = lambda: (
        lambda ao, tw, n: _stub_fallback_warning()
    )
    try:
        resp = client.post(
            "/api/v1/pretrade/check",
            json={"as_of": "2026-04-01", "target_weights": {"600519.SH": 1.0}},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    w = resp.json()["warnings"]
    assert any(x.get("code") == "PRETRADE_USING_FALLBACK_ADV" for x in w)
