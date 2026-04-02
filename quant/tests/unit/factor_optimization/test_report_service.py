from application.factor_optimization.report_service import build_factor_optimization_report


def test_build_factor_optimization_report_contains_audit_and_never_auto_apply() -> None:
    report = build_factor_optimization_report(
        start_date="2026-01-01",
        end_date="2026-04-01",
        factor_names=["momentum_20", "inv_volatility_20"],
        analysis={"factor_health": [], "correlation_matrix": {}, "coverage": {}},
        recommendations=[{"name": "balanced", "weights": {"momentum_20": 0.6, "inv_volatility_20": 0.4}}],
    )

    assert report["advice_only"] is True
    assert report["decision_weight"] == 0
    assert {"generated_at", "analysis_period", "g3_review_required"} <= set(report["audit"].keys())
