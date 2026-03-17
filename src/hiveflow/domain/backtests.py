"""回测结果模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class BacktestResult(SQLModel, table=True):
    """策略回测结果记录。"""

    # 主键。
    id: int | None = Field(default=None, primary_key=True)
    # 策略名称。
    strategy_name: str
    # 数据文件路径。
    prices_file: str
    # 回测周期数。
    periods: int
    # 总收益（小数）。
    total_return: float
    # 最大回撤（小数，<=0）。
    max_drawdown: float
    # Sharpe 比率（简化版）。
    sharpe: float
    # 权重快照（JSON 字符串，如 {"BTC":0.4,"ETH":0.3,...}）。
    weights_snapshot: str | None = Field(default=None)
    # 创建时间（UTC）。
    created_at: datetime = Field(default_factory=utc_now)
