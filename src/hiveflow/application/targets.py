"""目标持仓应用服务。"""

from csv import DictReader
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation


@dataclass(frozen=True)
class TargetAllocationView:
    strategy_name: str
    symbol: str
    target_weight: float

    def to_dict(self) -> dict[str, str | float]:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "target_weight": round(self.target_weight, 6),
        }


@dataclass(frozen=True)
class TargetImportResult:
    imported: int
    mode: str
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"imported": self.imported, "mode": self.mode, "file": self.file}


@dataclass(frozen=True)
class TargetTemplateResult:
    file: str
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        return {"file": self.file, "rows": self.rows}


def list_target_allocations() -> list[TargetAllocationView]:
    """读取并返回目标持仓（按策略名和标的排序）。"""
    create_all_tables()
    with get_session() as session:
        rows = session.exec(select(TargetAllocation)).all()
    return [
        TargetAllocationView(
            strategy_name=row.strategy_name,
            symbol=row.symbol,
            target_weight=row.target_weight,
        )
        for row in sorted(rows, key=lambda item: (item.strategy_name, item.symbol))
    ]


def import_target_allocations_from_csv(file: Path, mode: str) -> TargetImportResult:
    """从 CSV 导入目标持仓。"""
    if mode not in {"append", "replace"}:
        raise ValueError("导入模式仅支持 append 或 replace。")
    if not file.exists() or not file.is_file():
        raise FileNotFoundError("CSV 文件不存在或不可读取。")

    create_all_tables()
    imported = 0
    with get_session() as session:
        if mode == "replace":
            session.exec(delete(TargetAllocation))

        with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = DictReader(csv_file)
            required = {"strategy_name", "symbol", "target_weight"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError("CSV 列必须包含：strategy_name, symbol, target_weight")

            for row in reader:
                strategy_name = (row.get("strategy_name") or "").strip()
                symbol = (row.get("symbol") or "").strip().upper()
                if not strategy_name or not symbol:
                    continue
                session.add(
                    TargetAllocation(
                        strategy_name=strategy_name,
                        symbol=symbol,
                        target_weight=float(row.get("target_weight") or 0.0),
                    )
                )
                imported += 1
        session.commit()

    return TargetImportResult(imported=imported, mode=mode, file=str(file))


def export_target_template(file: Path) -> TargetTemplateResult:
    """导出目标持仓 CSV 模板。"""
    file.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "strategy_name,symbol,target_weight\n"
        "进攻型默认策略,BTC,0.50\n"
        "进攻型默认策略,ETH,0.30\n"
        "进攻型默认策略,USDT,0.20\n"
    )
    file.write_text(template, encoding="utf-8")
    return TargetTemplateResult(file=str(file), rows=3)

