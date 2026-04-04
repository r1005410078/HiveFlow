from __future__ import annotations

import logging
import time

import cvxpy as cp
import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)

_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}


def solve_portfolio(
    alpha: dict[str, float],
    cov_matrix: pd.DataFrame,
    prev_weights: dict[str, float],
    lambda_risk: float = 1.0,
    lambda_tc: float = 0.001,
    w_max: float = 0.40,
    ind_max: float = 0.40,
    industry_map: dict[str, str] | None = None,
) -> dict:
    """Solve mean-variance QP with turnover penalty.

    Returns dict with keys: optimization_status, fallback_reason,
    target_weights (list of dicts), optimization_report (dict).
    """
    symbols = list(alpha.keys())
    n = len(symbols)
    imap = industry_map if industry_map is not None else _INDUSTRY_MAP

    alpha_vec = np.array([alpha[s] for s in symbols], dtype=float)
    Sigma = cov_matrix.reindex(index=symbols, columns=symbols).fillna(0.0).values.astype(float)
    w_prev_vec = np.array([prev_weights.get(s, 0.0) for s in symbols], dtype=float)

    # Group symbols by industry for industry constraints
    industry_groups: dict[str, list[int]] = {}
    for i, s in enumerate(symbols):
        ind = imap.get(s, "other")
        industry_groups.setdefault(ind, []).append(i)

    w = cp.Variable(n)
    t = cp.Variable(n)  # auxiliary for |w - w_prev| linearisation

    objective = cp.Maximize(
        alpha_vec @ w
        - lambda_risk * cp.quad_form(w, Sigma)
        - lambda_tc * cp.sum(t)
    )

    constraints: list = [
        cp.sum(w) == 1,
        w >= 0,
        w <= w_max,
        t >= w - w_prev_vec,
        t >= w_prev_vec - w,
        t >= 0,
    ]
    for idxs in industry_groups.values():
        if len(idxs) > 1:
            constraints.append(cp.sum(w[idxs]) <= ind_max)

    prob = cp.Problem(objective, constraints)
    t0 = time.perf_counter()
    try:
        prob.solve(solver=cp.CLARABEL)
    except Exception as exc:
        _logger.warning("cvxpy solve raised exception: %s", exc)
        prob._status = "solver_error"  # noqa: SLF001
    solve_time_ms = max(1, int((time.perf_counter() - t0) * 1000))

    is_ok = prob.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)

    if is_ok:
        w_val = np.clip(w.value, 0.0, 1.0)
        w_total = float(w_val.sum())
        w_val = w_val / w_total if w_total > 1e-9 else np.ones(n) / n
        opt_status = "optimal" if prob.status == cp.OPTIMAL else "optimal_inaccurate"
        target_weights = [
            {
                "symbol": symbols[i],
                "weight": round(float(w_val[i]), 6),
                "prev_weight": round(float(w_prev_vec[i]), 6),
                "delta": round(float(w_val[i] - w_prev_vec[i]), 6),
            }
            for i in range(n)
        ]
        risk_contrib = round(float(w_val @ Sigma @ w_val), 6)
        turnover_cost = round(float(np.sum(np.abs(w_val - w_prev_vec))) * lambda_tc, 6)
        report = {
            "objective_value": round(float(prob.value) if prob.value is not None else 0.0, 6),
            "risk_contribution": risk_contrib,
            "turnover_cost": turnover_cost,
            "solver": "CLARABEL",
            "solve_time_ms": solve_time_ms,
        }
        return {
            "optimization_status": opt_status,
            "fallback_reason": None,
            "target_weights": target_weights,
            "optimization_report": report,
        }

    # Fallback
    fallback_reason = str(prob.status)
    prev_total = float(w_prev_vec.sum())
    if prev_total < 1e-9:
        w_fb = np.ones(n) / n
        opt_status = "fallback_equal_weight"
    else:
        w_fb = w_prev_vec / prev_total
        opt_status = "fallback_prev_weight"

    target_weights = [
        {
            "symbol": symbols[i],
            "weight": round(float(w_fb[i]), 6),
            "prev_weight": round(float(w_prev_vec[i]), 6),
            "delta": round(float(w_fb[i] - w_prev_vec[i]), 6),
        }
        for i in range(n)
    ]
    report = {
        "objective_value": 0.0,
        "risk_contribution": 0.0,
        "turnover_cost": 0.0,
        "solver": "CLARABEL",
        "solve_time_ms": solve_time_ms,
    }
    return {
        "optimization_status": opt_status,
        "fallback_reason": fallback_reason,
        "target_weights": target_weights,
        "optimization_report": report,
    }
