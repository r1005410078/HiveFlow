# AI Factor Optimization P1 Unified Evaluate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不新增 endpoint 的前提下，统一扩展 `POST /api/v1/factor-optimization/evaluate`，交付 P1-A（相关性告警）和 P1-B（10维报告）。

**Architecture:** 延续 P0 的统一接口模式，在 `application/factor_optimization` 中新增告警与报告组装逻辑，`interfaces/http` 仅扩展 DTO 与参数校验，CLI 继续复用 `hf factor optimize` 做 json/table 展示增强。保持依赖方向 `interfaces -> application -> domain` 与 `cmd -> application -> infrastructure`。

**Tech Stack:** Python (`pytest`, `fastapi`, `pydantic`, `uv`), Rust (`clap`, `reqwest`, `serde_json`, `cargo test`).

---

## 0. 文件与职责

**Quant Application**:
- Create: `quant/src/application/factor_optimization/correlation_alert_service.py` — 高相关告警生成
- Create: `quant/src/application/factor_optimization/report_10d_service.py` — 10维报告结构生成
- Modify: `quant/src/application/factor_optimization/report_service.py` — 统一编排 `analysis + recommendations + correlation_analysis + report`
- Modify: `quant/src/application/factor_optimization/__init__.py`

**Quant HTTP**:
- Modify: `quant/src/interfaces/http/schemas.py` — 扩展 request/response 字段
- Modify: `quant/src/interfaces/http/routes_factor_optimization.py` — 新增阈值校验（`0 < threshold <= 1`）

**Quant Tests**:
- Create: `quant/tests/unit/factor_optimization/test_correlation_alert_service.py`
- Create: `quant/tests/unit/factor_optimization/test_report_10d_service.py`
- Modify: `quant/tests/unit/factor_optimization/test_report_service.py`
- Modify: `quant/tests/contract/test_http_factor_optimization_endpoint.py`

**CLI**:
- Modify: `cli/src/infrastructure/http_client.rs` — 可选透传 `correlation_threshold`
- Modify: `cli/src/application/requests.rs` — 增加 `correlation_threshold`
- Modify: `cli/src/cmd/factor.rs` — 增加 `--correlation-threshold`
- Modify: `cli/src/application/handlers/factor_optimize.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs` — 增加“相关性告警”“10维摘要”板块

**CLI Tests**:
- Modify: `cli/tests/http_factor_optimize.rs`
- Modify: `cli/tests/http_factor_optimize_table.rs`

---

### Task 1: P1-A 失败测试（相关性告警）

**Files:**
- Create: `quant/tests/unit/factor_optimization/test_correlation_alert_service.py`

- [ ] **Step 1: 写失败测试（阈值触发 + severity 分级 + 计数）**

```python
from application.factor_optimization.correlation_alert_service import build_correlation_alerts


def test_build_correlation_alerts_filters_by_threshold_and_sets_severity() -> None:
    correlation_matrix = {
        "momentum_20": {
            "momentum_20": 1.0,
            "max_drawdown_60": 0.82,
            "turnover_rate": 0.55,
        },
        "max_drawdown_60": {
            "momentum_20": 0.82,
            "max_drawdown_60": 1.0,
            "turnover_rate": 0.71,
        },
        "turnover_rate": {
            "momentum_20": 0.55,
            "max_drawdown_60": 0.71,
            "turnover_rate": 1.0,
        },
    }
    metrics = {
        "momentum_20": {"ic": 0.12, "sharpe": 1.6},
        "max_drawdown_60": {"ic": 0.09, "sharpe": 1.2},
        "turnover_rate": {"ic": 0.05, "sharpe": 0.9},
    }

    out = build_correlation_alerts(
        correlation_matrix=correlation_matrix,
        metrics=metrics,
        threshold=0.7,
    )

    assert out["threshold"] == 0.7
    assert out["alert_count"] == 2
    assert out["alerts"][0]["severity"] in {"high", "medium"}
    assert {"factor_a", "factor_b", "correlation", "severity", "suggestion"} <= set(out["alerts"][0].keys())
```

- [ ] **Step 2: 跑测试并确认失败**

