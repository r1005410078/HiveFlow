"""动量策略：按过去 lookback_days 天涨幅排名，前 top_k 名均分。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class MomentumStrategy(BaseStrategy):
    """动量策略：过去涨幅排名前 top_k 的资产均分权重，USDT 保留最低比例。"""

    params: dict = {"lookback_days": 30, "top_k": 3, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        lookback = int(ctx.params.get("lookback_days", self.params["lookback_days"]))
        top_k = int(ctx.params.get("top_k", self.params["top_k"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        if len(prices) < 2:
            symbols = list(prices.columns)
            w = 1.0 / len(symbols) if symbols else 0.0
            return {s: w for s in symbols}

        window = min(lookback, len(prices) - 1)
        returns = prices.iloc[-1] / prices.iloc[-1 - window] - 1

        non_usdt = [s for s in prices.columns if s != "USDT"]
        sorted_assets = sorted(non_usdt, key=lambda s: returns.get(s, 0), reverse=True)
        top_assets = sorted_assets[:top_k]

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w
        per = remaining / len(top_assets) if top_assets else 0.0

        weights: dict[str, float] = {}
        for s in top_assets:
            weights[s] = per
        if "USDT" in prices.columns:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
