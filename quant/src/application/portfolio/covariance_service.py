from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

_MIN_VALID_BARS = 20
_DEFAULT_ANNUAL_VAR = 0.04  # fallback: ~20% annual vol on the diagonal

_logger = logging.getLogger(__name__)


def compute_covariance_matrix(
    symbols: list[str],
    as_of: str,
    bar_store,
    lookback_days: int = 60,
) -> pd.DataFrame:
    """Return annualised sample covariance matrix (symbols x symbols).

    Symbols with fewer than _MIN_VALID_BARS daily returns are treated as
    independent with diagonal variance equal to the mean of all valid symbols,
    and off-diagonal entries set to 0.
    """
    start_date = (date.fromisoformat(as_of) - timedelta(days=lookback_days)).isoformat()
    rows = bar_store.list_bars(
        symbols=symbols,
        timeframe="1d",
        start_date=start_date,
        end_date=as_of,
        limit=lookback_days + 20,
    )
    n = len(symbols)
    if not rows:
        return pd.DataFrame(
            _DEFAULT_ANNUAL_VAR * np.eye(n), index=symbols, columns=symbols,
        )

    df = pd.DataFrame(rows)
    df["_date"] = pd.to_datetime(df["bar_time"]).dt.date
    pivot = (
        df.pivot_table(index="_date", columns="symbol", values="close", aggfunc="last")
        .sort_index()
    )
    returns = pivot.pct_change().iloc[1:]  # drop first NaN row after pct_change

    # Determine which symbols have enough valid returns
    valid: dict[str, bool] = {
        s: (s in returns.columns and int(returns[s].dropna().shape[0]) >= _MIN_VALID_BARS)
        for s in symbols
    }
    valid_symbols = [s for s in symbols if valid[s]]

    if valid_symbols:
        annual_cov = returns[valid_symbols].cov() * 252
        diag_vals = [float(annual_cov.loc[s, s]) for s in valid_symbols]
        default_var = float(np.mean(diag_vals)) if diag_vals else _DEFAULT_ANNUAL_VAR
    else:
        annual_cov = pd.DataFrame()
        default_var = _DEFAULT_ANNUAL_VAR

    result = pd.DataFrame(0.0, index=symbols, columns=symbols)
    for i, s in enumerate(symbols):
        for j, t in enumerate(symbols):
            if valid[s] and valid[t] and s in annual_cov.index and t in annual_cov.columns:
                result.loc[s, t] = float(annual_cov.loc[s, t])
            elif i == j:
                result.loc[s, t] = default_var

    return result
