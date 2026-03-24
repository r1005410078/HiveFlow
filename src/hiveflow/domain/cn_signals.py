# src/hiveflow/domain/cn_signals.py
"""A 股特有信号实体：个股级（CNStockSignal）和市场级（CNMarketSignal）。"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class CNStockSignal(SQLModel, table=True):
    """个股 A 股特有信号快照（PE/PB、涨跌停触发）。

    唯一约束：同一 symbol 同一日期只保留最新一条（覆盖写入）。
    涨跌停检测已知限制：仅覆盖主板非 ST 股 ±10%，ST/创业板/科创板/北交所不适用。
    """

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_cn_stock_signal_symbol_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    date: str                           # "YYYY-MM-DD"，唯一约束用
    timestamp: datetime                 # 信号时间（UTC）
    market: str = "cn_a_share"
    pe_ratio: float | None = None       # 市盈率（TTM）
    pb_ratio: float | None = None       # 市净率
    limit_up_hit: bool | None = None    # 当日触及涨停
    limit_down_hit: bool | None = None  # 当日触及跌停


class CNMarketSignal(SQLModel, table=True):
    """市场级 A 股信号（北向资金、融资余额、全市场涨跌停家数）。

    唯一约束：同一日期只保留最新一条（覆盖写入）。
    """

    __table_args__ = (
        UniqueConstraint("date", name="uq_cn_market_signal_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    date: str                                             # "YYYY-MM-DD"
    timestamp: datetime                                   # 信号时间（UTC）
    northbound_net_flow: float | None = None              # 北向资金净流入（亿元）
    margin_balance: float | None = None                   # 融资余额（亿元，沪深合计）
    limit_up_count: int | None = None                     # 全市场涨停家数
    limit_down_count: int | None = None                   # 全市场跌停家数
