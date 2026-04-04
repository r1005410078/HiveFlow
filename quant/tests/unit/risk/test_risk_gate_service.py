from __future__ import annotations

import math
import numpy as np


_SYMBOLS = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"]
_BENCHMARK = "000300.SH"

# ── bar_store helpers ───────────────────────────────────────────────────────

def _make_bar_store(symbol_returns: dict[str, list[float]], base_price: float = 100.0):
    """Build a mock bar_store whose list_bars returns synthetic daily bars.
    symbol_returns: {symbol: [r1, r2, ...]}  (daily returns, e.g. 0.01 = +1%)
    Generates len(returns)+1 bars so pct_change().dropna() has len(returns) rows.
    """
    rows = []
    for sym, rets in symbol_returns.items():
        price = base_price
        prices = [price]
        for r in rets:
            price = price * (1 + r)
            prices.append(price)
        for i, p in enumerate(prices):
            rows.append({
                "symbol": sym,
                "bar_time": f"2026-01-{i+1:02d}T15:00:00+08:00",
                "close": p,
            })

    class _MockBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return [r for r in rows if r["symbol"] in symbols]

    return _MockBarStore()


def _low_vol_returns(n: int = 29) -> list[float]:
    """Returns that produce ~5% annual vol — well below normal threshold 0.25."""
    # Alternating +/- to get non-zero std: daily vol ~0.003, annual ~0.003*sqrt(252)~0.048
    return [0.003 if i % 2 == 0 else -0.003 for i in range(n)]


def _mid_vol_returns(n: int = 29) -> list[float]:
    """Returns that produce ~27% annual vol — in warning range [0.25, 0.40)."""
    # daily std ~0.017, annual ~0.017*sqrt(252)~0.270
    return [0.017 if i % 2 == 0 else -0.017 for i in range(n)]


def _high_vol_returns(n: int = 29) -> list[float]:
    """Returns that produce ~44% annual vol — in crisis range >=0.40."""
    # daily std ~0.028, annual ~0.028*sqrt(252)~0.444
    return [0.028 if i % 2 == 0 else -0.028 for i in range(n)]


def _equal_weights() -> dict[str, float]:
    return {s: 0.20 for s in _SYMBOLS}


# ── regime tests ────────────────────────────────────────────────────────────

def test_regime_normal_when_low_vol():
    from application.risk.risk_gate_service import run_risk_check

    bar_store = _make_bar_store({_BENCHMARK: _low_vol_returns()})
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime"] == "normal"
    assert result["data"]["regime_vol_source"] == "benchmark"


def test_regime_warning_when_mid_vol():
    from application.risk.risk_gate_service import run_risk_check

    bar_store = _make_bar_store({_BENCHMARK: _mid_vol_returns()})
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime"] == "warning"
    assert result["data"]["regime_vol_source"] == "benchmark"


def test_regime_crisis_when_high_vol():
    from application.risk.risk_gate_service import run_risk_check

    bar_store = _make_bar_store({_BENCHMARK: _high_vol_returns()})
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime"] == "crisis"
    assert result["data"]["regime_vol_source"] == "benchmark"


def test_regime_fallback_to_equal_weight():
    """000300.SH has < 20 returns → fall back to equal-weight portfolio."""
    from application.risk.risk_gate_service import run_risk_check

    # Only 5 bars for benchmark → 4 returns, below threshold of 20
    bar_store = _make_bar_store({
        _BENCHMARK: [0.03] * 4,
        **{s: _low_vol_returns() for s in _SYMBOLS},
    })
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime_vol_source"] == "equal_weight"


def test_regime_defaults_normal_when_no_data():
    """bar_store=None → regime=normal, no exception."""
    from application.risk.risk_gate_service import run_risk_check

    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights=None,
        bar_store=None,
    )
    assert result["data"]["regime"] == "normal"
    assert result["data"]["regime_vol_source"] == "none"
    assert result["data"]["regime_vol"] is None


# ── check tests ─────────────────────────────────────────────────────────────

