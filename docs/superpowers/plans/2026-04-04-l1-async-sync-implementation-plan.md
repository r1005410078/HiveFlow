# L1 行情同步异步化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 L1 `POST /v1/market-data/sync` 与 `POST /v1/market-data/universes/sync` 改为异步作业模型：提交即返（202）、后台串行执行、CLI 轮询 `GET /v1/market-data/sync-runs/{run_id}` 展示详细进度（含 **`current_symbol`**、**已同步/待同步标的列表与计数**、截断策略），消除大 scope 下的同步超时；并提供**协作式终止**（`POST .../cancel` + DB `cancel_requested_at` + 循环检查点退出，`status=cancelled`）；以及 **标的失败队列、同 run 自动重试（上限+退避）、失败次数与原因持久化（审计表）、`POST .../retry-failed` + CLI 仅补拉失败标的**（spec §4.4、§5.6）。

**Architecture:** Python 遵守 `interfaces → application → domain`：`SyncWorker` 仅存在于 `application/market_data`，不依赖 FastAPI；HTTP 路由只做 DTO 与状态码；`TimescaleBarStore` 扩展 `progress`/`phase`/`cancel_requested_at` 与按 `run_id` 查询及 cancel 请求写入。Rust CLI 遵守 `cmd → application → infrastructure`：短超时 POST + 轮询 GET，`indicatif` 展示进度；**cancel** 为独立子命令调用 `POST .../cancel`。

**Design spec:** [`docs/superpowers/specs/2026-04-04-l1-async-sync-design.md`](../specs/2026-04-04-l1-async-sync-design.md)

**Verification:** `make architecture-check`、`make check`；若 CLI 对外 JSON 包装或 `data` 子命令输出字段变化，须同步 `docs/CLI_OUTPUT_SCHEMA.json`、`docs/CLI_OUTPUT_EXAMPLES.md`、`tests/fixtures/cli_output/` 并执行 `make validate-cli-output`。

---

## 0. 文件与职责总览

### 0.1 Python 服务端

| 动作 | 路径 | 备注 |
|------|------|------|
| Create | `quant/db/migrations/0004_sync_runs_async.sql` | `progress jsonb`、`phase text`、`cancel_requested_at timestamptz`；**新建 `sync_run_symbol_failures`（或等价名）** `run_id+symbol`、attempt_count、last_error_*、时间戳；编号若冲突则顺延 |
| Modify | `quant/src/interfaces/adapters/market_data/timescale_bar_store.py` | 同上；**`upsert_symbol_failure(run_id, symbol, error_code, message, day)`**、**`list_terminal_failed_symbols(run_id)`**、**`clear_symbol_failure_on_success(...)`**（可选） |
| Modify | `quant/src/application/market_data/sync_service.py` | 同上；**失败入队、同 run retry pass、`MAX_SYMBOL_ATTEMPTS`、退避**；**`progress.failure_queue` / 摘要计数**；**execute_retry_failed_from_run(source_run_id, overrides)`** 或 Worker 编排 |
| Create | `quant/src/application/market_data/sync_worker.py` | 后台线程、互斥、工厂注入连接/repo、异常写 run；**循环内检查取消** |
| Modify | `quant/src/interfaces/http/routes_market_data.py` | POST 202/409/200；`GET .../sync-runs/{run_id}`；**`POST .../cancel`**；**`POST .../retry-failed`** |
| Modify | `quant/src/interfaces/http/schemas_market_data.py` | 响应模型 / 必要请求字段（若仅状态码+body dict 可最小改动） |
| Modify | `quant/src/interfaces/http/dependencies.py` | 提供 `SyncWorker` 或 `get_sync_worker`（从 `app.state`） |
| Modify | `quant/src/interfaces/http/app.py` | startup/shutdown 挂载 worker |

### 0.2 Python 测试

| 动作 | 路径 | 备注 |
|------|------|------|
| Create/Modify | `quant/tests/unit/market_data/test_sync_worker.py` | 串行、409 条件、mock store |
| Create/Modify | `quant/tests/unit/market_data/test_sync_service_async.py` | progress 回调与 debounce 行为（可用 fake clock 或计数） |
| Create | `quant/tests/contract/test_http_market_data_sync_async.py` | 202、GET run_id、409、**POST cancel**、**POST retry-failed** |

### 0.3 Rust CLI

| 动作 | 路径 | 备注 |
|------|------|------|
| Modify | `cli/src/infrastructure/http_client.rs` | `post_data_sync`；`get_sync_run_detail`；**`post_sync_run_cancel`**；**`post_sync_run_retry_failed`** |
| Modify | `cli/src/cmd/data.rs` | **`SyncCancel`**、`SyncRetryFailed`（`--from-run-id`）；另：`--no-wait`、`--poll-interval-ms` 等 |
| Modify | `cli/src/application/handlers/data_sync.rs` | 提交 + 轮询 + 进度条（**展示 current_symbol、done/pending 计数；verbose/table 展示截断列表**）+ Ctrl+C 提示 |
| Create | `cli/src/application/handlers/data_sync_cancel.rs` | cancel API |
| Create | `cli/src/application/handlers/data_sync_retry_failed.rs` | retry-failed API + 轮询 |
| Modify | `cli/src/application/handlers/mod.rs` | 导出 `data_sync_cancel`、`data_sync_retry_failed` |
| Modify | `cli/src/application/dispatch.rs` | `DataSyncCancel`、`DataSyncRetryFailed` |
| Modify | `cli/src/application/handlers/data_universe_sync.rs` | 与 bar sync 对齐 |
| Modify | `cli/src/application/requests.rs` | `AppCommand::DataSyncCancel`、`AppCommand::DataSyncRetryFailed` |
| Modify | `cli/src/cmd/mod.rs` | `Cli` → `AppCommand` 映射含 cancel |

### 0.4 Rust 测试

| 动作 | 路径 | 备注 |
|------|------|------|
| Modify/Create | `cli/tests/http_data_sync.rs` | mock 202 → poll → success |
| Create | `cli/tests/http_data_sync_conflict.rs` | mock 409 |
| Create | `cli/tests/http_data_sync_cancel.rs` | mock POST cancel 200 幂等 |
| Create | `cli/tests/http_data_sync_retry_failed.rs` | mock retry-failed 202 |

### 0.5 架构测试

| 动作 | 路径 | 备注 |
|------|------|------|
| Modify | `quant/tests/architecture/` | 若新增 application 模块，更新允许依赖规则（如需要） |

### 0.6 文档与契约（若 CLI 输出变）

| 动作 | 路径 |
|------|------|
| Modify | `docs/CLI_OUTPUT_SCHEMA.json` |
| Modify | `docs/CLI_OUTPUT_EXAMPLES.md` |
| Modify | `tests/fixtures/cli_output/...` |

---

## Task 1: DB migration + BarStore API

**Files:**

- Create: `quant/db/migrations/0004_sync_runs_async.sql`
- Modify: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`

