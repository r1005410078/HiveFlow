"""策略运行记录领域模型。"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class StrategyRun(SQLModel, table=True):
    """策略运行记录：量化策略每次执行的参数、权重输出及是否已写入目标配比。"""

    id: int | None = Field(default=None, primary_key=True)
    strategy_name: str          # "MomentumStrategy" 或自定义类名
    strategy_file: str | None = Field(default=None)  # 用户文件路径，内置策略为 None
    params: str                 # JSON 字符串，实际使用的参数
    weights: str                # JSON 字符串，输出权重 {"BTC": 0.4, ...}
    applied: bool = Field(default=False)   # 是否已写入 TargetAllocation
    run_at: datetime = Field(default_factory=utc_now)
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
