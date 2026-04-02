# L2-A Explainable Candidate Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 daily 输出中新增可解释的 `l2_decision`（v1 三因子），并预留 v1.1 因子扩展接口位。

**Architecture:** 评分与解释逻辑落在 `application` 新增 decision service；`daily_run_service` 只做编排；`interfaces/http` 仅做响应 DTO 校验；测试覆盖 unit/integration/contract，保持分层不变。

**Tech Stack:** Python (`pytest`, `fastapi`, `pydantic`, `uv`).

---

## 0. 文件与职责

**Domain 层**（新增）：
- Create: `quant/src/domain/models/l2_decision.py` — 数据类定义

**Application 层**（新增）：
- Create: `quant/src/application/decision/__init__.py`
- Create: `quant/src/application/decision/l2_decision_service.py` — 打分与解释逻辑

**Interfaces 层**（改动）：
- Modify: `quant/src/interfaces/http/schemas.py` — HTTP 响应 schema

**Application 编排**（改动）：
- Modify: `quant/src/application/daily_run_service.py` — daily 管道接入 l2_decision

**测试**（新增/改动）：
- Create: `quant/tests/unit/decision/test_l2_decision_service.py`
- Modify: `quant/tests/integration/test_daily_pipeline_mvp.py`
- Modify: `quant/tests/contract/test_http_daily_endpoint.py`
- Modify: `quant/tests/contract/test_python_cli_contract.py`

---

### Task 1: 先写失败测试（L2 决策服务）

**Files:**
- Create: `quant/tests/unit/decision/test_l2_decision_service.py`
- Test: `quant/tests/unit/decision/test_l2_decision_service.py`

- [x] **Step 1: 写决策服务失败测试（排序、解释字段、确定性）**

**主测试**：

```python
from application.decision.l2_decision_service import compute_l2_decision_from_snapshot


def _snapshot() -> dict:
    """标准测试数据：2 个标的，各 3 个因子完整"""
    return {
        "factor_version": "l2-basic-v1",
        "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate"],
        "coverage_rate": 1.0,
        "rows": [
            {"as_of": "2026-04-01", "symbol": "000001.SZ", "factor_name": "momentum_20", "factor_version": "l2-basic-v1", "raw_value": 0.011},
            {"as_of": "2026-04-01", "symbol": "000001.SZ", "factor_name": "inv_volatility_20", "factor_version": "l2-basic-v1", "raw_value": 1.1},
            {"as_of": "2026-04-01", "symbol": "000001.SZ", "factor_name": "turnover_rate", "factor_version": "l2-basic-v1", "raw_value": 0.006},
            {"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "momentum_20", "factor_version": "l2-basic-v1", "raw_value": 0.024},
            {"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "inv_volatility_20", "factor_version": "l2-basic-v1", "raw_value": 2.9},
            {"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "turnover_rate", "factor_version": "l2-basic-v1", "raw_value": 0.019},
        ],
    }


def test_l2_decision_contains_explainable_fields() -> None:
    """验证输出结构完整性（包含版本信息）"""
    out = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    
    # 验证版本和元数据
    assert out["schema_version"] == "1.0"
    assert out["score_version"] == "l2-score-v1"
    assert out["producer_version"] == "quant-l2"
    assert "generated_at" in out  # ISO8601 格式
    assert out["universe_size"] == 2
    
    # 验证候选和详细信息
    assert out["top_candidates"][0]["symbol"] == "600519.SH"
    first = out["score_breakdown"][0]
    assert "final_score" in first
    assert "factors" in first
    assert {"factor_name", "raw_value", "normalized_value", "percentile", "clipped", "anomaly_flags", "weight", "contribution"} <= set(first["factors"][0].keys())


def test_l2_decision_is_deterministic_for_same_input() -> None:
    """验证确定性（相同输入产生相同输出）"""
    a = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    b = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    # 注：generated_at 会不同，需排除该字段再对比
    a_copy = {k: v for k, v in a.items() if k != "generated_at"}
    b_copy = {k: v for k, v in b.items() if k != "generated_at"}
    assert a_copy == b_copy


def test_l2_decision_percentile_in_valid_range() -> None:
    """验证分位数范围 (0, 1]"""
    out = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    for item in out["score_breakdown"]:
        for factor in item["factors"]:
            percentile = factor["percentile"]
            assert 0 < percentile <= 1.0, f"percentile {percentile} out of range (0, 1]"
```