Run: `cd quant && uv run pytest tests/unit/factor_optimization/test_correlation_alert_service.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 提交失败测试**

```bash
git add quant/tests/unit/factor_optimization/test_correlation_alert_service.py
git commit -m "test: add failing tests for correlation alert service"
```

---

### Task 2: P1-A 实现（相关性告警 + report 编排接入）

**Files:**
- Create: `quant/src/application/factor_optimization/correlation_alert_service.py`
- Modify: `quant/src/application/factor_optimization/report_service.py`
- Modify: `quant/src/application/factor_optimization/__init__.py`
- Test: `quant/tests/unit/factor_optimization/test_correlation_alert_service.py`
- Modify: `quant/tests/unit/factor_optimization/test_report_service.py`

- [ ] **Step 1: 实现告警服务**

```python
def build_correlation_alerts(
    correlation_matrix: dict[str, dict[str, float]],
    metrics: dict[str, dict[str, float]],
    threshold: float = 0.7,
) -> dict:
    if threshold <= 0 or threshold > 1:
        raise ValueError("correlation_threshold must be in (0, 1]")

    names = sorted(correlation_matrix.keys())
    alerts = []
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            corr = float(correlation_matrix.get(left, {}).get(right, 0.0))
            if abs(corr) < threshold:
                continue
            severity = "high" if abs(corr) >= 0.8 else "medium"
            left_score = float(metrics.get(left, {}).get("ic", 0.0)) + float(metrics.get(left, {}).get("sharpe", 0.0))
            right_score = float(metrics.get(right, {}).get("ic", 0.0)) + float(metrics.get(right, {}).get("sharpe", 0.0))
            weaker = right if left_score >= right_score else left
            alerts.append(
                {
                    "factor_a": left,
                    "factor_b": right,
                    "correlation": round(corr, 6),
                    "severity": severity,
                    "suggestion": f"consider reducing weight for {weaker}",
                }
            )
    alerts.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return {"threshold": threshold, "alerts": alerts, "alert_count": len(alerts)}
```

- [ ] **Step 2: 在 `run_factor_optimization` 中接入 `correlation_analysis`**

```python
correlation_analysis = build_correlation_alerts(
    correlation_matrix=analysis.get("correlation_matrix", {}),
    metrics=metrics,
    threshold=correlation_threshold,
)
```

- [ ] **Step 3: 扩展 report_service 单测断言**

```python
assert "correlation_analysis" in report["data"]
assert report["data"]["correlation_analysis"]["threshold"] == 0.7
```

- [ ] **Step 4: 运行相关单测**

Run: `cd quant && uv run pytest tests/unit/factor_optimization/test_correlation_alert_service.py tests/unit/factor_optimization/test_report_service.py -q`
Expected: PASS。

- [ ] **Step 5: 提交实现**

```bash
git add quant/src/application/factor_optimization/correlation_alert_service.py \
  quant/src/application/factor_optimization/report_service.py \
  quant/src/application/factor_optimization/__init__.py \
  quant/tests/unit/factor_optimization/test_correlation_alert_service.py \
  quant/tests/unit/factor_optimization/test_report_service.py
git commit -m "feat: add correlation alerts to factor optimization evaluate"
```

---

### Task 3: P1-B 失败测试（10维报告）

**Files:**
- Create: `quant/tests/unit/factor_optimization/test_report_10d_service.py`

- [ ] **Step 1: 写失败测试（10维完整 + checklist）**

```python
from application.factor_optimization.report_10d_service import build_report_10d


def test_build_report_10d_returns_fixed_dimensions_and_g3_checklist() -> None:
    out = build_report_10d(
        factor_names=["momentum_20", "inv_volatility_20"],
        analysis={"factor_health": [], "coverage": {"symbols": 10, "bars": 800}},
        recommendations=[{"name": "balanced", "weights": {"momentum_20": 0.6, "inv_volatility_20": 0.4}}],
        correlation_analysis={"alert_count": 1, "alerts": []},
    )

    assert len(out["matrix_10d"]) == 10
    assert out["summary"]["recommended_scheme"] == "balanced"
    assert len(out["g3_checklist"]) == 3
    assert out["g3_checklist"][0]["checked"] is False
```

- [ ] **Step 2: 跑测试并确认失败**

Run: `cd quant && uv run pytest tests/unit/factor_optimization/test_report_10d_service.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 提交失败测试**

```bash
git add quant/tests/unit/factor_optimization/test_report_10d_service.py
git commit -m "test: add failing tests for 10d report service"
```

---

### Task 4: P1-B 实现（10维报告 + HTTP contract）

**Files:**
- Create: `quant/src/application/factor_optimization/report_10d_service.py`
- Modify: `quant/src/application/factor_optimization/report_service.py`
- Modify: `quant/src/application/factor_optimization/__init__.py`
- Modify: `quant/src/interfaces/http/schemas.py`
- Modify: `quant/src/interfaces/http/routes_factor_optimization.py`
- Modify: `quant/tests/contract/test_http_factor_optimization_endpoint.py`
- Test: `quant/tests/unit/factor_optimization/test_report_10d_service.py`

- [ ] **Step 1: 实现 10维报告服务**

