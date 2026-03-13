"""持仓聚合边界。"""

from dataclasses import dataclass

from hiveflow.domain.positions import Position
from hiveflow.domain.repositories import PositionRepository


@dataclass(frozen=True)
class PositionInput:
    """导入时的持仓输入数据。"""

    # 标的代码，如 BTC / ETH / AAPL。
    symbol: str
    # 持仓数量。
    quantity: float
    # 持仓市值。
    market_value: float
    # 持仓权重（0~1）。
    weight: float


class PositionBook:
    """持仓聚合。

    负责持仓导入场景下的业务边界：
    - append：追加写入
    - replace：原子替换全部持仓
    """

    def __init__(self, repository: PositionRepository) -> None:
        # 持仓仓储接口，实现可替换（SQLite/HTTP/Mock）。
        self._repository = repository

    def apply_import(self, rows: list[PositionInput], mode: str) -> int:
        """应用导入数据并返回导入条数。"""
        if mode not in {"append", "replace"}:
            raise ValueError("导入模式仅支持 append 或 replace。")

        positions = [
            Position(
                symbol=row.symbol.strip().upper(),
                quantity=row.quantity,
                market_value=row.market_value,
                weight=row.weight,
            )
            for row in rows
            if row.symbol.strip()
        ]

        if mode == "replace":
            self._repository.replace_all(positions)
        else:
            self._repository.add_many(positions)
        return len(positions)
