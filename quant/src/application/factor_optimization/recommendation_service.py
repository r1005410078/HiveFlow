from __future__ import annotations


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in weights.values())
    if total <= 0:
        n = len(weights)
        if n == 0:
            return {}
        eq = round(1.0 / n, 6)
        return {k: eq for k in weights}
    return {k: round(max(0.0, v) / total, 6) for k, v in weights.items()}


def _apply_caps(weights: dict[str, float], constraints: dict[str, float]) -> dict[str, float]:
    capped = dict(weights)
    for key, cap in constraints.items():
        prefix = "max_weight:"
        if not key.startswith(prefix):
            continue
        factor = key[len(prefix):]
        if factor in capped:
            capped[factor] = min(capped[factor], max(0.0, float(cap)))
    return _normalize(capped)


def _penalize_high_corr(
    weights: dict[str, float],
    metrics: dict[str, dict[str, float]],
    correlation_pairs: dict[tuple[str, str], float],
) -> dict[str, float]:
    adjusted = dict(weights)
    for (left, right), corr in correlation_pairs.items():
        if abs(corr) <= 0.7:
            continue
        left_score = float(metrics.get(left, {}).get("sharpe", 0.0)) + float(metrics.get(left, {}).get("ic", 0.0))
        right_score = float(metrics.get(right, {}).get("sharpe", 0.0)) + float(metrics.get(right, {}).get("ic", 0.0))
        loser = right if left_score >= right_score else left
        if loser in adjusted:
            adjusted[loser] *= 0.85
    return _normalize(adjusted)


def _expected_metrics(weights: dict[str, float], metrics: dict[str, dict[str, float]]) -> tuple[float, float]:
    expected_sharpe = 0.0
    expected_drawdown = 0.0
    for factor, weight in weights.items():
        item = metrics.get(factor, {})
        expected_sharpe += weight * float(item.get("sharpe", 0.0))
        expected_drawdown += weight * float(item.get("max_drawdown", 0.2))
    return round(expected_sharpe, 6), round(expected_drawdown, 6)


def suggest_weight_schemes(
    metrics: dict[str, dict[str, float]],
    correlation_pairs: dict[tuple[str, str], float],
    constraints: dict[str, float] | None = None,
) -> list[dict]:
    factor_names = list(metrics.keys())
    if not factor_names:
        return []

    constraints = constraints or {}

    raw_return_first: dict[str, float] = {}
    raw_risk_first: dict[str, float] = {}
    raw_balanced: dict[str, float] = {}

    for name in factor_names:
        ic = float(metrics[name].get("ic", 0.0))
        sharpe = float(metrics[name].get("sharpe", 0.0))
        drawdown = float(metrics[name].get("max_drawdown", 0.2))

        return_score = max(0.0, 0.6 * sharpe + 0.4 * ic)
        risk_score = 1.0 / max(0.05, drawdown)

        raw_return_first[name] = return_score
        raw_risk_first[name] = risk_score
        raw_balanced[name] = 0.5 * return_score + 0.5 * risk_score

    candidates = [
        ("return_first", raw_return_first),
        ("risk_first", raw_risk_first),
        ("balanced", raw_balanced),
    ]

    output: list[dict] = []
    for name, raw_weights in candidates:
        weights = _normalize(raw_weights)
        weights = _penalize_high_corr(weights, metrics, correlation_pairs)
        weights = _apply_caps(weights, constraints)

        expected_sharpe, expected_drawdown = _expected_metrics(weights, metrics)
        score = expected_sharpe - 0.5 * expected_drawdown
        if name == "balanced":
            # Keep balanced as default recommendation in P0, unless metrics are clearly worse.
            score += 0.15

        output.append(
            {
                "name": name,
                "weights": weights,
                "expected_sharpe": round(expected_sharpe, 6),
                "expected_drawdown": round(expected_drawdown, 6),
                "score": round(score, 6),
            }
        )

    return sorted(output, key=lambda x: x["score"], reverse=True)
