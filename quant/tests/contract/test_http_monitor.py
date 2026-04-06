"""Contract tests for L8 monitor health-report HTTP endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_health_report_service


def _stub_envelope_green(as_of: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf monitor health-report",
        "run_id": "hr_stub_001",
        "status": "ok",
        "generated_at": "2026-04-01T10:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "as_of": as_of,
            "overall_rating": "green",
            "factor_health": {
                "total": 1,
                "ok_count": 1,
                "warn_count": 0,
                "miss_count": 0,
                "details": [],
            },
            "signal_health": {
                "coverage_rate": 0.9,
                "composite_score_mean": 0.0,
                "composite_score_std": 0.0,
                "status": "ok",
            },
            "risk_health": {
                "regime": "normal",
                "triggered_rules": [],
                "status": "ok",
            },
            "trend": None,
            "run_daily_warnings": [],
        },
        "warnings": [],
        "errors": [],
    }


def test_get_health_report_ok() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_health_report_service] = lambda: (
        lambda ao: _stub_envelope_green(ao)
    )
    try:
        with patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=True):
            resp = client.get("/v1/monitor/health-report", params={"as_of": "2026-04-01"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf monitor health-report"
    assert payload["data"]["overall_rating"] == "green"
    assert "factor_health" in payload["data"]
    assert "signal_health" in payload["data"]
    assert "risk_health" in payload["data"]


def test_get_health_report_missing_as_of_422() -> None:
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_health_report_service] = lambda: (
        lambda ao: _stub_envelope_green(ao)
    )
    try:
        resp = client.get("/v1/monitor/health-report")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422


def test_get_health_report_db_unavailable_still_200() -> None:
    """无 DB 时 provider 仍应返回 200（内部 bar_store=None 走 deterministic daily）。"""
    app = create_app()
    client = TestClient(app)
    app.dependency_overrides[get_health_report_service] = lambda: (
        lambda ao: _stub_envelope_green(ao)
    )
    try:
        with patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=False):
            resp = client.get("/v1/monitor/health-report", params={"as_of": "2026-04-01"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["command"] == "hf monitor health-report"
