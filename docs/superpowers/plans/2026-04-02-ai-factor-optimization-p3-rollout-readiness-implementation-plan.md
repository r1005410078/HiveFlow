# AI Factor Optimization P3 Rollout Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 `advice_only=true` 的前提下，补齐 P3 上线前闭环：回放验证、输出合同固化、发布门禁状态。

**Architecture:** 继续复用统一接口 `POST /api/v1/factor-optimization/evaluate`，在 `application/factor_optimization` 增加发布门禁聚合，不在 `interfaces/http` 写业务逻辑。新增一个离线回放脚本用于批量调用 evaluate 并生成审计报告。CLI 输出合同通过 schema + fixtures 固化，避免字段漂移。

**Tech Stack:** Python (`fastapi`, `pytest`, `uv`, `jsonschema`), Rust CLI (`cargo test`), Markdown docs.

---

## 0. 文件与职责

**Application 层（quant）**
- Create: `quant/src/application/factor_optimization/release_gate_service.py` — 评估 `pass/watch/fail` 与门禁原因
- Modify: `quant/src/application/factor_optimization/report_service.py` — 组装 `data.release_gate`
- Modify: `quant/src/application/factor_optimization/__init__.py`

**Interfaces 层（quant）**
- Modify: `quant/tests/contract/test_http_factor_optimization_endpoint.py` — 验证 `release_gate` 结构

**离线回放工具**
- Create: `scripts/factor_optimize_replay.py` — 按日期区间调用 evaluate 并生成 JSON/Markdown 报告
- Create: `docs/analysis/factor_optimization/replay/README.md` — 回放报告目录规范

**输出合同与示例**
- Modify: `docs/CLI_OUTPUT_SCHEMA.json` — 新增 `hf factor optimize` 的 `data` 合同约束
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md` — 增加 `hf factor optimize` JSON 示例（含 `top_combinations/release_gate`）
- Create: `quant/tests/fixtures/cli_output/valid/factor_optimize_ok.json`
- Create: `quant/tests/fixtures/cli_output/invalid/factor_optimize_missing_release_gate.json`

**测试**
- Create: `quant/tests/unit/factor_optimization/test_release_gate_service.py`
- Modify: `quant/tests/unit/factor_optimization/test_report_service.py`

---

### Task 1: 先写失败测试（release_gate）

**Files:**
- Create: `quant/tests/unit/factor_optimization/test_release_gate_service.py`
- Modify: `quant/tests/unit/factor_optimization/test_report_service.py`
- Modify: `quant/tests/contract/test_http_factor_optimization_endpoint.py`

- [ ] **Step 1: 写 unit 失败测试（门禁分级）**

```python
from application.factor_optimization.release_gate_service import build_release_gate


def test_build_release_gate_returns_pass_when_metrics_healthy() -> None:
    out = build_release_gate(
        coverage={"symbols": 120, "bars": 32000},
        correlation_analysis={"alert_count": 0},
        top_combinations={"items": [{"rank": 1, "composite_score": 1.2}]},
    )
    assert out["status"] == "pass"
    assert out["blocking_reasons"] == []
```

- [ ] **Step 2: 写 unit 失败测试（高告警触发 fail）**

```python
def test_build_release_gate_returns_fail_when_alerts_too_high() -> None:
    out = build_release_gate(
        coverage={"symbols": 120, "bars": 32000},
        correlation_analysis={"alert_count": 5},
        top_combinations={"items": [{"rank": 1, "composite_score": 1.2}]},
    )
    assert out["status"] == "fail"
    assert any("alert_count" in reason for reason in out["blocking_reasons"])
```

- [ ] **Step 3: 扩展 report_service 测试（输出含 release_gate）**

```python
def test_build_factor_optimization_report_contains_release_gate() -> None:
    report = build_factor_optimization_report(
        start_date="2026-01-01",
        end_date="2026-04-01",
        factor_names=["momentum_20", "inv_volatility_20"],
        analysis={"factor_health": [], "correlation_matrix": {}, "coverage": {"symbols": 10, "bars": 1000}},
        recommendations=[{"name": "balanced", "weights": {"momentum_20": 0.6, "inv_volatility_20": 0.4}}],
    )
    assert {"status", "blocking_reasons", "watch_items"} <= set(report["data"]["release_gate"].keys())
```

- [ ] **Step 4: 扩展 contract 测试（接口结构）**

```python
assert {"status", "blocking_reasons", "watch_items"} <= set(payload["data"]["release_gate"].keys())
assert payload["data"]["release_gate"]["status"] in {"pass", "watch", "fail"}
```

- [ ] **Step 5: 运行失败测试确认 RED**

Run: `cd quant && uv run pytest tests/unit/factor_optimization/test_release_gate_service.py tests/unit/factor_optimization/test_report_service.py tests/contract/test_http_factor_optimization_endpoint.py -q`  
Expected: FAIL（`release_gate_service` 不存在）。

- [ ] **Step 6: 提交失败测试**

```bash
git add quant/tests/unit/factor_optimization/test_release_gate_service.py \
  quant/tests/unit/factor_optimization/test_report_service.py \
  quant/tests/contract/test_http_factor_optimization_endpoint.py
