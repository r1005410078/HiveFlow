from application.factor_optimization.combination_service import suggest_top_combinations


def test_suggest_top_combinations_enumerates_and_ranks() -> None:
    metrics = {
        "momentum_20": {"ic": 0.12, "sharpe": 1.7, "max_drawdown": 0.18},
        "inv_volatility_20": {"ic": 0.09, "sharpe": 1.4, "max_drawdown": 0.16},
        "turnover_rate": {"ic": 0.06, "sharpe": 1.1, "max_drawdown": 0.24},
        "max_drawdown_60": {"ic": 0.05, "sharpe": 0.8, "max_drawdown": 0.12},
        "trend_stability_20": {"ic": 0.07, "sharpe": 1.0, "max_drawdown": 0.15},
        "relative_strength_vs_index": {"ic": 0.1, "sharpe": 1.5, "max_drawdown": 0.2},
    }
    correlation_matrix = {
        "momentum_20": {
            "momentum_20": 1.0,
            "inv_volatility_20": 0.2,
            "turnover_rate": 0.32,
            "max_drawdown_60": 0.55,
            "trend_stability_20": 0.61,
            "relative_strength_vs_index": 0.88,
        },
        "inv_volatility_20": {
            "momentum_20": 0.2,
            "inv_volatility_20": 1.0,
            "turnover_rate": 0.31,
            "max_drawdown_60": 0.4,
            "trend_stability_20": 0.52,
            "relative_strength_vs_index": 0.45,
        },
        "turnover_rate": {
            "momentum_20": 0.32,
            "inv_volatility_20": 0.31,
            "turnover_rate": 1.0,
            "max_drawdown_60": 0.27,
            "trend_stability_20": 0.18,
            "relative_strength_vs_index": 0.35,
        },
        "max_drawdown_60": {
            "momentum_20": 0.55,
            "inv_volatility_20": 0.4,
            "turnover_rate": 0.27,
            "max_drawdown_60": 1.0,
            "trend_stability_20": 0.3,
            "relative_strength_vs_index": 0.43,
        },
        "trend_stability_20": {
            "momentum_20": 0.61,
            "inv_volatility_20": 0.52,
            "turnover_rate": 0.18,
            "max_drawdown_60": 0.3,
            "trend_stability_20": 1.0,
            "relative_strength_vs_index": 0.66,
        },
        "relative_strength_vs_index": {
            "momentum_20": 0.88,
            "inv_volatility_20": 0.45,
            "turnover_rate": 0.35,
            "max_drawdown_60": 0.43,
            "trend_stability_20": 0.66,
            "relative_strength_vs_index": 1.0,
        },
    }

    out = suggest_top_combinations(
        factor_names=list(metrics.keys()),
        metrics=metrics,
        correlation_matrix=correlation_matrix,
        correlation_threshold=0.7,
        combination_size_min=2,
        combination_size_max=4,
        top_k=5,
    )

    assert out["search_space"]["factor_pool_size"] == 6
    assert out["search_space"]["candidate_count"] == 50
    assert out["ranking_profile"] == "balanced_v1"
    assert len(out["items"]) == 5
    assert [item["rank"] for item in out["items"]] == [1, 2, 3, 4, 5]
    assert out["items"][0]["composite_score"] >= out["items"][-1]["composite_score"]
    assert "explanations" in out["items"][0]


def test_suggest_top_combinations_returns_empty_when_factor_pool_too_small() -> None:
    out = suggest_top_combinations(
        factor_names=["momentum_20"],
        metrics={"momentum_20": {"ic": 0.12, "sharpe": 1.4, "max_drawdown": 0.2}},
        correlation_matrix={"momentum_20": {"momentum_20": 1.0}},
        correlation_threshold=0.7,
        combination_size_min=2,
        combination_size_max=4,
        top_k=5,
    )
    assert out["search_space"]["candidate_count"] == 0
    assert out["items"] == []