def test_p1_portfolio_vol_block():
    """σ_p > normal threshold (0.30) → block + PORTFOLIO_VOL_EXCEEDED."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {s: 0.20 for s in symbols}
    # var=0.49 diagonal → σ_p = sqrt(5 * 0.04 * 0.49) = sqrt(0.098) ≈ 0.313 > 0.30 → BLOCK in normal
    n = len(symbols)
    Sigma = pd.DataFrame(0.49 * np.eye(n), index=symbols, columns=symbols)
    checks, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    assert any(c["name"] == "portfolio_vol" and not c["passed"] for c in checks)
    assert "PORTFOLIO_VOL_EXCEEDED" in block_codes


def test_p2_single_asset_block():
    """max weight > 0.35 (normal) → SINGLE_ASSET_CONCENTRATION."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {"000001.SZ": 0.40, "600519.SH": 0.20, "300750.SZ": 0.15, "601318.SH": 0.15, "000333.SZ": 0.10}
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    _, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    assert "SINGLE_ASSET_CONCENTRATION" in block_codes


def test_p3_industry_block():
    """industry sum > 0.45 (normal) → INDUSTRY_CONCENTRATION."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    # Give banking (000001.SZ) 0.50 of portfolio
    symbols = _SYMBOLS
    w = {"000001.SZ": 0.50, "600519.SH": 0.20, "300750.SZ": 0.15, "601318.SH": 0.10, "000333.SZ": 0.05}
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    _, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    assert "INDUSTRY_CONCENTRATION" in block_codes


def test_p4_turnover_block():
    """turnover > 0.80 (normal) → TURNOVER_EXCEEDED."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w_new = {s: 0.20 for s in symbols}
    # prev weights completely different → turnover = sum(|0.20 - prev|)
    w_prev = {"000001.SZ": 0.65, "600519.SH": 0.10, "300750.SZ": 0.10, "601318.SH": 0.10, "000333.SZ": 0.05}
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    _, block_codes = _run_checks(w_new, Sigma, prev_weights=w_prev, regime="normal")

    assert "TURNOVER_EXCEEDED" in block_codes


def test_all_checks_run_even_when_blocked():
    """Multiple failures → block_codes contains all of them."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    # High single-asset concentration AND high turnover
    w_new = {"000001.SZ": 0.50, "600519.SH": 0.20, "300750.SZ": 0.15, "601318.SH": 0.10, "000333.SZ": 0.05}
    w_prev = {s: 0.0 for s in symbols}  # turnover = 1.0 > 0.80
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    checks, block_codes = _run_checks(w_new, Sigma, prev_weights=w_prev, regime="normal")

    assert len(block_codes) >= 2
    assert "SINGLE_ASSET_CONCENTRATION" in block_codes
    assert "TURNOVER_EXCEEDED" in block_codes
    # All 4 checks must be present regardless
    check_names = {c["name"] for c in checks}
    assert check_names == {"portfolio_vol", "single_asset_max", "industry_max", "turnover"}


def test_pass_returns_ok_status():
    """All checks pass → risk_gate=pass, status=ok."""
    from application.risk.risk_gate_service import run_risk_check

    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),  # 0.20 each — well within all thresholds
        prev_weights=_equal_weights(),    # same as new → turnover = 0
        bar_store=None,
    )
    assert result["data"]["risk_gate"] == "pass"
    assert result["status"] == "ok"
    assert result["data"]["block_codes"] == []


def test_prev_weights_empty_means_full_turnover():
    """prev_weights={} → all prev values are 0 → turnover = sum(w_new) = 1.0."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {s: 0.20 for s in symbols}
    Sigma = pd.DataFrame(0.04 * np.eye(len(symbols)), index=symbols, columns=symbols)
    checks, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    turnover_check = next(c for c in checks if c["name"] == "turnover")
    assert abs(turnover_check["value"] - 1.0) < 1e-6
    assert "TURNOVER_EXCEEDED" in block_codes  # 1.0 > 0.80


def test_crisis_tightens_thresholds():
    """Equal weights (0.20 each) pass portfolio_vol in normal but block in crisis
    when diagonal var=0.15 → σ_p = sqrt(5 * 0.04 * 0.15) = sqrt(0.03) ≈ 0.173 > 0.15 crisis threshold."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {s: 0.20 for s in symbols}
    Sigma = pd.DataFrame(0.15 * np.eye(len(symbols)), index=symbols, columns=symbols)
    _, block_normal = _run_checks(w, Sigma, prev_weights=w, regime="normal")
    _, block_crisis = _run_checks(w, Sigma, prev_weights=w, regime="crisis")

    assert "PORTFOLIO_VOL_EXCEEDED" not in block_normal
    assert "PORTFOLIO_VOL_EXCEEDED" in block_crisis
