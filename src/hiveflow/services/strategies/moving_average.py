"""均线交叉策略：短期均线在长期均线上方的资产加权。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class MovingAverageCrossStrategy(BaseStrategy):
    """均线交叉策略：金叉（短期 > 长期均线）资产按趋势强度分配权重。"""

    params: dict = {"fast": 7, "slow": 30, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        fast = int(ctx.params.get("fast", self.params["fast"]))
        slow = int(ctx.params.get("slow", self.params["slow"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        non_usdt = [s for s in prices.columns if s != "USDT"]
        if not non_usdt or len(prices) < slow:
            n = len(prices.columns)
            return {s: 1.0 / n for s in prices.columns}

        scores: dict[str, float] = {}
        for s in non_usdt:
            fast_ma = prices[s].tail(fast).mean()
            slow_ma = prices[s].tail(slow).mean()
            if slow_ma > 1e-9:
                scores[s] = (fast_ma - slow_ma) / slow_ma
            else:
                scores[s] = 0.0

        positive = {s: max(0.0, v) for s, v in scores.items()}
        total_pos = sum(positive.values())

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w

        if total_pos < 1e-9:
            per = remaining / len(non_usdt) if non_usdt else 0.0
            weights = {s: per for s in non_usdt}
        else:
            weights = {s: (positive[s] / total_pos) * remaining for s in non_usdt}

        if "USDT" in prices.columns:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
