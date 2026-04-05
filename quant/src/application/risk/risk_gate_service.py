from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import uuid4

import numpy as np
import pandas as pd

from application.contracts.cli_output import ok_output
from application.portfolio.covariance_service import compute_covariance_matrix
from domain.universe.universe_loader import load_industry_map

_logger = logging.getLogger(__name__)

_BENCHMARK_SYMBOL = "000300.SH"
_DEFAULT_SYMBOLS = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"]
_MIN_REGIME_RETURNS = 20
_REGIME_LOOKBACK_BARS = 31  # fetch 31 bars → 30 returns, take tail(20)

_INDUSTRY_MAP: dict[str, str] = load_industry_map()

_THRESHOLDS: dict[str, dict[str, float]] = {
    "normal":  {"portfolio_vol": 0.30, "single_asset_max": 0.35, "industry_max": 0.45, "turnover": 0.80},
    "warning": {"portfolio_vol": 0.22, "single_asset_max": 0.28, "industry_max": 0.38, "turnover": 0.55},
    "crisis":  {"portfolio_vol": 0.15, "single_asset_max": 0.20, "industry_max": 0.30, "turnover": 0.30},
}

_BLOCK_CODES: dict[str, str] = {
    "portfolio_vol":    "PORTFOLIO_VOL_EXCEEDED",
    "single_asset_max": "SINGLE_ASSET_CONCENTRATION",
    "industry_max":     "INDUSTRY_CONCENTRATION",
    "turnover":         "TURNOVER_EXCEEDED",
}


def _compute_regime_vol_from_bars(
    symbols: list[str],
    as_of: str,
    bar_store,
) -> tuple[float | None, str]:
    """Try benchmark first, fall back to equal-weight. Returns (vol, source)."""
    start_date = (date.fromisoformat(as_of) - timedelta(days=60)).isoformat()

    # Priority 1: benchmark
    try:
        rows = bar_store.list_bars(
            symbols=[_BENCHMARK_SYMBOL],
            timeframe="1d",
            start_date=start_date,
            end_date=as_of,
            limit=_REGIME_LOOKBACK_BARS,
        )
        if rows:
            df = pd.DataFrame(rows)
            df["_date"] = pd.to_datetime(df["bar_time"]).dt.date
            pivot = (
                df.pivot_table(index="_date", columns="symbol", values="close", aggfunc="last")
                .sort_index()
            )
            if _BENCHMARK_SYMBOL in pivot.columns:
                prices = pivot[_BENCHMARK_SYMBOL]
                rets = prices.pct_change().dropna().tail(_MIN_REGIME_RETURNS)
                if len(rets) >= _MIN_REGIME_RETURNS:
                    vol = float(rets.std() * np.sqrt(252))
                    return vol, "benchmark"
    except Exception:
        _logger.debug("regime: benchmark fetch failed", exc_info=True)

    # Priority 2: equal-weight portfolio of default symbols
    try:
        rows = bar_store.list_bars(
            symbols=symbols,
            timeframe="1d",
            start_date=start_date,
            end_date=as_of,
            limit=_REGIME_LOOKBACK_BARS * len(symbols),
        )
        if rows:
            df = pd.DataFrame(rows)
            df["_date"] = pd.to_datetime(df["bar_time"]).dt.date
            pivot = (
                df.pivot_table(index="_date", columns="symbol", values="close", aggfunc="last")
                .sort_index()
            )
            eq_portfolio = pivot.mean(axis=1)
            rets = eq_portfolio.pct_change().dropna().tail(_MIN_REGIME_RETURNS)
            if len(rets) >= _MIN_REGIME_RETURNS:
                vol = float(rets.std() * np.sqrt(252))
                return vol, "equal_weight"
    except Exception:
        _logger.debug("regime: equal-weight fetch failed", exc_info=True)

    return None, "none"


