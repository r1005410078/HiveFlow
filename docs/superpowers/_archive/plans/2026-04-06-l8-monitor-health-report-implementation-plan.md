# L8 监控健康报告（Phase 1）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实现。步骤使用 checkbox（`- [ ]`）便于跟踪。

**Goal:** 实现 L8 Phase 1：基于 `run_daily` 输出聚合因子/信号/风控健康度与 `green|yellow|red` 总评，暴露 `GET /v1/monitor/health-report` 与 `hf monitor health-report`，行为与数据形状对齐设计文档 `docs/superpowers/specs/2026-04-06-l8-monitor-health-report-design.md`。

**Architecture:** 在 `application/monitor/health_report_service.py` 中编排：可选注入 `run_daily_fn(as_of) -> dict`（生产默认 `run_daily(as_of, root=None, bar_store=…)`），从 `l2_decision.factor_availability`、`signal_matrix`、`risk_gate` 派生 `factor_health` / `signal_health` / `risk_health`，按设计文档优先级表计算 `overall_rating`；HTTP 层仅 Query 解析 + `Depends` 注入 + `JSONResponse` 信封（对齐 `routes_walk_forward.py`）；CLI 经 `http_client::get_health_report` 拉取后 `json` 透传或 `table` 渲染。

**Tech Stack:** Python 3 + FastAPI + pytest；Rust + clap + reqwest + mockito；无新三方依赖。

**验证:** `cd quant && uv run python -m pytest tests/unit/test_health_report_service.py tests/contract/test_http_monitor.py tests/architecture/test_layering_rules.py -q`；`cd cli && cargo test`；仓库根目录 `make check`。

**关联设计:** [2026-04-06-l8-monitor-health-report-design.md](../specs/2026-04-06-l8-monitor-health-report-design.md)

---

## 文件映射（创建 / 修改）

| 路径 | 动作 |
|------|------|
| `quant/src/application/monitor/__init__.py` | 新建 |
| `quant/src/application/monitor/health_report_service.py` | 新建：聚合 + `run_health_report` |
| `quant/src/interfaces/http/routes_monitor.py` | 新建：`GET /v1/monitor/health-report` |
| `quant/tests/unit/test_health_report_service.py` | 新建：mock `run_daily_fn` |
| `quant/tests/contract/test_http_monitor.py` | 新建：`TestClient` + dependency override |
| `quant/tests/architecture/test_layering_rules.py` | 修改：新增 `application.monitor` 不得 import `interfaces` 的断言（对齐 `application.signal` 条目） |
| `quant/src/interfaces/http/dependencies.py` | 修改：`HealthReportService` 类型别名 + `get_health_report_service()` |
| `quant/src/interfaces/http/app.py` | 修改：`include_router(routes_monitor.router)` |
| `cli/src/cmd/monitor.rs` | 新建：`MonitorArgs` + `health-report` 子命令 |
| `cli/src/cmd/mod.rs` | 修改：注册 `Monitor` 与 `From` 映射 |
| `cli/src/application/requests.rs` | 新建 `MonitorHealthReportRequest` + `AppCommand::Monitor` 变体 |
| `cli/src/application/handlers/monitor.rs` | 新建：`handle` + `print_table` |
| `cli/src/application/handlers/mod.rs` | 修改：`pub mod monitor` |
| `cli/src/application/dispatch.rs` | 修改：`AppCommand::Monitor` 分支 |
| `cli/src/infrastructure/http_client.rs` | 新建 `get_health_report(server_url, as_of, timeout_ms) -> Result<Value, AppError>` |
| `cli/tests/http_monitor_health_report.rs` | 新建：mockito GET + table/json 断言 |
| `cli/tests/architecture_rules.rs` | 修改：`cmd_layer_must_not_import_infrastructure` 的 `cmd_files` 列表加入 `"cmd/monitor.rs"` |
| `docs/CLI_OUTPUT_SCHEMA.json` | 修改：新增 `if command == "hf monitor health-report"` 的 `then.data` 形状约束 |
| `docs/CLI_OUTPUT_EXAMPLES.md` | 修改：增加该命令示例段落 |
| `quant/tests/fixtures/cli_output/valid/monitor_health_report_ok.json` | 新建：供 `make validate-cli-output` |

