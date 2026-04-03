# Pipeline Compare Phase2 Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `pipeline compare` 中新增 Phase 2 收益/风险/分组稳定性评估（industry + market_cap_bucket），并在 CLI `json/table` 完整展示。

**Architecture:** `quant` 在现有 `application/pipeline_compare_service.py` 内扩展 analytics 编排；`interfaces/http` 仅扩展 DTO；`cli` 扩展 compare table 渲染区块。保持 `interfaces -> application -> domain` 与 `cmd -> application -> domain`、`application -> infrastructure` 约束。

**Tech Stack:** Python (`fastapi`, `pytest`, `pydantic`, `uv`), Rust (`clap`, `serde_json`, `comfy-table`), existing market-data stores.

---

## 0. 文件与职责

### Quant
- Modify: `quant/src/application/pipeline_compare_service.py`（收益序列、风险统计、分组稳定性）
- Modify: `quant/src/interfaces/http/schemas.py`（compare response 新增 `analytics`）
- Modify: `quant/tests/unit/pipeline/test_compare_service.py`（analytics 单测）
- Modify: `quant/tests/contract/test_http_pipeline_compare_endpoint.py`（contract 新字段）

### CLI
- Modify: `cli/src/infrastructure/table_renderer.rs`（compare table 新增 analytics 区块）
- Modify: `cli/tests/http_pipeline_compare.rs`（json 透传断言）
- Modify: `cli/tests/http_pipeline_compare_table.rs`（table analytics 区块断言）

### Docs
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`（补 compare Phase2 JSON 示例）
- Modify: `AGENTS.md`（更新“近期已交付”与常用命令说明）

---

### Task 1: 先写 Quant 失败测试（analytics）

**Files:**
- Modify: `quant/tests/unit/pipeline/test_compare_service.py`
- Modify: `quant/tests/contract/test_http_pipeline_compare_endpoint.py`

- [ ] **Step 1: 增加 unit 失败测试（收益与风险统计）**

```python
def test_compare_service_builds_return_metrics() -> None:
    # 构造 daily_runner 返回固定 top1 + next-day close
    # 断言 analytics.return_metrics.v1/v1_1/diff 存在且数值可计算
    ...
```

- [ ] **Step 2: 增加 unit 失败测试（分组稳定性）**

```python
def test_compare_service_builds_group_stability_by_industry_and_cap_bucket() -> None:
    # 构造 industry + market_cap 数据
    # 断言 group_key、items[*].industry/cap_bucket/sample_days/stability_flag
    ...
```

- [ ] **Step 3: 扩展 contract 失败测试（HTTP 响应新增 analytics）**

```python
def test_post_pipeline_compare_contains_phase2_analytics() -> None:
    payload = client.post("/api/v1/pipeline/compare", json={...}).json()
    assert "analytics" in payload["data"]
    assert {"return_metrics", "daily_return_series", "group_stability"} <= set(payload["data"]["analytics"].keys())
```

- [ ] **Step 4: 运行测试确认 RED**

Run:
`cd quant && uv run pytest tests/unit/pipeline/test_compare_service.py tests/contract/test_http_pipeline_compare_endpoint.py -q`

Expected: FAIL（`analytics` 字段/统计逻辑尚不存在）。

- [ ] **Step 5: 提交失败测试**

```bash
git add quant/tests/unit/pipeline/test_compare_service.py quant/tests/contract/test_http_pipeline_compare_endpoint.py
git commit -m "test: add failing tests for pipeline compare phase2 analytics"
```

---

### Task 2: 实现 Quant compare analytics（服务内扩展）

**Files:**
- Modify: `quant/src/application/pipeline_compare_service.py`
- Modify: `quant/src/interfaces/http/schemas.py`
- Modify: `quant/tests/unit/pipeline/test_compare_service.py`
- Modify: `quant/tests/contract/test_http_pipeline_compare_endpoint.py`

- [ ] **Step 1: 在 compare service 增加收益序列提取**

```python
# 每日提取 top1_next_day_return（缺失则记录 warning）
daily_return_series_v1 = [...]
daily_return_series_v1_1 = [...]
```

- [ ] **Step 2: 增加 return_metrics 计算函数**

```python
def _build_return_metrics(returns: list[float]) -> dict:
    # cumulative_return, win_rate, max_drawdown, annualized_volatility, sharpe
    ...
