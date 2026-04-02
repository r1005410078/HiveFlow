import pandas as pd
import numpy as np
from datetime import datetime, timezone
from domain.models.l2_decision import FactorDetail, ScoreBreakdownItem, TopCandidate

_FACTOR_WEIGHTS = {"momentum_20": 0.5, "inv_volatility_20": 0.3, "turnover_rate": 0.2}


def compute_l2_decision_from_snapshot(factor_snapshot: dict, top_n: int = 5) -> dict:
    rows = factor_snapshot.get("rows", [])
    if not rows:
        return {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "producer_version": "quant-l2",
            "score_version": "l2-score-v1",
            "universe_size": 0,
            "top_candidates": [],
            "score_breakdown": [],
        }

    df = pd.DataFrame(rows)
    wide = df.pivot_table(index="symbol", columns="factor_name", values="raw_value", aggfunc="first")

    score_breakdown = []

    for symbol in wide.index:
        factors = []
        for factor_name, weight in _FACTOR_WEIGHTS.items():
            raw_value = wide.loc[symbol, factor_name] if factor_name in wide.columns else float("nan")
            is_missing = pd.isna(raw_value)

            if is_missing:
                raw_value = 0.0
                anomaly_flags = [f"missing_factor:{factor_name}"]
                clipped = False
            else:
                anomaly_flags = []
                col_values_raw = [v for v in wide[factor_name] if not pd.isna(v)]
                p1, p99 = np.percentile(col_values_raw, [1, 99])
                clipped = False
                if raw_value < p1:
                    raw_value = p1
                    clipped = True
                elif raw_value > p99:
                    raw_value = p99
                    clipped = True

            col_values = [v for v in wide[factor_name].tolist() if not pd.isna(v)] if factor_name in wide.columns else []
            col_min = min(col_values) if col_values else 0.0
            col_max = max(col_values) if col_values else 0.0

            if col_max == col_min:
                normalized_value = 1.0
                percentile = 1.0
                anomaly_flags.append(f"flat_distribution:{factor_name}")
            else:
                normalized_value = (raw_value - col_min) / (col_max - col_min)
                series = pd.Series(sorted(col_values))
                # count values strictly less than raw_value, ties use average rank
                n_less = float((series < raw_value).sum())
                n_equal = float((series == raw_value).sum())
                if n_equal == 0:
                    # raw_value was clipped; find its rank by interpolation
                    n_less = float((series < raw_value).sum())
                    n_equal = 1.0
                rank_avg = n_less + (n_equal + 1.0) / 2.0
                percentile = rank_avg / len(col_values)

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
        "score_version": "l2-score-v1",
        "universe_size": len(wide),
        "top_candidates": [{"symbol": t.symbol, "score": t.score, "rank": t.rank} for t in top_candidates],
        "score_breakdown": [
            {"symbol": item.symbol, "final_score": item.final_score, "factors": [factor_to_dict(f) for f in item.factors]}
            for item in sorted_breakdown
        ],
    }