---

### Task 1: `health_report_service` 纯函数与 `run_health_report` 骨架（TDD）

**Files:**
- Create: `quant/src/application/monitor/__init__.py`（可为空）
- Create: `quant/src/application/monitor/health_report_service.py`
- Create: `quant/tests/unit/test_health_report_service.py`

**约束:** 仅依赖 `application.daily_run_service.run_daily`（默认路径）、`application.contracts.cli_output`（`ok_output` / `error_output` 若已有）、`typing` / `statistics` / `math`；**禁止** import `fastapi` 或 `interfaces`。

- [ ] **Step 1: 编写失败测试 `test_overall_green_all_ok`**

在 `quant/tests/unit/test_health_report_service.py`：

```python
from application.monitor.health_report_service import run_health_report


def _daily_all_green(as_of: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pipeline daily",
        "run_id": "run_daily_stub",
        "status": "ok",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [
                    {"factor_name": "momentum_20", "availability_rate": 0.95},
                    {"factor_name": "inv_volatility_20", "availability_rate": 0.9},
                ],
            },
            "signal_matrix": {
                "coverage_rate": 0.85,
                "composite_scores": [
                    {"symbol": "600519.SH", "composite_score": 0.1},
                    {"symbol": "000001.SZ", "composite_score": 0.2},
                ],
            },
            "risk_gate": {
                "regime": "normal",
                "block_codes": [],
            },
        },
        "warnings": [],
        "errors": [],
    }


def test_overall_green_all_ok() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_all_green)
    assert out["status"] == "ok"
    d = out["data"]
    assert d["overall_rating"] == "green"
    assert d["factor_health"]["ok_count"] == 2
    assert d["signal_health"]["status"] == "ok"
    assert d["risk_health"]["status"] == "ok"
    assert d["trend"] is None
    assert d["run_daily_warnings"] == []
```

运行：`cd quant && uv run python -m pytest tests/unit/test_health_report_service.py::test_overall_green_all_ok -v`  
**预期:** 失败（`run_health_report` / 模块不存在）。

- [ ] **Step 2: 实现最小 `run_health_report` 使绿色路径通过**

在 `health_report_service.py` 中实现：

1. 签名：`def run_health_report(as_of: str, *, bar_store=None, run_daily_fn=None) -> dict`  
   - `run_daily_fn` 为 `Callable[[str], dict]`；若为 `None`，则 `from application.daily_run_service import run_daily` 并调用 `run_daily(as_of=as_of, root=None, bar_store=bar_store)`。

2. 若 `daily["data"].get("skipped")` 为真：返回 `ok_output(command="hf monitor health-report", …, data={"as_of": as_of, "skipped": True, "skip_reason": daily["data"].get("skip_reason"), "overall_rating": None, "factor_health": None, "signal_health": None, "risk_health": None, "trend": None, "run_daily_warnings": daily.get("warnings", [])})`（`run_id` 用本地 uuid 前缀 `hr_` 即可）。

3. 否则从 `daily["data"]` 取 `l2_decision` / `signal_matrix` / `risk_gate`，计算：
   - **factor_health**：遍历 `l2_decision.get("factor_availability", [])`，每项 `availability_rate` 映射 `ok|warn|miss`（阈值 0.8 / 0.5 与设计文档一致），聚合 `total` / `ok_count` / `warn_count` / `miss_count` / `details`（`details` 含 `factor_name`, `availability_rate`, `status`）。
   - **signal_health**：若 `signal_matrix` 为 `None`：`coverage_rate` 视为 0，`composite_score_mean` / `std` 为 0 或 null（与测试约定一致即可，但 **`status` 必须为 `miss`**）。否则用 `signal_matrix["coverage_rate"]`，对 `composite_scores` 里 `composite_score` 数值做 mean/std（跳过 `nan`）。
   - **risk_health**：若 `risk_gate` 为 `None`：`regime` 可置 `"normal"`，`triggered_rules` 为 `[]`，**`status` 为 `ok`**（设计文档：L5 失败宽松）。否则 `regime = risk_gate["regime"]`，`triggered_rules = list(risk_gate.get("block_codes", []))`（设计文档字段名 `triggered_rules`，源数据为 `block_codes`），`status`：`crisis`→`crisis`；`warning` 或非空 `triggered_rules`→`warn`；否则 `ok`。

