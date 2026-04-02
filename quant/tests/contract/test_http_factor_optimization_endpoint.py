from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_factor_optimization_service


def _stub_factor_optimization_service(
    start_date: str,
    end_date: str,
    factor_names: list[str],
    constraints: dict[str, float],
) -> dict:
    correlation_threshold = constraints.get("__correlation_threshold__", 0.7)
    return {
        "schema_version": "1.0.0",
        "command": "hf factor optimize",
        "status": "ok",
        "advice_only": True,
        "decision_weight": 0,
        "data": {
            "factor_names": factor_names,
            "analysis": {"factor_health": [], "correlation_matrix": {}, "coverage": {"symbols": 0, "bars": 0}},
            "correlation_analysis": {
                "threshold": correlation_threshold,
                "alerts": [],
                "alert_count": 0,
            },
            "recommendations": [
                {
                    "name": "balanced",
                    "weights": {"momentum_20": 0.6, "inv_volatility_20": 0.4},
                    "expected_sharpe": 1.2,
                    "expected_drawdown": 0.2,
                    "score": 1.1,
                }
            ],
            "recommended_scheme": "balanced",
            "report": {
                "matrix_10d": [{"dimension": "IC"} for _ in range(10)],
                "summary": {"recommended_scheme": "balanced", "key_findings": []},
                "g3_checklist": [
                    {"item": "风控组评审", "checked": False},
                    {"item": "合规组审核", "checked": False},
                    {"item": "CRO 最终批准", "checked": False},
                ],
            },
        },
        "audit": {
            "generated_at": "2026-04-02T00:00:00+00:00",
            "analysis_period": {"start_date": start_date, "end_date": end_date},
            "g3_review_required": True,
        },
        "warnings": [],
        "errors": [],
    }


def test_factor_optimization_endpoint_contract_ok() -> None:
    app = create_app()
    app.dependency_overrides[get_factor_optimization_service] = lambda: _stub_factor_optimization_service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/factor-optimization/evaluate",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate"],
            "constraints": {"max_weight:max_drawdown_60": 0.3},
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["advice_only"] is True
    assert payload["decision_weight"] == 0
    assert payload["data"]["correlation_analysis"]["threshold"] == 0.7
    assert payload["data"]["correlation_analysis"]["alert_count"] == 0
    assert len(payload["data"]["report"]["matrix_10d"]) == 10