```

- [ ] **Step 3: 增加 group_stability 计算函数（industry + market_cap_bucket）**

```python
def _build_group_stability(daily_items: list[dict]) -> dict:
    # group_key 固定 industry_market_cap_bucket
    # items: industry/cap_bucket/sample_days/v1/v1_1/diff/stability_flag
    ...
```

- [ ] **Step 4: 将 analytics 挂载到 compare 响应 data**

```python
result["data"]["analytics"] = {
    "return_metrics": ...,
    "daily_return_series": ...,
    "group_stability": ...,
}
```

- [ ] **Step 5: 扩展 HTTP schema（compare response）**

```python
class PipelineCompareAnalytics(BaseModel): ...
# compare response data 新增 analytics: PipelineCompareAnalytics
```

- [ ] **Step 6: 运行 quant 测试确认 GREEN**

Run:
`cd quant && uv run pytest tests/unit/pipeline/test_compare_service.py tests/contract/test_http_pipeline_compare_endpoint.py tests/contract/test_http_daily_endpoint.py -q`

Expected: PASS。

- [ ] **Step 7: 提交实现**

```bash
git add quant/src/application/pipeline_compare_service.py quant/src/interfaces/http/schemas.py quant/tests/unit/pipeline/test_compare_service.py quant/tests/contract/test_http_pipeline_compare_endpoint.py
git commit -m "feat: add phase2 analytics to pipeline compare service"
```

---

### Task 3: 扩展 CLI compare 输出（json/table）

**Files:**
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Modify: `cli/tests/http_pipeline_compare.rs`
- Modify: `cli/tests/http_pipeline_compare_table.rs`

- [ ] **Step 1: 先扩展失败测试（json）**

```rust
#[test]
fn pipeline_compare_json_contains_phase2_analytics() {
    // 断言 data.analytics.return_metrics/group_stability 存在
}
```

- [ ] **Step 2: 扩展失败测试（table）**

```rust
#[test]
fn pipeline_compare_table_renders_phase2_analytics_sections() {
    // 断言“收益与风险统计”“分组稳定性（industry + market_cap_bucket）”及关键列
}
```

- [ ] **Step 3: 实现 table 渲染区块**

```rust
// render_pipeline_compare_table
// 追加 analytics 区块：
// 1) 收益与风险统计
// 2) 分组稳定性（industry + market_cap_bucket）
```

- [ ] **Step 4: 运行 CLI compare 测试**

Run:
`cd cli && cargo test --test http_pipeline_compare --test http_pipeline_compare_table`

Expected: PASS。

- [ ] **Step 5: 提交 CLI 改动**

```bash
git add cli/src/infrastructure/table_renderer.rs cli/tests/http_pipeline_compare.rs cli/tests/http_pipeline_compare_table.rs
git commit -m "feat: render phase2 analytics in pipeline compare outputs"
```

---

### Task 4: 文档收口与全量门禁

**Files:**
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: 更新 CLI_OUTPUT_EXAMPLES compare 示例**

补充 Phase 2 compare JSON 关键字段：
- `data.analytics.return_metrics`
- `data.analytics.daily_return_series`
- `data.analytics.group_stability`

- [ ] **Step 2: 更新 AGENTS 快速上下文**

在“近期已交付”中补：
- compare Phase2 analytics 指标
- 分组稳定性口径（industry + market_cap_bucket）

- [ ] **Step 3: 跑架构门禁**

Run:
`cd /Users/rongts/strat-flow && make architecture-check`

Expected: PASS。

- [ ] **Step 4: 跑全量门禁**

Run:
`cd /Users/rongts/strat-flow && make check`

Expected: PASS。

- [ ] **Step 5: 最终提交**

```bash
git add docs/CLI_OUTPUT_EXAMPLES.md AGENTS.md
git commit -m "docs: update pipeline compare phase2 analytics examples and context"
```

---

## 验收标准（Done）

- `/api/v1/pipeline/compare` 输出包含 `data.analytics` 且 contract 测试通过。
- analytics 至少包含：收益风险统计、日度收益序列、分组稳定性（industry + market_cap_bucket）。
- CLI `pipeline compare` 的 `json/table` 均展示 Phase 2 新字段。
- `make architecture-check` 与 `make check` 全绿。

## 自检（Spec Coverage）

- 收益/风险指标：Task 1/2 覆盖。
- 分组稳定性（industry + market_cap_bucket）：Task 1/2 覆盖。
- CLI 输出增强：Task 3 覆盖。
- 文档与门禁收口：Task 4 覆盖。
