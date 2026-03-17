"""等权重策略：所有资产均分，USDT 保留最低比例。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class EqualWeightStrategy(BaseStrategy):
    """等权重（基准策略）：所有资产平均分配，USDT 保留最低比例。"""

    params: dict = {"min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))
        symbols = list(ctx.prices.columns)
        n = len(symbols)
        if n == 0:
            return {}

        non_usdt = [s for s in symbols if s != "USDT"]
        usdt_w = max(min_usdt, 1.0 / n)
        remaining = 1.0 - usdt_w
        per = remaining / len(non_usdt) if non_usdt else 0.0

        weights = {s: per for s in non_usdt}
        if "USDT" in symbols:
            weights["USDT"] = usdt_w
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
