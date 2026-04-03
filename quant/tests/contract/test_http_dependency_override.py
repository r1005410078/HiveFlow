from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_daily_run_service


def _stub_daily_run_service(as_of: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pipeline daily",
        "run_id": "run_stub",
        "status": "ok",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "as_of": as_of,
            "data_manifest_id": "dm_stub",
            "factor_snapshot": {
                "snapshot_version": "l2-basic-v1.1",
                "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate"],
                "coverage_rate": 1.0,
                "rows": [
                    {
                        "as_of": as_of,
                        "symbol": "600519.SH",
                        "factor_name": "momentum_20",
                        "factor_version": "l2-basic-v1.1",
                        "raw_value": 0.02,
                    }
                ],
            },
            "execution_plan": {"orders": []},
            "l2_decision": {
                "schema_version": "1.0",
                "generated_at": "2026-04-01T00:00:00+00:00",
                "producer_version": "quant-l2",
                "score_version": "l2-score-v1.1",
                "universe_size": 1,
                "top_candidates": [{"symbol": "600519.SH", "score": 0.5, "rank": 1}],
                "factor_availability": [
                    {
                        "factor_name": "momentum_20",
                        "present_count": 1,
                        "missing_count": 0,
                        "availability_rate": 1.0,
                    },
                    {
                        "factor_name": "inv_volatility_20",
                        "present_count": 0,
                        "missing_count": 1,
                        "availability_rate": 0.0,
                    },
                    {
                        "factor_name": "turnover_rate",
                        "present_count": 0,
                        "missing_count": 1,
                        "availability_rate": 0.0,
                    },
                    {
                        "factor_name": "max_drawdown_60",
                        "present_count": 0,
                        "missing_count": 1,
                        "availability_rate": 0.0,
                    },
                    {
                        "factor_name": "trend_stability_20",
                        "present_count": 0,
                        "missing_count": 1,
                        "availability_rate": 0.0,
                    },
                    {
                        "factor_name": "relative_strength_vs_index",
                        "present_count": 0,
                        "missing_count": 1,
                        "availability_rate": 0.0,
                    },
                ],
                "score_breakdown": [
                    {
                        "symbol": "600519.SH",
                        "final_score": 0.5,
                        "factors": [
                            {
                                "factor_name": "momentum_20",
                                "raw_value": 0.02,
                                "normalized_value": 1.0,
                                "percentile": 1.0,
                                "clipped": False,
                                "anomaly_flags": [],
                                "weight": 0.5,
                                "contribution": 0.5,
                            },
                            {
                                "factor_name": "inv_volatility_20",
                                "raw_value": 0.0,
                                "normalized_value": 1.0,
                                "percentile": 1.0,
                                "clipped": False,
                                "anomaly_flags": ["missing_factor:inv_volatility_20"],
                                "weight": 0.3,
                                "contribution": 0.3,
                            },
                            {
                                "factor_name": "turnover_rate",
                                "raw_value": 0.0,
                                "normalized_value": 1.0,
                                "percentile": 1.0,
                                "clipped": False,
                                "anomaly_flags": ["missing_factor:turnover_rate"],
                                "weight": 0.2,
                                "contribution": 0.2,
                            }
                        ],
                    }
                ],
            },
        },
        "warnings": [],
        "errors": [],
    }


def test_http_dependency_override_for_daily_service():
    app = create_app()
    app.dependency_overrides[get_daily_run_service] = lambda: _stub_daily_run_service
    client = TestClient(app)

    resp = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-01"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["run_id"] == "run_stub"
    assert payload["data"]["data_manifest_id"] == "dm_stub"
    assert payload["data"]["factor_snapshot"]["snapshot_version"] == "l2-basic-v1.1"
