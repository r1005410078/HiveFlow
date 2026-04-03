# L3 信号工程 Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 L2 factor_snapshot 转换为标准化 signal_matrix（去极值 + zscore + 等权聚合），接入 daily pipeline 并提供独立 HTTP/CLI 查询入口。

**Architecture:** 新增 `application/signal/` 服务层消费 L2 factor_snapshot，复用 `hiveflow.signal.application.normalize_use_case` 中已有的 `winsorize_then_zscore`。daily pipeline 并行输出 signal_matrix（不替换 l2_decision）。独立 HTTP `POST /api/v1/signal/snapshot` + Rust CLI `hf signal snapshot` 提供单独查询通道。

**Tech Stack:** Python (pandas, pydantic, FastAPI), Rust (clap, reqwest, comfy_table, serde_json)

**Spec:** `docs/superpowers/specs/2026-04-03-l3-signal-engineering-phase1-design.md`

**Important note on direction:** L2 `FACTOR_METADATA` 当前所有 6 因子 direction 均为 +1（含 turnover_rate，因其已编码为「越大越好」）。代码仍需通用支持 direction=-1（为未来因子预留），但 Phase 1 测试用例以 direction=+1 为主，额外用构造数据测 direction=-1 路径。

---

### Task 1: Domain Models + Unit Tests

**Files:**
- Create: `quant/src/domain/models/signal.py`
- Test: `quant/tests/unit/signal/test_domain_signal.py`

- [ ] **Step 1: Write the failing test**

Create `quant/tests/unit/signal/test_domain_signal.py`:

```python
from domain.models.signal import (
    CompositeScore,
    SignalRow,
    TransformStats,
    TransformStatsDetail,
)


def test_signal_row_is_frozen():
    row = SignalRow(
        symbol="600519.SH",
        factor_name="momentum_20",
        raw_value=0.05,
        signal_value=1.23,
        direction=1,
    )
    assert row.symbol == "600519.SH"
    assert row.signal_value == 1.23


def test_transform_stats_detail():
    detail = TransformStatsDetail(count=5, mean=0.0, std=1.0, min_val=-1.5, max_val=1.8)
    assert detail.count == 5
    assert detail.min_val == -1.5


def test_composite_score():
    cs = CompositeScore(symbol="600519.SH", composite_score=0.87, factor_count=6)
    assert cs.factor_count == 6


def test_transform_stats():
    pre = TransformStatsDetail(count=5, mean=0.04, std=0.03, min_val=-0.01, max_val=0.1)
    post = TransformStatsDetail(count=5, mean=0.0, std=1.0, min_val=-1.5, max_val=1.8)
    ts = TransformStats(factor_name="momentum_20", pre_winsorize=pre, post_zscore=post)
    assert ts.factor_name == "momentum_20"
    assert ts.pre_winsorize.mean == 0.04
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_domain_signal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.models.signal'`

- [ ] **Step 3: Write minimal implementation**

Create `quant/src/domain/models/signal.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SignalRow:
    symbol: str
    factor_name: str
    raw_value: float
    signal_value: float
    direction: int


@dataclass(frozen=True)
class TransformStatsDetail:
    count: int
    mean: float
    std: float
    min_val: float
    max_val: float


@dataclass(frozen=True)
class TransformStats:
    factor_name: str
    pre_winsorize: TransformStatsDetail
    post_zscore: TransformStatsDetail


@dataclass(frozen=True)
class CompositeScore:
    symbol: str
    composite_score: float
    factor_count: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_domain_signal.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add quant/src/domain/models/signal.py quant/tests/unit/signal/test_domain_signal.py
git commit -m "feat(l3): add signal domain models (SignalRow, TransformStats, CompositeScore)"
```

---

### Task 2: Signal Engineering Service — Core compute_signal_matrix + Unit Tests

**Files:**
- Create: `quant/src/application/signal/__init__.py`
- Create: `quant/src/application/signal/signal_engineering_service.py`
- Test: `quant/tests/unit/signal/test_signal_engineering.py`

- [ ] **Step 1: Write the failing tests**

Create `quant/tests/unit/signal/test_signal_engineering.py`:

