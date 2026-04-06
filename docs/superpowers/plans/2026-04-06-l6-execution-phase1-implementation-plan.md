# L6 执行层 Phase 1（订单生成）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实现。步骤使用 checkbox（`- [ ]`）便于跟踪。

**Goal:** 实现 L6 Phase 1：基于 L4 目标权重、L5.5 `pretrade` 与 DB `positions` 生成结构化订单列表，写入 `run_daily` 的 `data.execution_plan`；暴露 `POST /v1/execution/plan` 与 `hf execution plan`（三跳：L4→L5.5→L6）。行为与数据形状对齐设计文档 `docs/superpowers/specs/2026-04-06-l6-execution-plan-design.md`。

**Architecture:** 在 `application/execution/execution_service.py` 实现 `run_execution_plan(as_of, target_weights, pretrade, bar_store, notional, …)`：可选从 `bar_store`（`TimescaleBarStore`）读取/写入 `positions`（与 `get_pretrade_service` 同源 conn；`bar_store is None` 时持仓视为 0 且跳过 positions 持久化）；按设计计算 `delta`、跳过阈值、A 股整手 `quantity`、`limit_price`、`action`；合并 `EXECUTION_USING_NO_PRICE` 等 warnings。HTTP 层：`routes_execution.py` + Pydantic 请求体 + `Depends(get_execution_service)`，风格对齐 `routes_monitor.py`（`/v1/...` 前缀）。CLI：`pretrade_check.rs` 三跳模式，新增 `post_execution_plan`，请求体带 `as_of`、`target_weights`、L5.5 响应中的 `data`（供 `impact_bp` 映射）。

**Tech Stack:** Python 3 + FastAPI + pytest；Rust + clap + reqwest + mockito；TimescaleDB 新表 `positions`；无新 Python 依赖。

**验证:** `cd quant && uv run python -m pytest tests/unit/test_execution_service.py tests/contract/test_http_execution.py tests/architecture/test_layering_rules.py tests/integration/test_daily_pipeline_mvp.py -q`；`cd cli && cargo test`；仓库根目录 `make check`、`make validate-cli-output`。

**关联设计:** [2026-04-06-l6-execution-plan-design.md](../specs/2026-04-06-l6-execution-plan-design.md)

**与设计文档差异（实现时以本计划为准）:**

- DB 迁移文件名：仓库已有 `0001`–`0004`，新建 **`quant/db/migrations/0005_positions.sql`**（设计文中的 `003_positions.sql` 为旧编号）。
- Rust CLI handler 文件：与现有 **`cli/src/application/handlers/pretrade_check.rs`** 命名一致，新建 **`cli/src/application/handlers/execution_plan.rs`**（而非泛化的 `execution.rs`，避免与 dispatch 模块名混淆）。

---

## 文件映射（创建 / 修改）

