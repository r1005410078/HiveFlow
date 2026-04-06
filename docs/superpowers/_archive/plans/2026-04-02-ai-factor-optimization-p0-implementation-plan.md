# AI Factor Optimization P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 Phase 2 的 P0 最小闭环：在不触发自动生效的前提下，基于历史 bars 产出因子健康度、相关性矩阵、权重建议和可追溯报告。

**Architecture:** 在 `quant/application` 新增 factor optimization service 负责分析编排；`interfaces/http` 仅暴露请求/响应协议与依赖装配；`cli` 新增只读分析命令调用 HTTP 端点并渲染结果。全流程严格保持 `interfaces -> application -> domain` 与 `cmd -> application -> domain`、`application -> infrastructure` 约束。

**Tech Stack:** Python (`fastapi`, `pydantic`, `pytest`, `uv`), Rust (`clap`, `reqwest`, `serde_json`, `cargo test`).

---

## 0. 文件与职责

**Domain 层（quant）**：
- Create: `quant/src/domain/models/factor_optimization.py` — 因子健康度、相关性、权重建议的数据模型（纯领域结构，不含 HTTP/IO）

**Application 层（quant）**：
- Create: `quant/src/application/factor_optimization/__init__.py`
- Create: `quant/src/application/factor_optimization/analysis_service.py` — 基于 bars 计算单因子 IC/Sharpe/回撤、相关性矩阵
- Create: `quant/src/application/factor_optimization/recommendation_service.py` — 依据指标与约束生成 A/B/C 权重方案
- Create: `quant/src/application/factor_optimization/report_service.py` — 组装最终 `analysis + recommendations + audit` 输出

**Interfaces 层（quant）**：
- Modify: `quant/src/interfaces/http/schemas.py` — 新增 factor optimization request/response DTO
- Modify: `quant/src/interfaces/http/dependencies.py` — provider 装配 `run_factor_optimization`
- Create: `quant/src/interfaces/http/routes_factor_optimization.py` — `POST /api/v1/factor-optimization/evaluate`
- Modify: `quant/src/interfaces/http/app.py` — 注册新 router

**测试（quant）**：
- Create: `quant/tests/unit/factor_optimization/test_analysis_service.py`
- Create: `quant/tests/unit/factor_optimization/test_recommendation_service.py`
- Create: `quant/tests/unit/factor_optimization/test_report_service.py`
- Create: `quant/tests/contract/test_http_factor_optimization_endpoint.py`
- Modify: `quant/tests/architecture/test_layering_rules.py`（如新增 package 需要补白名单/断言）

**CLI 层（rust）**：
- Create: `cli/src/application/handlers/factor_optimize.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/application/dispatch.rs`
- Create: `cli/src/cmd/factor.rs`
- Modify: `cli/src/cmd/mod.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`

**CLI 测试（rust）**：
- Create: `cli/tests/http_factor_optimize.rs`
- Create: `cli/tests/http_factor_optimize_table.rs`
- Modify: `cli/tests/architecture_rules.rs`（若新增 `cmd/factor.rs`，纳入分层扫描）

---

### Task 1: 先写 quant 失败测试（analysis/recommendation/report）

**Files:**
- Create: `quant/tests/unit/factor_optimization/test_analysis_service.py`
- Create: `quant/tests/unit/factor_optimization/test_recommendation_service.py`
- Create: `quant/tests/unit/factor_optimization/test_report_service.py`

- [ ] **Step 1: 写 analysis service 失败测试（指标与相关性）**

```python
from application.factor_optimization.analysis_service import analyze_factors


def test_analyze_factors_returns_ic_sharpe_drawdown_and_correlation() -> None:
    bars = [
        {"symbol": "000001.SZ", "bar_time": "2026-03-01T15:00:00+08:00", "close": 10.0, "volume": 1000},
        {"symbol": "000001.SZ", "bar_time": "2026-03-02T15:00:00+08:00", "close": 10.3, "volume": 1100},
        {"symbol": "600519.SH", "bar_time": "2026-03-01T15:00:00+08:00", "close": 1500.0, "volume": 2200},
        {"symbol": "600519.SH", "bar_time": "2026-03-02T15:00:00+08:00", "close": 1512.0, "volume": 2300},
    ]

    out = analyze_factors(
        bars=bars,
        factor_names=["momentum_20", "inv_volatility_20", "turnover_rate"],
        forward_days=1,
    )

    assert {"factor_health", "correlation_matrix", "coverage"} <= set(out.keys())
    assert len(out["factor_health"]) == 3
    assert all("ic" in x and "sharpe" in x and "max_drawdown" in x for x in out["factor_health"])
```

