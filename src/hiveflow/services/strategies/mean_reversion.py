"""均值回归策略：z-score 越低（跌越多）权重越高。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class MeanReversionStrategy(BaseStrategy):
    """均值回归策略：z-score 反向加权，跌得多分配更多权重。"""

    params: dict = {"window": 20, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        non_usdt = [s for s in prices.columns if s != "USDT"]
        if not non_usdt:
            return {"USDT": 1.0}

        w = min(window, len(prices))
        recent = prices.tail(w)
        mean = recent.mean()
        std = recent.std()

        # Compute deviation below mean (raw, not z-score normalized)
        # More negative deviation → more oversold → higher weight
        deviations: dict[str, float] = {}
        for s in non_usdt:
            deviations[s] = prices.iloc[-1][s] - mean[s]

        # Weight = max(0, -(deviation)) so assets below mean get positive weight
        raw = {s: max(0.0, -d) for s, d in deviations.items()}
        # If all assets are at or above mean, fall back to equal weight
        if sum(raw.values()) < 1e-9:
            raw = {s: 1.0 for s in non_usdt}
        total_raw = sum(raw.values()) or 1.0

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w

        weights: dict[str, float] = {}
        for s in non_usdt:
            weights[s] = (raw[s] / total_raw) * remaining
        if "USDT" in prices.columns:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