```python
import math

from application.factor.basic_factor_service import compute_basic_factor_snapshot


def _snapshot_5symbols() -> dict:
    """Reusable L2 snapshot with 5 symbols × 6 factors = 30 rows."""
    return compute_basic_factor_snapshot(
        as_of="2026-04-01",
        symbols=["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"],
    )


def test_signal_matrix_structure():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)

    assert result["schema_version"] == "1.0"
    assert result["producer_version"] == "quant-l3"
    assert result["signal_version"] == "l3-signal-v1.0"
    assert isinstance(result["generated_at"], str)
    assert set(result["factor_names"]) == {
        "momentum_20", "inv_volatility_20", "turnover_rate",
        "max_drawdown_60", "trend_stability_20", "relative_strength_vs_index",
    }
    assert len(result["rows"]) == 30  # 5 symbols × 6 factors
    assert len(result["composite_scores"]) == 5
    assert len(result["transform_stats"]) == 6


def test_signal_row_fields():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)
    row = result["rows"][0]
    assert "symbol" in row
    assert "factor_name" in row
    assert "raw_value" in row
    assert "signal_value" in row
    assert "direction" in row
    assert isinstance(row["signal_value"], float)


def test_zscore_properties():
    """Post-zscore mean ≈ 0, std ≈ 1 when >2 distinct values."""
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)

    for ts in result["transform_stats"]:
        post = ts["post_zscore"]
        if post["count"] > 2:
            assert abs(post["mean"]) < 0.01, f"{ts['factor_name']} post mean not ≈ 0"
            assert abs(post["std"] - 1.0) < 0.1, f"{ts['factor_name']} post std not ≈ 1"


def test_composite_equal_weight():
    """composite_score = mean(signal_values) for each symbol."""
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)

    rows_by_symbol: dict[str, list[float]] = {}
    for row in result["rows"]:
        if not math.isnan(row["signal_value"]):
            rows_by_symbol.setdefault(row["symbol"], []).append(row["signal_value"])

    for cs in result["composite_scores"]:
        if cs["factor_count"] > 0:
            expected = sum(rows_by_symbol[cs["symbol"]]) / len(rows_by_symbol[cs["symbol"]])
            assert abs(cs["composite_score"] - expected) < 1e-6, (
                f"{cs['symbol']}: expected {expected}, got {cs['composite_score']}"
            )


def test_empty_snapshot():
    from application.signal.signal_engineering_service import compute_signal_matrix

    empty = {"rows": [], "factor_names": [], "coverage_rate": 0.0}
    result = compute_signal_matrix(empty)
    assert result["rows"] == []
    assert result["composite_scores"] == []
    assert result["coverage_rate"] == 0.0
    assert result["transform_stats"] == []


def test_coverage_rate():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)
    assert result["coverage_rate"] == 1.0  # deterministic snapshot has no NaN


def test_direction_flip():
    """When direction=-1, signal should flip the raw value before standardizing."""
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"as_of": "2026-04-01", "symbol": f"SYM{i}", "factor_name": "test_factor",
         "factor_version": "v1", "raw_value": float(i), "direction": -1,
         "unit": "ratio", "missing_strategy": "none", "source": "real"}
        for i in range(1, 6)
    ]
    snapshot = {"rows": rows, "factor_names": ["test_factor"], "coverage_rate": 1.0}
    result = compute_signal_matrix(snapshot)

    signal_values = {r["symbol"]: r["signal_value"] for r in result["rows"]}
    # direction=-1: lower raw should become higher signal (after flipping + zscore)
    assert signal_values["SYM1"] > signal_values["SYM5"], (
        "direction=-1 should flip: SYM1 (raw=1) should have higher signal than SYM5 (raw=5)"
    )


def test_single_value_factor_produces_nan():
    """A factor with only 1 value: zscore std=0 → NaN signal, no crash."""
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"as_of": "2026-04-01", "symbol": "SYM1", "factor_name": "solo",
         "factor_version": "v1", "raw_value": 5.0, "direction": 1,
         "unit": "ratio", "missing_strategy": "none", "source": "real"}
    ]
    snapshot = {"rows": rows, "factor_names": ["solo"], "coverage_rate": 1.0}
    result = compute_signal_matrix(snapshot)

    assert len(result["rows"]) == 1
    assert math.isnan(result["rows"][0]["signal_value"])
    assert result["transform_stats"][0]["post_zscore"]["count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.signal'`

