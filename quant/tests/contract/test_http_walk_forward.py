"""Contract tests for walk-forward HTTP endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_walk_forward_service


def test_run_ok() -> None:
    """Test successful walk-forward run returns 200 with verdict."""
    app = create_app()
    client = TestClient(app)

    mock_result = {
        "verdict": "pass",
        "failed_gates": [],
        "windows": [
            {
                "warm_start": "2025-01-01",
                "warm_end": "2025-06-30",
                "test_start": "2025-07-01",
                "test_end": "2025-08-31",
                "cumulative_return": 0.05,
                "annualized_return": 0.10,
                "sharpe": 1.0,
                "max_drawdown": 0.08,
                "win_rate": 0.6,
                "days_run": 42,
                "cost_total_bp": 420.0,
            }
        ],
        "aggregate": {
            "window_count": 1,
            "annualized_return": {"mean": 0.10, "min": 0.10, "max": 0.10},
            "sharpe": {"mean": 1.0, "min": 1.0, "max": 1.0},
            "max_drawdown": {"mean": 0.08, "min": 0.08, "max": 0.08},
        },
        "params": {
            "start_date": "2025-01-01",
            "end_date": "2025-08-31",
            "warm_up_days": 180,
            "test_window_days": 63,
            "step_days": 21,
            "cost_bp": 0.0,
        },
    }

    def _stub_service(**kwargs):
        return mock_result

    app.dependency_overrides[get_walk_forward_service] = lambda: _stub_service
    try:
        with patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=True):
            resp = client.post(
                "/v1/walk-forward/run",
                params={
                    "start_date": "2025-01-01",
                    "end_date": "2025-08-31",
                    "warm_up_days": 180,
                    "test_window_days": 63,
                    "step_days": 21,
                    "cost_bp": 0.0,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf walk-forward run"
    assert payload["status"] == "ok"
    assert payload["data"]["verdict"] == "pass"
    assert payload["data"]["failed_gates"] == []
    assert len(payload["data"]["windows"]) == 1
    assert "aggregate" in payload["data"]


def test_run_db_unavailable() -> None:
    """Test returns 503 when database is not configured."""
    app = create_app()
    client = TestClient(app)

    with patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=False):
        resp = client.post(
            "/v1/walk-forward/run",
            params={
                "start_date": "2025-01-01",
                "end_date": "2025-08-31",
            },
        )

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["detail"]["code"] == "WALK_FORWARD_DB_UNAVAILABLE"
    assert "no database configured" in payload["detail"]["message"]


def test_run_invalid_dates() -> None:
    """Test returns 422 when start_date > end_date."""
    app = create_app()
    client = TestClient(app)

    def _stub_service(**kwargs):
        raise ValueError("start_date must be on or before end_date")

    app.dependency_overrides[get_walk_forward_service] = lambda: _stub_service
    try:
        with patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=True):
            resp = client.post(
                "/v1/walk-forward/run",
                params={
                    "start_date": "2025-12-31",
                    "end_date": "2025-01-01",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422
    payload = resp.json()
    assert payload["detail"]["code"] == "WALK_FORWARD_INVALID_PARAMS"


def test_run_with_custom_parameters() -> None:
    """Test walk-forward with custom parameters."""
    app = create_app()
    client = TestClient(app)

    mock_result = {
        "verdict": "no_go",
        "failed_gates": ["annualized_return_mean_min"],
        "windows": [],
        "aggregate": {
            "window_count": 0,
            "annualized_return": {"mean": 0.0, "min": 0.0, "max": 0.0},
            "sharpe": {"mean": 0.0, "min": 0.0, "max": 0.0},
            "max_drawdown": {"mean": 0.0, "min": 0.0, "max": 0.0},
        },
        "params": {
            "start_date": "2025-01-01",
            "end_date": "2025-03-31",
            "warm_up_days": 90,
            "test_window_days": 30,
            "step_days": 10,
            "cost_bp": 5.0,
        },
    }

    def _stub_service(**kwargs):
        return mock_result

    app.dependency_overrides[get_walk_forward_service] = lambda: _stub_service
    try:
        with patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=True):
            resp = client.post(
                "/v1/walk-forward/run",
                params={
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-31",
                    "warm_up_days": 90,
                    "test_window_days": 30,
                    "step_days": 10,
                    "cost_bp": 5.0,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["data"]["params"]["warm_up_days"] == 90
    assert payload["data"]["params"]["test_window_days"] == 30
    assert payload["data"]["params"]["step_days"] == 10
    assert payload["data"]["params"]["cost_bp"] == 5.0
