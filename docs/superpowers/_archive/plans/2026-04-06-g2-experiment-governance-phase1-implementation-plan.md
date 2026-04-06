# G2 实验治理 Phase 1（参数版本快照）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实现。步骤使用 checkbox（`- [ ]`）便于跟踪。

**Goal:** 实现 G2 Phase 1：将 L2/L4/L5/L5.5/L6/L7 策略参数以只读快照写入 `experiment_configs` 表；`run_daily` 每次调用在开头落库（或带 `EXPERIMENT_CONFIG_NO_DB` 警告）；暴露 `POST /api/v1/experiment/config/snapshot`、`GET /api/v1/experiment/configs`、`GET /api/v1/experiment/configs/{config_id}` 与 `hf config snapshot|list|get`；CLI 输出符合 `CLI_OUTPUT_SCHEMA.json`。

**Architecture:** `application/experiment/experiment_config_service.py` 负责枚举当前硬编码参数（单一收集函数，避免与管线默认值漂移）、生成 `config_id`、组装标准信封（`ok_output` / `error_output`）。**禁止** application 直接 `import interfaces`：在 `application/experiment/experiment_config_ports.py` 定义 `typing.Protocol`（如 `insert_experiment_config_rows`、`list_experiment_config_summaries`、`fetch_experiment_config_detail`）；`TimescaleBarStore` 在 `interfaces/adapters/market_data/timescale_bar_store.py` 实现上述方法（内部 `cursor.execute`）。HTTP 路由仅 DTO 解析 + `Depends` + `JSONResponse`；`dependencies.py` 装配带 `bar_store` 的 service closure。`run_daily` 在生成 `run_id` 之后尽早调用 `snapshot_current`（与设计文档「开头」一致；若后续产品要求仅交易日落库，再将调用下移到 `is_sse_trading_day` 分支内并修订 spec）。

**Tech Stack:** Python 3 + FastAPI + psycopg（经现有 DB 连接）+ pytest；Rust + clap + reqwest + mockito；无新三方依赖。

**验证:** `cd quant && uv run python -m pytest tests/unit/test_experiment_config_service.py tests/contract/test_http_experiment.py tests/architecture/test_layering_rules.py -q`；`cd cli && cargo test`；仓库根目录 `make check`。

**关联设计:** [2026-04-06-g2-experiment-governance-phase1-design.md](../specs/2026-04-06-g2-experiment-governance-phase1-design.md)

**与参数表对齐说明:** 设计文档中 L2 六因子等权示例与当前默认 `run_daily(..., score_version="l2-score-v1.1")` 所用 `SCORE_PROFILES` 因子集合/权重可能不一致。**实现以代码为准**：L2 行从 `application.decision.l2_decision_service.SCORE_PROFILES[<与 run_daily 默认一致的 version>]["weights"]` 展开为 `factor_weight_<factor_name>`，保证 `params_count` 与管线一致（当前合计仍为 33：6+4+14+3+2+4）。若与设计表字面不一致，在实现 PR 中追加设计文档 **追溯 errata** 段落（不阻塞 Phase 1）。

---

## 文件映射（创建 / 修改）