**边界情况测试**：

```python
def test_l2_decision_with_missing_factor() -> None:
    """某标的某因子缺失时，用 0.0 填补并标记异常"""
    snapshot = _snapshot()
    snapshot["rows"] = [row for row in snapshot["rows"] if row["symbol"] != "600519.SH" or row["factor_name"] != "turnover_rate"]
    out = compute_l2_decision_from_snapshot(snapshot, top_n=5)
    # 验证 600519.SH 的 turnover_rate 因子被填补为 0.0，anomaly_flags 包含 missing_factor
    breakdown_sh = [x for x in out["score_breakdown"] if x["symbol"] == "600519.SH"][0]
    turnover_factor = [f for f in breakdown_sh["factors"] if f["factor_name"] == "turnover_rate"][0]
    assert "missing_factor:turnover_rate" in turnover_factor["anomaly_flags"]


def test_l2_decision_with_empty_sample() -> None:
    """样本为空时返回空结果"""
    snapshot = _snapshot()
    snapshot["rows"] = []
    out = compute_l2_decision_from_snapshot(snapshot, top_n=5)
    assert out["universe_size"] == 0
    assert out["top_candidates"] == []
    assert out["score_breakdown"] == []


def test_l2_decision_with_flat_distribution() -> None:
    """某因子全样本同值时，标准化为 1.0、percentile=1.0 并标记异常"""
    snapshot = _snapshot()
    # 将所有 momentum_20 设为同一值
    for row in snapshot["rows"]:
        if row["factor_name"] == "momentum_20":
            row["raw_value"] = 0.05
    out = compute_l2_decision_from_snapshot(snapshot, top_n=5)
    # 验证 momentum_20 的所有 normalized_value 都是 1.0，percentile=1.0，anomaly_flags 包含 flat_distribution
    for item in out["score_breakdown"]:
        momentum = [f for f in item["factors"] if f["factor_name"] == "momentum_20"][0]
        assert momentum["normalized_value"] == 1.0
        assert momentum["percentile"] == 1.0
        assert "flat_distribution:momentum_20" in momentum["anomaly_flags"]


def test_l2_decision_contribution_sum_equals_final_score() -> None:
    """验证 sum(factors[].contribution) == final_score（6 位精度）"""
    out = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    for item in out["score_breakdown"]:
        contribution_sum = round(sum(f["contribution"] for f in item["factors"]), 6)
        assert contribution_sum == item["final_score"], (
            f"{item['symbol']}: sum(contribution)={contribution_sum} != final_score={item['final_score']}"
        )
```

- [x] **Step 2: 运行测试并确认失败**

Run: `cd quant && uv run pytest tests/unit/decision/test_l2_decision_service.py -q`  
Expected: FAIL（模块或函数尚不存在）。

- [x] **Step 3: 提交测试骨架**

```bash
git add quant/tests/unit/decision/test_l2_decision_service.py
git commit -m "test: add failing unit tests for l2 decision service"
```

---

### Task 2: 实现 decision service + domain 模型

**Files:**
- Create: `quant/src/domain/models/l2_decision.py` （数据类定义）
- Create: `quant/src/application/decision/__init__.py`
- Create: `quant/src/application/decision/l2_decision_service.py`
- Test: `quant/tests/unit/decision/test_l2_decision_service.py`

- [x] **Step 1: 定义 domain 模型（数据类）**

```python
# quant/src/domain/models/l2_decision.py
from typing import List
from dataclasses import dataclass

@dataclass
class FactorDetail:
    factor_name: str
    raw_value: float
    normalized_value: float
    percentile: float
    clipped: bool
    anomaly_flags: List[str]
    weight: float
    contribution: float

@dataclass
class ScoreBreakdownItem:
    symbol: str
    final_score: float
    factors: List[FactorDetail]

@dataclass
class TopCandidate:
    symbol: str
    score: float
    rank: int

@dataclass
class L2Decision:
    schema_version: str = "1.0"
    score_version: str = "l2-score-v1"
    universe_size: int
    top_candidates: List[TopCandidate]
    score_breakdown: List[ScoreBreakdownItem]
```

- [x] **Step 2: 实现打分逻辑（关键算法）**

