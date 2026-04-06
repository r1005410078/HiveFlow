# G2 实验治理 Phase 1 — 参数版本快照设计

## Goal

实现 G2 实验治理 Phase 1：将散落在各 application service 中的硬编码策略参数（L2/L4/L5/L5.5/L6/L7，共约 30 个）统一快照到 DB，每次 `run_daily` 自动记录本次使用的参数集（`config_id` + 各参数行 + 原因备注），并提供 HTTP 查询接口与 CLI 命令（`hf config snapshot/list/get`）。

Phase 1 为纯审计模式：代码中硬编码常量不变，DB 仅记录"此刻用了哪套参数"；Phase 2（配置驱动）将从 DB 读取 active 配置替代硬编码，本期不实现。

## Architecture

```
CLI: hf config snapshot [--note TEXT]
     hf config list [--layer LAYER] [--limit N]
     hf config get --config-id ID
  └─ POST /api/v1/experiment/config/snapshot
     GET  /api/v1/experiment/configs[?layer=...]
     GET  /api/v1/experiment/configs/{config_id}
       └─ get_experiment_config_service() [dependencies.py]
            └─ experiment_config_service.py
                 ├─ snapshot_current(note, bar_store)
                 │    ├─ 枚举全量参数（见参数表）
                 │    ├─ 生成 config_id = uuid4()
                 │    └─ INSERT INTO experiment_configs (批量)
                 ├─ list_configs(layer?, limit)
                 │    └─ SELECT DISTINCT config_id + metadata
                 └─ get_config(config_id)
                      └─ SELECT * WHERE config_id = ?

run_daily 在开头插入：
  experiment_config_service.snapshot_current(note="daily_run", bar_store=bar_store)
```

## DB Schema

```sql
-- quant/db/migrations/0006_experiment_configs.sql
CREATE TABLE IF NOT EXISTS experiment_configs (
    config_id   TEXT        NOT NULL,
    layer       TEXT        NOT NULL,   -- 'l2','l4','l5','l5.5','l6','l7'
    param_key   TEXT        NOT NULL,
    param_value FLOAT       NOT NULL,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  TEXT        NOT NULL DEFAULT 'system',
    PRIMARY KEY (config_id, layer, param_key)
);
CREATE INDEX IF NOT EXISTS idx_experiment_configs_layer_created
    ON experiment_configs (layer, created_at DESC);
```

- `config_id`：UUID，同一次 `snapshot_current()` 产生的所有参数行共享同一 `config_id`
- `bar_store=None` 时：跳过写入，`snapshot_current()` 仍返回 `config_id`（内存中的快照，不落库）
- 不支持更新/删除，历史快照仅追加

## 参数范围（Phase 1 全量，共约 30 个）