- [ ] **Step 3: Write the implementation**

Create `quant/src/application/signal/__init__.py` (empty file).

Create `quant/src/application/signal/signal_engineering_service.py`:

```python
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import numpy as np
import pandas as pd

from application.contracts.cli_output import ok_output
from application.factor.basic_factor_service import (
    compute_basic_factor_snapshot,
    compute_basic_factor_snapshot_from_bars,
)
from hiveflow.signal.application.normalize_use_case import winsorize_then_zscore

_SIGNAL_VERSION = "l3-signal-v1.0"
_BENCHMARK_SYMBOL = "000300.SH"

_logger = logging.getLogger(__name__)


def _series_stats(s: pd.Series) -> dict:
    clean = s.dropna()
    if len(clean) == 0:
        return {"count": 0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": int(len(clean)),
        "mean": round(float(clean.mean()), 6),
        "std": round(float(clean.std(ddof=0)), 6),
        "min": round(float(clean.min()), 6),
        "max": round(float(clean.max()), 6),
    }


def compute_signal_matrix(factor_snapshot: dict) -> dict:
    rows = factor_snapshot.get("rows", [])
    factor_names = factor_snapshot.get("factor_names", [])

    if not rows:
        return {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "producer_version": "quant-l3",
            "signal_version": _SIGNAL_VERSION,
            "factor_names": list(factor_names),
            "coverage_rate": 0.0,
            "rows": [],
            "composite_scores": [],
            "transform_stats": [],
        }

    df = pd.DataFrame(rows)
    wide = df.pivot_table(
        index="symbol", columns="factor_name", values="raw_value", aggfunc="first",
    )

    direction_map: dict[str, int] = {}
    for row in rows:
        fn = row["factor_name"]
        if fn not in direction_map:
            direction_map[fn] = row.get("direction", 1)

    active_factors = [f for f in factor_names if f in wide.columns]

    for fn in active_factors:
        if direction_map.get(fn, 1) == -1:
            wide[fn] = wide[fn] * -1

    signal_wide = pd.DataFrame(index=wide.index)
    transform_stats: list[dict] = []

    for fn in active_factors:
        col = wide[fn]
        pre_stats = _series_stats(col)

        if col.dropna().nunique() <= 1:
            signal_col = pd.Series(np.nan, index=col.index)
        else:
            signal_col = winsorize_then_zscore(col.dropna())
            signal_col = signal_col.reindex(col.index)

        post_stats = _series_stats(signal_col)
        signal_wide[fn] = signal_col

        transform_stats.append({
            "factor_name": fn,
            "pre_winsorize": pre_stats,
            "post_zscore": post_stats,
        })

    signal_rows: list[dict] = []
    for symbol in signal_wide.index:
        for fn in active_factors:
            sv = signal_wide.loc[symbol, fn]
            raw_val = wide.loc[symbol, fn]
            signal_rows.append({
                "symbol": symbol,
                "factor_name": fn,
                "raw_value": round(float(raw_val), 6) if not math.isnan(raw_val) else raw_val,
                "signal_value": round(float(sv), 6) if not math.isnan(sv) else sv,
                "direction": direction_map.get(fn, 1),
            })

    composite_scores: list[dict] = []
    for symbol in signal_wide.index:
        vals = signal_wide.loc[symbol].dropna()
        if len(vals) == 0:
            composite_scores.append({
                "symbol": symbol, "composite_score": float("nan"), "factor_count": 0,
            })
        else:
            composite_scores.append({
                "symbol": symbol,
                "composite_score": round(float(vals.mean()), 6),
                "factor_count": int(len(vals)),
            })

    total_cells = len(signal_wide.index) * len(active_factors)
    non_nan = int(signal_wide.notna().sum().sum()) if total_cells > 0 else 0
    coverage = round(non_nan / total_cells, 4) if total_cells > 0 else 0.0

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer_version": "quant-l3",
        "signal_version": _SIGNAL_VERSION,
        "factor_names": list(active_factors),
        "coverage_rate": coverage,
        "rows": signal_rows,
        "composite_scores": composite_scores,
        "transform_stats": transform_stats,
    }


def run_signal_snapshot(as_of: str, bar_store=None) -> dict:
    """Standalone signal snapshot (for the independent HTTP endpoint)."""
    symbols = [
        "000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ",
    ]
    factor_snapshot = compute_basic_factor_snapshot(as_of=as_of, symbols=symbols)
    if bar_store is not None:
        try:
            start_date = (date.fromisoformat(as_of) - timedelta(days=180)).isoformat()
            bar_rows = bar_store.list_bars(
                symbols=symbols, timeframe="1d",
                start_date=start_date, end_date=as_of, limit=10000,
            )
            try:
                benchmark_start = (date.fromisoformat(as_of) - timedelta(days=60)).isoformat()
                benchmark_rows = bar_store.list_bars(
                    symbols=[_BENCHMARK_SYMBOL], timeframe="1d",
                    start_date=benchmark_start, end_date=as_of, limit=60,
                )
            except Exception:
                benchmark_rows = None
            factor_snapshot = compute_basic_factor_snapshot_from_bars(
                as_of=as_of, symbols=symbols,
                bar_rows=bar_rows, benchmark_rows=benchmark_rows,
            )
        except Exception:
            _logger.warning(
                "signal snapshot: bar_store failed; using deterministic factor snapshot",
                exc_info=True,
            )

    signal_matrix = compute_signal_matrix(factor_snapshot)
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    return ok_output(
        command="hf signal snapshot",
        run_id=run_id,
        data=signal_matrix,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/signal/__init__.py quant/src/application/signal/signal_engineering_service.py quant/tests/unit/signal/test_signal_engineering.py
git commit -m "feat(l3): add signal engineering service with compute_signal_matrix"
```

