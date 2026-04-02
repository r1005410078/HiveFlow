from application.factor_optimization.report_service import build_factor_optimization_report


def test_build_factor_optimization_report_contains_audit_and_never_auto_apply() -> None:
    report = build_factor_optimization_report(
        start_date="2026-01-01",
        end_date="2026-04-01",
        factor_names=["momentum_20", "inv_volatility_20"],
        analysis={
            "factor_health": [
                {"factor_name": "momentum_20", "ic": 0.12, "sharpe": 1.6, "max_drawdown": 0.2},
                {"factor_name": "inv_volatility_20", "ic": 0.09, "sharpe": 1.3, "max_drawdown": 0.18},
            ],
            "correlation_matrix": {
                "momentum_20": {"momentum_20": 1.0, "inv_volatility_20": 0.82},
                "inv_volatility_20": {"momentum_20": 0.82, "inv_volatility_20": 1.0},
            },
            "coverage": {"symbols": 2, "bars": 4},
        },
        recommendations=[{"name": "balanced", "weights": {"momentum_20": 0.6, "inv_volatility_20": 0.4}}],
    )

    assert report["advice_only"] is True
    assert report["decision_weight"] == 0
    assert {"generated_at", "analysis_period", "g3_review_required"} <= set(report["audit"].keys())
    assert report["data"]["correlation_analysis"]["threshold"] == 0.7
    assert report["data"]["correlation_analysis"]["alert_count"] == 1
    assert len(report["data"]["report"]["matrix_10d"]) == 10
    assert len(report["data"]["report"]["g3_checklist"]) == 3
    assert "top_combinations" in report["data"]
