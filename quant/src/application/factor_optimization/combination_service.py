from __future__ import annotations

from itertools import combinations


def _factor_return_score(metrics: dict[str, dict[str, float]], factor: str) -> float:
    item = metrics.get(factor, {})
    ic = float(item.get("ic", 0.0))
    sharpe = float(item.get("sharpe", 0.0))
    return 0.6 * sharpe + 0.4 * ic


def _factor_risk_score(metrics: dict[str, dict[str, float]], factor: str) -> float:
    item = metrics.get(factor, {})
    max_drawdown = float(item.get("max_drawdown", 0.2))
    return 1.0 / max(0.05, max_drawdown)


def _pair_correlation(correlation_matrix: dict[str, dict[str, float]], left: str, right: str) -> float:
    if left in correlation_matrix and right in correlation_matrix[left]:
        return float(correlation_matrix[left][right])
    if right in correlation_matrix and left in correlation_matrix[right]:
        return float(correlation_matrix[right][left])
    return 0.0


def _redundancy_penalty(
    factors: tuple[str, ...],
    correlation_matrix: dict[str, dict[str, float]],
    threshold: float,
) -> tuple[float, int]:
    penalty = 0.0
    alerts_inside = 0
    for left, right in combinations(factors, 2):
        corr = _pair_correlation(correlation_matrix, left, right)
        abs_corr = abs(corr)
        if abs_corr < threshold:
            continue
        alerts_inside += 1
        penalty += 0.02 + 0.03 * max(0.0, abs_corr - threshold)
        if abs_corr >= 0.9:
            penalty += 0.02
    return round(penalty, 6), alerts_inside


def _equal_weights(factors: tuple[str, ...]) -> dict[str, float]:
    if not factors:
        return {}
    weight = round(1.0 / len(factors), 6)
    return {name: weight for name in factors}


def suggest_top_combinations(
    factor_names: list[str],
    metrics: dict[str, dict[str, float]],
    correlation_matrix: dict[str, dict[str, float]],
    correlation_threshold: float = 0.7,
    combination_size_min: int = 2,
    combination_size_max: int = 4,
    top_k: int = 5,
) -> dict:
    if combination_size_min < 2:
        raise ValueError("combination_size_min must be >= 2")
    if combination_size_max > 4:
        raise ValueError("combination_size_max must be <= 4")
    if combination_size_min > combination_size_max:
        raise ValueError("combination_size_min must be <= combination_size_max")
    if top_k <= 0:
        raise ValueError("top_k_combinations must be > 0")

    factor_pool = [name for name in factor_names if name in metrics]
    n = len(factor_pool)
    max_k = min(combination_size_max, n)

    ranked: list[dict] = []
    if n >= combination_size_min:
        for k in range(combination_size_min, max_k + 1):
            for combo in combinations(factor_pool, k):
                return_score = sum(_factor_return_score(metrics, factor) for factor in combo) / k
                risk_score = sum(_factor_risk_score(metrics, factor) for factor in combo) / k
                redundancy_penalty, alerts_inside = _redundancy_penalty(
                    factors=combo,
                    correlation_matrix=correlation_matrix,
                    threshold=correlation_threshold,
                )
                composite = 0.5 * return_score + 0.5 * risk_score - redundancy_penalty
                ranked.append(
                    {
                        "factors": list(combo),
                        "weights": _equal_weights(combo),
                        "composite_score": round(composite, 6),
                        "return_score": round(return_score, 6),
                        "risk_score": round(risk_score, 6),
                        "redundancy_penalty": redundancy_penalty,
                        "alerts_inside": alerts_inside,
                        "explanations": [
                            f"return_score={round(return_score, 4)} risk_score={round(risk_score, 4)}",
                            f"high_corr_pairs={alerts_inside}",
                        ],
                    }
                )

    ranked.sort(key=lambda item: (-item["composite_score"], item["factors"]))
    items = []
    for index, item in enumerate(ranked[:top_k], start=1):
        enriched = dict(item)
        enriched["rank"] = index
        items.append(enriched)

    return {
        "search_space": {
            "factor_pool_size": n,
            "combination_size_min": combination_size_min,
            "combination_size_max": combination_size_max,
            "candidate_count": len(ranked),
        },
        "ranking_profile": "balanced_v1",
        "items": items,
    }