---

### Task 3: Daily Pipeline Integration + Integration Tests

**Files:**
- Modify: `quant/src/application/daily_run_service.py`
- Test: `quant/tests/unit/signal/test_daily_integration.py`

- [ ] **Step 1: Write the failing tests**

Create `quant/tests/unit/signal/test_daily_integration.py`:

```python
from unittest.mock import patch

from application.daily_run_service import run_daily


def test_daily_pipeline_includes_signal_matrix():
    result = run_daily(as_of="2026-04-01", root=None)
    data = result["data"]
    assert "signal_matrix" in data
    sm = data["signal_matrix"]
    assert sm is not None
    assert sm["schema_version"] == "1.0"
    assert sm["signal_version"] == "l3-signal-v1.0"
    assert len(sm["rows"]) == 30  # 5 symbols × 6 factors
    assert len(sm["composite_scores"]) == 5


def test_daily_pipeline_signal_matrix_failure_resilient():
    with patch(
        "application.daily_run_service.compute_signal_matrix",
        side_effect=RuntimeError("boom"),
    ):
        result = run_daily(as_of="2026-04-01", root=None)
    assert result["status"] == "ok"
    assert result["data"]["signal_matrix"] is None
    warning_codes = [w["code"] for w in result["warnings"]]
    assert "SIGNAL_MATRIX_FAILED" in warning_codes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_daily_integration.py -v`
Expected: FAIL — `signal_matrix` not in `data`

- [ ] **Step 3: Modify daily_run_service.py**

In `quant/src/application/daily_run_service.py`, add the import at the top (after existing imports):

```python
from application.signal.signal_engineering_service import compute_signal_matrix
```

Then in `run_daily()`, after the `warnings = _build_factor_quality_warnings(l2_decision)` line and before the `return ok_output(...)`, add:

```python
    signal_matrix = None
    try:
        signal_matrix = compute_signal_matrix(factor_snapshot)
    except Exception:
        _logger.warning(
            "daily run: signal_matrix computation failed",
            exc_info=True,
        )
        warnings.append({
            "code": "SIGNAL_MATRIX_FAILED",
            "message": "L3 signal matrix computation failed; signal_matrix set to null",
        })
```

And add `"signal_matrix": signal_matrix,` to the `data` dict inside `ok_output(...)`:

