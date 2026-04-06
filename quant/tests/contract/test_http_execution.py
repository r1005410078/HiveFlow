"""Contract tests for L6 execution plan HTTP endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_execution_service


def _stub_ok() -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf execution plan",
        "run_id": "exec_stub_001",
        "status": "ok",
        "generated_at": "2026-04-01T10:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "as_of": "2026-04-01",
            "slippage_bp": 5,
            "estimated_total_cost_bp": 6.4,
            "orders": [
                {
                    "symbol": "600519.SH",
                    "direction": "buy",
                    "action": "open_long",
                    "quantity": 100,
                    "target_notional": 120_000.0,
                    "current_notional": 0.0,
                    "close_price": 1180.0,
                    "limit_price": 1180.59,
                    "order_type": "limit",
                    "validity": "day",
                    "impact_bp": 2.1,
                },
            ],
        },
        "warnings": [],
        "errors": [],
    }


def _stub_no_price() -> dict:
    out = _stub_ok()
    out["data"]["orders"] = [{
        "symbol": "600519.SH",
        "direction": "buy",
        "action": "open_long",
        "quantity": None,
        "target_notional": 1_000_000.0,
        "current_notional": 0.0,
        "close_price": None,
        "limit_price": None,
        "order_type": "limit",
        "validity": "day",
        "impact_bp": None,
    }]
    out["warnings"] = [{
        "code": "EXECUTION_USING_NO_PRICE",
        "message": "bar_store unavailable; close_price/quantity/limit_price set to null",
    }]
    return out


def test_post_execution_plan_ok() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_execution_service] = lambda: (
        lambda ao, tw, pt, n: _stub_ok()
    )
    try:
        resp = client.post(
            "/api/v1/execution/plan",
            json={
                "as_of": "2026-04-01",
                "target_weights": {"600519.SH": 1.0},
                "pretrade": {"orders": []},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["command"] == "hf execution plan"
    assert payload["data"]["slippage_bp"] == 5
    assert payload["data"]["orders"][0]["symbol"] == "600519.SH"


def test_post_execution_plan_missing_weights_422() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_execution_service] = lambda: (
        lambda ao, tw, pt, n: _stub_ok()
    )
    try:
        resp = client.post(
            "/api/v1/execution/plan",
            json={"as_of": "2026-04-01"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422


def test_post_execution_plan_degraded_warning() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_execution_service] = lambda: (
        lambda ao, tw, pt, n: _stub_no_price()
    )
    try:
        resp = client.post(
            "/api/v1/execution/plan",
            json={"as_of": "2026-04-01", "target_weights": {"600519.SH": 1.0}},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert any(w["code"] == "EXECUTION_USING_NO_PRICE" for w in resp.json()["warnings"])