4. **overall_rating**（严格按设计表顺序）：
   - `red`：`miss_count >= 1` 或 `risk regime == "crisis"` 或 `signal coverage < 0.5` 或 `signal_matrix is None`（与「signal miss 触发 red」一致）。
   - `yellow`（否则若）：`warn_count >= 2` 或 `regime == "warning"` 或 `len(triggered_rules) > 0` 或 `signal coverage < 0.7`。
   - 否则 `green`。

5. 返回 `ok_output(command="hf monitor health-report", data={...}, warnings=[], errors=[])`，其中 `data` 含设计文档所列字段；`run_daily_warnings` 取 `daily.get("warnings", [])`。

运行：`cd quant && uv run python -m pytest tests/unit/test_health_report_service.py::test_overall_green_all_ok -v`  
**预期:** PASS。

- [ ] **Step 3: 提交**

```bash
git add quant/src/application/monitor quant/tests/unit/test_health_report_service.py
git commit -m "feat: 增加 L8 health_report 服务骨架与绿色路径单测"
```

---

### Task 2: 单元测试覆盖设计文档 §Testing Strategy 余下场景

**Files:**
- Modify: `quant/tests/unit/test_health_report_service.py`

为每个场景新增独立测试函数，全部通过注入 `run_daily_fn` 构造 `daily` payload，**禁止**真实 DB。

- [ ] **Step 1: 编写 `test_overall_yellow_two_factor_warns`**

构造 `factor_availability`：两个因子 `availability_rate` 在 `[0.5, 0.8)`，其余 `>= 0.8`；`signal_matrix.coverage_rate >= 0.7`；`regime` `normal`；期望 `overall_rating == "yellow"`。

- [ ] **Step 2: 编写 `test_overall_red_one_factor_miss`**

一个因子 `availability_rate < 0.5`；期望 `red`。

- [ ] **Step 3: 编写 `test_overall_red_regime_crisis`**

`regime == "crisis"`；期望 `red`。

- [ ] **Step 4: 编写 `test_overall_red_signal_coverage_low`**

`coverage_rate == 0.4`；期望 `red`。

- [ ] **Step 5: 编写 `test_signal_matrix_null_is_miss_and_red`**

`signal_matrix` 键不存在或为 `None`；期望 `signal_health.status == "miss"` 且 `overall_rating == "red"`。

- [ ] **Step 6: 编写 `test_risk_gate_null_loose_ok`**

`risk_gate is None`；期望 `risk_health.status == "ok"`，且在因子与信号均健康时 **`overall_rating` 仍为 `green`**（不因 L5 缺失降级）。

- [ ] **Step 7: 编写 `test_run_daily_exception_returns_red_envelope`**

`run_daily_fn` 抛出 `RuntimeError("boom")`；期望返回信封 `status == "error"`（或 `warning` 二选一但与 schema 一致即可），`errors` 非空，`data["overall_rating"] == "red"`，且不抛异常。

- [ ] **Step 8: 编写 `test_non_trading_skipped`**

`run_daily_fn` 返回 `data.skipped True`；期望 `overall_rating is None`，`factor_health is None`。

每写完一组断言，运行：  
`cd quant && uv run python -m pytest tests/unit/test_health_report_service.py -v`  
**预期:** 全部 PASS；若失败则调整 `health_report_service` 逻辑直至满足设计文档。

- [ ] **Step 9: 提交**

```bash
git add quant/src/application/monitor/health_report_service.py quant/tests/unit/test_health_report_service.py
git commit -m "test: 覆盖 L8 health_report 黄/红/跳过/异常等场景"
```

---

### Task 3: HTTP 路由、依赖注入与合约测试

**Files:**
- Create: `quant/src/interfaces/http/routes_monitor.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/app.py`
- Create: `quant/tests/contract/test_http_monitor.py`

- [ ] **Step 1: 在 `dependencies.py` 增加**

```python
HealthReportService = Callable[[str], dict]

def get_health_report_service() -> HealthReportService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    from application.monitor.health_report_service import run_health_report

    return lambda as_of: run_health_report(as_of, bar_store=bar_store)
```

