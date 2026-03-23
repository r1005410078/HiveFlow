"""行情数据模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class MarketBar(SQLModel, table=True):
    """单个标的在某个时间点的行情记录。"""

    # 主键。
    id: int | None = Field(default=None, primary_key=True)
    # 标的代码。
    symbol: str
    # K 线时间（UTC）。
    timestamp: datetime
    # 开盘价。
    open: float
    # 最高价。
    high: float
    # 最低价。
    low: float
    # 收盘价。
    close: float
    # 成交量。
    volume: float
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
