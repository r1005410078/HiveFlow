from application.factor_optimization.report_10d_service import build_report_10d


def test_build_report_10d_returns_fixed_dimensions_and_g3_checklist() -> None:
    out = build_report_10d(
        factor_names=["momentum_20", "inv_volatility_20"],
        analysis={
            "factor_health": [
                {"factor_name": "momentum_20", "ic": 0.12, "sharpe": 1.5, "max_drawdown": 0.21},
                {"factor_name": "inv_volatility_20", "ic": 0.09, "sharpe": 1.3, "max_drawdown": 0.18},
            ],
            "coverage": {"symbols": 10, "bars": 800},
            "correlation_matrix": {},
        },
        recommendations=[{"name": "balanced", "weights": {"momentum_20": 0.6, "inv_volatility_20": 0.4}}],
        correlation_analysis={
            "threshold": 0.7,
            "alert_count": 1,
            "alerts": [
                {
                    "factor_a": "momentum_20",
                    "factor_b": "inv_volatility_20",
                    "correlation": 0.78,
                    "severity": "medium",
                    "suggestion": "consider reducing weight for inv_volatility_20",
                }
            ],
        },
    )

    assert len(out["matrix_10d"]) == 10
    assert [row["dimension"] for row in out["matrix_10d"]] == [
        "IC",
        "Sharpe",
        "Max Drawdown",
        "Correlation Redundancy",
        "Coverage",
        "Stability",
        "Data Quality",
        "Risk Contribution",
        "Incremental Value",
        "Operational Readiness",
    ]
    assert out["summary"]["recommended_scheme"] == "balanced"
    assert "correlation alerts: 1" in out["summary"]["key_findings"][0]
    assert len(out["g3_checklist"]) == 3
    assert out["g3_checklist"][0]["checked"] is False
