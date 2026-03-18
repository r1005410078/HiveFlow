# src/hiveflow/domain/blend_configs.py
"""多策略混合配置领域模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class BlendConfig(SQLModel, table=True):
    """多策略混合配置：记录参与混合的策略名称、权重及自动优化设置。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, unique=True))  # DB 级唯一约束
    strategy_names: str          # JSON list，如 ["MomentumStrategy", "EqualWeightStrategy"]
    weights: str                 # JSON dict，如 {"MomentumStrategy": 0.6, "EqualWeightStrategy": 0.4}
    auto_optimized: bool         # True = 运行时自动计算权重；False = 使用手动权重
    optimize_metric: str = Field(default="sharpe")  # "sharpe" | "calmar" | "return"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    # 注：updated_at 由 Application 层在每次 blend run 后手动更新