git commit -m "test: add failing tests for factor optimization release gate"
```

---

### Task 2: 实现 release_gate 并接入 evaluate

**Files:**
- Create: `quant/src/application/factor_optimization/release_gate_service.py`
- Modify: `quant/src/application/factor_optimization/report_service.py`
- Modify: `quant/src/application/factor_optimization/__init__.py`
- Test: `quant/tests/unit/factor_optimization/test_release_gate_service.py`
- Test: `quant/tests/unit/factor_optimization/test_report_service.py`
- Test: `quant/tests/contract/test_http_factor_optimization_endpoint.py`

- [ ] **Step 1: 实现 release_gate_service（最小规则）**

```python
def build_release_gate(coverage: dict, correlation_analysis: dict, top_combinations: dict) -> dict:
    symbols = int(coverage.get("symbols", 0))
    bars = int(coverage.get("bars", 0))
    alert_count = int(correlation_analysis.get("alert_count", 0))
    top_items = top_combinations.get("items", [])

    blocking_reasons: list[str] = []
    watch_items: list[str] = []

    if symbols < 20 or bars < 500:
        blocking_reasons.append("coverage_too_low")
    if alert_count >= 4:
        blocking_reasons.append(f"alert_count_too_high:{alert_count}")
    elif alert_count >= 2:
        watch_items.append(f"alert_count_watch:{alert_count}")
    if not top_items:
        blocking_reasons.append("no_top_combinations")

    status = "pass"
    if blocking_reasons:
        status = "fail"
    elif watch_items:
        status = "watch"

    return {"status": status, "blocking_reasons": blocking_reasons, "watch_items": watch_items}
```

- [ ] **Step 2: 在 report_service 中接入 release_gate**

```python
release_gate = build_release_gate(
    coverage=analysis.get("coverage", {}),
    correlation_analysis=correlation_analysis,
    top_combinations=top_combinations,
)
```

并在返回体 `data` 中增加：

```python
"release_gate": release_gate,
```

- [ ] **Step 3: 导出新服务**

```python
from application.factor_optimization.release_gate_service import build_release_gate
```

- [ ] **Step 4: 跑测试确认 GREEN**

Run: `cd quant && uv run pytest tests/unit/factor_optimization tests/contract/test_http_factor_optimization_endpoint.py -q`  
Expected: PASS。

- [ ] **Step 5: 提交实现**

```bash
git add quant/src/application/factor_optimization/release_gate_service.py \
  quant/src/application/factor_optimization/report_service.py \
  quant/src/application/factor_optimization/__init__.py \
  quant/tests/unit/factor_optimization/test_release_gate_service.py \
  quant/tests/unit/factor_optimization/test_report_service.py \
  quant/tests/contract/test_http_factor_optimization_endpoint.py
git commit -m "feat: add release gate status to factor optimization evaluate"
```

---

### Task 3: 固化 `hf factor optimize` 输出合同（schema + fixtures）

**Files:**
- Modify: `docs/CLI_OUTPUT_SCHEMA.json`
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Create: `quant/tests/fixtures/cli_output/valid/factor_optimize_ok.json`
- Create: `quant/tests/fixtures/cli_output/invalid/factor_optimize_missing_release_gate.json`

- [ ] **Step 1: 先加 fixtures（让校验先失败）**

`valid/factor_optimize_ok.json` 关键字段：

```json
{
  "schema_version": "1.0.0",
  "command": "hf factor optimize",
  "run_id": "run_factor_opt_001",
  "status": "ok",
  "generated_at": "2026-04-02T00:00:00+00:00",
  "source": "web_search",
  "advice_only": true,
  "decision_weight": 0,
  "data": {
    "factor_names": ["momentum_20", "inv_volatility_20"],
    "analysis": {"factor_health": [], "correlation_matrix": {}, "coverage": {"symbols": 30, "bars": 2000}},
    "correlation_analysis": {"threshold": 0.7, "alerts": [], "alert_count": 0},
    "top_combinations": {"search_space": {"factor_pool_size": 2, "combination_size_min": 2, "combination_size_max": 2, "candidate_count": 1}, "ranking_profile": "balanced_v1", "items": []},
    "release_gate": {"status": "watch", "blocking_reasons": [], "watch_items": ["alert_count_watch:2"]},
    "recommendations": [],
    "recommended_scheme": null
  },
  "warnings": [],
  "errors": []
}
```

- [ ] **Step 2: 在 schema 增加 `hf factor optimize` 条件约束**

在 `allOf` 增加：

```json
{
  "if": { "properties": { "command": { "const": "hf factor optimize" } } },
  "then": {
    "properties": {
      "data": {
        "type": "object",
        "required": ["factor_names", "analysis", "correlation_analysis", "top_combinations", "release_gate", "recommendations"]
      }
    }
  }
}
```

- [ ] **Step 3: 在示例文档追加 `hf factor optimize` JSON 示例**

追加章节标题：

```markdown
## 8. hf factor optimize（JSON 示例，含 Top5 与 release_gate）
```

- [ ] **Step 4: 跑合同校验**

Run: `./scripts/validate_cli_output_fixtures.sh`  
Expected: PASS，新增 valid/invalid 均被正确识别。

- [ ] **Step 5: 提交合同固化**

```bash
git add docs/CLI_OUTPUT_SCHEMA.json \
  docs/CLI_OUTPUT_EXAMPLES.md \
  quant/tests/fixtures/cli_output/valid/factor_optimize_ok.json \
  quant/tests/fixtures/cli_output/invalid/factor_optimize_missing_release_gate.json