- [ ] **Step 1:** 添加 `progress`、`phase`、`cancel_requested_at` 列；**创建 `sync_run_symbol_failures`**（PK `(run_id, symbol)`，含 `attempt_count`、`last_error_code`、`last_error_message`、`last_failed_day`、`first_failed_at`、`last_failed_at`）；本地 `make db-migrate` 验证。
- [ ] **Step 2:** 实现 `get_sync_run_by_id`、`get_running_sync_run`、`insert_sync_run_running`、`update_sync_progress`、`finalize_sync_run`、**`request_sync_cancel`**；**`upsert_symbol_failure`**、**`list_failed_symbols_for_retry(run_id)`**（仅 terminal / 超过重试阈值者，语义与 spec 一致）。
- [ ] **Step 3:** 单元测试或最小 SQL 契约测试：列/表存在；failure UPSERT 递增 `attempt_count`；cancel 列可写。

---

## Task 2: SyncService — 可中断/可汇报的执行核心

**Files:**

- Modify: `quant/src/application/market_data/sync_service.py`

- [ ] **Step 1:** 将主循环抽为 `execute_sync(..., on_progress: Callable | None)`（或等价），在 `resolving_symbols`、每个 debounce 点、`finalizing` 调用回调。
- [ ] **Step 1b:** 在循环内维护「本 run 窗口下各标的是否仍待拉」的推导（结合 `as_of_dates`、`checkpoint_starts`、`latest_bar_times` / 已处理日），更新 **`current_symbol`**（批次边界或 adapter 逐标的钩子）；组装 **`symbols_done_for_run` / `symbols_pending_for_run`**（字典序，列表长度上限 **N=200** 可配置常量，超出设 **`symbol_lists_truncated=true`**），并写入 **`symbols_done_count` / `symbols_pending_count`**（与 spec §4.3 一致）。
- [ ] **Step 2:** `on_progress` 写入由上层传入（Worker 内调用 store.update），**application 不直接 import psycopg**。
- [ ] **Step 3:** 保持原 `sync()` 在 `_InMemoryBarStore` 场景下**同步执行并返回 200 摘要**（路由层判断：无 DB 则不走 202）。
- [ ] **Step 4:** `request_id` 幂等：已成功 → 直接返回摘要；运行中 → 返回同一 `run_id`（与 design 最终选定一致）。
- [ ] **Step 5:** 主循环在**每个交易日批次开始前**（或与 `on_progress` 同频）调用 `should_cancel()`；若为真则跳出循环，进入 **`finalize` 为 `status=cancelled`**、`error_code=SYNC_CANCELLED`，并仍执行**已拉取数据的 checkpoint**（与 spec「已写入 bars 保留」一致；若需跳过 checkpoint 须在 spec 另行说明——默认**写已有 `latest_bar_times`**）。
- [ ] **Step 6（失败队列与重试）：** 解析单次 fetch 结果：无数据/异常按标的写入 **failure_queue** 与 **审计表 UPSERT**（`attempt_count`、`last_error_*`、`last_failed_day`）。主循环结束后（或按日穿插）执行 **retry pass**：对队列项重试直至 **`MAX_SYMBOL_ATTEMPTS`**（常量，默认 3）或成功；超限标为 **terminal_failed**，更新 `progress.terminal_failed_symbols_count` / `failure_queue_depth`。成功写入 bars 时更新 checkpoint 并**可选清除**该 symbol 的 open failure 记录。错误码规范化短码枚举（与 `error_codes` 风格一致，Rust/Python 契约后续对齐）。