| layer | param_key | 当前默认值 | 来源文件 |
|-------|-----------|-----------|---------|
| l2 | `factor_weight_momentum_20` | 0.25 | `l2_decision_service.py` SCORE_PROFILES["l2-score-v1.1"] |
| l2 | `factor_weight_inv_volatility_20` | 0.15 | 同上 |
| l2 | `factor_weight_turnover_rate` | 0.10 | 同上 |
| l2 | `factor_weight_max_drawdown_60` | 0.20 | 同上 |
| l2 | `factor_weight_trend_stability_20` | 0.15 | 同上 |
| l2 | `factor_weight_relative_strength_vs_index` | 0.15 | 同上 |
| l4 | `w_max` | 0.30 | `portfolio_optimize_service.py` |
| l4 | `ind_max` | 0.40 | `portfolio_optimize_service.py` |
| l4 | `lambda_risk` | 1.0 | `portfolio_optimize_service.py` |
| l4 | `lambda_tc` | 0.001 | `portfolio_optimize_service.py` |
| l5 | `regime_crisis_vol_threshold` | 0.40 | `risk_gate_service.py` |
| l5 | `regime_warning_vol_threshold` | 0.25 | `risk_gate_service.py` |
| l5 | `normal_portfolio_vol` | 0.30 | `risk_gate_service.py` |
| l5 | `normal_single_asset_max` | 0.35 | `risk_gate_service.py` |
| l5 | `normal_industry_max` | 0.45 | `risk_gate_service.py` |
| l5 | `normal_turnover` | 0.80 | `risk_gate_service.py` |
| l5 | `warning_portfolio_vol` | 0.22 | `risk_gate_service.py` |
| l5 | `warning_single_asset_max` | 0.28 | `risk_gate_service.py` |
| l5 | `warning_industry_max` | 0.38 | `risk_gate_service.py` |
| l5 | `warning_turnover` | 0.55 | `risk_gate_service.py` |
| l5 | `crisis_portfolio_vol` | 0.15 | `risk_gate_service.py` |
| l5 | `crisis_single_asset_max` | 0.20 | `risk_gate_service.py` |
| l5 | `crisis_industry_max` | 0.30 | `risk_gate_service.py` |
| l5 | `crisis_turnover` | 0.30 | `risk_gate_service.py` |
| l5.5 | `eta` | 0.1 | `pretrade_service.py` |
| l5.5 | `max_participation_tradable` | 0.10 | `pretrade_service.py` |
| l5.5 | `lookback_trading_days` | 20 | `pretrade_service.py` |
| l6 | `slippage_bp` | 5.0 | `execution_service.py` |
| l6 | `min_rel_delta` | 0.01 | `execution_service.py` |
| l7 | `warm_up_days` | 180.0 | `walk_forward_service.py` |
| l7 | `annualized_return_mean_min` | 0.06 | `walk_forward_service.py` |
| l7 | `max_drawdown_max_max` | 0.20 | `walk_forward_service.py` |
| l7 | `sharpe_min_min` | 0.5 | `walk_forward_service.py` |

**注**：`param_value` 为 FLOAT，L2 因子权重以比例存储（1/6 ≈ 0.1667）。

## Output Schema

### POST /api/v1/experiment/config/snapshot

```json
{
  "schema_version": "1.0.0",
  "command": "hf config snapshot",
  "run_id": "cfg_20260406_a1b2c3d4",
  "status": "ok",
  "generated_at": "2026-04-06T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "config_id": "a1b2c3d4-0000-0000-0000-000000000000",
    "params_count": 33,
    "note": "调低 eta 后首跑",
    "created_at": "2026-04-06T10:00:00+00:00"
  },
  "warnings": [],
  "errors": []
}
```

降级（bar_store=None）时追加 warning：
```json
{"code": "EXPERIMENT_CONFIG_NO_DB", "message": "bar_store unavailable; config not persisted"}
```

### GET /api/v1/experiment/configs

Query param: `layer` (optional), `limit` (default 20)

```json
{
  "data": {
    "configs": [
      {
        "config_id": "a1b2c3d4-...",
        "params_count": 33,
        "note": "调低 eta 后首跑",
        "created_at": "2026-04-06T10:00:00+00:00",
        "layers": ["l2", "l4", "l5", "l5.5", "l6", "l7"]
      }
    ]
  }
}
```

### GET /api/v1/experiment/configs/{config_id}

```json
{
  "data": {
    "config_id": "a1b2c3d4-...",
    "note": "调低 eta 后首跑",
    "created_at": "2026-04-06T10:00:00+00:00",
    "params": [
      {"layer": "l5.5", "param_key": "eta",                    "param_value": 0.1},
      {"layer": "l5.5", "param_key": "max_participation_tradable", "param_value": 0.1},
      {"layer": "l6",   "param_key": "slippage_bp",             "param_value": 5.0}
    ]
  }
}
```

404 when `config_id` not found:
```json
{"status": "error", "errors": [{"code": "CONFIG_NOT_FOUND", "message": "config_id not found"}]}
```

## CLI Output

**Table 模式（默认）：**

