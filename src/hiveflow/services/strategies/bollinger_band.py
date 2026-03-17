"""布林带策略：价格在下轨附近（超卖）时增加权重。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class BollingerBandStrategy(BaseStrategy):
    """布林带策略：超卖区域（靠近下轨）加权，超买区域（靠近上轨）减权。"""

    params: dict = {"window": 20, "num_std": 2.0, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        num_std = float(ctx.params.get("num_std", self.params["num_std"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        non_usdt = [s for s in prices.columns if s != "USDT"]
        if not non_usdt or len(prices) < window:
            n = len(prices.columns)
            return {s: 1.0 / n for s in prices.columns}

        w = min(window, len(prices))
        recent = prices.tail(w)
        mean = recent.mean()
        std = recent.std()

        scores: dict[str, float] = {}
        for s in non_usdt:
            if std[s] < 1e-9:
                scores[s] = 0.5
                continue
            lower = mean[s] - num_std * std[s]
            upper = mean[s] + num_std * std[s]
            band_width = upper - lower
            current = prices.iloc[-1][s]
            if band_width > 1e-9:
                scores[s] = 1.0 - (current - lower) / band_width
            else:
                scores[s] = 0.5
            scores[s] = max(0.0, min(1.0, scores[s]))

        total_scores = sum(scores.values()) or 1.0
        usdt_w = min_usdt
        remaining = 1.0 - usdt_w

        weights: dict[str, float] = {}
        for s in non_usdt:
            weights[s] = (scores[s] / total_scores) * remaining
        if "USDT" in prices.columns:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