```python
# quant/src/application/decision/l2_decision_service.py
import pandas as pd
import numpy as np
from domain.models.l2_decision import L2Decision, FactorDetail, ScoreBreakdownItem, TopCandidate

_FACTOR_WEIGHTS = {"momentum_20": 0.5, "inv_volatility_20": 0.3, "turnover_rate": 0.2}

def compute_l2_decision_from_snapshot(factor_snapshot: dict, top_n: int = 5) -> dict:
    """
    主流程：
    1) 长表聚合为宽表（按 symbol，columns = factor_names）
    2) 对每个因子，执行 p1~p99 分位截断，记录 clipped 标志
    3) 截断后的值 → min-max 标准化（处理 max==min 情况）
    4) 计算 percentile（rank-based，同值取平均）
    5) 计算 contribution = weight * normalized_value
    6) final_score = sum(weight_i * normalized_value_i)，保留 6 位小数
    7) 按 (-final_score, symbol) 排序，取前 top_n
    """
    
    rows = factor_snapshot.get("rows", [])
    if not rows:
        return {
            "schema_version": "1.0",
            "score_version": "l2-score-v1",
            "universe_size": 0,
            "top_candidates": [],
            "score_breakdown": [],
        }
    
    # Step 1: 聚合为宽表
    df = pd.DataFrame(rows)
    wide = df.pivot_table(index="symbol", columns="factor_name", values="raw_value", aggfunc="first")
    
    # Step 2-5: 逐因子处理（截断、标准化、分位、贡献度）
    score_breakdown = []
    normalized_scores = {}  # symbol -> final_score
    
    for symbol in wide.index:
        factors = []
        symbol_score_components = []
        
        for factor_name in _FACTOR_WEIGHTS.keys():
            raw_value = wide.loc[symbol, factor_name]
            is_missing = pd.isna(raw_value)
            if is_missing:
                # 缺失值处理：填补 0.0，跳过 clipping，优先级最高
                raw_value = 0.0
                anomaly_flags = [f"missing_factor:{factor_name}"]
                clipped = False
            else:
                anomaly_flags = []
                # 分位截断（仅非缺失值执行）
                col_values_raw = [v for v in wide[factor_name] if not pd.isna(v)]
                p1, p99 = np.percentile(col_values_raw, [1, 99])
                clipped = False
                if raw_value < p1:
                    raw_value = p1
                    clipped = True
                elif raw_value > p99:
                    raw_value = p99
                    clipped = True
            
            # 标准化
            col_values = [v for v in wide[factor_name] if not pd.isna(v)]
            col_min, col_max = min(col_values), max(col_values)
            
            if col_max == col_min:
                # flat_distribution：跳过 min-max 和 percentile 计算
                normalized_value = 1.0
                percentile = 1.0
                anomaly_flags.append(f"flat_distribution:{factor_name}")
            else:
                normalized_value = (raw_value - col_min) / (col_max - col_min)
                # 分位：rank(method="average") / N，范围 (0, 1]（仅非 flat_distribution 时执行）
                ranks = pd.Series(col_values).rank(method="average")
                raw_rank = ranks[pd.Series(col_values) == raw_value].mean() if raw_value in col_values else ranks.iloc[0]
                percentile = raw_rank / len(col_values)
            
            # 贡献度
            weight = _FACTOR_WEIGHTS[factor_name]
            contribution = weight * normalized_value
            symbol_score_components.append(contribution)
            
            factors.append(FactorDetail(
                factor_name=factor_name,
                raw_value=raw_value,
                normalized_value=round(normalized_value, 6),
                percentile=round(percentile, 6),
                clipped=clipped,
                anomaly_flags=anomaly_flags,
                weight=weight,
                contribution=round(contribution, 6),
            ))
        
        final_score = round(sum(symbol_score_components), 6)
        normalized_scores[symbol] = final_score
        score_breakdown.append(ScoreBreakdownItem(
            symbol=symbol,
            final_score=final_score,
            factors=factors,
        ))
    
    # Step 6: 排序与生成候选
    sorted_breakdown = sorted(score_breakdown, key=lambda x: (-x.final_score, x.symbol))
    top_candidates = [
        TopCandidate(symbol=item.symbol, score=item.final_score, rank=i+1)
        for i, item in enumerate(sorted_breakdown[:top_n])
    ]
    
    from datetime import datetime, timezone
    
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer_version": "quant-l2",
        "score_version": "l2-score-v1",
        "universe_size": len(wide),
        "top_candidates": [t.__dict__ for t in top_candidates],
        "score_breakdown": [item.__dict__ for item in sorted_breakdown],
    }
```