（`get_health_report_service` 内 `import` `run_health_report` 可避免循环引用；若项目惯例为文件顶部导入，则改为顶部并验证无循环。）

- [ ] **Step 2: 实现 `routes_monitor.py`**

- `APIRouter(prefix="/v1/monitor", tags=["monitor"])`
- `GET /health-report`，`as_of: str = Query(..., description="YYYY-MM-DD")`
- 注入 `HealthReportService = Depends(get_health_report_service)`
- 调用 `raw = service(as_of)`，返回 `JSONResponse(content=raw)`（内容已是完整 envelope，与 `run_health_report` 一致）

- [ ] **Step 3: `app.py` `include_router`**

- [ ] **Step 4: 合约测试 `test_http_monitor.py`**

仿照 `quant/tests/contract/test_http_walk_forward.py`：

1. `test_get_health_report_ok`：`dependency_overrides[get_health_report_service] = lambda: lambda as_of: { ... 固定最小合法 envelope ... }`，`GET /v1/monitor/health-report?as_of=2026-04-01` 断言 200 且 `schema_version`、`command == "hf monitor health-report"`、`data.overall_rating` 等键存在。

2. `test_get_health_report_missing_as_of_422`：无 query → 422。

3. `test_get_health_report_db_unavailable_still_200`：override service 返回固定 200 体；`patch has_db_config` 为 `False` 仅用于确认路由不强制 503（与 `get_daily_run_service` 行为一致）；若实现中无 503 分支，本测可与 stub 合并为「服务仍被调用且 200」。

运行：`cd quant && uv run python -m pytest tests/contract/test_http_monitor.py -v`

- [ ] **Step 5: 提交**

```bash
git add quant/src/interfaces/http/routes_monitor.py quant/src/interfaces/http/dependencies.py quant/src/interfaces/http/app.py quant/tests/contract/test_http_monitor.py
git commit -m "feat: 增加 GET /v1/monitor/health-report 与合约测试"
```

---

### Task 4: Python 架构测试 — `application.monitor` 边界

**Files:**
- Modify: `quant/tests/architecture/test_layering_rules.py`

- [ ] **Step 1: 复制 `test_application_signal_does_not_import_interfaces` 模式**，新增 `test_application_monitor_does_not_import_interfaces`，扫描 `quant/src/application/monitor/*.py`。

运行：`cd quant && uv run python -m pytest tests/architecture/test_layering_rules.py -q`

- [ ] **Step 2: 提交**

```bash
git add quant/tests/architecture/test_layering_rules.py
git commit -m "test: 断言 application.monitor 不依赖 interfaces"
```

---

### Task 5: Rust CLI（cmd / requests / http_client / handler / dispatch）

**Files:**
- Create: `cli/src/cmd/monitor.rs`
- Modify: `cli/src/cmd/mod.rs`
- Modify: `cli/src/application/requests.rs`
- Create: `cli/src/application/handlers/monitor.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/infrastructure/http_client.rs`

- [ ] **Step 1: `MonitorArgs`** — 子命令 `health-report`，字段：`--as-of`、`--output`（默认 `table`，可选 `json`）、`--timeout-ms`（`Option<u64>`），与 `walk_forward::WalkForwardArgs` 风格一致。

- [ ] **Step 2: `MonitorHealthReportRequest`** + `AppCommand::Monitor(MonitorHealthReportRequest)` + `Cli` 的 `From` 映射。

- [ ] **Step 3: `get_health_report`** — `GET {server}/v1/monitor/health-report?as_of=...`，成功则 `parse_json`。

- [ ] **Step 4: `handlers/monitor.rs`** — `load_default_config`，`args.output == "json"` 时 `println!` pretty JSON；`table` 时按设计文档打印：

```
as_of: ...   overall: GREEN
Factor Health
  total=...  ok=...  warn=...  miss=...
...
```

（`overall_rating` 大写；因子明细可只打印 `warn`/`miss` 行以控制宽度，或与设计完全一致。）

- [ ] **Step 5: `dispatch.rs` 分支** + **`cmd/mod.rs` 不 import `crate::infrastructure`**（架构测试）。

- [ ] **Step 6: 提交**

