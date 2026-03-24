"""A 股行情同步与持仓导入测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.domain.market import CN_A_SHARE


# ------------------------------------------------------------------ #
# Chunk 2 Task 6 — cn_sync
# ------------------------------------------------------------------ #

def _fake_bars(symbol: str = "000001.SZ"):
    from datetime import datetime, timezone
    from hiveflow.domain.market_data import MarketBar
    return [
        MarketBar(
            symbol=symbol,
            timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            open=10.0 + i,
            high=11.0 + i,
            low=9.0 + i,
            close=10.5 + i,
            volume=1_000_000.0,
            market=CN_A_SHARE,
        )
        for i in range(3)
    ]


def test_sync_cn_market_data_writes_bars_to_db(tmp_path: Path) -> None:
    """sync_cn_market_data 应将 MarketBar 写入数据库。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url, cn_market_data_source="akshare")
    create_all_tables(settings)

    fake_provider = MagicMock()
    fake_provider.fetch_bars.return_value = _fake_bars("000001.SZ")

    with patch(
        "hiveflow.application.cn_sync.CNMarketDataProvider",
        return_value=fake_provider,
    ):
        from hiveflow.application.cn_sync import sync_cn_market_data
        result = sync_cn_market_data(
            symbols=["000001.SZ"], days=30, settings=settings
        )

    assert result.imported == 3
    assert result.symbols == ["000001.SZ"]

    with get_session(settings) as session:
        bars = session.exec(
            select(MarketBar).where(MarketBar.symbol == "000001.SZ")
        ).all()
    assert len(bars) == 3
    assert all(b.market == CN_A_SHARE for b in bars)


def test_sync_cn_market_data_result_fields(tmp_path: Path) -> None:
    """result 包含 imported / symbols / source 字段。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url, cn_market_data_source="tushare", tushare_token="tok")
    create_all_tables(settings)

    fake_provider = MagicMock()
    fake_provider.fetch_bars.return_value = _fake_bars()

    with patch("hiveflow.application.cn_sync.CNMarketDataProvider", return_value=fake_provider):
        from hiveflow.application.cn_sync import sync_cn_market_data
        result = sync_cn_market_data(symbols=["000001.SZ"], days=7, settings=settings)

    assert result.source == "tushare"
    assert "000001.SZ" in result.symbols
    d = result.to_dict()
    assert "imported" in d
    assert "symbols" in d
    assert "source" in d


# ------------------------------------------------------------------ #
# Chunk 3 Task 7 — import_cn_positions_from_csv
# ------------------------------------------------------------------ #

def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_import_cn_positions_valid_csv(tmp_path: Path) -> None:
    """正常 CSV 导入后，Position.market == 'cn_a_share'。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    from hiveflow.application.positions import import_cn_positions_from_csv
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv_file = _write_csv(
        tmp_path / "cn.csv",
        "代码,数量,市值\n"
        "000001.SZ,1000,13200\n"
        "600000.SH,500,4600\n",
    )

    result = import_cn_positions_from_csv(str(csv_file), settings=settings)
    assert result.imported == 2

    with get_session(settings) as session:
        positions = session.exec(select(Position)).all()
    symbols = {p.symbol for p in positions}
    assert "000001.SZ" in symbols
    assert "600000.SH" in symbols
    assert all(p.market == CN_A_SHARE for p in positions)


def test_import_cn_positions_duplicate_overwrite(tmp_path: Path) -> None:
    """重复导入同一 symbol 时覆盖写入，不重复堆积。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    from hiveflow.application.positions import import_cn_positions_from_csv
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv1 = _write_csv(tmp_path / "cn1.csv", "代码,数量,市值\n000001.SZ,1000,13200\n")
    import_cn_positions_from_csv(str(csv1), settings=settings)

    csv2 = _write_csv(tmp_path / "cn2.csv", "代码,数量,市值\n000001.SZ,2000,22000\n")
    import_cn_positions_from_csv(str(csv2), settings=settings)

    with get_session(settings) as session:
        rows = session.exec(select(Position).where(Position.symbol == "000001.SZ")).all()
    assert len(rows) == 1
    assert rows[0].quantity == 2000.0


def test_import_cn_positions_crypto_symbol_rejected(tmp_path: Path) -> None:
    """CSV 中包含 BTC（加密 symbol）时应报错拒绝导入。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables
    from hiveflow.application.positions import import_cn_positions_from_csv

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv_file = _write_csv(
        tmp_path / "bad.csv",
        "代码,数量,市值\nBTC,0.5,25000\n",
    )

    with pytest.raises(ValueError, match="非 A 股 symbol"):
        import_cn_positions_from_csv(str(csv_file), settings=settings)


def test_import_cn_positions_market_mismatch_rejected(tmp_path: Path) -> None:
    """CSV market 列与 detect_market 推断结果不一致时应报错。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables
    from hiveflow.application.positions import import_cn_positions_from_csv

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv_file = _write_csv(
        tmp_path / "mismatch.csv",
        "代码,数量,市值,市场\n"
        "000001.SZ,1000,13200,crypto\n",  # market 列与 symbol 不符
    )

    with pytest.raises(ValueError, match="market 字段不一致"):
        import_cn_positions_from_csv(str(csv_file), settings=settings)
