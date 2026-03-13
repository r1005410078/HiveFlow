"""持仓应用服务。"""

from csv import DictReader
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import select

from hiveflow.domain.aggregates.position_book import PositionBook
from hiveflow.domain.aggregates.position_book import PositionInput
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.positions import Position
from hiveflow.domain.repositories import PositionRepository
from hiveflow.db import create_all_tables, get_session
from hiveflow.infrastructure.repositories.sqlmodel_position_repository import (
    SQLModelPositionRepository,
)


@dataclass(frozen=True)
class PositionView:
    symbol: str
    quantity: float
    market_value: float
    weight: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "symbol": self.symbol,
            "quantity": round(self.quantity, 6),
            "market_value": round(self.market_value, 2),
            "weight": round(self.weight, 6),
        }


@dataclass(frozen=True)
class ImportResult:
    imported: int
    mode: str
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"imported": self.imported, "mode": self.mode, "file": self.file}


@dataclass(frozen=True)
class TemplateResult:
    file: str
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        return {"file": self.file, "rows": self.rows}


@dataclass(frozen=True)
class PositionDriftView:
    """单个标的的持仓偏离视图。"""

    # 标的代码。
    symbol: str
    # 实际权重。
    actual_weight: float
    # 目标权重。
    target_weight: float
    # 偏离值（实际 - 目标）。
    delta: float
    # 偏离等级：low / medium / high。
    drift_level: str
    # 建议动作：buy / sell / hold。
    action: str

    def to_dict(self) -> dict[str, float | str]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "symbol": self.symbol,
            "actual_weight": round(self.actual_weight, 6),
            "target_weight": round(self.target_weight, 6),
            "delta": round(self.delta, 6),
            "drift_level": self.drift_level,
            "action": self.action,
        }


def _get_position_repository() -> PositionRepository:
    """获取持仓仓储实现。"""
    return SQLModelPositionRepository()


def add_position(symbol: str, quantity: float, market_value: float, weight: float) -> None:
    """新增一条持仓记录。"""
    repository = _get_position_repository()
    repository.add(
        Position(
            symbol=symbol.upper(),
            quantity=quantity,
            market_value=market_value,
            weight=weight,
        )
    )


def list_positions() -> list[PositionView]:
    """读取并返回所有持仓（按 symbol 排序）。"""
    repository = _get_position_repository()
    positions = repository.list()

    return [
        PositionView(
            symbol=position.symbol,
            quantity=position.quantity,
            market_value=position.market_value,
            weight=position.weight,
        )
        for position in sorted(positions, key=lambda item: item.symbol)
    ]


def import_positions_from_csv(file: Path, mode: str) -> ImportResult:
    """从 CSV 导入持仓记录。"""
    if mode not in {"append", "replace"}:
        raise ValueError("导入模式仅支持 append 或 replace。")
    if not file.exists() or not file.is_file():
        raise FileNotFoundError("CSV 文件不存在或不可读取。")

    with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = DictReader(csv_file)
        required = {"symbol", "quantity", "market_value", "weight"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("CSV 列必须包含：symbol, quantity, market_value, weight")

        rows = [
            PositionInput(
                symbol=(row.get("symbol") or "").strip(),
                quantity=float(row["quantity"]),
                market_value=float(row["market_value"]),
                weight=float(row["weight"]),
            )
            for row in reader
        ]

    repository = _get_position_repository()
    aggregate = PositionBook(repository=repository)
    imported = aggregate.apply_import(rows=rows, mode=mode)

    return ImportResult(imported=imported, mode=mode, file=str(file))


def export_positions_template(file: Path) -> TemplateResult:
    """导出持仓 CSV 模板文件。"""
    file.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "symbol,quantity,market_value,weight\n"
        "BTC,1.5,120000,0.6\n"
        "ETH,2,20000,0.2\n"
    )
    file.write_text(template, encoding="utf-8")
    return TemplateResult(file=str(file), rows=2)


def analyze_positions_drift(strategy_name: str | None = None) -> list[PositionDriftView]:
    """分析实际持仓与目标持仓偏离。

    Args:
        strategy_name: 策略名称。传 None 时聚合全部目标持仓。

    Returns:
        list[PositionDriftView]: 按偏离绝对值倒序输出。
    """
    create_all_tables()
    with get_session() as session:
        positions = session.exec(select(Position)).all()
        targets = session.exec(select(TargetAllocation)).all()

    actual = {item.symbol: item.weight for item in positions}

    filtered_targets = (
        [item for item in targets if item.strategy_name == strategy_name]
        if strategy_name
        else targets
    )
    target: dict[str, float] = {}
    for item in filtered_targets:
        target[item.symbol] = target.get(item.symbol, 0.0) + item.target_weight

    symbols = sorted(set(actual) | set(target))
    result: list[PositionDriftView] = []
    for symbol in symbols:
        actual_weight = actual.get(symbol, 0.0)
        target_weight = target.get(symbol, 0.0)
        delta = round(actual_weight - target_weight, 10)
        abs_delta = abs(delta)
        if abs_delta >= 0.10:
            drift_level = "high"
        elif abs_delta >= 0.05:
            drift_level = "medium"
        else:
            drift_level = "low"

        if delta > 0:
            action = "sell"
        elif delta < 0:
            action = "buy"
        else:
            action = "hold"

        result.append(
            PositionDriftView(
                symbol=symbol,
                actual_weight=actual_weight,
                target_weight=target_weight,
                delta=delta,
                drift_level=drift_level,
                action=action,
            )
        )

    return sorted(result, key=lambda item: abs(item.delta), reverse=True)
