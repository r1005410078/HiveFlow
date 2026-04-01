# L1 Data Ingestion (HTTP + Timescale + CLI Query Modes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 交付 L1 数据同步/查询闭环：quant 服务端支持 `sync/query`（PostgreSQL + Timescale），Rust CLI 支持 `table/json/chart` 输出模式。

**Architecture:** quant 采用契约优先的 HTTP 接口（`interfaces/http`），应用层编排同步/查询用例，适配器层负责 AkShare、Timescale、Parquet、manifest。cli 作为纯客户端：参数解析 -> HTTP 调用 -> 渲染输出；AI 路径强制 `--output json --non-interactive`。

**Tech Stack:** Python (FastAPI, pytest), PostgreSQL + TimescaleDB, Rust (clap, reqwest, serde_json, comfy-table, textplots/ratatui-lite), Makefile。

---

## 0. 文件与测试总览（含中文职责）

### 0.1 Quant server 文件职责
- Create: `quant/src/domain/market_data/entities.py`  
  备注：L1 领域实体定义（如 Bar、SyncRun），只放业务概念，不放 IO。
- Create: `quant/src/domain/market_data/ports.py`  
  备注：领域端口（Repository/Store 接口），用于隔离基础设施实现。
- Create: `quant/src/domain/market_data/value_objects.py`  
  备注：值对象（如 `Timeframe`, `SymbolSet`, `DateRange`），封装校验。
- Create: `quant/src/application/market_data/sync_service.py`  
  备注：同步编排服务，负责参数解析、增量拉取、写入流程控制。
- Create: `quant/src/application/market_data/query_service.py`  
  备注：查询编排服务，负责查询过滤、排序与响应结构。
- Create: `quant/src/interfaces/adapters/market_data/akshare_quote_adapter.py`  
  备注：AkShare 数据源适配器，实现行情拉取端口。
- Create: `quant/src/interfaces/adapters/market_data/parquet_quote_writer.py`  
  备注：Parquet 归档写入器（审计/回放层）。
