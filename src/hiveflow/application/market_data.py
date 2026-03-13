"""行情数据契约与校验服务。"""

from __future__ import annotations

from csv import DictReader
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.market_data import MarketBar


REQUIRED_COLUMNS = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class MarketDataTemplateResult:
    """行情模板导出结果。"""

    # 输出文件路径。
    file: str
    # 示例行数（不含表头）。
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        """转换为字典，便于 JSON 输出。"""
        return {"file": self.file, "rows": self.rows}


@dataclass(frozen=True)
class MarketDataValidateResult:
    """行情文件校验结果。"""

    # 文件路径。
    file: str
    # 是否通过校验。
    valid: bool
    # 有效数据行数。
    rows: int
    # 错误详情列表。
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "file": self.file,
            "valid": self.valid,
            "rows": self.rows,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class MarketDataImportResult:
    """行情导入结果。"""

    file: str
    mode: str
    imported: int

    def to_dict(self) -> dict[str, int | str]:
        """转换为字典，便于 JSON 输出。"""
        return {"file": self.file, "mode": self.mode, "imported": self.imported}


@dataclass(frozen=True)
class MarketBarView:
    """行情记录视图。"""

    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, float | str]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "open": round(self.open, 6),
            "high": round(self.high, 6),
            "low": round(self.low, 6),
            "close": round(self.close, 6),
            "volume": round(self.volume, 6),
        }


@dataclass(frozen=True)
class MarketDataSummary:
    """行情汇总。"""

    symbols_count: int
    bars_count: int
    latest_timestamp: str | None

    def to_dict(self) -> dict[str, int | str | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "symbols_count": self.symbols_count,
            "bars_count": self.bars_count,
            "latest_timestamp": self.latest_timestamp,
        }


def export_market_data_template(file: Path) -> MarketDataTemplateResult:
    """导出行情 CSV 模板。"""
    file.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "symbol,timestamp,open,high,low,close,volume\n"
        "BTC,2026-03-13T00:00:00Z,100000,102000,99000,101500,1200\n"
        "BTC,2026-03-13T01:00:00Z,101500,103200,100800,102900,1400\n"
        "ETH,2026-03-13T00:00:00Z,3000,3100,2950,3080,8500\n"
        "ETH,2026-03-13T01:00:00Z,3080,3150,3050,3120,9100\n"
    )
    file.write_text(template, encoding="utf-8")
    return MarketDataTemplateResult(file=str(file), rows=4)


def _parse_utc_timestamp(value: str) -> datetime:
    """解析并校验 UTC 时间戳。"""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp 必须带时区且为 UTC。")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp 必须是 UTC（使用 Z 或 +00:00）。")
    return parsed


def validate_market_data_csv(file: Path) -> MarketDataValidateResult:
    """校验行情 CSV 是否符合契约。"""
    if not file.exists() or not file.is_file():
        raise FileNotFoundError("CSV 文件不存在或不可读取。")

    errors: list[str] = []
    valid_rows = 0
    with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = DictReader(csv_file)
        fieldnames = reader.fieldnames or []
        if not set(REQUIRED_COLUMNS).issubset(set(fieldnames)):
            required_text = ", ".join(REQUIRED_COLUMNS)
            raise ValueError(f"CSV 列必须包含：{required_text}")

        for idx, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                errors.append(f"第 {idx} 行：symbol 不能为空。")
                continue

            try:
                _parse_utc_timestamp(row.get("timestamp") or "")
                open_p = float(row.get("open") or 0.0)
                high_p = float(row.get("high") or 0.0)
                low_p = float(row.get("low") or 0.0)
                close_p = float(row.get("close") or 0.0)
                volume = float(row.get("volume") or 0.0)
            except ValueError as exc:
                errors.append(f"第 {idx} 行：{exc}")
                continue

            if high_p < low_p:
                errors.append(f"第 {idx} 行：high 不能小于 low。")
                continue
            if min(open_p, high_p, low_p, close_p, volume) < 0:
                errors.append(f"第 {idx} 行：价格和成交量不能为负数。")
                continue
            valid_rows += 1

    return MarketDataValidateResult(
        file=str(file),
        valid=len(errors) == 0,
        rows=valid_rows,
        errors=errors,
    )


def import_market_data_csv(file: Path, mode: str = "append") -> MarketDataImportResult:
    """导入行情 CSV 到数据库。"""
    if mode not in {"append", "replace"}:
        raise ValueError("导入模式仅支持 append 或 replace。")

    validation = validate_market_data_csv(file=file)
    if not validation.valid:
        raise ValueError(f"CSV 校验失败：{validation.errors[0]}")

    create_all_tables()
    imported = 0
    with get_session() as session:
        if mode == "replace":
            session.exec(delete(MarketBar))

        with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = DictReader(csv_file)
            for row in reader:
                symbol = (row.get("symbol") or "").strip().upper()
                ts = _parse_utc_timestamp(row.get("timestamp") or "")
                session.exec(
                    delete(MarketBar).where(
                        (MarketBar.symbol == symbol) & (MarketBar.timestamp == ts)
                    )
                )
                session.add(
                    MarketBar(
                        symbol=symbol,
                        timestamp=ts,
                        open=float(row.get("open") or 0.0),
                        high=float(row.get("high") or 0.0),
                        low=float(row.get("low") or 0.0),
                        close=float(row.get("close") or 0.0),
                        volume=float(row.get("volume") or 0.0),
                    )
                )
                imported += 1
        session.commit()
    return MarketDataImportResult(file=str(file), mode=mode, imported=imported)


def list_market_bars(symbol: str | None = None, limit: int = 100) -> list[MarketBarView]:
    """列出行情记录。"""
    create_all_tables()
    with get_session() as session:
        rows = session.exec(select(MarketBar)).all()
    if symbol:
        rows = [item for item in rows if item.symbol == symbol.upper()]
    ordered = sorted(rows, key=lambda item: (item.symbol, item.timestamp), reverse=True)
    if limit > 0:
        ordered = ordered[:limit]
    return [
        MarketBarView(
            symbol=item.symbol,
            timestamp=item.timestamp.isoformat().replace("+00:00", "Z"),
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=item.volume,
        )
        for item in ordered
    ]


def summarize_market_data() -> MarketDataSummary:
    """汇总行情数据状态。"""
    create_all_tables()
    with get_session() as session:
        rows = session.exec(select(MarketBar)).all()
    if not rows:
        return MarketDataSummary(symbols_count=0, bars_count=0, latest_timestamp=None)
    latest = max(item.timestamp for item in rows)
    return MarketDataSummary(
        symbols_count=len({item.symbol for item in rows}),
        bars_count=len(rows),
        latest_timestamp=latest.isoformat().replace("+00:00", "Z"),
    )