```python
    return ok_output(
        command="hf pipeline daily",
        run_id=run_id,
        data={
            "as_of": as_of,
            "data_manifest_id": f"dm_{as_of.replace('-', '')}_{str(uuid4())[:6]}",
            "factor_snapshot": factor_snapshot,
            "execution_plan": {"orders": []},
            "l2_decision": l2_decision,
            "signal_matrix": signal_matrix,
        },
        warnings=warnings,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_daily_integration.py -v`
Expected: 2 passed

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `cd quant && uv run python -m pytest -q`
Expected: all pass (existing tests should still pass; new `signal_matrix` key is additive)

- [ ] **Step 6: Commit**

```bash
git add quant/src/application/daily_run_service.py quant/tests/unit/signal/test_daily_integration.py
git commit -m "feat(l3): integrate signal_matrix into daily pipeline with fallback"
```

---

### Task 4: Pydantic Schemas

**Files:**
- Modify: `quant/src/interfaces/http/schemas.py`

- [ ] **Step 1: Add Signal* Pydantic models**

In `quant/src/interfaces/http/schemas.py`, add the following classes **before** the `DailyRunData` class:

```python
class SignalSnapshotRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")


class SignalRowSchema(BaseModel):
    symbol: str
    factor_name: str
    raw_value: float
    signal_value: float
    direction: int


class SignalCompositeScore(BaseModel):
    symbol: str
    composite_score: float
    factor_count: int


class SignalTransformStatsDetail(BaseModel):
    count: int
    mean: float
    std: float
    min: float
    max: float


class SignalTransformStats(BaseModel):
    factor_name: str
    pre_winsorize: SignalTransformStatsDetail
    post_zscore: SignalTransformStatsDetail


class SignalMatrix(BaseModel):
    schema_version: str
    generated_at: str
    producer_version: str
    signal_version: str
    factor_names: list[str]
    coverage_rate: float
    rows: list[SignalRowSchema]
    composite_scores: list[SignalCompositeScore]
    transform_stats: list[SignalTransformStats]
```

- [ ] **Step 2: Update DailyRunData**

In the same file, update `DailyRunData` to add the optional `signal_matrix` field:

```python
class DailyRunData(BaseModel):
    as_of: str
    data_manifest_id: str
    factor_snapshot: FactorSnapshot
    execution_plan: ExecutionPlan
    l2_decision: L2Decision
    signal_matrix: SignalMatrix | None = None
```

- [ ] **Step 3: Add SignalSnapshotResponse**

Add after `SignalMatrix`:

```python
class SignalSnapshotResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: SignalMatrix
    warnings: list[dict]
    errors: list[dict]
```

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `cd quant && uv run python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add quant/src/interfaces/http/schemas.py
git commit -m "feat(l3): add Signal Pydantic schemas and update DailyRunData"
```

---

### Task 5: HTTP Endpoint (routes + dependencies + app registration)

**Files:**
- Create: `quant/src/interfaces/http/routes_signal.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/app.py`

- [ ] **Step 1: Create routes_signal.py**

Create `quant/src/interfaces/http/routes_signal.py`:

```python
from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    SignalSnapshotService,
    get_signal_snapshot_service,
)
from interfaces.http.schemas import (
    SignalSnapshotRequest,
    SignalSnapshotResponse,
)

router = APIRouter(prefix="/api/v1/signal", tags=["signal"])


@router.post(
    "/snapshot",
    summary="获取 L3 信号快照",
    description=(
        "对指定日期计算标准化信号矩阵（去极值 + zscore + 等权聚合），"
        "返回 signal_matrix 含 rows、composite_scores、transform_stats。"
    ),
    response_description="L3 信号快照，含标准化信号与诊断指标",
)
def post_signal_snapshot(
    req: SignalSnapshotRequest,
    service: SignalSnapshotService = Depends(get_signal_snapshot_service),
) -> SignalSnapshotResponse:
    return SignalSnapshotResponse.model_validate(service(req.as_of))
```

- [ ] **Step 2: Add provider to dependencies.py**

In `quant/src/interfaces/http/dependencies.py`, add the import at the top:

```python
from application.signal.signal_engineering_service import run_signal_snapshot
```

Add the type alias (near the other `Callable` type aliases):

```python
SignalSnapshotService = Callable[[str], dict]
```

Add the provider function (after `get_factor_optimization_service`):

