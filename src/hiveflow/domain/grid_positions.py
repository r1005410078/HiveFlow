# src/hiveflow/domain/grid_positions.py
"""OKX 网格机器人持仓模型。"""
from datetime import datetime
from sqlmodel import Field, SQLModel
from hiveflow.domain.common import utc_now


class GridPosition(SQLModel, table=True):
    """网格机器人持有的资产（不参与再平衡计算）。"""
    id: int | None = Field(default=None, primary_key=True)
    symbol: str           # 资产名（BTC）
    grid_id: str          # 网格机器人 ID
    inst_id: str          # 交易对（BTC-USDT）
    base_quantity: float  # 持有基础资产数量
    quote_quantity: float # 持有报价资产（USDT）数量
    state: str            # running / stopped
    inst_type: str = Field(default="SPOT")  # SPOT / SWAP / FUTURES
    synced_at: datetime = Field(default_factory=utc_now)
