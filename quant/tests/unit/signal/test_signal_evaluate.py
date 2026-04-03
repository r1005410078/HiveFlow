import math


def test_ic_perfect_positive():
    """When signal order perfectly predicts return order, IC should be ~1.0."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 1.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": 2.0},
            {"symbol": "C", "factor_name": "f1", "signal_value": 3.0},
            {"symbol": "D", "factor_name": "f1", "signal_value": 4.0},
            {"symbol": "E", "factor_name": "f1", "signal_value": 5.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 1.0},
            {"symbol": "B", "composite_score": 2.0},
            {"symbol": "C", "composite_score": 3.0},
            {"symbol": "D", "composite_score": 4.0},
            {"symbol": "E", "composite_score": 5.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert abs(result["f1"] - 1.0) < 0.01
    assert abs(result["composite"] - 1.0) < 0.01


def test_ic_perfect_negative():
    """When signal order is perfectly opposite to return order, IC should be ~-1.0."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 5.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": 4.0},
            {"symbol": "C", "factor_name": "f1", "signal_value": 3.0},
            {"symbol": "D", "factor_name": "f1", "signal_value": 2.0},
            {"symbol": "E", "factor_name": "f1", "signal_value": 1.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 5.0},
            {"symbol": "B", "composite_score": 4.0},
            {"symbol": "C", "composite_score": 3.0},
            {"symbol": "D", "composite_score": 2.0},
            {"symbol": "E", "composite_score": 1.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert abs(result["f1"] - (-1.0)) < 0.01
    assert abs(result["composite"] - (-1.0)) < 0.01


def test_ic_insufficient_pairs():
    """IC should be NaN when < 3 valid pairs."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 1.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": 2.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 1.0},
            {"symbol": "B", "composite_score": 2.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert math.isnan(result["f1"])
    assert math.isnan(result["composite"])


def test_ic_nan_signal_excluded():
    """NaN signal values should be excluded from IC computation."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 1.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": float("nan")},
            {"symbol": "C", "factor_name": "f1", "signal_value": 3.0},
            {"symbol": "D", "factor_name": "f1", "signal_value": 4.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 1.0},
            {"symbol": "B", "composite_score": float("nan")},
            {"symbol": "C", "composite_score": 3.0},
            {"symbol": "D", "composite_score": 4.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert not math.isnan(result["f1"])


def test_ic_ir_calculation():
    """IC IR = mean_ic / ic_std."""
    from application.signal.signal_evaluate_service import _aggregate_ic_series

    daily_ics = [0.1, 0.2, 0.3, -0.1, 0.15]
    result = _aggregate_ic_series(daily_ics)
    expected_mean = sum(daily_ics) / len(daily_ics)
    assert abs(result["mean_ic"] - expected_mean) < 1e-6
    assert abs(result["ic_ir"] - result["mean_ic"] / result["ic_std"]) < 1e-6


def test_hit_rate():
    """hit_rate = count(IC > 0) / total."""
    from application.signal.signal_evaluate_service import _aggregate_ic_series

    daily_ics = [0.1, -0.05, 0.2, 0.0, -0.1]
    result = _aggregate_ic_series(daily_ics)
    assert abs(result["hit_rate"] - 0.4) < 1e-6  # 2 out of 5 are > 0


def test_drift_flag_triggered():
    """When recent data deviates significantly from baseline, drift_flag should be True."""
    from application.signal.signal_evaluate_service import _compute_factor_drift

    baseline_means = [0.04, 0.042, 0.038, 0.041, 0.039, 0.04, 0.041]
    recent_means = [0.08, 0.082, 0.079]
    result = _compute_factor_drift("momentum_20", baseline_means, recent_means)
    assert result["drift_flag"] is True
    assert abs(result["drift_z"]) > 2.0


def test_drift_no_flag():
    """Stable data should not trigger drift."""
    from application.signal.signal_evaluate_service import _compute_factor_drift

    baseline_means = [0.04, 0.042, 0.038, 0.041, 0.039, 0.04, 0.041]
    recent_means = [0.040, 0.041, 0.039]
    result = _compute_factor_drift("momentum_20", baseline_means, recent_means)
    assert result["drift_flag"] is False


def test_drift_baseline_std_zero():
    """When baseline std is 0, drift_z should be 0 and no flag."""
    from application.signal.signal_evaluate_service import _compute_factor_drift

    baseline_means = [0.04, 0.04, 0.04, 0.04, 0.04]
    recent_means = [0.08, 0.08, 0.08]
    result = _compute_factor_drift("momentum_20", baseline_means, recent_means)
    assert result["drift_z"] == 0.0
    assert result["drift_flag"] is False


def test_rank_turnover_identical():
    """Identical rankings should give turnover = 0."""
    from application.signal.signal_evaluate_service import _kendall_tau_distance

    assert _kendall_tau_distance(["A", "B", "C", "D", "E"], ["A", "B", "C", "D", "E"]) == 0.0


def test_rank_turnover_reversed():
    """Fully reversed rankings should give turnover = 1.0."""
    from application.signal.signal_evaluate_service import _kendall_tau_distance

    assert _kendall_tau_distance(["A", "B", "C", "D", "E"], ["E", "D", "C", "B", "A"]) == 1.0


def test_rank_turnover_partial():
    """Partial reversal should give 0 < turnover < 1."""
    from application.signal.signal_evaluate_service import _kendall_tau_distance

    d = _kendall_tau_distance(["A", "B", "C", "D", "E"], ["B", "A", "C", "D", "E"])
    assert 0 < d < 1.0
