# src/hiveflow/domain/portfolio_snapshots.py
"""组合持仓快照领域模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class PortfolioSnapshot(SQLModel, table=True):
    """组合持仓快照：记录某时刻总持仓价值及各资产快照。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=utc_now)
    total_value_usd: float       # 总持仓价值（USD）
    positions_json: str          # 持仓快照，JSON，如 {"BTC": {"qty": 0.5, "value_usd": 5000}}
    source: str = Field(default="manual")  # "manual" | "cron"
    notes: Optional[str] = None
