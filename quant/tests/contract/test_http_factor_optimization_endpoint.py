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
    combination_size_min = int(constraints.get("__combination_size_min__", 2))
    combination_size_max = int(constraints.get("__combination_size_max__", 4))
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
            "top_combinations": {
                "search_space": {
                    "factor_pool_size": len(factor_names),
                    "combination_size_min": combination_size_min,
                    "combination_size_max": combination_size_max,
                    "candidate_count": 3,
                },
                "ranking_profile": "balanced_v1",
                "items": [],
            },
            "report": {
                "matrix_10d": [{"dimension": "IC"} for _ in range(10)],
                "summary": {"recommended_scheme": "balanced", "key_findings": []},
                "g3_checklist": [
                    {"item": "风控组评审", "checked": False},
                    {"item": "合规组审核", "checked": False},
                    {"item": "CRO 最终批准", "checked": False},
                ],
            },
            "release_gate": {
                "status": "pass",
                "blocking_reasons": [],
                "watch_items": [],
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
    assert {"threshold", "alerts", "alert_count"} <= set(payload["data"]["correlation_analysis"].keys())
    assert payload["data"]["correlation_analysis"]["threshold"] == 0.7
    assert payload["data"]["correlation_analysis"]["alert_count"] == 0
    assert {"search_space", "ranking_profile", "items"} <= set(payload["data"]["top_combinations"].keys())
    report = payload["data"]["report"]
    assert {"matrix_10d", "summary", "g3_checklist"} <= set(report.keys())
    assert len(report["matrix_10d"]) == 10
    assert all("dimension" in row for row in report["matrix_10d"])
    assert len(report["g3_checklist"]) == 3
    assert all({"item", "checked"} <= set(item.keys()) for item in report["g3_checklist"])
    assert all(isinstance(item["checked"], bool) for item in report["g3_checklist"])
    release_gate = payload["data"]["release_gate"]
    assert {"status", "blocking_reasons", "watch_items"} <= set(release_gate.keys())
    assert release_gate["status"] in {"pass", "watch", "fail"}
    assert release_gate["blocking_reasons"] == []
    assert release_gate["watch_items"] == []


def test_factor_optimization_endpoint_accepts_custom_correlation_threshold() -> None:
    app = create_app()
    app.dependency_overrides[get_factor_optimization_service] = lambda: _stub_factor_optimization_service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/factor-optimization/evaluate",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20"],
            "constraints": {"max_weight:max_drawdown_60": 0.3},
            "correlation_threshold": 0.9,
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["data"]["correlation_analysis"]["threshold"] == 0.9


def test_factor_optimization_endpoint_accepts_combination_args() -> None:
    app = create_app()
    app.dependency_overrides[get_factor_optimization_service] = lambda: _stub_factor_optimization_service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/factor-optimization/evaluate",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20", "max_drawdown_60"],
            "constraints": {},
            "combination_size_min": 3,
            "combination_size_max": 4,
            "top_k_combinations": 3,
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    search_space = payload["data"]["top_combinations"]["search_space"]
    assert search_space["combination_size_min"] == 3
    assert search_space["combination_size_max"] == 4


def test_factor_optimization_endpoint_rejects_invalid_combination_range() -> None:
    app = create_app()
    app.dependency_overrides[get_factor_optimization_service] = lambda: _stub_factor_optimization_service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/factor-optimization/evaluate",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20"],
            "constraints": {},
            "combination_size_min": 4,
            "combination_size_max": 3,
        },
    )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["detail"]["code"] == "INVALID_ARGUMENT"
