"""风格回测排名（Phase 1）。"""

from __future__ import annotations

import json
import math
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import timezone
from io import StringIO

from sqlmodel import select

from hiveflow.application.backtest import run_quant_backtest
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.common import utc_now
from hiveflow.domain.market_data import MarketBar
from hiveflow.services.strategies import (
    MeanReversionStrategy,
    MomentumStrategy,
    MovingAverageCrossStrategy,
    RiskParityStrategy,
)

STYLE_TO_STRATEGY = {
    "Trend-Following": MomentumStrategy,
    "Mean-Reversion": MeanReversionStrategy,
    "Defensive-RiskOff": RiskParityStrategy,
    "Breakout-Aggressive": MovingAverageCrossStrategy,
}

STYLE_FEATURE_KEYS = {
    "Trend-Following": [
        "golden_cross",
        "momentum_20d",
        "trend_persistence",
        "trend_strength_adx",
    ],
    "Mean-Reversion": [
        "max_drawdown_7d",
        "atr_volatility_14d",
        "signal_consensus",
    ],
    "Defensive-RiskOff": [
        "max_drawdown_30d",
        "concentration_risk",
        "volatility_regime_label",
        "confidence_score",
    ],
    "Breakout-Aggressive": [
        "breakout_20d",
        "volume_breakout_confirm",
        "multi_timeframe_confirm",
    ],
}


@dataclass(frozen=True)
class StyleBacktestError(ValueError):
    """风格回测严格模式异常。"""

    context: str
    message: str
    details: dict
    hint: dict | str | None = None


def _curve_returns(equity_curve: list[float]) -> list[float]:
    values: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        curr = equity_curve[i]
        if prev <= 0:
            continue
        values.append(curr / prev - 1.0)
    return values


def _annualized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
    return math.sqrt(variance) * math.sqrt(365.0)


def _win_rate(returns: list[float]) -> float:
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns)


def _calmar(total_return: float, periods: int, max_drawdown: float) -> float:
    if periods <= 0:
        return 0.0
    annualized_return = (1.0 + total_return) ** (365.0 / periods) - 1.0
    if abs(max_drawdown) < 1e-9:
        return round(annualized_return * 100.0, 6)
    return annualized_return / abs(max_drawdown)


def _rank(rows: list[dict]) -> list[dict]:
    ordered = sorted(
        rows,
        key=lambda item: (
            -item["calmar"],
            abs(item["max_drawdown"]),
            -item["sharpe"],
            -item["total_return"],
            item["style_name"],
        ),
    )
    rank_rows: list[dict] = []
    for idx, row in enumerate(ordered, start=1):
        rank_rows.append({"rank": idx, **row})
    return rank_rows


def run_style_backtest_rank(
    *,
    settings: Settings | None = None,
    rebalance_days: int = 7,
    symbols: list[str] | None = None,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> dict:
    """运行 4 风格回测并输出排序结果。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        bars = session.exec(select(MarketBar.timestamp).order_by(MarketBar.timestamp)).all()
    if not bars:
        raise StyleBacktestError(
            context="style.backtest-rank",
            message="风格评估失败，严格模式中断。",
            details={
                "strict_mode": True,
                "completed_styles": [],
                "failed_style": "Trend-Following",
                "styles_total": list(STYLE_TO_STRATEGY.keys()),
                "reason": "MarketBar is empty",
            },
            hint={"action": "run_backtest_pipeline"},
        )

    start_ts = bars[0].astimezone(timezone.utc).isoformat()
    end_ts = bars[-1].astimezone(timezone.utc).isoformat()
    as_of = utc_now().isoformat()

    completed: list[str] = []
    styles: list[dict] = []
    for style_name, strategy_class in STYLE_TO_STRATEGY.items():
        try:
            with redirect_stdout(StringIO()):
                result = run_quant_backtest(
                    strategy=strategy_class(),
                    rebalance_days=rebalance_days,
                    symbols=symbols,
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                    settings=app_settings,
                )
            curve = json.loads(result.equity_curve or "[]")
            returns = _curve_returns(curve)
            style_row = {
                "style_name": style_name,
                "strategy_name": result.strategy_name,
                "total_return": round(result.total_return, 6),
                "max_drawdown": round(result.max_drawdown, 6),
                "sharpe": round(result.sharpe, 6),
                "calmar": round(_calmar(result.total_return, result.periods, result.max_drawdown), 6),
                "win_rate": round(_win_rate(returns), 6),
                "annualized_volatility": round(_annualized_volatility(returns), 6),
                "periods": result.periods,
                "backtest_window": {"start": start_ts, "end": end_ts},
                "feature_keys": STYLE_FEATURE_KEYS[style_name],
            }
            styles.append(style_row)
            completed.append(style_name)
        except Exception as exc:
            raise StyleBacktestError(
                context="style.backtest-rank",
                message="风格评估失败，严格模式中断。",
                details={
                    "strict_mode": True,
                    "completed_styles": completed,
                    "failed_style": style_name,
                    "styles_total": list(STYLE_TO_STRATEGY.keys()),
                    "error": str(exc),
                },
                hint={"action": "run_backtest_pipeline"},
            ) from exc

    return {
        "as_of": as_of,
        "sort_key": "calmar",
        "tie_breaker": "calmar desc -> |max_drawdown| asc -> sharpe desc -> total_return desc",
        "styles": styles,
        "rank_table": _rank(styles),
        "backtest_window": {"start": start_ts, "end": end_ts},
    }
