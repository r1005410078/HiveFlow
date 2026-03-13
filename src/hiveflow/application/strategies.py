"""策略应用服务。"""

from __future__ import annotations

from csv import DictReader
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.strategies import Strategy


@dataclass(frozen=True)
class StrategyView:
    """策略只读视图。"""

    # 策略名称。
    name: str
    # 策略分类。
    category: str
    # 策略维度。
    dimension: str | None
    # 策略核心理念。
    thesis: str
    # 适用市场环境。
    market_regime: str | None
    # 回测摘要。
    backtest_summary: str | None

    def to_dict(self) -> dict[str, str | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "name": self.name,
            "category": self.category,
            "strategy_type": self.category,
            "dimension": self.dimension,
            "thesis": self.thesis,
            "market_regime": self.market_regime,
            "backtest_summary": self.backtest_summary,
        }


@dataclass(frozen=True)
class StrategyImportResult:
    """策略导入结果。"""

    # 实际导入条数。
    imported: int
    # 导入模式：append/replace。
    mode: str
    # 导入文件路径。
    file: str

    def to_dict(self) -> dict[str, int | str]:
        """转换为字典，便于 JSON 输出。"""
        return {"imported": self.imported, "mode": self.mode, "file": self.file}


@dataclass(frozen=True)
class StrategyTemplateResult:
    """策略模板导出结果。"""

    # 模板文件输出路径。
    file: str
    # 模板示例行数（不含表头）。
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        """转换为字典，便于 JSON 输出。"""
        return {"file": self.file, "rows": self.rows}


def list_strategies() -> list[StrategyView]:
    """读取并返回策略列表（按分类与名称排序）。"""
    create_all_tables()
    with get_session() as session:
        rows = session.exec(select(Strategy)).all()

    return [
        StrategyView(
            name=row.name,
            category=row.category,
            dimension=row.dimension,
            thesis=row.thesis,
            market_regime=row.market_regime,
            backtest_summary=row.backtest_summary,
        )
        for row in sorted(rows, key=lambda item: (item.category, item.name))
    ]


def import_strategies_from_csv(file: Path, mode: str) -> StrategyImportResult:
    """从 CSV 导入策略。"""
    if mode not in {"append", "replace"}:
        raise ValueError("导入模式仅支持 append 或 replace。")
    if not file.exists() or not file.is_file():
        raise FileNotFoundError("CSV 文件不存在或不可读取。")

    create_all_tables()
    imported = 0
    with get_session() as session:
        if mode == "replace":
            session.exec(delete(Strategy))

        with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = DictReader(csv_file)
            fieldnames = set(reader.fieldnames or [])
            required = {"name", "thesis", "market_regime", "backtest_summary"}
            has_type = "category" in fieldnames or "strategy_type" in fieldnames
            if not reader.fieldnames or not required.issubset(fieldnames) or not has_type:
                raise ValueError(
                    "CSV 列必须包含：name, thesis, market_regime, backtest_summary，且需包含 category 或 strategy_type"
                )

            for row in reader:
                name = (row.get("name") or "").strip()
                category = (row.get("category") or row.get("strategy_type") or "").strip()
                thesis = (row.get("thesis") or "").strip()
                if not name or not category or not thesis:
                    continue

                session.add(
                    Strategy(
                        name=name,
                        category=category,
                        dimension=(row.get("dimension") or "").strip() or None,
                        thesis=thesis,
                        market_regime=(row.get("market_regime") or "").strip() or None,
                        backtest_summary=(row.get("backtest_summary") or "").strip() or None,
                    )
                )
                imported += 1
        session.commit()

    return StrategyImportResult(imported=imported, mode=mode, file=str(file))


def export_strategy_template(file: Path) -> StrategyTemplateResult:
    """导出策略 CSV 模板。"""
    file.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
        "进攻突破策略,进攻型,顺势突破+风控,趋势|动量,趋势市,年化 18%\n"
        "防守轮动策略,防守型,低波动防守轮动,波动|防守,震荡市,最大回撤 8%\n"
    )
    file.write_text(template, encoding="utf-8")
    return StrategyTemplateResult(file=str(file), rows=2)