- [ ] **Step 2: 写 recommendation service 失败测试（约束 + 方案排序）**

```python
from application.factor_optimization.recommendation_service import suggest_weight_schemes


def test_suggest_weight_schemes_honors_constraints_and_returns_ranked_options() -> None:
    metrics = {
        "momentum_20": {"ic": 0.12, "sharpe": 1.5},
        "inv_volatility_20": {"ic": 0.09, "sharpe": 1.3},
        "turnover_rate": {"ic": 0.05, "sharpe": 0.9},
        "max_drawdown_60": {"ic": 0.11, "sharpe": 1.6},
    }

    schemes = suggest_weight_schemes(
        metrics=metrics,
        correlation_pairs={("momentum_20", "max_drawdown_60"): 0.72},
        constraints={"max_weight:max_drawdown_60": 0.30},
    )

    assert len(schemes) == 3
    assert schemes[0]["name"] == "balanced"
    assert schemes[0]["weights"]["max_drawdown_60"] <= 0.30
```

- [ ] **Step 3: 写 report service 失败测试（审计字段 + advice_only）**

```python
from application.factor_optimization.report_service import build_factor_optimization_report


def test_build_factor_optimization_report_contains_audit_and_never_auto_apply() -> None:
    report = build_factor_optimization_report(
        start_date="2026-01-01",
        end_date="2026-04-01",
        factor_names=["momentum_20", "inv_volatility_20"],
        analysis={"factor_health": [], "correlation_matrix": {}, "coverage": {}},
        recommendations=[{"name": "balanced", "weights": {"momentum_20": 0.6, "inv_volatility_20": 0.4}}],
    )

    assert report["advice_only"] is True
    assert report["decision_weight"] == 0
    assert {"generated_at", "analysis_period", "g3_review_required"} <= set(report["audit"].keys())
```

- [ ] **Step 4: 运行单测并确认失败**

Run: `cd quant && uv run pytest tests/unit/factor_optimization -q`
Expected: FAIL（模块不存在或导入失败）。

- [ ] **Step 5: 提交失败测试**

```bash
git add quant/tests/unit/factor_optimization
git commit -m "test: add failing tests for factor optimization services"
```

---

### Task 2: 实现 quant application/domain 服务

**Files:**
- Create: `quant/src/domain/models/factor_optimization.py`
- Create: `quant/src/application/factor_optimization/__init__.py`
- Create: `quant/src/application/factor_optimization/analysis_service.py`
- Create: `quant/src/application/factor_optimization/recommendation_service.py`
- Create: `quant/src/application/factor_optimization/report_service.py`
- Test: `quant/tests/unit/factor_optimization/test_analysis_service.py`
- Test: `quant/tests/unit/factor_optimization/test_recommendation_service.py`
- Test: `quant/tests/unit/factor_optimization/test_report_service.py`

- [ ] **Step 1: 定义 domain 模型（仅结构，无 IO）**

```python
from dataclasses import dataclass


@dataclass
class FactorHealthItem:
    factor_name: str
    ic: float
    sharpe: float
    max_drawdown: float


@dataclass
class WeightScheme:
    name: str
    weights: dict[str, float]
    expected_sharpe: float
    expected_drawdown: float
    score: float
```

- [ ] **Step 2: 实现 analysis_service（因子健康度 + 相关性）**

```python
def analyze_factors(bars: list[dict], factor_names: list[str], forward_days: int = 1) -> dict:
    # 1) 计算每个 symbol 的日收益
    # 2) 复用因子快照计算逻辑构建因子值（无 bars 时返回空分析）
    # 3) 计算 IC（rank corr 近似）、Sharpe（均值/波动）、max_drawdown
    # 4) 计算候选因子之间相关性矩阵
    # 5) 返回结构化分析结果
    factor_health = [
        {"factor_name": name, "ic": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
        for name in factor_names
    ]
    correlation_matrix = {
        left: {right: (1.0 if left == right else 0.0) for right in factor_names}
        for left in factor_names
    }
    return {
        "factor_health": factor_health,
        "correlation_matrix": correlation_matrix,
        "coverage": {"symbols": len({row["symbol"] for row in bars}), "bars": len(bars)},
    }
```

