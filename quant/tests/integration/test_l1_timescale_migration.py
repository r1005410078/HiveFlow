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


def test_timescale_migration_adds_sync_run_columns_incrementally() -> None:
    """验证 sync_runs 新字段通过增量迁移安全演进。"""
    root = Path(__file__).resolve().parents[2]
    migration = root / "db" / "migrations" / "0002_sync_runs_add_selection_mode_written_rows.sql"
    manifest_migration = root / "db" / "migrations" / "0003_sync_runs_add_manifest_ids.sql"

    assert migration.exists(), "missing migration: quant/db/migrations/0002_sync_runs_add_selection_mode_written_rows.sql"
    assert manifest_migration.exists(), "missing migration: quant/db/migrations/0003_sync_runs_add_manifest_ids.sql"

    sql = migration.read_text(encoding="utf-8").lower()
    manifest_sql = manifest_migration.read_text(encoding="utf-8").lower()
    assert "alter table sync_runs" in sql
    assert "add column if not exists selection_mode text" in sql
    assert "update sync_runs" in sql
    assert "set selection_mode = coalesce(selection_mode, 'default')" in sql
    assert "alter column selection_mode set default 'default'" in sql
    assert "alter column selection_mode set not null" in sql
    assert "add column if not exists written_rows integer" in sql
    assert "set written_rows = coalesce(written_rows, 0)" in sql
    assert "alter column written_rows set default 0" in sql
    assert "alter column written_rows set not null" in sql
    assert "add column if not exists manifest_ids text[]" in manifest_sql
    assert "set manifest_ids = coalesce(manifest_ids, array[]::text[])" in manifest_sql
    assert "alter column manifest_ids set default array[]::text[]" in manifest_sql
    assert "alter column manifest_ids set not null" in manifest_sql
