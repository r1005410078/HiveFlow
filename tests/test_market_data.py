from pathlib import Path

import pytest

from hiveflow.application.market_data import export_market_data_template
from hiveflow.application.market_data import import_market_data_csv
from hiveflow.application.market_data import list_market_bars
from hiveflow.application.market_data import summarize_market_data
from hiveflow.application.market_data import validate_market_data_csv


def test_export_market_data_template_creates_file(tmp_path: Path) -> None:
    template_path = tmp_path / "prices.csv"
    result = export_market_data_template(file=template_path)
    assert template_path.exists()
    assert result.rows == 4
    content = template_path.read_text(encoding="utf-8")
    assert "symbol,timestamp,open,high,low,close,volume" in content
    assert "BTC,2026-03-13T01:00:00Z" in content
    assert "ETH,2026-03-13T01:00:00Z" in content


def test_validate_market_data_csv_accepts_valid_utc_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(
        (
            "symbol,timestamp,open,high,low,close,volume\n"
            "BTC,2026-03-13T00:00:00Z,100,110,95,105,1000\n"
            "BTC,2026-03-13T01:00:00Z,105,112,101,111,1200\n"
        ),
        encoding="utf-8",
    )
    result = validate_market_data_csv(file=csv_path)
    assert result.valid is True
    assert result.rows == 2
    assert result.errors == []


def test_validate_market_data_csv_rejects_missing_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad-prices.csv"
    csv_path.write_text(
        "symbol,timestamp,open,close\nBTC,2026-03-13T00:00:00Z,100,105\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CSV 列必须包含"):
        validate_market_data_csv(file=csv_path)


def test_validate_market_data_csv_rejects_non_utc_timestamp(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad-ts.csv"
    csv_path.write_text(
        (
            "symbol,timestamp,open,high,low,close,volume\n"
            "BTC,2026-03-13T08:00:00+08:00,100,110,95,105,1000\n"
        ),
        encoding="utf-8",
    )
    result = validate_market_data_csv(file=csv_path)
    assert result.valid is False
    assert result.rows == 0
    assert any("timestamp 必须是 UTC" in item for item in result.errors)


def test_import_market_data_and_list_summary(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "market-data.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(
        (
            "symbol,timestamp,open,high,low,close,volume\n"
            "BTC,2026-03-13T00:00:00Z,100,110,95,105,1000\n"
            "BTC,2026-03-13T01:00:00Z,105,112,101,111,1200\n"
            "ETH,2026-03-13T00:00:00Z,50,55,45,50,2000\n"
        ),
        encoding="utf-8",
    )
    import_result = import_market_data_csv(file=csv_path, mode="replace")
    assert import_result.imported == 3

    bars = list_market_bars(symbol="BTC", limit=10)
    assert len(bars) == 2
    assert bars[0].symbol == "BTC"

    summary = summarize_market_data()
    assert summary.symbols_count == 2
    assert summary.bars_count == 3
