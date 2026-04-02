from application.factor_optimization.recommendation_service import suggest_weight_schemes


def test_suggest_weight_schemes_honors_constraints_and_returns_ranked_options() -> None:
    metrics = {
        "momentum_20": {"ic": 0.12, "sharpe": 1.5},
        "inv_volatility_20": {"ic": 0.09, "sharpe": 1.3},
        "turnover_rate": {"ic": 0.05, "sharpe": 0.9},
        "max_drawdown_60": {"ic": 0.11, "sharpe": 1.6},
    }

    schemes = suggest_weight_schemes(
        metrics=metrics,
        correlation_pairs={("momentum_20", "max_drawdown_60"): 0.72},
        constraints={"max_weight:max_drawdown_60": 0.30},
    )

    assert len(schemes) == 3
    assert schemes[0]["name"] == "balanced"
    assert schemes[0]["weights"]["max_drawdown_60"] <= 0.30
