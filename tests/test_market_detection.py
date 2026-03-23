"""detect_market 单元测试。"""
import pytest
from hiveflow.domain.market import CN_A_SHARE, CRYPTO, ANNUALIZATION_FACTOR, detect_market


def test_detect_market_cn_sh() -> None:
    assert detect_market("600000.SH") == CN_A_SHARE


def test_detect_market_cn_sz() -> None:
    assert detect_market("000001.SZ") == CN_A_SHARE


def test_detect_market_cn_bj() -> None:
    assert detect_market("830017.BJ") == CN_A_SHARE


def test_detect_market_case_insensitive() -> None:
    assert detect_market("600000.sh") == CN_A_SHARE


def test_detect_market_cn_with_whitespace() -> None:
    assert detect_market("  000001.SZ  ") == CN_A_SHARE


def test_detect_market_crypto_btc() -> None:
    assert detect_market("BTC") == CRYPTO


def test_detect_market_crypto_eth() -> None:
    assert detect_market("ETH") == CRYPTO


def test_detect_market_no_suffix() -> None:
    """6 位数字但没有 .SH/.SZ/.BJ 后缀 → crypto（不是 A 股）"""
    assert detect_market("000001") == CRYPTO


def test_detect_market_empty_string() -> None:
    assert detect_market("") == CRYPTO


def test_detect_market_does_not_raise_on_garbage() -> None:
    assert detect_market("!@#$%") == CRYPTO


def test_annualization_factor_crypto() -> None:
    assert ANNUALIZATION_FACTOR[CRYPTO] == 365


def test_annualization_factor_cn() -> None:
    assert ANNUALIZATION_FACTOR[CN_A_SHARE] == 252


# tests/test_market_detection.py — 在文件末尾追加

import os
import tempfile
from pathlib import Path


def test_lightweight_migration_adds_market_to_position(tmp_path: Path) -> None:
    """旧库（无 market 列）在迁移后可正常读写，存量数据 market 默认 'crypto'。"""
    db_path = tmp_path / "hiveflow.db"
    db_url = f"sqlite:///{db_path}"

    # 用 SQLite 直接建一张模拟旧 position 表（无 market 列）
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE position (id INTEGER PRIMARY KEY, symbol TEXT, "
        "quantity REAL DEFAULT 0, market_value REAL DEFAULT 0, weight REAL DEFAULT 0, "
        "updated_at TEXT)"
    )
    conn.execute("INSERT INTO position (symbol) VALUES ('BTC')")
    conn.commit()
    conn.close()

    from hiveflow.config import Settings
    settings = Settings(database_url=db_url)
    from hiveflow.db import create_all_tables
    create_all_tables(settings)

    # 迁移后 market 列存在，旧行默认为 'crypto'
    conn2 = sqlite3.connect(str(db_path))
    row = conn2.execute(
        "SELECT market FROM position WHERE symbol='BTC'"
    ).fetchone()
    conn2.close()
    assert row is not None
    assert row[0] == "crypto"


def test_new_position_market_field_readable(tmp_path: Path) -> None:
    """新写入的 Position 可以读出 market 字段。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    with get_session(settings) as session:
        session.add(Position(symbol="000001.SZ", quantity=100, market_value=1000, weight=0.1, market="cn_a_share"))
        session.commit()

    with get_session(settings) as session:
        pos = session.exec(select(Position).where(Position.symbol == "000001.SZ")).first()
    assert pos is not None
    assert pos.market == "cn_a_share"