git commit -m "test: harden factor optimize cli output contract with schema and fixtures"
```

---

### Task 4: 增加离线回放验证脚本与报告产物

**Files:**
- Create: `scripts/factor_optimize_replay.py`
- Create: `docs/analysis/factor_optimization/replay/README.md`

- [ ] **Step 1: 写脚本最小接口**

```python
#!/usr/bin/env python3
import argparse
import json
from datetime import date, timedelta
from pathlib import Path
import requests
```

参数：
- `--server-url`
- `--start-date`
- `--end-date`
- `--factors`
- `--output-dir`（默认 `docs/analysis/factor_optimization/replay`）

- [ ] **Step 2: 实现逐日调用 evaluate + 汇总**

输出结构示例：

```json
{
  "summary": {
    "days": 20,
    "pass_days": 14,
    "watch_days": 5,
    "fail_days": 1,
    "avg_alert_count": 0.8
  },
  "daily_items": [
    {"as_of": "2026-03-01", "release_gate_status": "pass", "alert_count": 0, "top1_factors": ["momentum_20", "inv_volatility_20"]}
  ]
}
```

- [ ] **Step 3: 生成 Markdown 报告**

报告文件：`docs/analysis/factor_optimization/replay/replay_<start>_<end>.md`  
包含：
- Summary 指标
- `fail/watch` 日期列表
- Top1 组合变更天数

- [ ] **Step 4: 增加 README（使用方式）**

命令示例：

```bash
python scripts/factor_optimize_replay.py \
  --server-url http://127.0.0.1:8000 \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60,trend_stability_20,relative_strength_vs_index
```

- [ ] **Step 5: 手工执行一次并检查产物**

Run: 上述命令  
Expected: 生成 `.json` 与 `.md` 报告文件。

- [ ] **Step 6: 提交回放工具**

```bash
git add scripts/factor_optimize_replay.py docs/analysis/factor_optimization/replay/README.md
git commit -m "feat: add factor optimize replay report generator"
```

---

### Task 5: 全量验收与收口

**Files:**
- Modify: `docs/DOCUMENTATION_INDEX.md`
- Modify: `docs/FACTOR_OPTIMIZATION_P2_USAGE.md`

- [ ] **Step 1: 更新文档导航**

新增入口：
- P3 回放与门禁说明
- 回放报告目录入口

- [ ] **Step 2: 更新 P2 使用文档（追加 P3 门禁字段）**

追加字段说明：
- `data.release_gate.status`
- `data.release_gate.blocking_reasons`
- `data.release_gate.watch_items`

- [ ] **Step 3: 跑门禁**

Run:
- `make architecture-check`
- `make check`

Expected: 全部 PASS。

- [ ] **Step 4: 最终提交**

```bash
git add docs/DOCUMENTATION_INDEX.md docs/FACTOR_OPTIMIZATION_P2_USAGE.md
git commit -m "docs: add p3 rollout readiness and replay guidance"
```

---

## 验收标准（P3 Done）

- `evaluate` 输出包含 `release_gate` 且 contract 测试通过
- CLI 输出 schema 对 `hf factor optimize` 有明确约束并通过 fixtures 回归
- 可一键执行回放脚本并生成 JSON + Markdown 报告
- `make architecture-check` 与 `make check` 全绿

## 自检（Spec Coverage）

- 回放验证：Task 4 覆盖（批量 evaluate + 报告）
- 输出合同固化：Task 3 覆盖（schema + fixtures + examples）
- 发布门禁：Task 1/2 覆盖（`release_gate` pass/watch/fail）