| 路径 | 动作 |
|------|------|
| `quant/db/migrations/0006_experiment_configs.sql` | 新建：DDL 与设计一致 |
| `quant/src/application/experiment/__init__.py` | 新建 |
| `quant/src/application/experiment/experiment_config_ports.py` | 新建：`Protocol` 定义 |
| `quant/src/application/experiment/experiment_config_service.py` | 新建：参数收集 + `snapshot_current` / `list_configs` / `get_config` |
| `quant/src/interfaces/adapters/market_data/timescale_bar_store.py` | 修改：实现 Protocol 三方法 |
| `quant/src/application/risk/risk_gate_service.py` | 修改：将 regime 波动阈值 `0.40` / `0.25` 提升为模块级命名常量，供 `_detect_regime` 与参数快照共用 |
| `quant/src/application/daily_run_service.py` | 修改：`run_id` 生成后调用 `snapshot_current`（注入 `note="daily_run"`）；需处理返回值（例如写入 `run_daily` 的 `data.experiment_config` 可选字段，**或**仅副作用落库——若设计未要求回显，可不在 daily 信封中暴露，但须在任务中二选一并与契约测试一致） |
| `quant/src/interfaces/http/routes_experiment.py` | 新建：3 路由 |
| `quant/src/interfaces/http/dependencies.py` | 修改：`ExperimentConfig*` 类型别名 + `get_experiment_config_snapshot_service` 等 |
| `quant/src/interfaces/http/app.py` | 修改：`include_router(routes_experiment.router)` |
| `quant/tests/unit/test_experiment_config_service.py` | 新建：mock Protocol |
| `quant/tests/contract/test_http_experiment.py` | 新建：`TestClient` + override |
| `quant/tests/architecture/test_layering_rules.py` | 修改：新增 `test_application_experiment_does_not_import_interfaces` |
| `cli/src/cmd/config.rs` | 新建：`ConfigArgs` + `snapshot` / `list` / `get` |
| `cli/src/cmd/mod.rs` | 修改：注册 `Config` |
| `cli/src/application/requests.rs` | 修改：`AppCommand::Config` + 请求结构体 |
| `cli/src/application/handlers/config.rs` | 新建：handle + table 渲染 |
| `cli/src/application/handlers/mod.rs` | 修改：`pub mod config` |
| `cli/src/application/dispatch.rs` | 修改：`AppCommand::Config` 分支 |
| `cli/src/infrastructure/http_client.rs` | 修改：`post_experiment_config_snapshot`、`get_experiment_configs`、`get_experiment_config_detail` |
| `cli/src/infrastructure/table_renderer.rs`（若已有 monitor 等模式） | 修改：新增 config 表格函数，或于 `handlers/config.rs` 内联简单对齐输出 |
| `cli/tests/http_experiment_config.rs` | 新建：mockito + table 断言 |
| `cli/tests/architecture_rules.rs` | 修改：`cmd_files` 加入 `cmd/config.rs` |
| `cli/src/contracts/error_codes.rs` | 按需：若 HTTP 404/502 映射需新变体则补充 |
| `docs/CLI_OUTPUT_SCHEMA.json` | 修改：`hf config snapshot` / `hf config list` / `hf config get` 的 `data` 形状 |
| `docs/CLI_OUTPUT_EXAMPLES.md` | 修改：三节示例 |
| `quant/tests/fixtures/cli_output/valid/experiment_config_snapshot_ok.json` 等 | 新建：与 `make validate-cli-output` 一致 |

---

### Task 1: DB 迁移 `experiment_configs`

**Files:**
- Create: `quant/db/migrations/0006_experiment_configs.sql`

- [ ] **Step 1: 添加 DDL**

内容与设计文档 `DB Schema` 节一致（`experiment_configs` 表 + `idx_experiment_configs_layer_created`）。

- [ ] **Step 2: 本地验证（可选）**

在已配置 DB 的环境：`make db-migrate`（或项目等价命令）后 `\d experiment_configs` 确认表存在。

- [ ] **Step 3: Commit**

```bash
git add quant/db/migrations/0006_experiment_configs.sql
git commit -m "feat: 新增 experiment_configs 表用于 G2 参数快照"
```

---

### Task 2: L5 regime 阈值常量提取（避免快照与 `_detect_regime` 漂移）

**Files:**
- Modify: `quant/src/application/risk/risk_gate_service.py`
- Test: `quant/tests/unit/test_experiment_config_service.py`（后续 Task 3 会间接固定行为；此处可先加 `risk_gate` 小测或仅在 Task 3 中断言 `regime_crisis_vol_threshold` 数值）

- [ ] **Step 1: 在模块顶部定义**

```python
REGIME_CRISIS_VOL_THRESHOLD = 0.40
REGIME_WARNING_VOL_THRESHOLD = 0.25
```

- [ ] **Step 2: `_detect_regime` 内用常量替换字面 `0.40` / `0.25`**

- [ ] **Step 3: Commit**

```bash
git add quant/src/application/risk/risk_gate_service.py
git commit -m "refactor: 提取 L5 市场状态波动阈值为命名常量供 G2 快照复用"
```

---

### Task 3: `Protocol` + `TimescaleBarStore` 持久化与查询方法

**Files:**
- Create: `quant/src/application/experiment/experiment_config_ports.py`
- Modify: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`

- [ ] **Step 1: 定义 Protocol**（`experiment_config_ports.py`）

```python
from __future__ import annotations