```
hf config snapshot --note "调低 eta"
  config_id: a1b2c3d4   params: 33   note: 调低 eta
  created_at: 2026-04-06T10:00:00+00:00

hf config list --layer l5.5
  CONFIG ID    PARAMS  NOTE              CREATED_AT
  a1b2c3d4     33      调低 eta 后首跑   2026-04-06 10:00
  b2c3d4e5     33      daily_run         2026-04-05 08:00

hf config get --config-id a1b2c3d4
  LAYER   PARAM_KEY                   PARAM_VALUE
  l2      factor_weight_momentum_20   0.1667
  l4      w_max                       0.3
  l5      regime_crisis_vol_threshold 0.4
  l5.5    eta                         0.1
  l6      slippage_bp                 5.0
  l7      warm_up_days                180.0
  ...（共 33 行）
```

**JSON 模式（`--output json`）：** 完整信封透传。

## File Structure

**新增文件：**

| 文件 | 职责 |
|------|------|
| `quant/db/migrations/0006_experiment_configs.sql` | `experiment_configs` 表 DDL |
| `quant/src/application/experiment/__init__.py` | package init |
| `quant/src/application/experiment/experiment_config_service.py` | `snapshot_current()` + `list_configs()` + `get_config()` |
| `quant/src/interfaces/http/routes_experiment.py` | 3 个 HTTP 路由 |
| `quant/tests/unit/test_experiment_config_service.py` | 单元测试（mock bar_store） |
| `quant/tests/contract/test_http_experiment.py` | 合约测试 |
| `cli/src/cmd/config.rs` | clap Args（snapshot/list/get） |
| `cli/src/application/handlers/config.rs` | CLI handler |
| `cli/tests/http_experiment_config.rs` | Rust mock 测试 |

**修改文件：**

| 文件 | 修改内容 |
|------|---------|
| `quant/src/application/daily_run_service.py` | `run_daily` 开头调用 `snapshot_current(note="daily_run", bar_store=bar_store)` |
| `quant/src/interfaces/http/dependencies.py` | 新增 `get_experiment_config_service()` |
| `quant/src/interfaces/http/app.py` | 注册 `routes_experiment` router |
| `cli/src/cmd/mod.rs` | 注册 `config` 子命令 |
| `cli/src/application/handlers/mod.rs` | 注册 config handler |
| `cli/src/application/dispatch.rs` | 路由 `AppCommand::Config` |
| `cli/src/infrastructure/http_client.rs` | 新增 3 个 HTTP 函数 |

## Testing Strategy

### 单元测试（`test_experiment_config_service.py`）

1. `snapshot_current(bar_store=mock)` → 返回 `config_id`，mock bar_store 收到正确 INSERT 调用，参数数量 = 33
2. `bar_store=None` → 返回 `config_id`，不调用 INSERT，返回 warning
3. `list_configs(layer='l5.5')` → 仅返回 l5.5 相关参数行聚合的 config 列表
4. `get_config(config_id)` → 返回完整 33 行参数列表
5. `get_config('nonexistent')` → 返回 `None`（HTTP 层转 404）

### 合约测试（`test_http_experiment.py`）

1. `POST /api/v1/experiment/config/snapshot` 合法 payload → 200，`data.config_id` 非空，`data.params_count` = 33
2. `GET /api/v1/experiment/configs` → 200，`data.configs` 为列表
3. `GET /api/v1/experiment/configs/{id}` 已知 id → 200，`data.params` 含 `layer`/`param_key`/`param_value`
4. `GET /api/v1/experiment/configs/nonexistent` → 404

### Rust CLI 测试（`http_experiment_config.rs`）

1. snapshot mock → table 输出含 `config_id`
2. list mock → table 含列头 `CONFIG ID`
3. get mock → table 含 `LAYER` 列
4. server 502 → `AppError::Upstream`

## Future Work (Phase 2)

- 配置驱动：`experiment_configs` 新增 `is_active BOOL` 列，`run_daily` 从 DB 读取 active 配置替代硬编码，`hf config activate --config-id` 切换
- 实验对比：同一个 `as_of` 跑两套 `config_id`，输出指标差异（类 L7 compare）
- `created_by` 记录操作人身份（接入 G3 审批流后自动填充）
