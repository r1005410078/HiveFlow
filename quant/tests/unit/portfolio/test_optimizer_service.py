from __future__ import annotations
import pandas as pd


def _cov_2x2(symbols: list[str], var: float = 0.04, corr: float = 0.3) -> pd.DataFrame:
    cov = pd.DataFrame(index=symbols, columns=symbols, dtype=float)
    for i, s in enumerate(symbols):
        for j, t in enumerate(symbols):
            cov.loc[s, t] = var if i == j else corr * var
    return cov


def test_weights_sum_to_one():
    """Target weights must sum to 1."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {s: float(i + 1) for i, s in enumerate(symbols)}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={})

    weights = [row["weight"] for row in result["target_weights"]]
    assert abs(sum(weights) - 1.0) < 1e-4


def test_single_asset_cap():
    """No individual weight may exceed w_max."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {"A": 10.0, "B": 0.1, "C": 0.1, "D": 0.1, "E": 0.1}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={}, w_max=0.30)

    for row in result["target_weights"]:
        assert row["weight"] <= 0.30 + 1e-4, f"{row['symbol']} weight {row['weight']} > 0.30"


def test_industry_constraint():
    """Sum of weights in one industry must not exceed ind_max."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C"]
    # A and B are in the same industry
    industry_map = {"A": "tech", "B": "tech", "C": "finance"}
    alpha = {"A": 5.0, "B": 4.0, "C": 1.0}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(
        alpha=alpha, cov_matrix=cov, prev_weights={},
        w_max=0.40, ind_max=0.60, industry_map=industry_map,
    )

    w = {row["symbol"]: row["weight"] for row in result["target_weights"]}
    assert w["A"] + w["B"] <= 0.60 + 1e-4


def test_fallback_equal_weight_when_infeasible():
    """When problem is infeasible and prev_weights are all zero, return equal weights."""
    from application.portfolio.optimizer_service import solve_portfolio

    # w_max=0.10 with 5 symbols: 5 * 0.10 = 0.50 < 1.0  →  infeasible
    symbols = ["A", "B", "C", "D", "E"]
    alpha = {s: 1.0 for s in symbols}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={}, w_max=0.10)

    assert result["optimization_status"] == "fallback_equal_weight"
    weights = [row["weight"] for row in result["target_weights"]]
    for w in weights:
        assert abs(w - 0.20) < 1e-6


def test_fallback_prev_weight_when_infeasible_with_prev():
    """When infeasible and prev_weights non-zero, return normalised prev weights."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {s: 1.0 for s in symbols}
    cov = _cov_2x2(symbols)
    prev = {"A": 0.3, "B": 0.3, "C": 0.2, "D": 0.1, "E": 0.1}
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights=prev, w_max=0.10)

    assert result["optimization_status"] == "fallback_prev_weight"
    w = {row["symbol"]: row["weight"] for row in result["target_weights"]}
    assert abs(w["A"] - 0.30) < 1e-6
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_no_short_selling():
    """All weights must be non-negative."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {"A": -5.0, "B": 0.1, "C": 0.1, "D": 0.1, "E": 0.1}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={})

    for row in result["target_weights"]:
        assert row["weight"] >= -1e-6
