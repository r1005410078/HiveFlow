"""风险信号应用服务。"""

from csv import DictReader
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.risk import RiskSignal


@dataclass(frozen=True)
class RiskSignalView:
    # 标的代码。
    symbol: str
    # 风险水位标签。
    waterline: str
    # 风险评分（数值化）。
    score: float
    # 风险备注。
    note: str | None

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "symbol": self.symbol,
            "waterline": self.waterline,
            "score": round(self.score, 6),
            "note": self.note,
        }


@dataclass(frozen=True)
class RiskImportResult:
    # 实际导入条数。
    imported: int
    # 导入模式：append/replace。
    mode: str
    # 导入文件路径。
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"imported": self.imported, "mode": self.mode, "file": self.file}


@dataclass(frozen=True)
class RiskTemplateResult:
    # 模板文件输出路径。
    file: str
    # 模板示例行数（不含表头）。
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        return {"file": self.file, "rows": self.rows}


def list_risk_signals() -> list[RiskSignalView]:
    """读取并返回所有风险信号（按 symbol 排序）。

    Returns:
        list[RiskSignalView]: 风险信号视图列表。
    """
    create_all_tables()
    with get_session() as session:
        signals = session.exec(select(RiskSignal)).all()
    return [
        RiskSignalView(
            symbol=signal.symbol,
            waterline=signal.waterline,
            score=signal.score,
            note=signal.note,
        )
        for signal in sorted(signals, key=lambda item: item.symbol)
    ]


def import_risk_signals_from_csv(file: Path, mode: str) -> RiskImportResult:
    """从 CSV 导入风险信号。

    Args:
        file: CSV 文件路径。
        mode: 导入模式，仅支持 append 或 replace。

    Returns:
        RiskImportResult: 导入结果摘要。
    """
    if mode not in {"append", "replace"}:
        raise ValueError("导入模式仅支持 append 或 replace。")
    if not file.exists() or not file.is_file():
        raise FileNotFoundError("CSV 文件不存在或不可读取。")

    create_all_tables()
    imported = 0
    with get_session() as session:
        if mode == "replace":
            session.exec(delete(RiskSignal))

        with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = DictReader(csv_file)
            required = {"symbol", "waterline", "score", "note"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError("CSV 列必须包含：symbol, waterline, score, note")

            for row in reader:
                symbol = (row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                session.add(
                    RiskSignal(
                        symbol=symbol,
                        waterline=(row.get("waterline") or "low").strip().lower(),
                        score=float(row.get("score") or 0.0),
                        note=(row.get("note") or "").strip() or None,
                    )
                )
                imported += 1
        session.commit()

    return RiskImportResult(imported=imported, mode=mode, file=str(file))


def export_risk_template(file: Path) -> RiskTemplateResult:
    """导出风险信号 CSV 模板。

    Args:
        file: 模板输出路径。

    Returns:
        RiskTemplateResult: 模板生成结果。
    """
    file.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "symbol,waterline,score,note\n"
        "BTC,high,0.82,波动放大且接近阻力位\n"
        "ETH,medium,0.55,短期震荡\n"
    )
    file.write_text(template, encoding="utf-8")
    return RiskTemplateResult(file=str(file), rows=2)