```python
def build_report_10d(factor_names, analysis, recommendations, correlation_analysis) -> dict:
    recommended = recommendations[0]["name"] if recommendations else None
    matrix_10d = [
        {"dimension": "IC"},
        {"dimension": "Sharpe"},
        {"dimension": "Max Drawdown"},
        {"dimension": "Correlation Redundancy", "value": str(correlation_analysis.get("alert_count", 0))},
        {"dimension": "Coverage", "value": str(analysis.get("coverage", {}))},
        {"dimension": "Stability", "value": "N/A"},
        {"dimension": "Data Quality", "value": "N/A"},
        {"dimension": "Risk Contribution", "value": "N/A"},
        {"dimension": "Incremental Value", "value": "N/A"},
        {"dimension": "Operational Readiness", "value": "G3 checklist required"},
    ]
    return {
        "matrix_10d": matrix_10d,
        "summary": {
            "recommended_scheme": recommended,
            "key_findings": [f"correlation alerts: {correlation_analysis.get('alert_count', 0)}"],
        },
        "g3_checklist": [
            {"item": "风控组评审", "checked": False},
            {"item": "合规组审核", "checked": False},
            {"item": "CRO 最终批准", "checked": False},
        ],
    }
```

- [ ] **Step 2: 在 report_service 中挂接 `report` 字段**

```python
report_10d = build_report_10d(...)
payload["data"]["report"] = report_10d
```

- [ ] **Step 3: 扩展 schema + route 参数校验**

```python
class FactorOptimizationEvaluateRequest(BaseModel):
    ...
    correlation_threshold: float = Field(default=0.7, gt=0.0, le=1.0)
```

- [ ] **Step 4: 更新 contract 测试字段断言**

```python
assert "correlation_analysis" in payload["data"]
assert "report" in payload["data"]
assert len(payload["data"]["report"]["matrix_10d"]) == 10
```

- [ ] **Step 5: 运行 quant 测试**

Run: `cd quant && uv run pytest tests/unit/factor_optimization tests/contract/test_http_factor_optimization_endpoint.py -q`
Expected: PASS。

- [ ] **Step 6: 提交实现**

```bash
git add quant/src/application/factor_optimization/report_10d_service.py \
  quant/src/application/factor_optimization/report_service.py \
  quant/src/application/factor_optimization/__init__.py \
  quant/src/interfaces/http/schemas.py \
  quant/src/interfaces/http/routes_factor_optimization.py \
  quant/tests/unit/factor_optimization/test_report_10d_service.py \
  quant/tests/contract/test_http_factor_optimization_endpoint.py
git commit -m "feat: add 10d report to factor optimization evaluate"
```

---

### Task 5: CLI 扩展（统一命令 + table 告警/报告展示）

**Files:**
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/cmd/factor.rs`
- Modify: `cli/src/application/handlers/factor_optimize.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Modify: `cli/tests/http_factor_optimize.rs`
- Modify: `cli/tests/http_factor_optimize_table.rs`

- [ ] **Step 1: 先写/改失败测试（threshold 透传 + table 新区块）**

```rust
assert!(table.contains("相关性告警"));
assert!(table.contains("10维评估摘要"));
assert!(table.contains("severity"));
```

- [ ] **Step 2: 增加 `--correlation-threshold` 参数（可选）**

```rust
#[arg(long)]
pub correlation_threshold: Option<f64>
```

- [ ] **Step 3: HTTP client 透传可选阈值**

```rust
"correlation_threshold": correlation_threshold
```

- [ ] **Step 4: table 渲染新增告警和 10维摘要板块**

```rust
let alerts = payload["data"]["correlation_analysis"]["alerts"].as_array();
let matrix = payload["data"]["report"]["matrix_10d"].as_array();
```

- [ ] **Step 5: 运行 CLI 测试**

Run: `cd cli && cargo test --test http_factor_optimize --test http_factor_optimize_table`
Expected: PASS。

- [ ] **Step 6: 提交 CLI 改动**

```bash
git add cli/src/application/requests.rs \
  cli/src/cmd/factor.rs \
  cli/src/application/handlers/factor_optimize.rs \
  cli/src/infrastructure/http_client.rs \
  cli/src/infrastructure/table_renderer.rs \
  cli/tests/http_factor_optimize.rs \
  cli/tests/http_factor_optimize_table.rs
git commit -m "feat: extend factor optimize cli with alerts and 10d report view"
```

---

### Task 6: 门禁与文档收尾

**Files:**
- Modify (if needed): `cli/tests/architecture_rules.rs`
- Modify: `AGENTS.md`

- [ ] **Step 1: 架构门禁**

Run: `make architecture-check`
Expected: PASS。

- [ ] **Step 2: 全量门禁**

Run: `make check`
Expected: PASS。

- [ ] **Step 3: 更新快速上下文（P1 能力）**

在 `AGENTS.md` 的近期交付补充：

```markdown
- Factor Optimization P1: unified evaluate 增加 correlation alerts 与 10维报告
```

- [ ] **Step 4: 提交收尾文档**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS context for factor optimization p1"
```

---

## 完成定义（DoD）

- `evaluate` 单接口同时输出 `correlation_analysis` 与 `report.matrix_10d`
- CLI `hf factor optimize --output table` 可展示告警与10维摘要
- `make architecture-check` 与 `make check` 均通过
- 输出继续满足 `advice_only=true`、`decision_weight=0`（不自动生效）