```python
def get_signal_snapshot_service() -> SignalSnapshotService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of: run_signal_snapshot(as_of=as_of, bar_store=bar_store)
```

- [ ] **Step 3: Register router in app.py**

In `quant/src/interfaces/http/app.py`, add the import:

```python
from interfaces.http.routes_signal import router as signal_router
```

And add to `create_app()` after the existing `app.include_router(...)` calls:

```python
    app.include_router(signal_router)
```

- [ ] **Step 4: Run all Python tests**

Run: `cd quant && uv run python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add quant/src/interfaces/http/routes_signal.py quant/src/interfaces/http/dependencies.py quant/src/interfaces/http/app.py
git commit -m "feat(l3): add POST /api/v1/signal/snapshot HTTP endpoint"
```

---

### Task 6: Architecture Tests

**Files:**
- Modify: `quant/tests/architecture/test_layering_rules.py`

- [ ] **Step 1: Add L3 architecture tests**

Append the following tests to `quant/tests/architecture/test_layering_rules.py`:

```python
def test_application_signal_does_not_import_interfaces():
    """application.signal 禁止依赖 interfaces 层"""
    signal_dir = APP_DIR / "signal"
    if not signal_dir.exists():
        return
    violations: list[str] = []
    for py in signal_dir.rglob("*.py"):
        imports = _imports(py)
        if any(name == "interfaces" or name.startswith("interfaces.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"application.signal must not import interfaces: {violations}"


def test_domain_signal_does_not_import_application():
    """domain.models.signal 禁止依赖 application"""
    signal_file = SRC / "domain" / "models" / "signal.py"
    if not signal_file.exists():
        return
    imports = _imports(signal_file)
    violations = [name for name in imports if name == "application" or name.startswith("application.")]
    assert not violations, f"domain.models.signal must not import application: {violations}"
```

- [ ] **Step 2: Run architecture tests**

Run: `cd quant && uv run python -m pytest tests/architecture/ -v`
Expected: all pass (including 2 new tests)

- [ ] **Step 3: Commit**

```bash
git add quant/tests/architecture/test_layering_rules.py
git commit -m "test(l3): add architecture boundary tests for signal layer"
```

---

### Task 7: Rust CLI — `hf signal snapshot`

**Files:**
- Create: `cli/src/cmd/signal.rs`
- Modify: `cli/src/cmd/mod.rs`
- Modify: `cli/src/application/requests.rs`
- Create: `cli/src/application/handlers/signal_snapshot.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`

- [ ] **Step 1: Create cmd/signal.rs**

Create `cli/src/cmd/signal.rs`:

```rust
use crate::application::requests::SignalSnapshotRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct SignalArgs {
    #[command(subcommand)]
    pub command: SignalSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum SignalSubcommand {
    Snapshot(SnapshotArgs),
}

#[derive(Debug, Args)]
pub struct SnapshotArgs {
    #[arg(long)]
    pub as_of: String,
    #[arg(long, default_value = "json")]
    pub output: String,
}

impl From<SnapshotArgs> for SignalSnapshotRequest {
    fn from(args: SnapshotArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
```

- [ ] **Step 2: Register in cmd/mod.rs**

In `cli/src/cmd/mod.rs`, add `pub mod signal;` at the top with the other module declarations.

Add `Signal(signal::SignalArgs),` to the `Commands` enum.

Add the match arm in the `From<Cli> for AppCommand` impl:

```rust
Commands::Signal(args) => match args.command {
    signal::SignalSubcommand::Snapshot(snapshot) => {
        AppCommand::SignalSnapshot(snapshot.into())
    }
},
```

The full file should be:

