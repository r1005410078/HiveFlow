"""风险平价策略：按波动率倒数分配权重。PyPortfolioOpt 可选。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


def _equal_weight_fallback(symbols: list[str], min_usdt: float) -> dict[str, float]:
    """PyPortfolioOpt 不可用时，降级为等权重。"""
    n = len(symbols)
    if n == 0:
        return {}
    non_usdt = [s for s in symbols if s != "USDT"]
    usdt_w = max(min_usdt, 1.0 / n) if "USDT" in symbols else 0.0
    remaining = 1.0 - usdt_w
    per = remaining / len(non_usdt) if non_usdt else 0.0
    weights = {s: per for s in non_usdt}
    if "USDT" in symbols:
        weights["USDT"] = usdt_w
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


class RiskParityStrategy(BaseStrategy):
    """风险平价策略：等风险贡献，权重反比于波动率。PyPortfolioOpt 可选。"""

    params: dict = {"window": 30, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        symbols = list(prices.columns)
        non_usdt = [s for s in symbols if s != "USDT"]
        if not non_usdt:
            return {"USDT": 1.0}

        try:
            import pypfopt  # type: ignore
            if pypfopt is None:
                raise ImportError("pypfopt is None")
            from pypfopt import risk_models  # type: ignore
            w = min(window, len(prices))
            sample = prices[non_usdt].tail(w)
            cov = risk_models.sample_cov(sample)
            vols = {s: float(cov.loc[s, s]) ** 0.5 for s in non_usdt}
        except (ImportError, Exception):
            print("[提示] PyPortfolioOpt 不可用，RiskParityStrategy 降级为等权重分配。")
            return _equal_weight_fallback(symbols, min_usdt)

        inv_vol = {s: 1.0 / v if v > 1e-9 else 1.0 for s, v in vols.items()}
        total_inv = sum(inv_vol.values()) or 1.0

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w
        weights: dict[str, float] = {s: (inv_vol[s] / total_inv) * remaining for s in non_usdt}
        if "USDT" in symbols:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