---

## Task 3: SyncWorker

**Files:**

- Create: `quant/src/application/market_data/sync_worker.py`

- [ ] **Step 1:** 单线程执行队列或「当前 job + lock」；`submit` 若已有 running → 返回 False（路由转 409）。
- [ ] **Step 2:** Worker 内使用 **新** DB 连接 / 新 `TimescaleBarStore` 实例（避免与请求线程共连）。
- [ ] **Step 3:** 捕获异常，写 `sync_runs.status`/`error_*`/`phase`/`progress`。
- [ ] **Step 4:** Universe sync 与 bar sync **互斥**（同一 lock）。
- [ ] **Step 5:** 将 `should_cancel` 实现为**读库**（`get_by_run_id` 判 `cancel_requested_at is not None`）或 Worker 内缓存+失效策略；避免 HTTP 线程与 Worker 竞态时漏读。

---

## Task 4: HTTP 路由与 app 生命周期

**Files:**

- Modify: `quant/src/interfaces/http/routes_market_data.py`
- Modify: `quant/src/interfaces/http/schemas_market_data.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/app.py`

- [ ] **Step 1:** `POST /sync`：创建 running run → enqueue → 202；冲突 409；幂等 200。
- [ ] **Step 2:** `GET /v1/market-data/sync-runs/{run_id}`：404 / 200。
- [ ] **Step 3:** `POST /universes/sync`：同样异步与互斥。
- [ ] **Step 4:** `app.state.sync_worker`；shutdown 等待策略带超时并打日志。
- [ ] **Step 5:** **`POST /v1/market-data/sync-runs/{run_id}/cancel`**：调用 `bar_store.request_sync_cancel`；404 / 200 幂等（终态返回 `cancel_accepted: false`）；路由**不写**业务循环。
- [ ] **Step 6（续跑 / 恢复）：** **`startup` 收口孤儿 run**：查询 `sync_runs` 中 `status=running`（且无活跃 Worker 线程时等价于崩溃残留），批量更新为 **`interrupted`**（或 `failed`）+ `error_code=SYNC_ORPHAN_RUN` + `finished_at`，释放串行锁。详见 spec **§8**。数据续拉不依赖同一 `run_id`，由既有 **checkpoint** 在下次 `POST /sync` 自动增量。
- [ ] **Step 7:** **`POST /v1/market-data/sync-runs/{run_id}/retry-failed`**：校验源 run 已终态；读 `list_failed_symbols_for_retry`；组装新 job（继承 `days`/`end_date`/`timeframe`，可 body 覆盖）；**新 `run_id` + 新 `request_id` 策略**（客户端传或服务端生成）；入队 Worker。

---

## Task 5: Python 测试与 contract

**Files:**

- `quant/tests/unit/market_data/test_sync_worker.py`（新建）
- `quant/tests/unit/market_data/test_sync_service_async.py`（新建或并入现有 sync tests）
- `quant/tests/contract/test_http_market_data_sync_async.py`（新建）

- [ ] **Step 1:** Worker 串行与双提交 409。
- [ ] **Step 2:** Contract：TestClient 或现有 harness 验证 202 body 含 `run_id`；GET 返回 `progress`；**POST cancel** 404、running→200、终态幂等 200。
- [ ] **Step 3:** 单元：`execute_sync` 在 `should_cancel=True` 后**不再发起后续 fetch**（mock repo 调用次数断言）。
- [ ] **Step 4:** **孤儿 run**：构造 DB 中 `running` 行 → 触发应用 startup 收口 → 断言变为 `interrupted`/`failed` 且可再次 `POST /sync`。
- [ ] **Step 5:** `request_id`：**仅 success 短路**；`failed`/`cancelled`/`interrupted` 后相同 `request_id` 可再次提交（单测或 contract）。
- [ ] **Step 6:** `cd quant && uv run python -m pytest` 相关子集通过。

