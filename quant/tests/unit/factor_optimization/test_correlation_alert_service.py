from application.factor_optimization.correlation_alert_service import build_correlation_alerts


def test_build_correlation_alerts_filters_by_threshold_and_marks_severity() -> None:
    correlation_matrix = {
        "momentum_20": {
            "momentum_20": 1.0,
            "max_drawdown_60": 0.82,
            "turnover_rate": 0.55,
        },
        "max_drawdown_60": {
            "momentum_20": 0.82,
            "max_drawdown_60": 1.0,
            "turnover_rate": 0.71,
        },
        "turnover_rate": {
            "momentum_20": 0.55,
            "max_drawdown_60": 0.71,
            "turnover_rate": 1.0,
        },
    }
    metrics = {
        "momentum_20": {"ic": 0.12, "sharpe": 1.6},
        "max_drawdown_60": {"ic": 0.09, "sharpe": 1.2},
        "turnover_rate": {"ic": 0.05, "sharpe": 0.9},
    }

    default_threshold = build_correlation_alerts(
        correlation_matrix=correlation_matrix,
        metrics=metrics,
    )

    assert default_threshold["threshold"] == 0.7
    assert default_threshold["alert_count"] == 2
    assert len(default_threshold["alerts"]) == 2
    assert default_threshold["alerts"][0]["severity"] == "high"
    assert {"factor_a", "factor_b", "correlation", "severity", "suggestion"} <= set(
        default_threshold["alerts"][0].keys()
    )
    assert "max_drawdown_60" in default_threshold["alerts"][0]["suggestion"]
    assert "turnover_rate" in default_threshold["alerts"][1]["suggestion"]

    strict_threshold = build_correlation_alerts(
        correlation_matrix=correlation_matrix,
        metrics=metrics,
        threshold=0.8,
    )

    assert strict_threshold["threshold"] == 0.8
    assert strict_threshold["alert_count"] == 1
    assert strict_threshold["alerts"][0]["severity"] == "high"
