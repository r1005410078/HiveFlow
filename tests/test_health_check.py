# tests/test_health_check.py
from datetime import datetime, timezone
from hiveflow.application.health_check import AlertLevel, HealthCheckResult, run_health_check
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position


def _pos(symbol: str, weight: float) -> Position:
    return Position(symbol=symbol, quantity=1.0, market_value=weight * 10000, weight=weight)


def _bars(symbol: str, closes: list[float]) -> list[MarketBar]:
    return [
        MarketBar(symbol=symbol, timestamp=datetime(2026, 3, i+1, tzinfo=timezone.utc),
                  open=c, high=c, low=c, close=c, volume=1000.0)
        for i, c in enumerate(closes)
    ]


def test_all_normal_safe_verdict() -> None:
    result = run_health_check(
        positions=[_pos("BTC", 1.0)],
        bars_by_symbol={"BTC": _bars("BTC", [100, 102, 101, 103, 104, 105, 106])},
    )
    assert result.verdict == "safe"
    assert result.signals[0].alert_level == AlertLevel.NORMAL


def test_drawdown_warning_triggers_watch() -> None:
    result = run_health_check(
        positions=[_pos("ETH", 1.0)],
        bars_by_symbol={"ETH": _bars("ETH", [100, 95, 90, 85, 87, 88, 89])},
    )
    assert result.verdict == "watch"
    assert result.signals[0].alert_level == AlertLevel.WARNING


def test_severe_drawdown_triggers_danger() -> None:
    result = run_health_check(
        positions=[_pos("SOL", 1.0)],
        bars_by_symbol={"SOL": _bars("SOL", [100, 80, 75, 72, 70, 69, 68])},
    )
    assert result.verdict == "danger"
    assert result.signals[0].alert_level == AlertLevel.DANGER


def test_no_bars_skips_risk_layer() -> None:
    result = run_health_check(positions=[_pos("BTC", 1.0)], bars_by_symbol={})
    assert result.signals == []
    assert result.has_no_history is True
    assert result.verdict == "safe"


def test_mixed_levels_worst_wins() -> None:
    result = run_health_check(
        positions=[_pos("BTC", 0.5), _pos("ETH", 0.5)],
        bars_by_symbol={
            "BTC": _bars("BTC", [100, 102, 101, 103, 104, 105, 106]),
            "ETH": _bars("ETH", [100, 80, 75, 72, 70, 69, 68]),
        },
    )
    assert result.verdict == "danger"


def test_tiny_positions_are_ignored() -> None:
    tiny_btc = Position(symbol="BTC", quantity=0.000001, market_value=0.009, weight=0.000001)
    result = run_health_check(
        positions=[tiny_btc, _pos("ETH", 1.0)],
        bars_by_symbol={
            "BTC": _bars("BTC", [100, 80, 75, 72, 70, 69, 68]),
            "ETH": _bars("ETH", [100, 102, 101, 103, 104, 105, 106]),
        },
    )
    assert [signal.symbol for signal in result.signals] == ["ETH"]
    assert result.verdict == "safe"
