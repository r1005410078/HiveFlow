# Pipeline Compare Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 `pipeline compare` 版本对比回放能力（30 天窗口，`json/table` 双输出），支持 `v1` vs `v1.1` 逐日明细与汇总统计。

**Architecture:** `quant` 侧新增 compare 用例服务并暴露 `/api/v1/pipeline/compare`；HTTP 层仅做 DTO + service 调用；`cli` 侧新增 `pipeline compare` 子命令并接入 table 渲染；复用现有 `run_daily(score_version=...)` 与统一 CLI Output 合同。

**Tech Stack:** Python (`fastapi`, `pytest`, `pydantic`, `uv`), Rust (`clap`, `reqwest`, `serde_json`, `comfy-table`).

---

## 0. 文件与职责

- Modify: `quant/src/application/daily_run_service.py`（补 `score_version` 可选参数）
- Create: `quant/src/application/pipeline_compare_service.py`（逐日对比与汇总）
- Modify: `quant/src/interfaces/http/dependencies.py`（provider 装配 compare service）
- Modify: `quant/src/interfaces/http/schemas.py`（compare 请求/响应 DTO）
- Modify: `quant/src/interfaces/http/routes_daily_run.py`（新增 `/compare` 路由）
- Create: `quant/tests/unit/pipeline/test_compare_service.py`
- Create: `quant/tests/contract/test_http_pipeline_compare_endpoint.py`
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/cmd/pipeline.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Create: `cli/src/application/handlers/pipeline_compare.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Create: `cli/tests/http_pipeline_compare.rs`
- Create: `cli/tests/http_pipeline_compare_table.rs`

---

### Task 1: 先补 quant 侧失败测试（TDD 起手）

**Files:**
- Create: `quant/tests/unit/pipeline/test_compare_service.py`
- Create: `quant/tests/contract/test_http_pipeline_compare_endpoint.py`

- [x] **Step 1: 写 compare service 单测（逐日条目 + 汇总统计）**

```python
def test_compare_service_builds_daily_items_and_summary(): ...
def test_compare_service_counts_top1_changes(): ...
def test_compare_service_handles_empty_window(): ...
```

- [x] **Step 2: 写 HTTP contract 测试**

```python
def test_post_pipeline_compare_contract(): ...
```

- [x] **Step 3: 运行并确认失败**

Run:
`cd quant && uv run pytest tests/unit/pipeline/test_compare_service.py tests/contract/test_http_pipeline_compare_endpoint.py -q`

- [x] **Step 4: 提交失败测试**

```bash
git add quant/tests/unit/pipeline/test_compare_service.py quant/tests/contract/test_http_pipeline_compare_endpoint.py
git commit -m "test: add failing tests for pipeline compare endpoint and service"
```

---

### Task 2: 实现 quant compare service 与 HTTP 接口

**Files:**
- Modify: `quant/src/application/daily_run_service.py`
- Create: `quant/src/application/pipeline_compare_service.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/schemas.py`
- Modify: `quant/src/interfaces/http/routes_daily_run.py`
- Test: `quant/tests/unit/pipeline/test_compare_service.py`
- Test: `quant/tests/contract/test_http_pipeline_compare_endpoint.py`

- [x] **Step 1: 扩展 daily 服务签名（可传 `score_version`）**

```python
def run_daily(as_of: str, root, bar_store=None, score_version: str = "l2-score-v1.1") -> dict:
    ...
    l2_decision = compute_l2_decision_from_snapshot(..., score_version=score_version)
```

- [x] **Step 2: 新建 compare service**

```python
def run_pipeline_compare(start_date: str, end_date: str, top_n: int, daily_runner) -> dict:
    # 逐日执行 v1 / v1.1，提取 top1, warning_count, min_availability
    # 聚合 summary（days, avg_warning, avg_min_availability, top1_change_days）
```

- [x] **Step 3: 装配 provider 与路由**

```python
# dependencies.py
def get_pipeline_compare_service() -> PipelineCompareService: ...

# routes_daily_run.py
@router.post("/compare")
def post_compare(...): ...
```

- [x] **Step 4: 定义 compare DTO**

```python
class PipelineCompareRequest(BaseModel): ...
class PipelineCompareResponse(BaseModel): ...
```

- [x] **Step 5: 运行 quant 测试**

Run:
`cd quant && uv run pytest tests/unit/pipeline/test_compare_service.py tests/contract/test_http_pipeline_compare_endpoint.py tests/contract/test_http_daily_endpoint.py -q`

- [x] **Step 6: 提交 quant 实现**

```bash
git add quant/src/application/daily_run_service.py quant/src/application/pipeline_compare_service.py quant/src/interfaces/http/dependencies.py quant/src/interfaces/http/schemas.py quant/src/interfaces/http/routes_daily_run.py quant/tests/unit/pipeline/test_compare_service.py quant/tests/contract/test_http_pipeline_compare_endpoint.py
git commit -m "feat: add pipeline compare service and http endpoint"
```

---

### Task 3: 实现 CLI `pipeline compare`（json/table）

**Files:**
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/cmd/pipeline.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Create: `cli/src/application/handlers/pipeline_compare.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Create: `cli/tests/http_pipeline_compare.rs`
- Create: `cli/tests/http_pipeline_compare_table.rs`

- [x] **Step 1: 增加命令与请求结构**

```rust
pipeline compare --start-date --end-date --top-n --output
```

- [x] **Step 2: 新增 compare HTTP client 方法**

```rust
pub fn post_pipeline_compare(...) -> Result<Value, AppError>
```

- [x] **Step 3: 新增 handler 与 table 渲染**

```rust
pub fn handle(args: PipelineCompareRequest) -> Result<(), AppError> { ... }
pub fn render_pipeline_compare_table(payload: &Value) -> String { ... }
```

- [x] **Step 4: 补 CLI 测试（json + table）**

Run:
`cd cli && cargo test --test http_pipeline_compare --test http_pipeline_compare_table`

- [x] **Step 5: 提交 CLI 实现**

```bash
git add cli/src/application/requests.rs cli/src/cmd/pipeline.rs cli/src/application/handlers/mod.rs cli/src/application/handlers/pipeline_compare.rs cli/src/application/dispatch.rs cli/src/infrastructure/http_client.rs cli/src/infrastructure/table_renderer.rs cli/tests/http_pipeline_compare.rs cli/tests/http_pipeline_compare_table.rs
git commit -m "feat: add cli pipeline compare command with table output"
```

---

### Task 4: 全量验证与收口

**Files:**
- Verify only

- [x] **Step 1: 架构门禁**

Run:
`cd /Users/rongts/strat-flow && make architecture-check`

- [x] **Step 2: 全量检查**

Run:
`cd /Users/rongts/strat-flow && make check`

- [x] **Step 3: 若有微调提交**

```bash
git add <files>
git commit -m "test: finalize pipeline compare verification"
```

- [x] **Step 4: 推送分支**

```bash
git push
```
