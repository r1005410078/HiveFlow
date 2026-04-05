"""Unit tests for MA5/MA10 SMA cross (close)."""

from application.technical.ma_cross_service import (
    _cross_state_for_closes,
    build_ma_cross_technical,
)


def test_golden_cross_strictly_increasing_closes() -> None:
    # Last two days: SMA5 jumps above SMA10 from below-equal
    # Use 11 days: first 9 flat at 100, day 10 = 100, day 11 big jump so SMA5 > SMA10
    closes = [100.0] * 9 + [100.0, 120.0]
    out = _cross_state_for_closes(closes)
    assert out["available"] is True
    # t-1 window for SMA10: last 10 before last = days 1-10 all 100 -> SMA10=100
    # t: last 10 include 120 once -> need compute
    assert out["golden_cross"] is True
    assert out["death_cross"] is False


def test_no_cross_when_short_always_above() -> None:
    # Monotonic strong uptrend: SMA5 > SMA10 both days
    closes = [float(i) for i in range(11)]
    out = _cross_state_for_closes(closes)
    assert out["available"] is True
    assert out["golden_cross"] is False


def test_death_cross() -> None:
    # t-1: SMA5 == SMA10 == 20; last close 1 drags SMA5 below SMA10
    closes = [20.0] * 10 + [1.0]
    out = _cross_state_for_closes(closes)
    assert out["available"] is True
    assert out["death_cross"] is True
    assert out["golden_cross"] is False


def test_insufficient_bars() -> None:
    closes = [100.0] * 5
    out = _cross_state_for_closes(closes)
    assert out["available"] is False
    assert out["golden_cross"] is False
    assert out["death_cross"] is False
    assert out["sma5"] is None
    assert out["sma10"] is None


def test_build_ma_cross_technical_groups_symbols() -> None:
    rows = []
    sym = "600519.SH"
    for i in range(11):
        rows.append({
            "symbol": sym,
            "bar_time": f"2026-03-{(15+i):02d}T00:00:00",
            "close": 100.0 + i * 0.5,
        })
    payload = build_ma_cross_technical("2026-03-25", [sym, "000001.SZ"], rows)
    assert payload["schema_version"] == "1.0.0"
    assert payload["definition"] == "sma_close_5_10"
    assert sym in payload["by_symbol"]
    assert "000001.SZ" in payload["by_symbol"]
    assert payload["by_symbol"]["000001.SZ"]["available"] is False
