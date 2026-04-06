"""Unit tests for walk_forward_service."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from application.walk_forward_service import (
    generate_windows,
    _coerce_finite_float,
    _compute_daily_return,
    _build_window_metrics,
    _aggregate_windows,
    _gate_check,
    run_walk_forward,
)


class TestGenerateWindows:
    """Test window generation logic."""

    def test_generate_windows_basic(self) -> None:
        """Test basic window generation."""
        windows = generate_windows(
            start_date="2025-01-01",
            end_date="2025-09-30",
            warm_up_days=180,
            test_window_days=63,
            step_days=21,
        )
        assert len(windows) >= 1
        # First window should start from start_date
        assert windows[0]["warm_start"] == "2025-01-01"
        # First test window should be 180 days after start
        assert "test_start" in windows[0]
        assert "test_end" in windows[0]
        assert "warm_end" in windows[0]

    def test_generate_windows_order(self) -> None:
        """Windows should be time-ordered with no overlaps."""
        windows = generate_windows(
            start_date="2025-01-01",
            end_date="2026-12-31",
            warm_up_days=180,
            test_window_days=63,
            step_days=21,
        )
        # Should have multiple windows
        assert len(windows) >= 2

        for i, w in enumerate(windows):
            # Each window must have valid dates
            warm_start = date.fromisoformat(w["warm_start"])
            warm_end = date.fromisoformat(w["warm_end"])
            test_start = date.fromisoformat(w["test_start"])
            test_end = date.fromisoformat(w["test_end"])

            assert warm_start <= warm_end
            assert warm_end < test_start
            assert test_start <= test_end

            # Warm-up should be ~180 days (unless truncated)
            warm_days = (warm_end - warm_start).days
            assert warm_days > 0

            # Test window must have at least 1 day
            test_days = (test_end - test_start).days
            assert test_days >= 0

            if i > 0:
                # Next window should start after or at previous warm_start
                assert w["warm_start"] >= windows[i-1]["warm_start"]

    def test_generate_windows_invalid_dates(self) -> None:
        """Should raise ValueError if start > end."""
        with pytest.raises(ValueError):
            generate_windows(
                start_date="2025-12-31",
                end_date="2025-01-01",
                warm_up_days=180,
                test_window_days=63,
                step_days=21,
            )

    def test_generate_windows_short_period(self) -> None:
        """Test with period shorter than warm-up."""
        windows = generate_windows(
            start_date="2025-01-01",
            end_date="2025-03-31",
            warm_up_days=180,
            test_window_days=63,
            step_days=21,
        )
        # Should return empty or 0 windows
        assert len(windows) == 0


class TestCoerceFiniteFloat:
    """Test float coercion helper."""

    def test_coerce_valid_float(self) -> None:
        """Should return float for valid inputs."""
        assert _coerce_finite_float(1.5) == 1.5
        assert _coerce_finite_float(0) == 0.0
        assert _coerce_finite_float(-0.5) == -0.5

    def test_coerce_nan(self) -> None:
        """Should return None for NaN."""
        import math
        assert _coerce_finite_float(math.nan) is None

    def test_coerce_inf(self) -> None:
        """Should return None for infinity."""
        import math
        assert _coerce_finite_float(math.inf) is None
        assert _coerce_finite_float(-math.inf) is None

    def test_coerce_none(self) -> None:
        """Should return None for None."""
        assert _coerce_finite_float(None) is None


class TestComputeDailyReturn:
    """Test daily return calculation."""

    def test_compute_daily_return_basic(self, monkeypatch) -> None:
        """Test basic daily return calculation."""
        weights = {"600519.SH": 1.0}
        as_of = "2026-04-01"

        # Mock bar_store
        bar_store = MagicMock()
        bar_store.list_bars.return_value = [
            {"symbol": "600519.SH", "date": "2026-04-01", "close": 100.0},
            {"symbol": "600519.SH", "date": "2026-04-02", "close": 101.0},
        ]

        result = _compute_daily_return(
            weights=weights,
            as_of=as_of,
            bar_store=bar_store,
            cost_bp=0.0,
        )

        # Return should be (101 - 100) / 100 = 0.01 = 1%
        assert result is not None
        assert abs(result - 0.01) < 1e-6

    def test_compute_daily_return_with_cost(self) -> None:
        """Test return calculation with transaction cost."""
        weights = {"600519.SH": 1.0}
        as_of = "2026-04-01"

        bar_store = MagicMock()
        bar_store.list_bars.return_value = [
            {"symbol": "600519.SH", "date": "2026-04-01", "close": 100.0},
            {"symbol": "600519.SH", "date": "2026-04-02", "close": 101.0},
        ]

        # Gross return is 1%, cost is 10 bp = 0.001 = 0.1%
        result = _compute_daily_return(
            weights=weights,
            as_of=as_of,
            bar_store=bar_store,
            cost_bp=10.0,
        )

        # Net return = 0.01 - 0.001 = 0.009
        assert result is not None
        assert abs(result - 0.009) < 1e-6

    def test_compute_daily_return_missing_next_day_bar(self) -> None:
        """Should return None if next day bar missing."""
        weights = {"600519.SH": 1.0}
        as_of = "2026-04-01"

        bar_store = MagicMock()
        # Only today's bar, no tomorrow
        bar_store.list_bars.return_value = [
            {"symbol": "600519.SH", "date": "2026-04-01", "close": 100.0},
        ]

        result = _compute_daily_return(
            weights=weights,
            as_of=as_of,
            bar_store=bar_store,
            cost_bp=0.0,
        )

        assert result is None

    def test_compute_daily_return_zero_weight(self) -> None:
        """Test with zero weight (no position)."""
        weights = {}
        as_of = "2026-04-01"

        bar_store = MagicMock()
        bar_store.list_bars.return_value = []

        result = _compute_daily_return(
            weights=weights,
            as_of=as_of,
            bar_store=bar_store,
            cost_bp=0.0,
        )

        # No position, so only cost deduction (if any)
        # Cost still applies even with no position
        assert result == -0.0  # -0 bp

    def test_compute_daily_return_multiple_assets(self) -> None:
        """Test with multiple assets."""
        weights = {"600519.SH": 0.6, "000333.SZ": 0.4}
        as_of = "2026-04-01"

        bar_store = MagicMock()
        bar_store.list_bars.return_value = [
            # Today
            {"symbol": "600519.SH", "date": "2026-04-01", "close": 100.0},
            {"symbol": "000333.SZ", "date": "2026-04-01", "close": 50.0},
            # Tomorrow
            {"symbol": "600519.SH", "date": "2026-04-02", "close": 101.0},
            {"symbol": "000333.SZ", "date": "2026-04-02", "close": 51.0},
        ]

        result = _compute_daily_return(
            weights=weights,
            as_of=as_of,
            bar_store=bar_store,
            cost_bp=0.0,
        )

        # 600519 return: 1%, 000333 return: 2%
        # Weighted: 0.6 * 0.01 + 0.4 * 0.02 = 0.006 + 0.008 = 0.014
        assert result is not None
        assert abs(result - 0.014) < 1e-6


class TestBuildWindowMetrics:
    """Test window metrics calculation."""

    def test_build_window_metrics_positive_returns(self) -> None:
        """Test metrics with all positive returns."""
        daily_returns = [0.01, 0.02, 0.015, 0.01]

        metrics = _build_window_metrics(daily_returns)

        assert "cumulative_return" in metrics
        assert "annualized_return" in metrics
        assert "sharpe" in metrics
        assert "max_drawdown" in metrics
        assert "win_rate" in metrics

        # Win rate should be 1.0 (all 4 positive days)
        assert metrics["win_rate"] == 1.0

        # Cumulative return: (1.01 * 1.02 * 1.015 * 1.01) - 1 ≈ 0.0557
        assert metrics["cumulative_return"] > 0

        # MDD should be 0 (no drawdown in positive sequence)
        assert metrics["max_drawdown"] == 0.0

    def test_build_window_metrics_mixed_returns(self) -> None:
        """Test metrics with mixed positive and negative returns."""
        daily_returns = [0.01, -0.02, 0.015, 0.01, -0.005]

        metrics = _build_window_metrics(daily_returns)

        # Win rate: 3 out of 5 positive = 0.6
        assert metrics["win_rate"] == 0.6

        # MDD > 0 due to negative days
        assert metrics["max_drawdown"] >= 0

    def test_build_window_metrics_negative_returns(self) -> None:
        """Test metrics with all negative returns."""
        daily_returns = [-0.01, -0.02, -0.015]

        metrics = _build_window_metrics(daily_returns)

        # Win rate should be 0
        assert metrics["win_rate"] == 0.0

        # Cumulative return should be negative
        assert metrics["cumulative_return"] < 0

    def test_build_window_metrics_single_day(self) -> None:
        """Test with single day return."""
        daily_returns = [0.02]

        metrics = _build_window_metrics(daily_returns)

        assert abs(metrics["cumulative_return"] - 0.02) < 1e-6
        assert metrics["win_rate"] == 1.0


class TestAggregateWindows:
    """Test window aggregation."""

    def test_aggregate_windows_basic(self) -> None:
        """Test basic aggregation of window results."""
        windows = [
            {
                "annualized_return": 0.20,
                "sharpe": 1.0,
                "max_drawdown": 0.10,
            },
            {
                "annualized_return": 0.30,
                "sharpe": 1.5,
                "max_drawdown": 0.15,
            },
        ]

        agg = _aggregate_windows(windows)

        assert agg["window_count"] == 2
        assert agg["annualized_return"]["mean"] == 0.25
        assert agg["annualized_return"]["min"] == 0.20
        assert agg["annualized_return"]["max"] == 0.30
        assert agg["sharpe"]["mean"] == 1.25
        assert agg["max_drawdown"]["mean"] == 0.125

    def test_aggregate_windows_single(self) -> None:
        """Test aggregation with single window."""
        windows = [
            {
                "annualized_return": 0.15,
                "sharpe": 0.8,
                "max_drawdown": 0.08,
            },
        ]

        agg = _aggregate_windows(windows)

        assert agg["window_count"] == 1
        assert agg["annualized_return"]["mean"] == 0.15
        assert agg["annualized_return"]["min"] == 0.15
        assert agg["annualized_return"]["max"] == 0.15


class TestGateCheck:
    """Test gate check logic."""

    def test_gate_pass(self) -> None:
        """Test when all gates pass."""
        aggregate = {
            "window_count": 2,
            "annualized_return": {"mean": 0.10, "min": 0.08, "max": 0.12},
            "sharpe": {"mean": 1.0, "min": 0.8, "max": 1.2},
            "max_drawdown": {"mean": 0.10, "min": 0.08, "max": 0.12},
        }
        thresholds = {
            "annualized_return_mean_min": 0.06,
            "max_drawdown_max_max": 0.20,
            "sharpe_min_min": 0.5,
        }

        result = _gate_check(aggregate, thresholds)

        assert result["verdict"] == "pass"
        assert result["failed_gates"] == []

    def test_gate_fail_annualized_return(self) -> None:
        """Test when annualized return is below threshold."""
        aggregate = {
            "window_count": 2,
            "annualized_return": {"mean": 0.04, "min": 0.02, "max": 0.06},
            "sharpe": {"mean": 1.0, "min": 0.8, "max": 1.2},
            "max_drawdown": {"mean": 0.10, "min": 0.08, "max": 0.12},
        }
        thresholds = {
            "annualized_return_mean_min": 0.06,
            "max_drawdown_max_max": 0.20,
            "sharpe_min_min": 0.5,
        }

        result = _gate_check(aggregate, thresholds)

        assert result["verdict"] == "no_go"
        assert "annualized_return_mean_min" in result["failed_gates"]

    def test_gate_fail_max_drawdown(self) -> None:
        """Test when max drawdown is above threshold."""
        aggregate = {
            "window_count": 2,
            "annualized_return": {"mean": 0.10, "min": 0.08, "max": 0.12},
            "sharpe": {"mean": 1.0, "min": 0.8, "max": 1.2},
            "max_drawdown": {"mean": 0.15, "min": 0.12, "max": 0.25},
        }
        thresholds = {
            "annualized_return_mean_min": 0.06,
            "max_drawdown_max_max": 0.20,
            "sharpe_min_min": 0.5,
        }

        result = _gate_check(aggregate, thresholds)

        assert result["verdict"] == "no_go"
        assert "max_drawdown_max_max" in result["failed_gates"]

    def test_gate_fail_sharpe(self) -> None:
        """Test when min sharpe is below threshold."""
        aggregate = {
            "window_count": 2,
            "annualized_return": {"mean": 0.10, "min": 0.08, "max": 0.12},
            "sharpe": {"mean": 0.6, "min": 0.4, "max": 0.8},
            "max_drawdown": {"mean": 0.10, "min": 0.08, "max": 0.12},
        }
        thresholds = {
            "annualized_return_mean_min": 0.06,
            "max_drawdown_max_max": 0.20,
            "sharpe_min_min": 0.5,
        }

        result = _gate_check(aggregate, thresholds)

        assert result["verdict"] == "no_go"
        assert "sharpe_min_min" in result["failed_gates"]

    def test_gate_fail_multiple(self) -> None:
        """Test when multiple gates fail."""
        aggregate = {
            "window_count": 2,
            "annualized_return": {"mean": 0.04, "min": 0.02, "max": 0.06},
            "sharpe": {"mean": 0.4, "min": 0.2, "max": 0.6},
            "max_drawdown": {"mean": 0.15, "min": 0.12, "max": 0.25},
        }
        thresholds = {
            "annualized_return_mean_min": 0.06,
            "max_drawdown_max_max": 0.20,
            "sharpe_min_min": 0.5,
        }

        result = _gate_check(aggregate, thresholds)

        assert result["verdict"] == "no_go"
        assert len(result["failed_gates"]) >= 2


class TestRunWalkForward:
    """Integration tests for run_walk_forward."""

    def test_run_walk_forward_minimal(self, monkeypatch) -> None:
        """Test minimal walk-forward run with mocked dependencies."""
        # Mock run_daily to return fixed portfolio
        def mock_run_daily(as_of, root, bar_store=None, **kwargs):
            return {
                "data": {
                    "portfolio": {
                        "target_weights": [
                            {"symbol": "600519.SH", "weight": 1.0}
                        ]
                    }
                }
            }

        monkeypatch.setattr(
            "application.walk_forward_service.run_daily",
            mock_run_daily,
        )

        # Mock bar_store
        bar_store = MagicMock()
        bar_store.list_bars.return_value = [
            {"symbol": "600519.SH", "date": "2025-07-30", "close": 100.0},
            {"symbol": "600519.SH", "date": "2025-07-31", "close": 101.0},
        ]

        result = run_walk_forward(
            start_date="2025-01-01",
            end_date="2025-08-31",
            warm_up_days=180,
            test_window_days=30,
            step_days=30,
            cost_bp=0.0,
            bar_store=bar_store,
        )

        assert "verdict" in result
        assert "windows" in result
        assert "aggregate" in result
        assert len(result["windows"]) >= 1

    def test_run_walk_forward_invalid_dates(self) -> None:
        """Test with invalid date range."""
        with pytest.raises(ValueError):
            run_walk_forward(
                start_date="2025-12-31",
                end_date="2025-01-01",
                warm_up_days=180,
                test_window_days=63,
                step_days=21,
                bar_store=None,
            )