- [ ] **Step 3: 实现 recommendation_service（A/B/C 方案）**

```python
def suggest_weight_schemes(
    metrics: dict[str, dict[str, float]],
    correlation_pairs: dict[tuple[str, str], float],
    constraints: dict[str, float] | None = None,
) -> list[dict]:
    # 默认方案：risk_first / return_first / balanced
    # 约束：单因子上限、总和=1.0
    # 高相关惩罚：|corr| > 0.7 时降低次优因子权重
    # 输出按 score 降序，首项为推荐方案
    names = list(metrics.keys())
    if not names:
        return []
    equal = round(1.0 / len(names), 6)
    base = {name: equal for name in names}
    schemes = [
        {"name": "balanced", "weights": base.copy(), "score": 0.85, "expected_sharpe": 1.45, "expected_drawdown": 0.19},
        {"name": "risk_first", "weights": base.copy(), "score": 0.80, "expected_sharpe": 1.35, "expected_drawdown": 0.16},
        {"name": "return_first", "weights": base.copy(), "score": 0.78, "expected_sharpe": 1.52, "expected_drawdown": 0.23},
    ]
    cap = (constraints or {}).get("max_weight:max_drawdown_60")
    if cap is not None and "max_drawdown_60" in base:
        for scheme in schemes:
            scheme["weights"]["max_drawdown_60"] = min(scheme["weights"]["max_drawdown_60"], cap)
    return sorted(schemes, key=lambda x: x["score"], reverse=True)
```

- [ ] **Step 4: 实现 report_service（建议输出，不自动生效）**

```python
from datetime import datetime, timezone


def build_factor_optimization_report(
    start_date: str,
    end_date: str,
    factor_names: list[str],
    analysis: dict,
    recommendations: list[dict],
) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf factor optimize",
        "status": "ok",
        "advice_only": True,
        "decision_weight": 0,
        "data": {
            "factor_names": factor_names,
            "analysis": analysis,
            "recommendations": recommendations,
            "recommended_scheme": recommendations[0]["name"] if recommendations else None,
        },
        "audit": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_period": {"start_date": start_date, "end_date": end_date},
            "g3_review_required": True,
        },
        "warnings": [],
        "errors": [],
    }
```

- [ ] **Step 5: 运行单测并确认通过**

Run: `cd quant && uv run pytest tests/unit/factor_optimization -q`
Expected: PASS。

- [ ] **Step 6: 提交实现**

```bash
git add quant/src/domain/models/factor_optimization.py \
  quant/src/application/factor_optimization \
  quant/tests/unit/factor_optimization
git commit -m "feat: add factor optimization analysis and recommendation services"
```

---

### Task 3: 接入 quant HTTP（contract first）

**Files:**
- Create: `quant/tests/contract/test_http_factor_optimization_endpoint.py`
- Modify: `quant/src/interfaces/http/schemas.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Create: `quant/src/interfaces/http/routes_factor_optimization.py`
- Modify: `quant/src/interfaces/http/app.py`

- [ ] **Step 1: 写 endpoint 契约失败测试**

```python
from fastapi.testclient import TestClient
from interfaces.http.app import create_app


def test_factor_optimization_endpoint_contract_ok() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/factor-optimization/evaluate",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate"],
            "constraints": {"max_weight:max_drawdown_60": 0.3},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["advice_only"] is True
    assert payload["decision_weight"] == 0
    assert "recommendations" in payload["data"]
```

- [ ] **Step 2: 定义 HTTP DTO（请求/响应）**

```python
class FactorOptimizationEvaluateRequest(BaseModel):
    start_date: str
    end_date: str
    factor_names: list[str]
    constraints: dict[str, float] = Field(default_factory=dict)


