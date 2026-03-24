# src/hiveflow/domain/providers.py
"""市场数据与持仓提供者抽象接口（Clean Architecture domain 层）。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from hiveflow.domain.positions import Position


class MarketDataProvider(ABC):
    """行情数据提供者接口。"""

    @abstractmethod
    def fetch_bars(self, symbols: list[str], days: int) -> list:
        """拉取最近 days 天的 OHLCV 行情，返回 MarketBar 列表。"""
        ...


class PositionProvider(ABC):
    """持仓数据提供者接口（面向长期连接的持仓同步，如券商 API）。"""

    @abstractmethod
    def fetch_positions(self) -> list[Position]:
        """返回当前账户持仓列表。"""
        ...