- [x] **Step 3: 运行单测并确认通过**

Run: `cd quant && uv run pytest tests/unit/decision/test_l2_decision_service.py -q`  
Expected: PASS （包含正常、缺失、空样本、同值等所有测试）。

- [x] **Step 4: 提交实现**

```bash
git add quant/src/domain/models/l2_decision.py quant/src/application/decision/__init__.py quant/src/application/decision/l2_decision_service.py quant/tests/unit/decision/test_l2_decision_service.py
git commit -m "feat: implement l2 decision scoring service with deterministic algorithm"
```

---

### Task 3: 接入 daily 输出与 HTTP schema

**Files:**
- Modify: `quant/tests/integration/test_daily_pipeline_mvp.py`（测试优先）
- Modify: `quant/tests/contract/test_http_daily_endpoint.py`（测试优先）
- Modify: `quant/tests/contract/test_python_cli_contract.py`（测试优先）
- Modify: `quant/src/interfaces/http/schemas.py`（定义 schema）
- Modify: `quant/src/application/daily_run_service.py`（实现）

- [x] **Step 1: 先写集成测试（测试优先）**

```python
# quant/tests/integration/test_daily_pipeline_mvp.py
def test_daily_run_includes_l2_decision() -> None:
    """验证 daily 编排包含 l2_decision 输出"""
    result = run_daily(as_of="2026-04-01", symbols=["600519.SH", "000001.SZ"])
    
    # 断言 l2_decision 存在
    assert "l2_decision" in result
    l2d = result["l2_decision"]
    
    # 验证结构完整性
    assert l2d["score_version"] == "l2-score-v1"
    assert l2d["universe_size"] >= 0
    assert isinstance(l2d["top_candidates"], list)
    assert isinstance(l2d["score_breakdown"], list)
    
    # 验证排序正确（top 5 应按分数降序）
    scores = [c["score"] for c in l2d["top_candidates"]]
    assert scores == sorted(scores, reverse=True)
```

```python
# quant/tests/contract/test_http_daily_endpoint.py
def test_http_daily_response_schema_includes_l2_decision() -> None:
    """验证 HTTP 响应 schema 包含 l2_decision 且类型正确"""
    response = post_to_daily_endpoint(as_of="2026-04-01")
    assert response.status_code == 200
    
    payload = response.json()
    assert "data" in payload
    assert "l2_decision" in payload["data"]
    
    # 验证 schema 符合 CLI_OUTPUT_SCHEMA.json
    l2d = payload["data"]["l2_decision"]
    assert "schema_version" in l2d
    assert "score_version" in l2d
    assert "top_candidates" in l2d
    assert "score_breakdown" in l2d
```

- [x] **Step 2: 定义 HTTP typed response**

```python
# quant/src/interfaces/http/schemas.py
from pydantic import BaseModel
from typing import List

class FactorBreakdown(BaseModel):
    factor_name: str
    raw_value: float
    normalized_value: float
    percentile: float
    clipped: bool
    anomaly_flags: List[str]
    weight: float
    contribution: float

class ScoreBreakdownItem(BaseModel):
    symbol: str
    final_score: float
    factors: List[FactorBreakdown]

class TopCandidate(BaseModel):
    symbol: str
    score: float
    rank: int

class L2Decision(BaseModel):
    schema_version: str = "1.0"
    generated_at: str  # ISO8601 with timezone
    producer_version: str = "quant-l2"
    score_version: str = "l2-score-v1"
    universe_size: int
    top_candidates: List[TopCandidate]
    score_breakdown: List[ScoreBreakdownItem]

class DailyRunData(BaseModel):
    factor_snapshot: dict  # 现有
    execution_plan: dict  # 现有
    l2_decision: L2Decision  # 新增

class DailyRunResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: DailyRunData  # 包含 l2_decision
    warnings: List[str] = []
    errors: List[str] = []
```

- [x] **Step 3: 实现 daily 编排接入**

