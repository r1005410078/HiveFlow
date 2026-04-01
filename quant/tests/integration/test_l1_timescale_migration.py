from pathlib import Path


def test_timescale_migration_contains_required_tables() -> None:
    """验证 L1 Timescale 迁移脚本包含必需扩展、表和关键约束。"""
    root = Path(__file__).resolve().parents[2]
    migration = root / "db" / "migrations" / "0001_l1_timescale.sql"

    assert migration.exists(), "missing migration: quant/db/migrations/0001_l1_timescale.sql"

    sql = migration.read_text(encoding="utf-8").lower()
    assert "create extension if not exists timescaledb" in sql
    assert "create table if not exists bars" in sql
    assert "create table if not exists sync_runs" in sql
    assert "create table if not exists sync_checkpoints" in sql
    assert "primary key (symbol, timeframe, bar_time)" in sql
    assert "on conflict (symbol, timeframe, bar_time)" in sql
    assert "create_hypertable('bars','bar_time'" in sql
