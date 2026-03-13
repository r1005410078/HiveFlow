"""目标持仓应用服务。"""

from csv import DictReader
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.strategies import Strategy
from hiveflow.services.allocation_engine import generate_target_allocations


@dataclass(frozen=True)
class TargetAllocationView:
    # 策略名称。
    strategy_name: str
    # 标的代码。
    symbol: str
    # 目标权重（0~1）。
    target_weight: float

    def to_dict(self) -> dict[str, str | float]:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "target_weight": round(self.target_weight, 6),
        }


@dataclass(frozen=True)
class TargetImportResult:
    # 实际导入条数。
    imported: int
    # 导入模式：append/replace。
    mode: str
    # 导入文件路径。
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"imported": self.imported, "mode": self.mode, "file": self.file}


@dataclass(frozen=True)
class TargetTemplateResult:
    # 模板文件输出路径。
    file: str
    # 模板示例行数（不含表头）。
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        return {"file": self.file, "rows": self.rows}


@dataclass(frozen=True)
class TargetGenerateResult:
    # 生成所使用的策略名称。
    strategy: str
    # 策略分类。
    category: str
    # 生成条数。
    generated: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "strategy": self.strategy,
            "category": self.category,
            "generated": self.generated,
        }


def list_target_allocations() -> list[TargetAllocationView]:
    """读取并返回目标持仓（按策略名和标的排序）。

    Returns:
        list[TargetAllocationView]: 目标持仓视图列表。
    """
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
    """从 CSV 导入目标持仓。

    Args:
        file: CSV 文件路径。
        mode: 导入模式，仅支持 append 或 replace。

    Returns:
        TargetImportResult: 导入结果摘要。
    """
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
    """导出目标持仓 CSV 模板。

    Args:
        file: 模板输出路径。

    Returns:
        TargetTemplateResult: 模板生成结果。
    """
    file.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "strategy_name,symbol,target_weight\n"
        "进攻型默认策略,BTC,0.50\n"
        "进攻型默认策略,ETH,0.30\n"
        "进攻型默认策略,USDT,0.20\n"
    )
    file.write_text(template, encoding="utf-8")
    return TargetTemplateResult(file=str(file), rows=3)


def _default_allocations_for_category(category: str) -> dict[str, float]:
    """按策略分类返回默认目标权重配置。"""
    normalized = category.strip()
    presets: dict[str, dict[str, float]] = {
        "进攻型": {"BTC": 0.50, "ETH": 0.30, "USDT": 0.20},
        "防守型": {"BTC": 0.20, "ETH": 0.20, "USDT": 0.60},
        "长期型": {"BTC": 0.40, "ETH": 0.40, "USDT": 0.20},
    }
    return presets.get(normalized, {"BTC": 0.34, "ETH": 0.33, "USDT": 0.33})


def generate_targets_for_strategy(strategy_name: str) -> TargetGenerateResult:
    """根据策略自动生成目标持仓（覆盖该策略已有目标）。"""
    create_all_tables()
    with get_session() as session:
        strategy = session.exec(select(Strategy).where(Strategy.name == strategy_name)).first()
        if strategy is None:
            raise ValueError("策略不存在，无法生成目标持仓。")

        session.exec(
            delete(TargetAllocation).where(TargetAllocation.strategy_name == strategy_name)
        )
        allocations = _default_allocations_for_category(strategy.category)
        targets = generate_target_allocations(strategy_name=strategy_name, allocations=allocations)
        for item in targets:
            session.add(item)
        session.commit()

        return TargetGenerateResult(
            strategy=strategy_name,
            category=strategy.category,
            generated=len(targets),
        )
