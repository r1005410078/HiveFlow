"""量化策略基础层：BaseStrategy + StrategyContext。"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class StrategyContext:
    """策略上下文：行情数据、当前持仓、风险信号、策略参数。"""

    prices: pd.DataFrame           # index=date, columns=symbol，收盘价
    current_positions: dict        # {symbol: weight}，当前自由持仓权重
    risk_signals: dict             # {symbol: RiskSignal}，最新风险信号
    params: dict = field(default_factory=dict)  # 策略参数（类定义 + CLI 覆盖）


class BaseStrategy:
    """量化策略抽象基类。子类实现 compute_weights。"""

    params: dict = {}              # 子类在类体里定义默认参数

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        """
        输入：StrategyContext（行情 + 持仓 + 风险信号 + 参数）
        输出：{symbol: weight}，权重之和为 1.0
        """
        raise NotImplementedError