```rust
pub mod data;
pub mod factor;
pub mod pipeline;
pub mod signal;

use crate::application::requests::AppCommand;
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(name = "hf")]
#[command(about = "HiveFlow CLI")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Debug, Subcommand)]
pub enum Commands {
    Pipeline(pipeline::PipelineArgs),
    Factor(factor::FactorArgs),
    Data(data::DataArgs),
    Signal(signal::SignalArgs),
}

impl From<Cli> for AppCommand {
    fn from(cli: Cli) -> Self {
        match cli.command {
            Commands::Pipeline(args) => match args.command {
                pipeline::PipelineSubcommand::Daily(daily) => {
                    AppCommand::PipelineDaily(daily.into())
                }
                pipeline::PipelineSubcommand::Compare(compare) => {
                    AppCommand::PipelineCompare(compare.into())
                }
            },
            Commands::Factor(args) => match args.command {
                factor::FactorSubcommand::Optimize(optimize) => {
                    AppCommand::FactorOptimize(optimize.into())
                }
                factor::FactorSubcommand::Replay(replay) => AppCommand::FactorReplay(replay.into()),
            },
            Commands::Data(args) => match args.command {
                data::DataSubcommand::Sync(sync_args) => AppCommand::DataSync(sync_args.into()),
                data::DataSubcommand::UniverseSync(sync_args) => {
                    AppCommand::DataUniverseSync(sync_args.into())
                }
                data::DataSubcommand::Query(query_args) => AppCommand::DataQuery(query_args.into()),
                data::DataSubcommand::Bars(bars_args) => AppCommand::DataBars(bars_args.into()),
            },
            Commands::Signal(args) => match args.command {
                signal::SignalSubcommand::Snapshot(snapshot) => {
                    AppCommand::SignalSnapshot(snapshot.into())
                }
            },
        }
    }
}
```

- [ ] **Step 3: Add request and enum variant in requests.rs**

In `cli/src/application/requests.rs`, add the struct:

```rust
#[derive(Debug, Clone)]
pub struct SignalSnapshotRequest {
    pub as_of: String,
    pub output: String,
}
```

Add to the `AppCommand` enum:

```rust
SignalSnapshot(SignalSnapshotRequest),
```

- [ ] **Step 4: Add http_client function**

In `cli/src/infrastructure/http_client.rs`, add:

```rust
pub fn post_signal_snapshot(
    server_url: &str,
    as_of: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!("{}/api/v1/signal/snapshot", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({"as_of": as_of}))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    parse_json(&body_text)
}
```

- [ ] **Step 5: Add table renderer function**

In `cli/src/infrastructure/table_renderer.rs`, add:

```rust
pub fn render_signal_snapshot_table(payload: &Value) -> String {
    let data = payload.get("data");
    let signal_version = as_str(data.and_then(|d| d.get("signal_version")));
    let coverage = as_f64(data.and_then(|d| d.get("coverage_rate")));

    let mut header = Table::new();
    header
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("信号版本"), Cell::new("覆盖率")]);
    header.add_row(vec![signal_version, coverage]);

    let mut rows_table = Table::new();
    rows_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("因子"),
            Cell::new("原始值"),
            Cell::new("信号值"),
            Cell::new("方向"),
        ]);

    if let Some(items) = data.and_then(|d| d.get("rows")).and_then(Value::as_array) {
        for item in items {
            rows_table.add_row(vec![
                as_str(item.get("symbol")),
                as_str(item.get("factor_name")),
                as_f64(item.get("raw_value")),
                as_f64(item.get("signal_value")),
                as_i64(item.get("direction")),
            ]);
        }
    }

    let mut composite = Table::new();
    composite
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("综合分"),
            Cell::new("参与因子数"),
        ]);

    if let Some(items) = data
        .and_then(|d| d.get("composite_scores"))
        .and_then(Value::as_array)
    {
        for item in items {
            composite.add_row(vec![
                as_str(item.get("symbol")),
                as_f64(item.get("composite_score")),
                as_i64(item.get("factor_count")),
            ]);
        }
    }

    format!(
        "L3 信号快照\n{}\n信号明细\n{}\n综合分排名\n{}\n",
        header, rows_table, composite
    )
}
```

- [ ] **Step 6: Create handler**

Create `cli/src/application/handlers/signal_snapshot.rs`:

```rust
use crate::application::requests::SignalSnapshotRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_signal_snapshot_table;

pub fn handle(args: SignalSnapshotRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_signal_snapshot(&cfg.server_url, &args.as_of, cfg.timeout_ms)?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_signal_snapshot_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for signal snapshot: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
```

- [ ] **Step 7: Register handler module**

In `cli/src/application/handlers/mod.rs`, add:

```rust
pub mod signal_snapshot;
```

- [ ] **Step 8: Add dispatch arm**

