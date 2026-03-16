# tests/test_drawdown.py
from datetime import datetime, timezone
from hiveflow.domain.market_data import MarketBar
from hiveflow.services.risk_engine import calculate_max_drawdown


def _bar(day: int, close: float) -> MarketBar:
    return MarketBar(
        symbol="BTC", timestamp=datetime(2026, 3, day, tzinfo=timezone.utc),
        open=close, high=close, low=close, close=close, volume=1000.0,
    )


def test_monotone_up_zero_drawdown() -> None:
    bars = [_bar(i, float(i * 1000)) for i in range(1, 8)]
    assert calculate_max_drawdown(bars) == 0.0


def test_simple_drop() -> None:
    result = calculate_max_drawdown([_bar(1, 100.0), _bar(2, 90.0), _bar(3, 80.0)])
    assert abs(result - (-0.20)) < 0.001


def test_recovery_keeps_max() -> None:
    result = calculate_max_drawdown([_bar(1, 100.0), _bar(2, 60.0), _bar(3, 90.0)])
    assert abs(result - (-0.40)) < 0.001


def test_empty_returns_zero() -> None:
    assert calculate_max_drawdown([]) == 0.0


def test_single_bar_returns_zero() -> None:
    assert calculate_max_drawdown([_bar(1, 100.0)]) == 0.0