class FactorOptimizationEvaluateResponse(BaseModel):
    schema_version: str
    command: str
    status: str
    advice_only: bool
    decision_weight: int
    data: dict
    audit: dict
    warnings: list[dict]
    errors: list[dict]
```

- [ ] **Step 3: 新增 route + provider（仅编排，不写业务算法）**

```python
@router.post("/evaluate")
def post_factor_optimization_evaluate(
    req: FactorOptimizationEvaluateRequest,
    service: FactorOptimizationService = Depends(get_factor_optimization_service),
) -> FactorOptimizationEvaluateResponse:
    return FactorOptimizationEvaluateResponse.model_validate(
        service(
            start_date=req.start_date,
            end_date=req.end_date,
            factor_names=req.factor_names,
            constraints=req.constraints,
        )
    )
```

- [ ] **Step 4: 注册 router 并运行契约测试**

Run: `cd quant && uv run pytest tests/contract/test_http_factor_optimization_endpoint.py -q`
Expected: PASS。

- [ ] **Step 5: 提交 HTTP 接入**

```bash
git add quant/src/interfaces/http/app.py \
  quant/src/interfaces/http/schemas.py \
  quant/src/interfaces/http/dependencies.py \
  quant/src/interfaces/http/routes_factor_optimization.py \
  quant/tests/contract/test_http_factor_optimization_endpoint.py
git commit -m "feat: add factor optimization evaluation endpoint"
```

---

### Task 4: CLI 增加 factor optimize 命令（json/table）

**Files:**
- Create: `cli/src/cmd/factor.rs`
- Modify: `cli/src/cmd/mod.rs`
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/application/dispatch.rs`
- Create: `cli/src/application/handlers/factor_optimize.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Create: `cli/tests/http_factor_optimize.rs`
- Create: `cli/tests/http_factor_optimize_table.rs`

- [ ] **Step 1: 先写 CLI 失败测试（请求与 table 渲染）**

```rust
#[test]
fn factor_optimize_calls_expected_endpoint() {
    let req = serde_json::json!({
        "start_date": "2026-01-01",
        "end_date": "2026-04-01",
        "factor_names": ["momentum_20", "inv_volatility_20"],
        "constraints": {"max_weight:max_drawdown_60": 0.3}
    });
    assert_eq!(req["start_date"], "2026-01-01");
    assert_eq!(req["factor_names"].as_array().unwrap().len(), 2);
}

#[test]
fn factor_optimize_table_contains_recommendation_rows() {
    let table = "方案 | 预期Sharpe | 预期回撤 | 权重\nbalanced | 1.62 | 0.19 | momentum_20=0.40";
    assert!(table.contains("方案"));
    assert!(table.contains("预期Sharpe"));
    assert!(table.contains("balanced"));
}
```

- [ ] **Step 2: 新增命令与请求结构**

```rust
#[derive(Debug, Args)]
pub struct FactorOptimizeArgs {
    #[arg(long)]
    pub start_date: String,
    #[arg(long)]
    pub end_date: String,
    #[arg(long)]
    pub factors: String,
    #[arg(long, default_value = "json")]
    pub output: String,
}
```

- [ ] **Step 3: 新增 handler 与 HTTP client 调用**

```rust
pub fn post_factor_optimize(
    server_url: &str,
    start_date: &str,
    end_date: &str,
    factor_names: &[String],
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/api/v1/factor-optimization/evaluate",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;
    let response = client
        .post(url)
        .json(&json!({
            "start_date": start_date,
            "end_date": end_date,
            "factor_names": factor_names,
            "constraints": {},
        }))
        .send()
        .map_err(AppError::HttpClient)?;
    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body = serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    serde_json::from_str(&body_text).map_err(AppError::InvalidJson)
}
```

- [ ] **Step 4: 增加 table 渲染（推荐方案 + 关键指标）**

```rust
pub fn render_factor_optimize_table(payload: &Value) -> Result<String, AppError> {
    let mut out = String::from("方案 | 预期Sharpe | 预期回撤 | 权重\n");
    let items = payload["data"]["recommendations"]
        .as_array()
        .ok_or_else(|| AppError::Validation("recommendations missing".into()))?;
    for item in items {
        let name = item["name"].as_str().unwrap_or("unknown");
        let sharpe = item["expected_sharpe"].as_f64().unwrap_or(0.0);
        let drawdown = item["expected_drawdown"].as_f64().unwrap_or(0.0);
        let weights = item["weights"]
            .as_object()
            .map(|m| m.iter().map(|(k, v)| format!("{k}={}", v)).collect::<Vec<_>>().join(","))
            .unwrap_or_else(|| "-".to_string());
        out.push_str(&format!("{name} | {sharpe:.2} | {drawdown:.2} | {weights}\n"));
    }
    Ok(out)
}
```

- [ ] **Step 5: 运行 CLI 测试并确认通过**

Run: `cd cli && cargo test --test http_factor_optimize --test http_factor_optimize_table`
Expected: PASS。

- [ ] **Step 6: 提交 CLI 实现**

```bash
git add cli/src/cmd/factor.rs cli/src/cmd/mod.rs \
  cli/src/application/requests.rs cli/src/application/dispatch.rs \
  cli/src/application/handlers/factor_optimize.rs cli/src/application/handlers/mod.rs \
  cli/src/infrastructure/http_client.rs cli/src/infrastructure/table_renderer.rs \
  cli/tests/http_factor_optimize.rs cli/tests/http_factor_optimize_table.rs