```python
# quant/src/application/daily_run_service.py
from application.decision.l2_decision_service import compute_l2_decision_from_snapshot

def run_daily(as_of: str, symbols: List[str]) -> dict:
    """更新主编排，包含 l2_decision"""
    # 现有逻辑...
    factor_snapshot = compute_basic_factor_snapshot(as_of=as_of, symbols=symbols)
    
    # 新增：计算 l2_decision
    l2_decision = compute_l2_decision_from_snapshot(
        factor_snapshot=factor_snapshot, 
        top_n=5
    )
    
    # 返回完整响应
    return {
        "schema_version": "1.0",
        "command": "hf run daily",
        "run_id": "<generated_run_id>",
        "status": "ok",
        "generated_at": datetime.now().isoformat(),
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "factor_snapshot": factor_snapshot,
            "l2_decision": l2_decision,
            "execution_plan": {"orders": []},
        },
        "warnings": [],
        "errors": [],
    }
```

- [x] **Step 4: 运行集成 + 契约测试验证**

Run:  
```bash
cd quant && uv run pytest tests/integration/test_daily_pipeline_mvp.py tests/contract/test_http_daily_endpoint.py tests/contract/test_python_cli_contract.py -q
```
Expected: PASS。

- [x] **Step 5: 提交集成改动**

```bash
git add quant/tests/integration/test_daily_pipeline_mvp.py quant/tests/contract/test_http_daily_endpoint.py quant/tests/contract/test_python_cli_contract.py quant/src/interfaces/http/schemas.py quant/src/application/daily_run_service.py
git commit -m "feat: integrate l2 decision into daily pipeline with typed schema"
```

---

### Task 4: 可扩展性设计（为 Phase 2 预留）

**Files:**
- Modify: `quant/src/application/decision/l2_decision_service.py`
- Test: `quant/tests/unit/decision/test_l2_decision_service.py`

- [x] **Step 1: 增加配置化权重结构（当前仅 v1，保持不变）**

```python
# quant/src/application/decision/l2_decision_service.py
# 可扩展配置框架，支持未来新增评分版本

SCORE_PROFILES = {
    "l2-score-v1": {
        "weights": {"momentum_20": 0.5, "inv_volatility_20": 0.3, "turnover_rate": 0.2},
        "enabled_factors": ["momentum_20", "inv_volatility_20", "turnover_rate"],
    },
    # Phase 2+ 预留：新增因子时需确保数据在 factor_snapshot 中可用
    # "l2-score-v1.1": {
    #     "weights": {...},
    # }
}

def compute_l2_decision_from_snapshot(
    factor_snapshot: dict, 
    top_n: int = 5,
    score_version: str = "l2-score-v1",
) -> dict:
    """支持多版本评分，当前默认 v1"""
    profile = SCORE_PROFILES.get(score_version)
    if not profile:
        raise ValueError(f"Unknown score_version: {score_version}")
    
    # 使用 profile["weights"] 和 profile["enabled_factors"]
    # ...现有逻辑...
```

- [x] **Step 2: 验证 v1 版本锁定**

```python
# quant/tests/unit/decision/test_l2_decision_service.py
def test_default_score_version_is_v1() -> None:
    """确保默认版本为 v1（Phase 1 锁定）"""
    out = compute_l2_decision_from_snapshot(_snapshot())
    assert out["score_version"] == "l2-score-v1"
```

Run: `cd quant && uv run pytest tests/unit/decision/test_l2_decision_service.py -q`  
Expected: PASS。

- [x] **Step 3: 提交可扩展框架**

```bash
git add quant/src/application/decision/l2_decision_service.py quant/tests/unit/decision/test_l2_decision_service.py
git commit -m "refactor: add pluggable score profile framework for future versions"
```

**Phase 2 计划提示**：  
新增因子时需同步：
1. 确认数据已在 `factor_snapshot` 中可用（L1 阶段补齐）
2. 更新 `SCORE_PROFILES["l2-score-v1.1"]`
3. 补充新因子的单测（缺失、异常、权重验证）
4. 回测验证新权重的有效性（IC/Sharpe）

---

### Task 5: 最终门禁验证

**Files:**
- Verify only

- [x] **Step 1: 架构门禁**

Run: `cd /Users/rongts/strat-flow && make architecture-check`  
Expected: PASS。

- [x] **Step 2: 全量检查**

Run: `cd /Users/rongts/strat-flow && make check`  
Expected: PASS。

- [x] **Step 3: 提交任何剩余微调（如有）**

```bash
git add <touched-files>
git commit -m "test: finalize l2 decision verification updates"
```

