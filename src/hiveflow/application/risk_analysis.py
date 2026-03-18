"""风险分析应用服务。"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.services.backtest_engine import load_close_prices_from_db
from hiveflow.services.risk_engine import (
    compute_correlation,
    compute_drawdown,
    compute_portfolio_risk,
    compute_volatility,
)


@dataclass(frozen=True)
class AssetRiskView:
    symbol: str
    annual_vol: float
    daily_vol: float
    max_drawdown: float
    periods: int


@dataclass(frozen=True)
class CorrelationView:
    symbols: list[str]
    matrix: list[list[float]]


def analyze_asset_risk(
    symbols: list[str] | None = None,
    settings=None,
) -> tuple[list[AssetRiskView], CorrelationView]:
    """从 MarketBar 读取价格序列，返回各资产风险视图 + 相关性矩阵。

    symbols=None 时先查询所有 distinct symbol（与 run_quant_backtest 相同模式），
    再调用 load_close_prices_from_db。MarketBar 无数据时抛 ValueError。
    """
    from hiveflow.domain.market_data import MarketBar

    create_all_tables(settings)

    if symbols is None:
        with get_session(settings) as session:
            rows = session.exec(select(MarketBar.symbol).distinct()).all()
        symbols = list(rows)

    if not symbols:
        raise ValueError("MarketBar 中没有数据，请先运行 hiveflow market-data import。")

    prices = load_close_prices_from_db(symbols=symbols, settings=settings)
    if not prices:
        raise ValueError("指定 symbol 在 MarketBar 中无数据。")

    vols = compute_volatility(prices)
    dds = compute_drawdown(prices)
    corr = compute_correlation(prices)

    dd_by_symbol = {d.symbol: d for d in dds}
    asset_views = [
        AssetRiskView(
            symbol=v.symbol,
            annual_vol=v.annual_vol,
            daily_vol=v.daily_vol,
            max_drawdown=dd_by_symbol[v.symbol].max_drawdown if v.symbol in dd_by_symbol else 0.0,
            periods=v.periods,
        )
        for v in vols
    ]
    return asset_views, CorrelationView(symbols=corr.symbols, matrix=corr.matrix)


def analyze_portfolio_risk(
    backtest_id: int,
    settings=None,
) -> dict | None:
    """从 BacktestResult.equity_curve 计算组合级风险指标。

    - backtest_id 不存在 → 抛 ValueError
    - equity_curve 为 NULL → 返回 None（CLI 层输出降级提示，exit_code=0）
    - 正常 → 返回 compute_portfolio_risk() 的结果字典
    """
    from hiveflow.domain.backtests import BacktestResult

    create_all_tables(settings)
    with get_session(settings) as session:
        row = session.get(BacktestResult, backtest_id)
        if row is None:
            raise ValueError(f"回测记录 #{backtest_id} 不存在。")
        equity_curve_str = row.equity_curve

    if equity_curve_str is None:
        return None

    curve = _json.loads(equity_curve_str)
    return compute_portfolio_risk(curve)
