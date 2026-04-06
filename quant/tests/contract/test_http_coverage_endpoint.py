from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_coverage_query


def test_coverage_ok() -> None:
    app = create_app()
    client = TestClient(app)

    def _stub_coverage(**_kwargs):
        return {
            "universe": "default",
            "start_date": "2025-04-06",
            "end_date": "2026-04-06",
            "min_bars": 1,
            "universe_size": 28,
            "covered_count": 28,
            "missing_count": 0,
            "coverage_rate": 1.0,
            "covered": [],
            "missing": [],
        }

    app.dependency_overrides[get_market_data_coverage_query] = lambda: _stub_coverage
    try:
        with (
            patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=True),
            patch("interfaces.adapters.market_data.db_connection.open_db_connection_from_env", return_value=MagicMock()),
            patch("interfaces.adapters.market_data.timescale_bar_store.TimescaleBarStore"),
        ):
            resp = client.get(
                "/v1/market-data/coverage",
                params={
                    "universe": "default",
                    "start_date": "2025-04-06",
                    "end_date": "2026-04-06",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["coverage_rate"] == 1.0


def test_coverage_db_unavailable() -> None:
    app = create_app()
    client = TestClient(app)

    with patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=False):
        resp = client.get(
            "/v1/market-data/coverage",
            params={
                "universe": "default",
                "start_date": "2025-04-06",
                "end_date": "2026-04-06",
            },
        )

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "COVERAGE_DB_UNAVAILABLE"


def test_coverage_universe_not_found() -> None:
    app = create_app()
    client = TestClient(app)

    def _raise(**_kwargs):
        raise FileNotFoundError("Universe 'nope' not found")

    app.dependency_overrides[get_market_data_coverage_query] = lambda: _raise
    try:
        with (
            patch("interfaces.adapters.market_data.db_connection.has_db_config", return_value=True),
            patch("interfaces.adapters.market_data.db_connection.open_db_connection_from_env", return_value=MagicMock()),
            patch("interfaces.adapters.market_data.timescale_bar_store.TimescaleBarStore"),
        ):
            resp = client.get(
                "/v1/market-data/coverage",
                params={
                    "universe": "nope",
                    "start_date": "2025-04-06",
                    "end_date": "2026-04-06",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "COVERAGE_UNIVERSE_NOT_FOUND"
