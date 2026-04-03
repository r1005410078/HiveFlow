from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_pipeline_compare_service


def _stub_compare_service(start_date: str, end_date: str, top_n: int) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pipeline compare",
        "run_id": "run_compare_stub",
        "status": "ok",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "start_date": start_date,
            "end_date": end_date,
            "top_n": top_n,
            "score_versions": ["l2-score-v1", "l2-score-v1.1"],
            "daily_items": [
                {
                    "as_of": start_date,
                    "v1": {
                        "score_version": "l2-score-v1",
                        "top_candidates": [{"symbol": "000001.SZ", "score": 0.4, "rank": 1}],
                        "warning_count": 1,
                        "min_availability": 1.0,
                    },
                    "v1_1": {
                        "score_version": "l2-score-v1.1",
                        "top_candidates": [{"symbol": "600519.SH", "score": 0.6, "rank": 1}],
                        "warning_count": 0,
                        "min_availability": 0.5,
                    },
                }
            ],
            "summary": {
                "days": 1,
                "avg_warning_count_v1": 1.0,
                "avg_warning_count_v1_1": 0.0,
                "avg_min_availability_v1": 1.0,
                "avg_min_availability_v1_1": 0.5,
                "top1_symbol_change_days": 1,
            },
            "analytics": {
                "return_metrics": {
                    "v1": {
                        "cumulative_return": 0.02,
                        "win_rate": 1.0,
                        "max_drawdown": 0.0,
                        "annualized_volatility": 0.0,
                        "sharpe": 0.0,
                    },
                    "v1_1": {
                        "cumulative_return": 0.01,
                        "win_rate": 1.0,
                        "max_drawdown": 0.0,
                        "annualized_volatility": 0.0,
                        "sharpe": 0.0,
                    },
                    "diff": {
                        "excess_cumulative_return_v1_1_vs_v1": -0.01,
                        "excess_sharpe_v1_1_vs_v1": 0.0,
                    },
                },
                "daily_return_series": {
                    "v1": [{"as_of": start_date, "top1_next_day_return": 0.02}],
                    "v1_1": [{"as_of": start_date, "top1_next_day_return": 0.01}],
                },
                "group_stability": {
                    "group_key": "industry_market_cap_bucket",
                    "items": [
                        {
                            "industry": "Bank",
                            "market_cap_bucket": "LARGE",
                            "sample_days": 1,
                            "v1": {
                                "cumulative_return": 0.02,
                                "win_rate": 1.0,
                                "sharpe": 0.0,
                            },
                            "v1_1": {
                                "cumulative_return": 0.01,
                                "win_rate": 1.0,
                                "sharpe": 0.0,
                            },
                            "diff": {
                                "excess_cumulative_return": -0.01,
                                "excess_sharpe": 0.0,
                            },
                            "stability_flag": "LOW_SAMPLE",
                        }
                    ],
                },
            },
        },
        "warnings": [],
        "errors": [],
    }


def test_post_pipeline_compare_contract() -> None:
    app = create_app()
    app.dependency_overrides[get_pipeline_compare_service] = lambda: _stub_compare_service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/pipeline/compare",
        json={"start_date": "2026-04-01", "end_date": "2026-04-01", "top_n": 5},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf pipeline compare"
    assert payload["data"]["start_date"] == "2026-04-01"
    assert payload["data"]["end_date"] == "2026-04-01"
    assert payload["data"]["top_n"] == 5
    assert payload["data"]["score_versions"] == ["l2-score-v1", "l2-score-v1.1"]
    analytics = payload["data"]["analytics"]
    assert {"return_metrics", "daily_return_series", "group_stability"} <= set(analytics.keys())
    assert payload["data"]["daily_items"][0]["v1"]["warning_count"] == 1
    assert payload["data"]["summary"]["top1_symbol_change_days"] == 1