- Create: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`  
  备注：Timescale 读写适配器（在线查询/增量索引层）。
- Create: `quant/src/interfaces/http/routes_market_data.py`  
  备注：L1 HTTP 路由入口（`/v1/market-data/*`）。
- Create: `quant/src/interfaces/http/schemas_market_data.py`  
  备注：HTTP 请求/响应 schema（Pydantic）。
- Modify: `quant/src/interfaces/http/dependencies.py`  
  备注：依赖注入装配（service/provider）。
- Modify: `quant/src/interfaces/http/app.py`  
  备注：注册新路由到 FastAPI app。
- Create: `quant/db/migrations/0001_l1_timescale.sql`  
  备注：Timescale 最小表结构迁移。
- Create: `quant/config/watchlist.yml`  
  备注：关注股配置文件模板。
- Create: `quant/config/positions.yml`  
  备注：持仓股配置文件模板。

### 0.2 Quant tests 文件职责
- Create: `quant/tests/unit/market_data/test_sync_service.py`  
  备注：验证同步编排逻辑（参数/幂等/默认股票范围）。
- Create: `quant/tests/unit/market_data/test_query_service.py`  
  备注：验证查询编排逻辑（过滤、输出结构）。
- Create: `quant/tests/unit/market_data/test_timescale_bar_store.py`  
  备注：验证 Timescale upsert/checkpoint/idempotency。
- Create: `quant/tests/contract/test_http_market_data_sync_endpoint.py`  
  备注：验证 `POST /v1/market-data/sync` 契约。
- Create: `quant/tests/contract/test_http_market_data_query_endpoint.py`  
  备注：验证 `GET /v1/market-data/sync-runs` 契约。
- Create: `quant/tests/integration/test_l1_sync_query_e2e.py`  
  备注：验证数据库迁移 + 同步查询端到端流程。

### 0.3 Rust CLI 文件职责
- Modify: `cli/src/cmd/data.rs`  
  备注：定义 `hf data sync/query` 命令与参数。
- Modify: `cli/src/application/dispatch.rs`  
  备注：命令分发入口，挂接 data handler。
- Create: `cli/src/application/handlers/data_sync.rs`  
  备注：`data sync` 执行逻辑。
- Create: `cli/src/application/handlers/data_query.rs`  
  备注：`data query` 执行逻辑与输出模式路由。
- Modify: `cli/src/application/handlers/mod.rs`  
  备注：导出新 handler 模块。
- Modify: `cli/src/infrastructure/http_client.rs`  
  备注：新增 sync/query HTTP 请求方法。
- Create: `cli/src/infrastructure/table_renderer.rs`  
  备注：人读表格渲染（默认精简 6 列）。
- Create: `cli/src/infrastructure/chart_renderer.rs`  
  备注：趋势图渲染与降级逻辑。
- Modify: `cli/src/infrastructure/mod.rs`  
  备注：导出 renderer 模块。

### 0.4 CLI tests 文件职责
- Create: `cli/tests/http_data_sync.rs`  
  备注：验证 `data sync` HTTP 映射与参数透传。
- Create: `cli/tests/http_data_query_json.rs`  
  备注：验证 `data query --output json` 机器可读输出。
- Create: `cli/tests/http_data_query_table.rs`  
  备注：验证 `data query --output table` 列结构与格式。
- Create: `cli/tests/http_data_query_chart.rs`  
  备注：验证 `data query --output chart` 图表输出与降级策略。

### 0.5 Docs/Contract 文件职责
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`  
  备注：补充 sync/query 的 table/json/chart 示例。
- Modify: `docs/CLI_OUTPUT_SCHEMA.json`  
  备注：补充新命令输出 schema（重点是 json 模式）。
- Modify: `Makefile`  
  备注：整合验证命令，保证 CI 一键校验。

---

## 1. 关键字段说明（实现前统一口径）

### 1.1 `POST /v1/market-data/sync` 请求字段
- `days`：同步最近 N 天窗口，`N>=1`。
- `end_date`：窗口结束日期（`YYYY-MM-DD`）。
- `timeframe`：粒度（`1d`/`1m`）。
- `symbols`：显式股票列表（优先级最高）。
- `universe`：股票池标识（次优先级）。
- `request_id`：幂等请求 ID（同 ID 重复请求返回同结果）。

### 1.2 `sync` 成功响应字段
- `status`：执行状态（`success`）。
- `run_id`：任务唯一 ID。
- `timeframe`：本次同步粒度。
- `days`：本次同步窗口。
- `effective_symbols_count`：最终参与同步股票数量。
- `manifest_ids`：本次关联 manifest 列表。

### 1.3 `GET /v1/market-data/sync-runs` 查询字段
- `days`：最近 N 天查询窗口。
- `timeframe`：粒度过滤。
- `symbols`：股票过滤。
- `status`：状态过滤（`success`/`failed`）。

### 1.4 Timescale 表字段
- `bars`：行情事实表。  
  关键字段：`symbol/timeframe/bar_time`（唯一键）、`open/high/low/close/volume/amount`、`adj_factor`、`data_source`。
- `sync_runs`：同步任务元数据表。  
  关键字段：`run_id`、`request_id`、`status`、`days/end_date/timeframe`、`symbols_hash`、`effective_symbols_count`、`error_code/error_message`。
- `sync_checkpoints`：增量游标表。  
  关键字段：`symbol/timeframe`（主键）、`last_bar_time`、`last_run_id`。

### 1.5 CLI 表格列字段（`--output table`）
- 默认精简 6 列：`date/status/timeframe/symbols_count/run_id/manifest_id`。
- `--verbose` 追加：`error_code/error_message/started_at/finished_at`。

---

### Task 1: Database Schema First (Timescale MVP)

**Files:**
- Create: `quant/db/migrations/0001_l1_timescale.sql`
- Test: `quant/tests/integration/test_l1_sync_query_e2e.py`

- [x] **Step 1: Write the failing integration test**  
目标：先锁定数据库最小表结构契约，确保迁移是“被测试驱动”的。

```python
def test_timescale_tables_exist(db_conn):
    rows = db_conn.execute("""
        select table_name from information_schema.tables
        where table_schema='public' and table_name in ('bars','sync_runs','sync_checkpoints')
        order by table_name
    """).fetchall()
    assert [r[0] for r in rows] == ["bars", "sync_checkpoints", "sync_runs"]
```

- [x] **Step 2: Run test to verify it fails**  
目标：确认当前没有实现，测试确实处于 red 状态。

Run: `cd quant && pytest tests/integration/test_l1_sync_query_e2e.py::test_timescale_tables_exist -v`  
Expected: FAIL with table list mismatch.

- [x] **Step 3: Write migration SQL**  
目标：一次性建立 `bars/sync_runs/sync_checkpoints` 及唯一约束、索引。

```sql
create extension if not exists timescaledb;

create table if not exists bars (
  symbol text not null,
  timeframe text not null,
  bar_time timestamptz not null,
  open double precision not null,
  high double precision not null,
  low double precision not null,
  close double precision not null,
  volume double precision not null,
  amount double precision not null,
  adj_factor double precision not null default 1.0,
  data_source text not null,
  ingested_at timestamptz not null default now(),
  primary key (symbol, timeframe, bar_time)
);
select create_hypertable('bars','bar_time', if_not_exists => true);
```

- [x] **Step 4: Re-run test**  
目标：验证迁移后数据库结构满足契约。

Run: `cd quant && pytest tests/integration/test_l1_sync_query_e2e.py::test_timescale_tables_exist -v`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：把“数据库结构基线”独立提交，便于回滚与审阅。

```bash
git add quant/db/migrations/0001_l1_timescale.sql quant/tests/integration/test_l1_sync_query_e2e.py
git commit -m "feat(quant): add timescale schema for l1 bars and sync metadata"
```

### Task 2: Domain + Application Contracts (Sync/Query)

**Files:**
- Create: `quant/src/domain/market_data/entities.py`
- Create: `quant/src/domain/market_data/ports.py`
- Create: `quant/src/domain/market_data/value_objects.py`
- Create: `quant/src/application/market_data/sync_service.py`
- Create: `quant/src/application/market_data/query_service.py`
- Test: `quant/tests/unit/market_data/test_sync_service.py`
- Test: `quant/tests/unit/market_data/test_query_service.py`

- [x] **Step 1: Write failing unit tests for service contracts**  
目标：先定义 `sync/query` 的应用层输入输出口径。

```python
def test_sync_service_returns_run_summary(fake_repo, fake_store):
    svc = SyncService(quote_repo=fake_repo, bar_store=fake_store)
    out = svc.sync(days=5, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])
    assert out["status"] == "success"
    assert out["effective_symbols_count"] == 1
```

- [x] **Step 2: Run tests to verify red state**  
目标：确认服务层尚未实现。

Run: `cd quant && pytest tests/unit/market_data/test_sync_service.py tests/unit/market_data/test_query_service.py -v`  
Expected: FAIL

- [x] **Step 3: Implement minimal service skeletons**  
目标：以最小实现打通接口，避免过度设计。

```python
class SyncService:
    def __init__(self, quote_repo, bar_store):
        self.quote_repo = quote_repo
        self.bar_store = bar_store

    def sync(self, days, end_date, timeframe, symbols=None, universe=None, request_id=None):
        return {"status": "success", "effective_symbols_count": len(symbols or [])}
```

- [x] **Step 4: Re-run tests**  
目标：验证 green，并确保最小契约成立。

Run: `cd quant && pytest tests/unit/market_data/test_sync_service.py tests/unit/market_data/test_query_service.py -v`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：固定应用层契约基线。

```bash
git add quant/src/domain/market_data quant/src/application/market_data quant/tests/unit/market_data/test_sync_service.py quant/tests/unit/market_data/test_query_service.py
git commit -m "feat(quant): add market-data sync/query service contracts"
```

### Task 3: Timescale Adapter + Idempotency/Checkpoint

**Files:**
- Create: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`
- Test: `quant/tests/unit/market_data/test_timescale_bar_store.py`

- [x] **Step 1: Write failing adapter tests**  
目标：先锁定 upsert 幂等与 checkpoint 更新行为。

```python
def test_upsert_bars_on_conflict_symbol_timeframe_bar_time(store, sample_rows):
    store.upsert_bars(sample_rows)
    store.upsert_bars(sample_rows)
    assert store.count_bars() == len(sample_rows)
```

- [x] **Step 2: Run tests to verify red state**  
目标：确认适配器当前不可用。

Run: `cd quant && pytest tests/unit/market_data/test_timescale_bar_store.py -v`  
Expected: FAIL

- [x] **Step 3: Implement adapter methods**  
目标：实现 `bars` upsert、`sync_runs` 记录、`sync_checkpoints` 更新。

```python
def upsert_bars(self, rows):
    sql = """
    insert into bars (...) values (...)
    on conflict (symbol, timeframe, bar_time)
    do update set open=excluded.open, high=excluded.high, low=excluded.low,
                  close=excluded.close, volume=excluded.volume,
                  amount=excluded.amount, adj_factor=excluded.adj_factor,
                  data_source=excluded.data_source, ingested_at=now()
    """
```

- [x] **Step 4: Re-run tests**  
目标：验证幂等与数据一致性。

Run: `cd quant && pytest tests/unit/market_data/test_timescale_bar_store.py -v`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：隔离基础设施提交，降低 review 复杂度。

```bash
git add quant/src/interfaces/adapters/market_data/timescale_bar_store.py quant/tests/unit/market_data/test_timescale_bar_store.py
git commit -m "feat(quant): implement timescale bar store with upsert and checkpoint"
```

### Task 4: HTTP Endpoints for Sync/Query (Contract First)

**Files:**
- Create: `quant/src/interfaces/http/schemas_market_data.py`
- Create: `quant/src/interfaces/http/routes_market_data.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/app.py`
- Test: `quant/tests/contract/test_http_market_data_sync_endpoint.py`
- Test: `quant/tests/contract/test_http_market_data_query_endpoint.py`

- [x] **Step 1: Write failing contract tests**  
目标：先固定 HTTP 行为，再写实现。

```python
def test_post_sync_returns_200_and_run_id(client):
    resp = client.post("/v1/market-data/sync", json={"days":5,"end_date":"2026-04-01","timeframe":"1d"})
    assert resp.status_code == 200
    assert "run_id" in resp.json()
```

- [x] **Step 2: Run tests to verify red state**  
目标：确认新路由尚不存在。

Run: `cd quant && pytest tests/contract/test_http_market_data_sync_endpoint.py tests/contract/test_http_market_data_query_endpoint.py -v`  
Expected: FAIL

- [x] **Step 3: Implement schemas/routes with DI**  
目标：保持 DDD 分层，HTTP 层仅做入参与映射。

```python
router = APIRouter(prefix="/v1/market-data", tags=["market-data"])

@router.post("/sync")
def post_sync(req: SyncRequest, svc: SyncService = Depends(get_sync_service)):
    return svc.sync(**req.model_dump())
```

- [x] **Step 4: Re-run tests**  
目标：验证接口契约满足测试。

Run: `cd quant && pytest tests/contract/test_http_market_data_sync_endpoint.py tests/contract/test_http_market_data_query_endpoint.py -v`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：固定 HTTP 契约版本。

```bash
git add quant/src/interfaces/http/app.py quant/src/interfaces/http/dependencies.py quant/src/interfaces/http/routes_market_data.py quant/src/interfaces/http/schemas_market_data.py quant/tests/contract/test_http_market_data_sync_endpoint.py quant/tests/contract/test_http_market_data_query_endpoint.py
git commit -m "feat(quant): add l1 market-data sync/query http endpoints"
```

### Task 5: CLI Command Surface (`hf data sync/query`)

**Files:**
- Modify: `cli/src/cmd/data.rs`
- Modify: `cli/src/application/dispatch.rs`
- Create: `cli/src/application/handlers/data_sync.rs`
- Create: `cli/src/application/handlers/data_query.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Test: `cli/tests/http_data_sync.rs`
- Test: `cli/tests/http_data_query_json.rs`

- [x] **Step 1: Write failing CLI tests**  
目标：先锁定命令解析与 URL 映射行为。

```rust
#[test]
fn data_query_json_calls_sync_runs_endpoint() {
    // assert URL: /v1/market-data/sync-runs
}
```

- [x] **Step 2: Run tests to verify red state**  
目标：确认当前 data 子命令仍是 placeholder。

Run: `cd cli && cargo test http_data_sync http_data_query_json -- --nocapture`  
Expected: FAIL

- [x] **Step 3: Implement command enums and handlers**  
目标：打通 `hf data sync` 与 `hf data query`。

```rust
pub enum DataSubcommand {
    Sync(DataSyncArgs),
    Query(DataQueryArgs),
}
```

- [x] **Step 4: Re-run tests**  
目标：验证 CLI 调用路径 green。

Run: `cd cli && cargo test http_data_sync http_data_query_json -- --nocapture`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：固定 CLI 命令面。

```bash
git add cli/src/cmd/data.rs cli/src/application/dispatch.rs cli/src/application/handlers/data_sync.rs cli/src/application/handlers/data_query.rs cli/src/application/handlers/mod.rs cli/src/infrastructure/http_client.rs cli/tests/http_data_sync.rs cli/tests/http_data_query_json.rs
git commit -m "feat(cli): add data sync/query commands with http integration"
```

### Task 6: CLI Table/Chart Rendering Modes

**Files:**
- Create: `cli/src/infrastructure/table_renderer.rs`
- Create: `cli/src/infrastructure/chart_renderer.rs`
- Modify: `cli/src/infrastructure/mod.rs`
- Modify: `cli/src/application/handlers/data_query.rs`
- Test: `cli/tests/http_data_query_table.rs`
- Test: `cli/tests/http_data_query_chart.rs`

- [x] **Step 1: Write failing rendering tests**  
目标：先固定 table/chart 的可见行为。

```rust
#[test]
fn data_query_table_renders_six_columns() {
    // expect: date|status|timeframe|symbols_count|run_id|manifest_id
}
```

- [x] **Step 2: Run tests to verify red state**  
目标：确认渲染器尚未实现。

Run: `cd cli && cargo test http_data_query_table http_data_query_chart -- --nocapture`  
Expected: FAIL

- [x] **Step 3: Implement renderers + fallback**  
目标：实现默认 6 列、`--verbose` 扩展、chart 降级策略。

```rust
// table: comfy_table fixed 6 columns
// chart: success/failed + symbols_count trend
// fallback: unsupported terminal => table + warning
```

- [x] **Step 4: Re-run tests**  
目标：验证输出模式全部 green。

Run: `cd cli && cargo test http_data_query_table http_data_query_chart -- --nocapture`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：隔离“呈现层”改动，便于回归。

```bash
git add cli/src/infrastructure/table_renderer.rs cli/src/infrastructure/chart_renderer.rs cli/src/infrastructure/mod.rs cli/src/application/handlers/data_query.rs cli/tests/http_data_query_table.rs cli/tests/http_data_query_chart.rs
git commit -m "feat(cli): support data query table and chart outputs"
```

### Task 7: Watchlist/Positions Config + Symbol Scope Resolution

**Files:**
- Create: `quant/config/watchlist.yml`
- Create: `quant/config/positions.yml`
- Modify: `quant/src/application/market_data/sync_service.py`
- Test: `quant/tests/unit/market_data/test_sync_service.py`

- [x] **Step 1: Write failing unit test for union rule**  
目标：锁定“默认股票范围 = 关注股 + 持仓股 (+可选 universe)”规则。

```python
def test_default_symbols_include_watchlist_and_positions(sync_service):
    out = sync_service.sync(days=1, end_date="2026-04-01", timeframe="1d")
    assert out["effective_symbols_count"] >= 2
```

- [x] **Step 2: Run test to verify red state**  
目标：确认当前默认范围尚未实现。

Run: `cd quant && pytest tests/unit/market_data/test_sync_service.py::test_default_symbols_include_watchlist_and_positions -v`  
Expected: FAIL

- [x] **Step 3: Implement resolver + templates**  
目标：落地可用默认配置并实现读取合并逻辑。

```yaml
version: 1
updated_at: "2026-04-01T09:30:00+08:00"
symbols: ["600519.SH"]
```

- [x] **Step 4: Re-run test**  
目标：验证默认集合策略生效。

Run: `cd quant && pytest tests/unit/market_data/test_sync_service.py::test_default_symbols_include_watchlist_and_positions -v`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：固定配置驱动策略基线。

```bash
git add quant/config/watchlist.yml quant/config/positions.yml quant/src/application/market_data/sync_service.py quant/tests/unit/market_data/test_sync_service.py
git commit -m "feat(quant): add watchlist/positions config based default symbol scope"
```

### Task 8: Output Contract + Docs + Full Verification

**Files:**
- Modify: `docs/CLI_OUTPUT_SCHEMA.json`
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Modify: `Makefile`
- Test: quant + cli full suites

- [x] **Step 1: Add failing contract fixtures**  
目标：先让 schema 约束覆盖新增 query 输出模式。

```json
{
  "schema_version": "1.0",
  "command": "data query",
  "data": {"items": []}
}
```

- [x] **Step 2: Run validation in red state**  
目标：确认 contract 校验能拦住未更新 schema。

Run: `make validate-cli-output`  
Expected: FAIL

- [x] **Step 3: Update schema/examples/Make target**  
目标：完成文档与校验脚本对齐。

```make
check: validate-cli-output
	cd quant && pytest -q
	cd cli && cargo test
```

- [x] **Step 4: Run full verification**  
目标：在统一入口下完成全链路绿灯。

Run: `make check`  
Expected: PASS

- [x] **Step 5: Commit**  
目标：固定最终契约与验证入口。

```bash
git add docs/CLI_OUTPUT_SCHEMA.json docs/CLI_OUTPUT_EXAMPLES.md Makefile
git commit -m "docs: update cli output contract for l1 sync/query modes"
```

---

## 2. Spec Coverage Self-Check
- L1 sync/query HTTP 契约：Task 4 + Task 5。
- Timescale 持久化 + checkpoint + 幂等：Task 1 + Task 3。
- CLI 输出模式（table/json/chart）与 AI JSON 约束：Task 6 + Task 8。
- 默认股票范围（watchlist + positions + optional universe）：Task 7。
- CI/验证闭环：Task 8。

## 3. Placeholder Scan
- 无 `TODO/TBD/implement later`。
- 每个任务包含文件、命令、预期结果。

## 4. Type/Signature Consistency
- `sync(days, end_date, timeframe, symbols, universe, request_id)` 在计划中保持一致。
- 查询接口固定：`GET /v1/market-data/sync-runs`。
- CLI 输出模式固定：`--output table|json|chart`，AI 固定 `--output json --non-interactive`。