| 路径 | 动作 |
|------|------|
| `quant/db/migrations/0005_positions.sql` | 新建：`positions` 表 DDL（见设计 spec） |
| `quant/src/application/execution/__init__.py` | 新建 |
| `quant/src/application/execution/execution_service.py` | 新建：`run_execution_plan` |
| `quant/src/interfaces/http/routes_execution.py` | 新建：`POST /v1/execution/plan`，`JSONResponse` 信封 |
| `quant/src/interfaces/http/schemas.py` | 修改：请求体 `ExecutionPlanRequest` / 响应包装（若与现有 `ExecutionPlan` 冲突则拆名，如 `ExecutionPlanResult`） |
| `quant/tests/unit/test_execution_service.py` | 新建：mock `list_bars` + positions 读写（可用 `SimpleNamespace` / 协议桩） |
| `quant/tests/contract/test_http_execution.py` | 新建：`TestClient` + dependency override |
| `quant/tests/architecture/test_layering_rules.py` | 修改：新增 `test_application_execution_does_not_import_interfaces` |
| `quant/src/application/daily_run_service.py` | 修改：L5.5 之后调用 L6；`portfolio is None` 时 `execution_plan=None`，否则写入服务结果 |
| `quant/src/interfaces/http/dependencies.py` | 修改：`ExecutionPlanService` 类型别名 + `get_execution_service()` |
| `quant/src/interfaces/http/app.py` | 修改：`include_router(routes_execution.router)` |
| `quant/src/interfaces/adapters/market_data/timescale_bar_store.py` | 修改：可选新增 `get_positions_snapshot(as_of)`、`upsert_positions(rows)`（或等价私有 SQL），仅供 execution 经同一 conn 使用 |
| `quant/src/interfaces/http/schemas.py`（DailyRunData） | 修改：`execution_plan` 允许 `None`，与 L4/L5.5 失败语义一致 |
| `quant/tests/integration/test_daily_pipeline_mvp.py` 等 | 修改：断言从固定 `{"orders":[]}` 调整为可空或含订单（按场景） |
| `cli/src/cmd/execution.rs` | 新建：`execution plan` 子命令 + `--as-of` / `--output` |
| `cli/src/application/handlers/execution_plan.rs` | 新建：三跳 + table/json |
| `cli/src/application/requests.rs` | 修改：`ExecutionPlanRequest` + `AppCommand::Execution` |
| `cli/src/cmd/mod.rs` | 修改：注册 `Execution` |
| `cli/src/application/handlers/mod.rs` | 修改：`pub mod execution_plan` |
| `cli/src/application/dispatch.rs` | 修改：`AppCommand::Execution` 分支 |
| `cli/src/infrastructure/http_client.rs` | 新建 `post_execution_plan(...)` → `POST {server}/v1/execution/plan` |
| `cli/src/infrastructure/table_renderer.rs`（或新建渲染函数） | 修改：table 格式对齐设计 spec 示例 |
| `cli/tests/http_execution_plan.rs` | 新建：mockito 三跳或单测 L6 端点 |
| `cli/tests/architecture_rules.rs` | 修改：`cmd_files` 加入 `cmd/execution.rs` |
| `cli/src/contracts/cli_output.rs` | 若需强类型：补充 `data` 形状（可选，Phase 1 可仍以 `Value` 透传） |
| `docs/CLI_OUTPUT_SCHEMA.json` | 修改：`if command == "hf execution plan"` 的 `then.data` |
| `docs/CLI_OUTPUT_EXAMPLES.md` | 修改：增加 `hf execution plan` 段落 |
| `quant/tests/fixtures/cli_output/valid/execution_plan_ok.json` | 新建：供 `make validate-cli-output` |
| `quant/src/interfaces/http/routes_daily_run.py` / `quant/src/hiveflow/pipeline/...` | 若存在硬编码 `execution_plan` 占位：与 `daily_run_service` 行为对齐 |

---

### Task 1: DB `positions` 与 `TimescaleBarStore` 读写（TDD 可选先后）