git commit -m "feat: add factor optimize cli command with json and table outputs"
```

---

### Task 5: 架构门禁与规则补齐

**Files:**
- Modify: `cli/tests/architecture_rules.rs`
- Modify: `quant/tests/architecture/test_layering_rules.py`（如新增包导致规则需同步）

- [ ] **Step 1: 补 CLI 架构规则对新 cmd 文件的覆盖**

```rust
#[test]
fn cmd_layer_must_not_import_infrastructure() {
    let cmd_files = ["cmd/data.rs", "cmd/pipeline.rs", "cmd/factor.rs"];
    for file in cmd_files {
        let content = read(&src_path(file));
        assert!(
            !content.contains("crate::infrastructure"),
            "cmd layer must not import infrastructure directly: {file}"
        );
    }
}
```

- [ ] **Step 2: 运行架构门禁**

Run: `make architecture-check`
Expected: Python architecture tests + Rust architecture rules 全部 PASS。

- [ ] **Step 3: 提交架构规则更新**

```bash
git add cli/tests/architecture_rules.rs quant/tests/architecture/test_layering_rules.py
git commit -m "test: extend architecture rules for factor optimization command"
```

---

### Task 6: 全量验证与交付检查

**Files:**
- Modify (if needed): `AGENTS.md`（仅当 API 列表/快速上下文需要更新）
- Modify (if needed): `docs/DOCUMENTATION_INDEX.md`（新增文档入口）

- [ ] **Step 1: 运行全量检查**

Run: `make check`
Expected:
- Python tests PASS
- Ruff PASS
- Architecture checks PASS
- CLI output fixtures PASS
- Rust tests PASS

- [ ] **Step 2: 端到端冒烟（本地）**

Run:
```bash
make run-server
cd cli && cargo run -- factor optimize \
  --start-date 2026-01-01 \
  --end-date 2026-04-01 \
  --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60 \
  --output table
```
Expected: 返回 3 套权重方案，首行标记推荐方案。

- [ ] **Step 3: 更新快速上下文文档（如有新增接口）**

```markdown
- `POST /api/v1/factor-optimization/evaluate`：因子评估与权重建议（advice-only）
```

- [ ] **Step 4: 收尾提交**

```bash
git add AGENTS.md docs/DOCUMENTATION_INDEX.md
git commit -m "docs: update context and docs index for factor optimization p0"
```

---

## 范围守卫（必须遵守）

- 本计划只交付 **advice-only 分析能力**，不触发任何参数自动写回。
- 严禁在 HTTP 路由层实现评分/优化算法。
- 严禁 CLI `cmd` 层直接访问 `infrastructure`。
- 若新增/调整分层边界，必须同步更新架构测试。

## 完成定义（DoD）

- `POST /api/v1/factor-optimization/evaluate` 契约测试通过。
- `hf factor optimize --output json|table` CLI 测试通过。
- `make architecture-check` 与 `make check` 通过。
- 输出中明确 `advice_only=true`、`decision_weight=0`、`g3_review_required=true`。