from typing import Any, Protocol


class ExperimentConfigStore(Protocol):
    def insert_experiment_config_rows(self, rows: list[dict[str, Any]]) -> None:
        """rows: config_id, layer, param_key, param_value, note, created_by."""

    def list_experiment_config_summaries(
        self, *, layer: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Return list of {config_id, params_count, note, created_at, layers}."""

    def fetch_experiment_config_detail(self, config_id: str) -> dict[str, Any] | None:
        """Return {config_id, note, created_at, params: [...]} or None if missing."""
```

- [ ] **Step 2: 在 `TimescaleBarStore` 实现三方法**

- `insert_experiment_config_rows`：`executemany` 插入 `experiment_configs`（`param_value` cast float）。
- `list_experiment_config_summaries`：`GROUP BY config_id`，`layer` 过滤时仅保留「该 `config_id` 至少有一行满足 `layer`」的快照；`layers` 用 `array_agg(DISTINCT layer ORDER BY layer)` 或等价 Python 后处理。
- `fetch_experiment_config_detail`：`SELECT` 全部行组装 `params`；无行返回 `None`。

- [ ] **Step 3: Commit**

```bash
git add quant/src/application/experiment/experiment_config_ports.py quant/src/interfaces/adapters/market_data/timescale_bar_store.py
git commit -m "feat: TimescaleBarStore 支持 experiment_configs 写入与列表查询"
```

---

### Task 4: `experiment_config_service` 参数收集与快照（TDD）

**Files:**
- Create: `quant/src/application/experiment/__init__.py`（可空）
- Create: `quant/src/application/experiment/experiment_config_service.py`
- Create: `quant/tests/unit/test_experiment_config_service.py`

**约束:** 仅依赖 `application.*`、`domain.*`、`typing`、`uuid`；使用 `application.contracts.cli_output` 的 `ok_output` / `error_output`。

- [ ] **Step 1: 编写失败测试 `test_snapshot_persists_via_store`**

```python
from unittest.mock import MagicMock

from application.experiment.experiment_config_service import snapshot_current


def test_snapshot_persists_via_store() -> None:
    store = MagicMock()
    out = snapshot_current(note="unit", store=store)
    assert out["status"] == "ok"
    assert out["data"]["params_count"] == 33
    store.insert_experiment_config_rows.assert_called_once()
    rows = store.insert_experiment_config_rows.call_args[0][0]
    assert len(rows) == 33
    cid = out["data"]["config_id"]
    assert all(r["config_id"] == cid for r in rows)
```

运行：`cd quant && uv run python -m pytest tests/unit/test_experiment_config_service.py::test_snapshot_persists_via_store -v`  
**预期:** 失败（模块/函数不存在）。

- [ ] **Step 2: 实现 `collect_param_rows() -> list[dict]`**

逻辑要点（伪代码级，实现时展开为真实导入）：

- **l2:** `from application.decision.l2_decision_service import SCORE_PROFILES, SCORE_VERSION`；对 `SCORE_PROFILES[SCORE_VERSION]["weights"].items()` 生成 `layer="l2"`, `param_key=f"factor_weight_{name}"`, `param_value=float(w)`。
- **l4:** 使用 `run_portfolio_optimize` 默认 `w_max=0.30`, `ind_max=0.40`, `lambda_risk=1.0`, `lambda_tc=0.001`（可直接字面或与函数签名 default 同源：推荐从 `inspect.signature` 读 default **或** 在 `portfolio_optimize_service` 增加只读元组常量 `PORTFOLIO_DEFAULT_PARAMS` 供单点维护——择一并在计划中固定）。
- **l5:** `regime_crisis_vol_threshold` / `regime_warning_vol_threshold` 来自 Task 2 常量；`normal_*` / `warning_*` / `crisis_*` 来自 `risk_gate_service._THRESHOLDS` 展开为扁平 `param_key`（与设计表一致）。
- **l5.5:** `pretrade_service.ETA`, `MAX_PARTICIPATION_TRADABLE`, `LOOKBACK_TRADING_DAYS`。
- **l6:** `execution_service.SLIPPAGE_BP`（存 float）、`MIN_REL_DELTA`。
- **l7:** `walk_forward_service` 中 `run_walk_forward` 默认 `warm_up_days=180` + `_DEFAULT_THRESHOLDS` 三项。

每行 dict：`{"layer", "param_key", "param_value"}`（插入前在 `snapshot_current` 内补 `config_id`, `note`, `created_by`）。

- [ ] **Step 3: 实现 `snapshot_current(note: str, store: ExperimentConfigStore | None) -> dict`**

- `config_id = str(uuid4())`；`run_id = f"cfg_{date_or_utc_compact}_{uuid[:8]}"`（与现有 CLI `run_id` 风格一致即可）。
- `store is None`：不调用 insert，追加 `warnings.append({"code": "EXPERIMENT_CONFIG_NO_DB", "message": "bar_store unavailable; config not persisted"})`，仍返回 `ok` + `data.config_id` + `params_count=33`。
- `store` 非空：批量 insert；`created_by="system"`。

- [ ] **Step 4: 运行测试通过**

`cd quant && uv run python -m pytest tests/unit/test_experiment_config_service.py -v`

- [ ] **Step 5: 补充测试**（设计文档 Testing Strategy）

- `test_snapshot_no_store_no_insert`
- `test_list_configs_layer_filter`（mock `list_experiment_config_summaries` 或通过 fake store）
- `test_get_config_found` / `test_get_config_missing`

实现 `list_configs(layer, limit)`、`get_config(config_id)` 返回 `ok_output`/`error_output`（`get` 未找到时 `status=error`, `errors=[{"code":"CONFIG_NOT_FOUND",...}]`，与 HTTP 层 404 映射一致）。

- [ ] **Step 6: Commit**

```bash
git add quant/src/application/experiment/ quant/tests/unit/test_experiment_config_service.py
git commit -m "feat: G2 实验参数快照 application 服务与单元测试"
```

---

### Task 5: HTTP 路由与依赖注入

**Files:**
- Create: `quant/src/interfaces/http/routes_experiment.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/app.py`
- Create: `quant/tests/contract/test_http_experiment.py`

- [ ] **Step 1: `dependencies.py`**

- 提供 `get_experiment_config_store()`：与 `get_daily_run_service` 类似，在 `has_db_config()` 时构造 `TimescaleBarStore`，否则 `None`。
- 提供 `get_experiment_snapshot_handler()` 等 closure，调用 `snapshot_current` / `list_configs` / `get_config`。

- [ ] **Step 2: `routes_experiment.py`**

- `APIRouter(prefix="/api/v1/experiment", tags=["experiment"])`
- `POST /config/snapshot`：Body 可选 `{"note": str}`，默认 `""`；响应完整信封。
- `GET /configs`：Query `layer`, `limit`（默认 20）。
- `GET /configs/{config_id}`：若 service 返回 error + CONFIG_NOT_FOUND → `JSONResponse(status_code=404, content=envelope)`；否则 200。

- [ ] **Step 3: 合约测试**（与设计 4 条一致）

使用 `dependency_overrides` 注入 fake service，断言状态码与 `data` 形状。

- [ ] **Step 4: Commit**

```bash
git add quant/src/interfaces/http/routes_experiment.py quant/src/interfaces/http/dependencies.py quant/src/interfaces/http/app.py quant/tests/contract/test_http_experiment.py
git commit -m "feat: G2 experiment config HTTP 端点与合约测试"
```

---

### Task 6: `run_daily` 接入快照

**Files:**
- Modify: `quant/src/application/daily_run_service.py`
- 可选新增: `quant/tests/integration/...` 或扩展现有 daily 测试

- [ ] **Step 1: 在 `run_daily` 开头（`run_id` 赋值后）调用**

```python
from application.experiment.experiment_config_service import snapshot_current

# run_id = ...
_exp = snapshot_current(note="daily_run", store=bar_store)
```

- [ ] **Step 2: 决定是否写入 `data`**

若将 `experiment_config` 并入 `run_daily` 的 `data`：更新 `docs/CLI_OUTPUT_SCHEMA.json` 中 `hf pipeline daily` 的 `data` 可选字段说明 + 对应 fixture；若仅落库不回显：不改编译契约，但需在实现注释中说明「审计仅 DB」。

- [ ] **Step 3: Commit**

```bash
git add quant/src/application/daily_run_service.py
git commit -m "feat: run_daily 开头写入实验参数快照"
```

---

### Task 7: 架构测试 `application.experiment`

**Files:**
- Modify: `quant/tests/architecture/test_layering_rules.py`

- [ ] **Step 1: 复制 `test_application_monitor_does_not_import_interfaces` 模式为 `experiment` 目录**

- [ ] **Step 2: Commit**

```bash
git add quant/tests/architecture/test_layering_rules.py
git commit -m "test: application.experiment 不得依赖 interfaces"
```

---

### Task 8: Rust CLI `hf config` 与 HTTP 客户端

**Files:**
- Create/modify: 见上文文件映射

- [ ] **Step 1: `http_client.rs`**

实现三个函数，URL 与 Python 路由一致；错误时映射 `AppError::Upstream`；404 对 `get` 保留响应体供上层解析或统一转为 `AppError`。

- [ ] **Step 2: `cmd/config.rs` + dispatch + handler**

- `hf config snapshot [--note TEXT] [--output json|table]`
- `hf config list [--layer LAYER] [--limit N] [--output json|table]`
- `hf config get --config-id ID [--output json|table]`

table 模式列与设计文档「CLI Output」一致。

- [ ] **Step 3: `cli/tests/http_experiment_config.rs`**

mockito 覆盖 snapshot/list/get 成功路径与 502。

- [ ] **Step 4: `cargo test`**

`cd cli && cargo test`

- [ ] **Step 5: Commit**

```bash
git add cli/src cli/tests
git commit -m "feat: hf config snapshot/list/get CLI 与 HTTP 客户端"
```

---

### Task 9: CLI 输出契约（schema / examples / fixtures）

**Files:**
- Modify: `docs/CLI_OUTPUT_SCHEMA.json`
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Create: `quant/tests/fixtures/cli_output/valid/experiment_config_*.json`

- [ ] **Step 1: 更新 schema** — 为三条 command 增加 `if/then` 分支（遵循仓库现有 JSON Schema 写法）。

- [ ] **Step 2: 更新 EXAMPLES** — 各一节真实样例（含 `schema_version`, `source`, `decision_weight`）。

- [ ] **Step 3: 添加 valid fixtures** — 运行 `make validate-cli-output`。

- [ ] **Step 4: Commit**

```bash
git add docs/CLI_OUTPUT_SCHEMA.json docs/CLI_OUTPUT_EXAMPLES.md quant/tests/fixtures/cli_output/valid/
git commit -m "docs: G2 hf config 命令 CLI 输出契约与 fixtures"
```

---

## Self-Review（对照设计）

| 设计要点 | 对应任务 |
|---------|---------|
| `0006_experiment_configs.sql` | Task 1 |
| `snapshot_current` / `list` / `get` | Task 3–5 |
| `bar_store=None` 警告 `EXPERIMENT_CONFIG_NO_DB` | Task 4 |
| `run_daily` 开头快照 | Task 6 |
| HTTP 三端点 + 404 CONFIG_NOT_FOUND | Task 5 |
| CLI 三子命令 + table | Task 8 |
| 单元 / 合约 / Rust 测试策略 | Task 4–5, 8 |
| L2 权重与代码默认 score_version 一致 | Task 4 说明 + collect 实现 |

**Placeholder 扫描:** 本计划未使用「TBD / 稍后实现」类占位；`run_daily` 是否回显 `experiment_config` 为明确二选一，须在 Task 6 落笔选定。

**类型一致性:** `param_value` 全为 float；`layer` 字符串与设计一致（含 `l5.5`）；`config_id` UUID 字符串。

---

## 执行交接

Plan 已保存至 `docs/superpowers/plans/2026-04-06-g2-experiment-governance-phase1-implementation-plan.md`。

**执行方式二选一：**

1. **Subagent-Driven（推荐）** — 每任务独立子代理，任务间人工复核；须遵循 superpowers:subagent-driven-development。  
2. **Inline Execution** — 本会话内用 superpowers:executing-plans 批量执行并设检查点。

请告知希望采用哪种方式；开始编码前建议在 `.worktrees/` 下按 superpowers:using-git-worktrees 建立隔离 worktree（与 AGENTS.md 一致）。
