"""持仓应用服务。"""

from csv import DictReader
from dataclasses import dataclass
from pathlib import Path

from hiveflow.domain.aggregates.position_book import PositionBook
from hiveflow.domain.aggregates.position_book import PositionInput
from hiveflow.domain.positions import Position
from hiveflow.domain.repositories import PositionRepository
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