```bash
git add cli/src/cmd/monitor.rs cli/src/cmd/mod.rs cli/src/application/requests.rs cli/src/application/handlers/monitor.rs cli/src/application/handlers/mod.rs cli/src/application/dispatch.rs cli/src/infrastructure/http_client.rs
git commit -m "feat: 增加 hf monitor health-report CLI"
```

---

### Task 6: Rust 集成测试与 `architecture_rules` 更新

**Files:**
- Create: `cli/tests/http_monitor_health_report.rs`
- Modify: `cli/tests/architecture_rules.rs`

- [ ] **Step 1: `http_monitor_health_report.rs`** — `mockito::Server` mock `GET /v1/monitor/health-report`，body 为完整 envelope（`command`: `hf monitor health-report`，`data.overall_rating`: `green`，含 `factor_health` 精简字段）；调用 `hf_cli::infrastructure::http_client::get_health_report` 或公开 handler 测试路径（与现有 `http_pipeline_daily_table.rs` 一致）；断言 table 输出含 `overall` / `GREEN`（或等价字符串）。

- [ ] **Step 2: `architecture_rules.rs`** — `cmd_files` 增加 `"cmd/monitor.rs"`。

运行：`cd cli && cargo test`

- [ ] **Step 3: 提交**

```bash
git add cli/tests/http_monitor_health_report.rs cli/tests/architecture_rules.rs
git commit -m "test: CLI monitor health-report mock HTTP 与 cmd 架构规则"
```

---

### Task 7: CLI 输出合同（schema + fixture + 文档示例）

**Files:**
- Modify: `docs/CLI_OUTPUT_SCHEMA.json`
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Create: `quant/tests/fixtures/cli_output/valid/monitor_health_report_ok.json`

- [ ] **Step 1: 在 `allOf` 中新增分支** — `if.properties.command.const = "hf monitor health-report"`，`then.properties.data` 要求 `required`: `as_of`, `overall_rating`, `factor_health`, `signal_health`, `risk_health`, `trend`, `run_daily_warnings`（非交易日允许 `overall_rating` null 时，将对应字段设为 `type: ["object","null"]` 或使用宽松 `oneOf`，与 fixture 一致）。

- [ ] **Step 2: 新增 fixture** — 与实现返回形状一致的最小合法样例。

- [ ] **Step 3: `CLI_OUTPUT_EXAMPLES.md`** — 增加一节展示 JSON 样例。

运行：`make validate-cli-output`

- [ ] **Step 4: 提交**

```bash
git add docs/CLI_OUTPUT_SCHEMA.json docs/CLI_OUTPUT_EXAMPLES.md quant/tests/fixtures/cli_output/valid/monitor_health_report_ok.json
git commit -m "docs: 补充 monitor health-report CLI 输出合同与样例"
```

---

### Task 8: 全量门禁

- [ ] **Step 1: 运行** `make check`  
**预期:** 通过。

- [ ] **Step 2: 提交**（若有格式化残留）

```bash
git add -A && git commit -m "chore: make check 收口"
```

---

## 计划自检（对照设计文档）

| 设计章节 | 对应任务 |
|----------|----------|
| Goal / Architecture / 复用 `run_daily` | Task 1–3 |
| Output Schema / 阈值 / `triggered_rules` | Task 1–2 + Task 7 |
| 非交易日 `skipped` | Task 1–2 |
| Overall Rating 优先级表 | Task 1–2 |
| CLI table/json | Task 5–6 |
| 单元 / 合约 / Rust 测试策略 | Task 2–3、6 |
| Phase 2 `trend` | 显式不实现（保持 `null`） |

**占位符检查:** 本计划不含 TBD/TODO 式步骤；实现时若发现 `run_daily` 返回键名与假设不一致，以 `daily_run_service.py` 实况为准并更新测试桩。

---

## 执行交接

计划已保存至 `docs/superpowers/plans/2026-04-06-l8-monitor-health-report-implementation-plan.md`。

**可选执行方式：**

1. **Subagent-Driven（推荐）** — 每任务独立子代理，任务间人工检查点。  
2. **Inline Execution** — 本会话用 `executing-plans` 批量推进并设检查点。

**编码前:** 按 `AGENTS.md` 在 `.worktrees/` 下使用 `using-git-worktrees` 建立隔离 worktree（除非你在对话中书面豁免 worktree）。

你希望采用哪种执行方式？
