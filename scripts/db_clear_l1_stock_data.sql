-- 清空 L1 行情与同步元数据，便于重新测试 data sync（保留表结构）
-- 使用一条 TRUNCATE ... CASCADE，避免 sync_run_symbol_failures → sync_runs 外键顺序问题
BEGIN;
TRUNCATE TABLE
  sync_run_symbol_failures,
  sync_runs,
  sync_checkpoints,
  bars
  CASCADE;
COMMIT;
