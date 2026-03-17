"""最小方差策略。PyPortfolioOpt 可选。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext
from hiveflow.services.strategies.risk_parity import _equal_weight_fallback


class MinVarianceStrategy(BaseStrategy):
    """最小方差策略：最小化组合整体波动率。PyPortfolioOpt 可选。"""

    params: dict = {"window": 60, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        symbols = list(prices.columns)
        non_usdt = [s for s in symbols if s != "USDT"]

        try:
            import pypfopt  # type: ignore
            if pypfopt is None:
                raise ImportError("pypfopt is None")
            from pypfopt import risk_models  # type: ignore
            from pypfopt.efficient_frontier import EfficientFrontier  # type: ignore
            w = min(window, len(prices))
            sample = prices[non_usdt].tail(w)
            S = risk_models.sample_cov(sample)
            ef = EfficientFrontier(None, S)
            ef.min_volatility()
            cleaned = ef.clean_weights()
            usdt_w = min_usdt
            remaining = 1.0 - usdt_w
            total_raw = sum(cleaned.values()) or 1.0
            weights: dict[str, float] = {s: (v / total_raw) * remaining for s, v in cleaned.items()}
            if "USDT" in symbols:
                weights["USDT"] = usdt_w
            total = sum(weights.values())
            return {k: v / total for k, v in weights.items()}
        except (ImportError, Exception):
            print("[提示] PyPortfolioOpt 不可用，MinVarianceStrategy 降级为等权重分配。")
            return _equal_weight_fallback(symbols, min_usdt)