**Files:**
- Create: `quant/db/migrations/0005_positions.sql`
- Modify: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`
- Test: 在 `quant/tests/unit/` 或 integration 中覆盖 SQL 行为（若单测无 DB，可先契约测试 + 本地 `make db-migrate` 手工验）

- [ ] **Step 1:** 添加 migration：`positions (symbol, as_of, notional, updated_at)`，`PRIMARY KEY (symbol, as_of)`。
- [ ] **Step 2:** 在 `TimescaleBarStore` 实现：
  - `get_positions_snapshot(as_of: str) -> dict[str, float]`：取 `max(as_of) <= :as_of` 的全表统一快照日，再 `SELECT symbol, notional WHERE as_of = :snap`；无数据返回 `{}`。
  - `upsert_positions_for_as_of(as_of: str, notionals: dict[str, float]) -> None`：`INSERT ... ON CONFLICT DO UPDATE` 批量写当前截面目标名义资金。
- [ ] **Step 3:** 本地 `make db-migrate` 验证 DDL 可应用。

---

### Task 2: `run_execution_plan` 核心逻辑（TDD）

**Files:**
- Create: `quant/src/application/execution/execution_service.py`
- Create: `quant/tests/unit/test_execution_service.py`

**约束:** 仅依赖 `application.contracts.cli_output`、`list_bars` 鸭子类型协议、可选 `positions_store` 回调或 `bar_store` 上新增方法；**禁止** import `fastapi` / `interfaces`。

按设计 spec **Testing Strategy** 逐项编写失败测试再实现：

- [ ] 无持仓 + `target>0` → `open_long` / `buy` / `quantity` & `limit_price`。
- [ ] 有持仓 + `target>current` → `add_long`。
- [ ] 有持仓 + `target<current` 且 `target>0` → `reduce_long` / `sell`。
- [ ] 有持仓 + `target≈0` → `close_long`。
- [ ] `bar_store=None`（或无法取 close）→ `close_price`/`quantity`/`limit_price` 为 `null` + warning `EXECUTION_USING_NO_PRICE`。
- [ ] `|delta|/max(current,1) < 1%` → 不产生订单。
- [ ] `estimated_total_cost_bp` = Σ `target_weight × (slippage_bp + impact_bp)`，`impact_bp` 缺失时仅 `slippage_bp`（固定 5）。
- [ ] `command` 字段信封：`hf execution plan`。

`target_notional`：由组合权重 × `notional`（与 L5.5 daily 默认 `1_000_000` 对齐；HTTP/CLI 可传或默认一致）。

---

### Task 3: HTTP `POST /v1/execution/plan`

**Files:**
- Create: `quant/src/interfaces/http/routes_execution.py`
- Modify: `quant/src/interfaces/http/schemas.py`、`dependencies.py`、`app.py`
- Create: `quant/tests/contract/test_http_execution.py`

- [ ] 定义请求体：`as_of: str`，`target_weights: dict[str, float]` 或与设计一致的列表结构，`pretrade: dict | None`（至少包含按 symbol 查找 `impact_bp` 的字段路径，与现有 `run_pretrade_check` 的 `data` 对齐）。
- [ ] `get_execution_service()`：与 `get_pretrade_service()` 相同方式构造 `bar_store`（有 DB 则 `TimescaleBarStore`）。
- [ ] 合法 payload → 200，响应为统一 CLI 信封 JSON。
- [ ] 缺 `target_weights` → 422。
- [ ] `bar_store=None`（dependency override）→ 200 + 降级字段 + warning。

---

### Task 4: `run_daily` 接入 L6

**Files:**
- Modify: `quant/src/application/daily_run_service.py`
- Modify: `quant/src/interfaces/http/schemas.py`（`execution_plan` 可空）
- Modify: `quant/tests/integration/test_daily_pipeline_mvp.py`、`quant/tests/contract/test_http_daily_endpoint.py` 等

- [ ] 在 `pretrade_result` 计算之后：若 `portfolio is None`，则 `execution_plan=None`；否则调用 `run_execution_plan(...)`，`target_weights` 来自 `portfolio["target_weights"]`，`pretrade` 来自 `pretrade_result.get("data")`，`notional=1_000_000.0` 与 L5.5 一致。
- [ ] L6 抛错时：log + warning（如 `EXECUTION_PLAN_FAILED`），`execution_plan=None` 或保留部分结果（与 L5/L5.5 异常策略一致，优先不阻断 daily）。
- [ ] 更新契约/集成测试断言。

---

### Task 5: Rust CLI `hf execution plan`

**Files:**
- Create: `cli/src/cmd/execution.rs`
- Create: `cli/src/application/handlers/execution_plan.rs`
- Modify: `requests.rs`、`mod.rs`、`dispatch.rs`、`http_client.rs`、`table_renderer.rs`
- Create: `cli/tests/http_execution_plan.rs`
- Modify: `cli/tests/architecture_rules.rs`

- [ ] `post_portfolio_optimize` → 解析 `target_weights`。
- [ ] `post_pretrade_check` → 保留完整 JSON `data` 供 L6 请求体使用。
- [ ] `post_execution_plan` → 打印 table（默认）或透传 json。
- [ ] 任一跳失败 → 非零 exit，行为对齐 `pretrade_check`。

---

### Task 6: CLI 输出契约与文档

**Files:**
- Modify: `docs/CLI_OUTPUT_SCHEMA.json`、`docs/CLI_OUTPUT_EXAMPLES.md`
- Create: `quant/tests/fixtures/cli_output/valid/execution_plan_ok.json`

- [ ] Schema 增加 `hf execution plan` 的 `data` 必填/可选字段（`as_of`、`slippage_bp`、`estimated_total_cost_bp`、`orders[]` 等）。
- [ ] 样例与 fixture 通过 `make validate-cli-output`。

---

### Task 7: 架构测试与全量门禁

- [ ] `test_layering_rules.py`：新增 `application.execution` 不得 import `interfaces`。
- [ ] 运行 `make architecture-check` 与 `make check`，修复 `dead_code` 仅当本任务引入。

---

## 提交建议

- `feat: 新增 L6 execution plan 服务与 positions 表`
- `feat: daily pipeline 接入 L6 并更新 execution_plan 契约`
- `feat: hf execution plan CLI 与输出 schema`

（按实际拆分为 1–3 个逻辑提交即可。）
