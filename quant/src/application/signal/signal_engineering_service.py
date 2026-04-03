from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import numpy as np
import pandas as pd

from application.contracts.cli_output import ok_output
from application.factor.basic_factor_service import (
    compute_basic_factor_snapshot,
    compute_basic_factor_snapshot_from_bars,
)
from hiveflow.signal.application.normalize_use_case import winsorize_then_zscore

_SIGNAL_VERSION = "l3-signal-v1.0"
_BENCHMARK_SYMBOL = "000300.SH"

_logger = logging.getLogger(__name__)


def _series_stats(s: pd.Series) -> dict:
    clean = s.dropna()
    if len(clean) == 0:
        return {"count": 0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": int(len(clean)),
        "mean": round(float(clean.mean()), 6),
        "std": round(float(clean.std(ddof=0)), 6),
        "min": round(float(clean.min()), 6),
        "max": round(float(clean.max()), 6),
    }


def compute_signal_matrix(factor_snapshot: dict) -> dict:
    rows = factor_snapshot.get("rows", [])
    factor_names = factor_snapshot.get("factor_names", [])

    if not rows:
        return {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "producer_version": "quant-l3",
            "signal_version": _SIGNAL_VERSION,
            "factor_names": list(factor_names),
            "coverage_rate": 0.0,
            "rows": [],
            "composite_scores": [],
            "transform_stats": [],
        }

    df = pd.DataFrame(rows)
    wide = df.pivot_table(
        index="symbol", columns="factor_name", values="raw_value", aggfunc="first",
    )

    direction_map: dict[str, int] = {}
    for row in rows:
        fn = row["factor_name"]
        if fn not in direction_map:
            direction_map[fn] = row.get("direction", 1)

    active_factors = [f for f in factor_names if f in wide.columns]

    for fn in active_factors:
        if direction_map.get(fn, 1) == -1:
            wide[fn] = wide[fn] * -1

    signal_wide = pd.DataFrame(index=wide.index)
    transform_stats: list[dict] = []

    for fn in active_factors:
        col = wide[fn]
        pre_stats = _series_stats(col)

        if col.dropna().nunique() <= 1:
            signal_col = pd.Series(np.nan, index=col.index)
            post_stats = _series_stats(signal_col)
            non_nan_raw = col.dropna()
            if len(non_nan_raw) > 0:
                post_stats["count"] = int(len(non_nan_raw))
        else:
            signal_col = winsorize_then_zscore(col.dropna())
            signal_col = signal_col.reindex(col.index)
            post_stats = _series_stats(signal_col)
        signal_wide[fn] = signal_col

        transform_stats.append({
            "factor_name": fn,
            "pre_winsorize": pre_stats,
            "post_zscore": post_stats,
        })

    signal_rows: list[dict] = []
    for symbol in signal_wide.index:
        for fn in active_factors:
            sv = signal_wide.loc[symbol, fn]
            raw_val = wide.loc[symbol, fn]
            signal_rows.append({
                "symbol": symbol,
                "factor_name": fn,
                "raw_value": round(float(raw_val), 6) if not math.isnan(raw_val) else raw_val,
                "signal_value": round(float(sv), 6) if not math.isnan(sv) else sv,
                "direction": direction_map.get(fn, 1),
            })

    composite_scores: list[dict] = []
    for symbol in signal_wide.index:
        vals = signal_wide.loc[symbol].dropna()
        if len(vals) == 0:
            composite_scores.append({
                "symbol": symbol, "composite_score": float("nan"), "factor_count": 0,
            })
        else:
            composite_scores.append({
                "symbol": symbol,
                "composite_score": round(float(vals.mean()), 6),
                "factor_count": int(len(vals)),
            })

    total_cells = len(signal_wide.index) * len(active_factors)
    non_nan = int(signal_wide.notna().sum().sum()) if total_cells > 0 else 0
    coverage = round(non_nan / total_cells, 4) if total_cells > 0 else 0.0

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer_version": "quant-l3",
        "signal_version": _SIGNAL_VERSION,
        "factor_names": list(active_factors),
        "coverage_rate": coverage,
        "rows": signal_rows,
        "composite_scores": composite_scores,
        "transform_stats": transform_stats,
    }


def run_signal_snapshot(as_of: str, bar_store=None) -> dict:
    """Standalone signal snapshot (for the independent HTTP endpoint)."""
    symbols = [
        "000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ",
    ]
    factor_snapshot = compute_basic_factor_snapshot(as_of=as_of, symbols=symbols)
    if bar_store is not None:
        try:
            start_date = (date.fromisoformat(as_of) - timedelta(days=180)).isoformat()
            bar_rows = bar_store.list_bars(
                symbols=symbols, timeframe="1d",
                start_date=start_date, end_date=as_of, limit=10000,
            )
            try:
                benchmark_start = (date.fromisoformat(as_of) - timedelta(days=60)).isoformat()
                benchmark_rows = bar_store.list_bars(
                    symbols=[_BENCHMARK_SYMBOL], timeframe="1d",
                    start_date=benchmark_start, end_date=as_of, limit=60,
                )
            except Exception:
                benchmark_rows = None
            factor_snapshot = compute_basic_factor_snapshot_from_bars(
                as_of=as_of, symbols=symbols,
                bar_rows=bar_rows, benchmark_rows=benchmark_rows,
            )
        except Exception:
            _logger.warning(
                "signal snapshot: bar_store failed; using deterministic factor snapshot",
                exc_info=True,
            )

    signal_matrix = compute_signal_matrix(factor_snapshot)
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    return ok_output(
        command="hf signal snapshot",
        run_id=run_id,
        data=signal_matrix,
    )