---

## Task 6: Rust HTTP client

**Files:**

- Modify: `cli/src/infrastructure/http_client.rs`

- [ ] **Step 1:** `post_data_sync`：区分 200 / 202 / 409（返回类型或 `Result` 枚举），**勿**对 202 当错误。
- [ ] **Step 2:** `get_sync_run_detail(server_url, run_id, timeout_ms)`。
- [ ] **Step 3:** **`post_sync_run_cancel(server_url, run_id, timeout_ms)`** → `POST .../sync-runs/{run_id}/cancel`。
- [ ] **Step 4:** **`post_sync_run_retry_failed(server_url, run_id, overrides, timeout_ms)`** → `POST .../sync-runs/{run_id}/retry-failed`；处理 202/409/422/404。
- [ ] **Step 5:** 单元/集成测试 mock server（含 retry-failed 路径）。

---

## Task 7: CLI handlers + args

**Files:**

- Modify: `cli/src/cmd/data.rs`
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/application/handlers/data_sync.rs`
- Modify: `cli/src/application/handlers/data_universe_sync.rs`

- [ ] **Step 1:** `data sync`：提交短超时；轮询默认 1500ms；`--no-wait`。
- [ ] **Step 2:** `indicatif` 进度：**`current_symbol`**、**done/pending 计数**、日进度、ETA、`symbol_errors` 截断；**`--verbose` 或 `--output table`（若与 data query 对齐）** 打印 `symbols_done_for_run` / `symbols_pending_for_run` 前缀列表及 `symbol_lists_truncated` 提示。
- [ ] **Step 3:** Ctrl+C 提示 `run_id`。
- [ ] **Step 4:** `universe-sync` 对齐。
- [ ] **Step 5:** 最终 stdout 仍为合法 JSON（若外层 schema 不变，仅 `data` 字段内嵌服务端摘要，需确认 validator）。
- [ ] **Step 6:** 子命令 **`hf data sync cancel --run-id`**：包装 CLI 输出；子命令名以实现为准（如 `sync-cancel` 与 clap 命名一致）。
- [ ] **Step 7:** 子命令 **`hf data sync retry-failed --from-run-id`**：调用 `post_sync_run_retry_failed`；成功后 202 → 进入轮询（复用 Step 1–2 逻辑）或 `--no-wait` 打印 `run_id`。

---

## Task 8: CLI 契约与全量门禁

- [ ] **Step 1:** 若 `hf data sync` 顶层 CLI JSON 字段变化 → 更新 schema、examples、fixtures → `make validate-cli-output`。
- [ ] **Step 2:** `make architecture-check`
- [ ] **Step 3:** `make check`

---

## Task 9: 文档收口

- [ ] 在 [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) 或 L1 相关小节增加一句「行情同步为异步作业 + 轮询」（若维护者希望索引；可选，**不**强制大块改写）。
- [ ] 将本 plan 与 spec 状态在 spec 文首更新为「已确认 / 进行中 / 已完成」（合入后由维护者更新）。

---

## 开放决策（实现前在代码中写死并回写 spec）

1. **`status` vs `phase` 终态**：列表接口与单条接口是否同时返回两者；终态时 `phase` 取值。
2. **`--timeout-ms` 语义**：仅单次 HTTP 还是包含轮询总等待；若后者，需在 `config.toml` 文档中说明。
3. **`symbol_errors` 上限**：默认条数（如 50）及溢出策略（丢弃最旧 / 仅计数）。
4. **Ctrl+C 是否自动 cancel**：默认仅打印 `run_id`；若增加 `--cancel-on-interrupt`，仅在**当前 CLI 会话提交的 run** 上调用 cancel，避免误杀他人任务。
5. **`progress` 列表截断上限 N**：默认 **200**（与 spec §4.3 一致）；是否实现 `GET ...?symbol_lists=full` 本期可选。
6. **`MAX_SYMBOL_ATTEMPTS`、retry pass 时机**（主循环后集中重试 vs 日内穿插）与 **退避秒数**：实现写死常量，可后续改配置。
7. **批量 `fetch` 失败**时审计按标的归因策略（整批记同一原因 vs 拆批）——实现计划选一种并文档化。

---

## 提交规范

- 使用约定式提交：`feat:` / `test:` / `docs:` 等，中文描述具体改动（见根目录 `AGENTS.md`）。