In `cli/src/application/dispatch.rs`, add the import `signal_snapshot` to the `use` statement:

```rust
use crate::application::handlers::{
    data_bars, data_query, data_sync, data_universe_sync, factor_optimize, factor_replay,
    pipeline_compare, pipeline_daily, signal_snapshot,
};
```

Add the match arm:

```rust
AppCommand::SignalSnapshot(args) => signal_snapshot::handle(args),
```

- [ ] **Step 9: Build and test**

Run: `cd cli && cargo build`
Expected: compiles with no errors

Run: `cd cli && cargo test`
Expected: all tests pass

- [ ] **Step 10: Commit**

```bash
git add cli/src/cmd/signal.rs cli/src/cmd/mod.rs cli/src/application/requests.rs cli/src/application/handlers/signal_snapshot.rs cli/src/application/handlers/mod.rs cli/src/application/dispatch.rs cli/src/infrastructure/http_client.rs cli/src/infrastructure/table_renderer.rs
git commit -m "feat(l3): add hf signal snapshot CLI command (json|table)"
```

---

### Task 8: Documentation Update

**Files:**
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`

- [ ] **Step 1: Add signal snapshot example to CLI_OUTPUT_EXAMPLES.md**

Add a new section to `docs/CLI_OUTPUT_EXAMPLES.md` (after the existing pipeline daily example section). The section should include:

1. A `### hf signal snapshot` heading
2. A JSON example showing the signal snapshot output with the standard envelope wrapper and a `signal_matrix` `data` block with `schema_version`, `generated_at`, `producer_version`, `signal_version`, `factor_names`, `coverage_rate`, `rows` (showing 1-2 sample `SignalRow`), `composite_scores` (1-2 samples), and `transform_stats` (1-2 samples).

Also update the existing `hf pipeline daily` example to show the new `signal_matrix` field in `data` (can be `null` or a short inline example).

- [ ] **Step 2: Run CLI output validation if applicable**

Run: `make validate-cli-output`
Expected: pass (new examples should validate against schema; if schema needs updating, update `docs/CLI_OUTPUT_SCHEMA.json` first — but since `signal_matrix` sits inside `data` which is a free-form object in the schema, it should pass)

- [ ] **Step 3: Commit**

```bash
git add docs/CLI_OUTPUT_EXAMPLES.md
git commit -m "docs(l3): add signal snapshot example to CLI_OUTPUT_EXAMPLES"
```

---

### Task 9: Final Verification

- [ ] **Step 1: Run full Python test suite**

Run: `cd quant && uv run python -m pytest -q`
Expected: all pass

- [ ] **Step 2: Run architecture check**

Run: `make architecture-check`
Expected: pass

- [ ] **Step 3: Run Rust tests**

Run: `cd cli && cargo test`
Expected: pass

- [ ] **Step 4: Run full CI gate**

Run: `make check`
Expected: pass

- [ ] **Step 5: Verify CLI help includes signal command**

Run: `cd cli && cargo run -- signal --help`
Expected: shows `snapshot` subcommand

Run: `cd cli && cargo run -- signal snapshot --help`
Expected: shows `--as-of` and `--output` flags

---

## Self-Review Checklist

1. **Spec coverage**: All 13 spec sections mapped to tasks — domain models (§10→T1), core service (§5→T2), daily integration (§6→T3), pydantic schemas (§9→T4), HTTP endpoint (§7→T5), architecture tests (§11.3→T6), Rust CLI (§8→T7), docs (§12 docs row→T8), verification (§13→T9).
2. **Placeholder scan**: No TBD/TODO. All steps have complete code.
3. **Type consistency**: `SignalRow` (domain) vs `SignalRowSchema` (pydantic) — intentionally different names to avoid collision; `compute_signal_matrix` signature consistent across T2 and T3; `run_signal_snapshot` consistent between T2 and T5; `SignalSnapshotRequest` (Python Pydantic) vs `SignalSnapshotRequest` (Rust struct) — same name, different languages.
4. **Direction note**: Spec §5.3 says `turnover_rate` is direction=-1 but L2 code has direction=+1 for all factors. Plan handles this generically (T2 `test_direction_flip` uses constructed data with direction=-1). No spec change needed — the code handles both.
