import pandas as pd
import numpy as np
from datetime import datetime, timezone
from domain.models.l2_decision import FactorDetail, ScoreBreakdownItem, TopCandidate

SCORE_VERSION = "l2-score-v1.1"

SCORE_PROFILES = {
    "l2-score-v1": {
        "weights": {"momentum_20": 0.5, "inv_volatility_20": 0.3, "turnover_rate": 0.2},
        "enabled_factors": ["momentum_20", "inv_volatility_20", "turnover_rate"],
    },
    "l2-score-v1.1": {
        "weights": {
            "momentum_20": 0.25,
            "inv_volatility_20": 0.15,
            "turnover_rate": 0.10,
            "max_drawdown_60": 0.20,
            "trend_stability_20": 0.15,
            "relative_strength_vs_index": 0.15,
        },
        "enabled_factors": [
            "momentum_20",
            "inv_volatility_20",
            "turnover_rate",
            "max_drawdown_60",
            "trend_stability_20",
            "relative_strength_vs_index",
        ],
    },
}

for profile_name, profile in SCORE_PROFILES.items():
    assert abs(sum(profile["weights"].values()) - 1.0) < 1e-9, f"Weights in {profile_name} must sum to 1.0"


def compute_l2_decision_from_snapshot(factor_snapshot: dict, top_n: int = 5, score_version: str = SCORE_VERSION) -> dict:
    # Validate score_version
    profile = SCORE_PROFILES.get(score_version)
    if not profile:
        raise ValueError(f"Unknown score_version: {score_version}")
    factor_weights = profile["weights"]

    rows = factor_snapshot.get("rows", [])
    if not rows:
        return {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "producer_version": "quant-l2",
            "score_version": score_version,
            "universe_size": 0,
            "top_candidates": [],
            "score_breakdown": [],
        }

    df = pd.DataFrame(rows)
    wide = df.pivot_table(index="symbol", columns="factor_name", values="raw_value", aggfunc="first")

    # Pre-compute per-factor clipped columns (Issue 1 fix)
    # For each factor: compute p1/p99 on non-missing raw values, clip all non-missing values,
    # then derive col_min/col_max from the clipped column.
    factor_clip_info: dict = {}  # factor_name -> {clipped_col, col_min, col_max, p1, p99}
    for factor_name in factor_weights:
        if factor_name not in wide.columns:
            factor_clip_info[factor_name] = None
            continue
        raw_col = wide[factor_name]
        non_missing_mask = ~pd.isna(raw_col)
        non_missing_values = raw_col[non_missing_mask].values
        if len(non_missing_values) == 0:
            factor_clip_info[factor_name] = None
            continue
        p1, p99 = np.percentile(non_missing_values, [1, 99])
        # Build clipped column (NaN preserved for missing)
        clipped_col = raw_col.copy()
        clipped_col[non_missing_mask] = np.clip(raw_col[non_missing_mask].values, p1, p99)
        clipped_non_missing = clipped_col[non_missing_mask]
        col_min = float(clipped_non_missing.min())
        col_max = float(clipped_non_missing.max())
        factor_clip_info[factor_name] = {
            "clipped_col": clipped_col,
            "col_min": col_min,
            "col_max": col_max,
            "p1": p1,
            "p99": p99,
        }

    score_breakdown = []

    for symbol in wide.index:
        factors = []
        for factor_name, weight in factor_weights.items():
            raw_value = wide.loc[symbol, factor_name] if factor_name in wide.columns else float("nan")
            is_missing = pd.isna(raw_value)

            if is_missing:
                # Fill with 0.0 (conservative: treated as lowest possible value).
                # Assumption: all three factors have non-negative values in practice.
                # Revisit when real missing-data patterns are observed.
                raw_value = 0.0
                anomaly_flags = [f"missing_factor:{factor_name}"]
                clipped = False
                normalized_value = 1.0
                percentile = 1.0
                # Check flat distribution using clip info if available
                info = factor_clip_info.get(factor_name)
                if info is not None and info["col_max"] != info["col_min"]:
                    # Missing filled with 0.0; normalize against clipped range
                    normalized_value = (raw_value - info["col_min"]) / (info["col_max"] - info["col_min"])
                    # Rank 0.0 against the clipped column (Fix 3)
                    clipped_series = info["clipped_col"].dropna()
                    clipped_values_with_fill = list(clipped_series) + [0.0]
                    temp = pd.Series(clipped_values_with_fill)
                    ranks = temp.rank(method="average")
                    percentile = float(ranks.iloc[-1] / len(temp))
            else:
                anomaly_flags = []
                info = factor_clip_info.get(factor_name)
                if info is None:
                    # No valid column data
                    normalized_value = 1.0
                    percentile = 1.0
                    clipped = False
                    anomaly_flags.append(f"flat_distribution:{factor_name}")
                else:
                    # Determine if this symbol's value was clipped
                    clipped_value = float(info["clipped_col"].loc[symbol])
                    clipped = float(raw_value) < info["p1"] or float(raw_value) > info["p99"]

                    col_min = info["col_min"]
                    col_max = info["col_max"]

                    if col_max == col_min:
                        normalized_value = 1.0
                        percentile = 1.0
                        anomaly_flags.append(f"flat_distribution:{factor_name}")
                    else:
                        normalized_value = (clipped_value - col_min) / (col_max - col_min)
                        # Rank using symbol-indexed Series (Fix 1)
                        clipped_series = info["clipped_col"].dropna()
                        rank_series = clipped_series.rank(method="average")
                        percentile = float(rank_series.loc[symbol] / len(clipped_series))

                    # Use clipped_value as the reported raw_value
                    raw_value = clipped_value

            contribution = weight * normalized_value
            factors.append(FactorDetail(
                factor_name=factor_name,
                raw_value=raw_value,
                normalized_value=round(normalized_value, 6),
                percentile=round(percentile, 6),
                clipped=clipped,
                anomaly_flags=anomaly_flags,
                weight=weight,
                contribution=round(contribution, 6),
            ))

        final_score = round(sum(f.contribution for f in factors), 6)
        score_breakdown.append(ScoreBreakdownItem(symbol=symbol, final_score=final_score, factors=factors))

    sorted_breakdown = sorted(score_breakdown, key=lambda x: (-x.final_score, x.symbol))
    top_candidates = [
        TopCandidate(symbol=item.symbol, score=item.final_score, rank=i + 1)
        for i, item in enumerate(sorted_breakdown[:top_n])
    ]

    def factor_to_dict(f: FactorDetail) -> dict:
        return {
            "factor_name": f.factor_name,
            "raw_value": f.raw_value,
            "normalized_value": f.normalized_value,
            "percentile": f.percentile,
            "clipped": f.clipped,
            "anomaly_flags": f.anomaly_flags,
            "weight": f.weight,
            "contribution": f.contribution,
        }

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer_version": "quant-l2",
        "score_version": score_version,
        "universe_size": len(wide),
        "top_candidates": [{"symbol": t.symbol, "score": t.score, "rank": t.rank} for t in top_candidates],
        "score_breakdown": [
            {"symbol": item.symbol, "final_score": item.final_score, "factors": [factor_to_dict(f) for f in item.factors]}
            for item in sorted_breakdown
        ],
    }
