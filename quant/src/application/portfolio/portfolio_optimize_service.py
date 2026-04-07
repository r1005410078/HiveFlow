from __future__ import annotations

import logging
import math
from uuid import uuid4

import numpy as np
import pandas as pd

from application.contracts.cli_output import ok_output
from application.portfolio.covariance_service import compute_covariance_matrix
from application.portfolio.optimizer_service import solve_portfolio
from application.signal.signal_engineering_service import run_signal_snapshot
from domain.universe.universe_loader import load_universe

_OPTIMIZE_VERSION = "l4-optimize-v1.0"
_DEFAULT_SYMBOLS = load_universe("default")
_DIAGONAL_VAR = 0.04  # fallback annual variance when bar_store unavailable

_logger = logging.getLogger(__name__)


def run_portfolio_optimize(
    as_of: str,
    alpha: dict[str, float] | None = None,
    prev_weights: dict[str, float] | None = None,
    lambda_risk: float = 1.0,
    lambda_tc: float = 0.001,
    w_max: float = 0.30,
    ind_max: float = 0.40,
    lookback_days: int = 60,
    bar_store=None,
) -> dict:
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"

    if alpha is None:
        snapshot = run_signal_snapshot(as_of=as_of, bar_store=bar_store)
        data = snapshot.get("data") or {}
        signal_matrix = data.get("signal_matrix") or {}
        composite_scores = signal_matrix.get("composite_scores", [])
        alpha = {
            cs["symbol"]: float(cs["composite_score"])
            for cs in composite_scores
            if not math.isnan(float(cs["composite_score"]))
        }
        if not alpha:
            alpha = {s: 1.0 for s in _DEFAULT_SYMBOLS}

    symbols = list(alpha.keys())
    prev_w = prev_weights or {}

    cov_matrix: pd.DataFrame | None = None
    if bar_store is not None:
        try:
            cov_matrix = compute_covariance_matrix(
                symbols=symbols,
                as_of=as_of,
                bar_store=bar_store,
                lookback_days=lookback_days,
            )
        except Exception:
            _logger.warning(
                "portfolio optimize: covariance computation failed, using diagonal",
                exc_info=True,
            )

    if cov_matrix is None:
        n = len(symbols)
        cov_matrix = pd.DataFrame(
            _DIAGONAL_VAR * np.eye(n), index=symbols, columns=symbols,
        )

    result = solve_portfolio(
        alpha=alpha,
        cov_matrix=cov_matrix,
        prev_weights=prev_w,
        lambda_risk=lambda_risk,
        lambda_tc=lambda_tc,
        w_max=w_max,
        ind_max=ind_max,
    )

    is_fallback = result["optimization_status"].startswith("fallback")
    warnings: list[dict] = []
    if is_fallback:
        warnings.append({
            "code": "PORTFOLIO_OPTIMIZATION_FALLBACK",
            "message": f"Optimizer fallback ({result['optimization_status']}): {result['fallback_reason']}",
        })

    data = {
        "as_of": as_of,
        "optimize_version": _OPTIMIZE_VERSION,
        "optimization_status": result["optimization_status"],
        "fallback_reason": result["fallback_reason"],
        "target_weights": result["target_weights"],
        "optimization_report": result["optimization_report"],
    }

    output = ok_output(
        command="hf portfolio optimize",
        run_id=run_id,
        data=data,
        warnings=warnings,
    )
    if is_fallback:
        output["status"] = "warning"
    return output