def _detect_regime(bar_store, as_of: str) -> tuple[str, float | None, str]:
    """Return (regime, regime_vol, regime_vol_source)."""
    if bar_store is None:
        return "normal", None, "none"

    vol, source = _compute_regime_vol_from_bars(_DEFAULT_SYMBOLS, as_of, bar_store)
    if vol is None:
        return "normal", None, "none"

    if vol >= 0.40:
        regime = "crisis"
    elif vol >= 0.25:
        regime = "warning"
    else:
        regime = "normal"

    return regime, vol, source


def _run_checks(
    target_weights: dict[str, float],
    cov_matrix: pd.DataFrame,
    prev_weights: dict[str, float],
    regime: str,
) -> tuple[list[dict], list[str]]:
    """Run all 4 checks. Returns (checks_list, block_codes_list)."""
    thresholds = _THRESHOLDS[regime]
    symbols = list(target_weights.keys())
    w_vec = np.array([target_weights[s] for s in symbols], dtype=float)
    Sigma = cov_matrix.reindex(index=symbols, columns=symbols).fillna(0.0).values.astype(float)

    # P1: portfolio vol (Sigma already annualised)
    sigma_p = float(np.sqrt(w_vec @ Sigma @ w_vec))

    # P2: single asset max
    single_max = float(max(w_vec))

    # P3: industry max
    industry_groups: dict[str, list[int]] = {}
    for i, s in enumerate(symbols):
        ind = _INDUSTRY_MAP.get(s, "other")
        industry_groups.setdefault(ind, []).append(i)
    industry_max = max(
        float(sum(w_vec[i] for i in idxs)) for idxs in industry_groups.values()
    )

    # P4: turnover
    prev_w = prev_weights or {}
    turnover = float(sum(abs(target_weights.get(s, 0.0) - prev_w.get(s, 0.0)) for s in symbols))

    values = {
        "portfolio_vol":    sigma_p,
        "single_asset_max": single_max,
        "industry_max":     industry_max,
        "turnover":         turnover,
    }

    checks: list[dict] = []
    block_codes: list[str] = []
    for name, value in values.items():
        threshold = thresholds[name]
        passed = value <= threshold
        checks.append({"name": name, "value": round(value, 6), "threshold": threshold, "passed": passed})
        if not passed:
            block_codes.append(_BLOCK_CODES[name])

    return checks, block_codes


def run_risk_check(
    as_of: str,
    target_weights: dict[str, float],
    prev_weights: dict[str, float] | None = None,
    bar_store=None,
) -> dict:
    """L5 risk gate check. Returns standard CLI envelope.

    risk_gate: "pass" | "block"
    status: "ok" (pass) | "warning" (block)
    """
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"

    # Step 1: detect regime
    regime, regime_vol, regime_vol_source = _detect_regime(bar_store, as_of)

    # Step 2: covariance matrix for sigma_p
    symbols = list(target_weights.keys())
    cov_matrix: pd.DataFrame | None = None
    if bar_store is not None and symbols:
        try:
            cov_matrix = compute_covariance_matrix(
                symbols=symbols, as_of=as_of, bar_store=bar_store
            )
        except Exception:
            _logger.warning("risk gate: covariance computation failed, using diagonal", exc_info=True)

    if cov_matrix is None:
        n = len(symbols)
        cov_matrix = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)

    # Step 3: run all 4 checks
    prev_w = prev_weights or {}
    checks, block_codes = _run_checks(target_weights, cov_matrix, prev_w, regime)

    risk_gate = "block" if block_codes else "pass"
    warnings: list[dict] = []
    if risk_gate == "block":
        warnings.append({
            "code": "RISK_GATE_BLOCKED",
            "message": f"Risk gate blocked: {', '.join(block_codes)}",
        })

    data = {
        "as_of": as_of,
        "risk_gate": risk_gate,
        "regime": regime,
        "regime_vol": regime_vol,
        "regime_vol_source": regime_vol_source,
        "checks": checks,
        "block_codes": block_codes,
    }

    output = ok_output(
        command="hf risk check",
        run_id=run_id,
        data=data,
        warnings=warnings,
    )
    if risk_gate == "block":
        output["status"] = "warning"
    return output
