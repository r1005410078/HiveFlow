"""持仓过滤规则。"""

from __future__ import annotations

SMALL_POSITION_MARKET_VALUE_THRESHOLD = 0.01


def is_small_position_market_value(market_value: float) -> bool:
    """判断持仓市值是否小到可以忽略。"""
    return market_value <= SMALL_POSITION_MARKET_VALUE_THRESHOLD
