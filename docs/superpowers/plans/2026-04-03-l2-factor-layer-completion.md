# L2 因子层补全 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 L2 因子层 6 项缺口：per-factor 独立版本号、direction/unit/missing_strategy/source 字段、真实基准计算、稳定性监控、FactorValue domain model 对齐、L2→L3 契约字段。

**Architecture:** 就地扩展 `basic_factor_service.py`，新增 `FACTOR_METADATA` 注册表替换共享版本号，`compute_basic_factor_snapshot_from_bars` 增加可选 `benchmark_rows` 和 `historical_baselines` 参数，稳定性指标嵌入 snapshot 输出。调用方 `daily_run_service.py` 负责查询基准 bars 并传入，Pydantic schemas 同步补字段。

**Tech Stack:** Python 3.12+, FastAPI/Pydantic v2, pytest, uv

---

## Chunk 1: FACTOR_METADATA 注册表 + per-factor 版本号

### Task 1: 替换共享 `_FACTOR_VERSION` 为 `FACTOR_METADATA` 注册表

**Files:**
- Modify: `quant/src/application/factor/basic_factor_service.py:7-15`
- Test: `quant/tests/unit/factor/test_basic_factor_service.py`

- [ ] **Step 1: 写失败测试（per-factor 版本号）**

在 `test_basic_factor_service.py` 中新增：

```python
def test_per_factor_version_in_deterministic_snapshot() -> None:
    out = compute_basic_factor_snapshot(as_of="2026-04-01", symbols=["000001.SZ"])
    versions = {r["factor_name"]: r["factor_version"] for r in out["rows"]}
    assert versions["momentum_20"] == "l2-momentum-v1.0"
    assert versions["inv_volatility_20"] == "l2-inv-vol-v1.0"
    assert versions["turnover_rate"] == "l2-turnover-v1.0"
    assert versions["max_drawdown_60"] == "l2-mdd-v1.0"
    assert versions["trend_stability_20"] == "l2-trend-stab-v1.0"
    assert versions["relative_strength_vs_index"] == "l2-rsi-v1.1"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd quant && uv run python -m pytest tests/unit/factor/test_basic_factor_service.py::test_per_factor_version_in_deterministic_snapshot -v
```

期望：`FAILED` — `AssertionError: assert 'l2-basic-v1.1' == 'l2-momentum-v1.0'`

- [ ] **Step 3: 实现 `FACTOR_METADATA` 注册表**

将 `basic_factor_service.py` 顶部的：

```python
_FACTOR_VERSION = "l2-basic-v1.1"
_FACTOR_NAMES = (
    "momentum_20",
    ...
)
```

替换为：

```python
FACTOR_METADATA: dict[str, dict] = {
    "momentum_20": {
        "version": "l2-momentum-v1.0",
        "direction": 1,
        "unit": "return",
        "missing_strategy": "deterministic_fallback",
    },
    "inv_volatility_20": {
        "version": "l2-inv-vol-v1.0",
        "direction": 1,
        "unit": "1/return_std",
        "missing_strategy": "deterministic_fallback",
    },
    "turnover_rate": {
        "version": "l2-turnover-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "max_drawdown_60": {
        "version": "l2-mdd-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "trend_stability_20": {
        "version": "l2-trend-stab-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "relative_strength_vs_index": {
        "version": "l2-rsi-v1.1",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "benchmark_proxy_fallback",
    },
}

_FACTOR_NAMES = tuple(FACTOR_METADATA.keys())
```

- [ ] **Step 4: 更新 `compute_basic_factor_snapshot` 中的 `factor_version` 引用**

将函数内构造 row 的部分（原 `"factor_version": _FACTOR_VERSION`）改为：

```python
for factor_name, raw_value in values.items():
    meta = FACTOR_METADATA[factor_name]
    rows.append(
        {
            "as_of": as_of,
            "symbol": symbol,
            "factor_name": factor_name,
            "factor_version": meta["version"],
            "raw_value": raw_value,
        }
    )
```

顶层返回的 `factor_version` 字段保留，改为固定字符串 `"l2-basic-v1.1"`（snapshot 级 producer 标识，不变）。

- [ ] **Step 5: 同样更新 `compute_basic_factor_snapshot_from_bars` 中的 row 构造**

```python
for factor_name, raw_value in values.items():
    meta = FACTOR_METADATA[factor_name]
    output_rows.append(
        {
            "as_of": as_of,
            "symbol": symbol,
            "factor_name": factor_name,
            "factor_version": meta["version"],
            "raw_value": raw_value,
        }
    )
```

- [ ] **Step 6: 更新已有测试中的 `factor_version` 断言**

`test_basic_factor_service.py` 中有两处旧断言引用 `"l2-basic-v1.1"` 作为 row 级 version：

```python
# 旧（test_compute_basic_factor_snapshot_shape 第 27 行）
assert out["rows"][0]["factor_version"] == "l2-basic-v1.1"
```

改为：

```python
assert out["rows"][0]["factor_version"] in {m["version"] for m in FACTOR_METADATA.values()}
```

同理更新 `test_compute_basic_factor_snapshot_from_bars_prefers_real_data` 中的 `factor_version == "l2-basic-v1.1"` 断言（如有）。

- [ ] **Step 7: 运行测试，确认全部通过**

```bash
cd quant && uv run python -m pytest tests/unit/factor/ -v
```

期望：全部 `PASSED`

- [ ] **Step 8: Commit**

```bash
git add quant/src/application/factor/basic_factor_service.py quant/tests/unit/factor/test_basic_factor_service.py
git commit -m "feat(l2): replace shared _FACTOR_VERSION with per-factor FACTOR_METADATA registry"
```

---

## Chunk 2: direction/unit/missing_strategy/source 字段加入 rows

### Task 2: rows 输出中添加元数据字段

**Files:**
- Modify: `quant/src/application/factor/basic_factor_service.py`
- Test: `quant/tests/unit/factor/test_basic_factor_service.py`

- [ ] **Step 1: 写失败测试（row 字段完整性）**

```python
def test_row_schema_contains_metadata_fields() -> None:
    out = compute_basic_factor_snapshot(as_of="2026-04-01", symbols=["600519.SH"])
    row = out["rows"][0]
    assert "direction" in row
    assert "unit" in row
    assert "missing_strategy" in row
    assert "source" in row
    assert row["direction"] == 1
    assert row["source"] == "deterministic_fallback"


def test_bars_row_source_is_real_when_data_sufficient() -> None:
    from datetime import date, timedelta
    bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01", symbols=["600519.SH"], bar_rows=bars
    )
    for row in out["rows"]:
        if row["symbol"] == "600519.SH" and row["factor_name"] != "relative_strength_vs_index":
            assert row["source"] == "real", f"{row['factor_name']} should be real"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd quant && uv run python -m pytest tests/unit/factor/ -k "test_row_schema" -v
```

期望：`FAILED` — `KeyError: 'direction'`

- [ ] **Step 3: 更新 `compute_basic_factor_snapshot`（deterministic 路径）的 row 构造**

```python
for factor_name, raw_value in values.items():
    meta = FACTOR_METADATA[factor_name]
    rows.append(
        {
            "as_of": as_of,
            "symbol": symbol,
            "factor_name": factor_name,
            "factor_version": meta["version"],
            "raw_value": raw_value,
            "direction": meta["direction"],
            "unit": meta["unit"],
            "missing_strategy": meta["missing_strategy"],
            "source": "deterministic_fallback",
        }
    )
```

- [ ] **Step 4: 更新 `compute_basic_factor_snapshot_from_bars` 的 row 构造**

在 `_factor_values_from_real_bars` 返回 None（走 fallback）的路径：`source = "deterministic_fallback"`  
`_factor_values_from_real_bars` 返回真实值的路径：`source = "real"`  

修改 symbols 循环：

```python
for symbol in symbols:
    real_values = _factor_values_from_real_bars(rows_by_symbol.get(symbol, []))
    if real_values is None:
        values = _factor_values_for_symbol(symbol)
        default_source = "deterministic_fallback"
    else:
        values = real_values
        default_source = "real"
    for factor_name, raw_value in values.items():
        meta = FACTOR_METADATA[factor_name]
        output_rows.append(
            {
                "as_of": as_of,
                "symbol": symbol,
                "factor_name": factor_name,
                "factor_version": meta["version"],
                "raw_value": raw_value,
                "direction": meta["direction"],
                "unit": meta["unit"],
                "missing_strategy": meta["missing_strategy"],
                "source": default_source,
            }
        )
```

（`relative_strength_vs_index` 的 `source` 会在 Task 3 中单独处理为 `"benchmark_proxy_fallback"`）

- [ ] **Step 5: 运行全部测试，确认通过**

```bash
cd quant && uv run python -m pytest tests/unit/factor/ -v
```

- [ ] **Step 6: Commit**

```bash
git add quant/src/application/factor/basic_factor_service.py quant/tests/unit/factor/test_basic_factor_service.py
git commit -m "feat(l2): add direction/unit/missing_strategy/source fields to factor rows"
```

---

## Chunk 3: 真实基准计算 relative_strength_vs_index

### Task 3: `benchmark_rows` 参数 + 真实相对强度计算

**Files:**
- Modify: `quant/src/application/factor/basic_factor_service.py`
- Test: `quant/tests/unit/factor/test_basic_factor_service.py`

- [ ] **Step 1: 写失败测试（有 benchmark_rows）**

```python
def test_relative_strength_uses_real_benchmark_when_provided() -> None:
    from datetime import date, timedelta

    symbol_bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    # 基准涨幅更小（base_close=50，增幅相同绝对值但比例不同）
    benchmark_bars = _build_monotonic_bars("000300.SH", date(2026, 1, 1), 80, 50.0)

    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01",
        symbols=["600519.SH"],
        bar_rows=symbol_bars,
        benchmark_rows=benchmark_bars,
    )
    rs_row = next(r for r in out["rows"] if r["factor_name"] == "relative_strength_vs_index")
    assert rs_row["source"] == "real"
    # 个股涨幅 > 基准涨幅，相对强度应 > 0
    assert rs_row["raw_value"] > 0.0


def test_relative_strength_falls_back_to_proxy_without_benchmark() -> None:
    from datetime import date

    symbol_bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01",
        symbols=["600519.SH"],
        bar_rows=symbol_bars,
        benchmark_rows=None,
    )
    rs_row = next(r for r in out["rows"] if r["factor_name"] == "relative_strength_vs_index")
    assert rs_row["source"] == "benchmark_proxy_fallback"
    # 其他因子仍为 real
    other_rows = [r for r in out["rows"] if r["factor_name"] != "relative_strength_vs_index"]
    assert all(r["source"] == "real" for r in other_rows)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd quant && uv run python -m pytest tests/unit/factor/ -k "benchmark" -v
```

期望：`FAILED` — `TypeError: unexpected keyword argument 'benchmark_rows'`

- [ ] **Step 3: 实现基准计算逻辑**

在 `_factor_values_from_real_bars` 下方新增辅助函数：

```python
def _relative_strength_from_benchmark(
    symbol_closes: list[float],
    benchmark_rows: list[dict],
) -> float | None:
    """基准不足 21 条时返回 None，调用方走 proxy 路径。"""
    ordered = sorted(benchmark_rows, key=lambda r: str(r.get("bar_time", "")))
    b_closes = [float(r["close"]) for r in ordered]
    if len(b_closes) < 21:
        return None
    b_t = b_closes[-1]
    b_t20 = b_closes[-21]
    if b_t20 == 0:
        return None
    benchmark_ret_20 = (b_t / b_t20) - 1.0
    symbol_t = symbol_closes[-1]
    symbol_t20 = symbol_closes[-21]
    if symbol_t20 == 0:
        return None
    symbol_ret_20 = (symbol_t / symbol_t20) - 1.0
    return (1.0 + symbol_ret_20) / (1.0 + benchmark_ret_20) - 1.0
```

- [ ] **Step 4: 修改 `compute_basic_factor_snapshot_from_bars` 签名和循环**

签名改为：

```python
def compute_basic_factor_snapshot_from_bars(
    as_of: str,
    symbols: list[str],
    bar_rows: list[dict],
    benchmark_rows: list[dict] | None = None,
    historical_baselines: dict[str, dict] | None = None,
) -> dict:
```

用 `rs_used_real_benchmark` 布尔变量记录是否成功用了真实基准，避免循环内重复计算。完整实现：

```python
for symbol in symbols:
    real_values = _factor_values_from_real_bars(rows_by_symbol.get(symbol, []))
    if real_values is None:
        values = _factor_values_for_symbol(symbol)
        default_source = "deterministic_fallback"
        rs_used_real_benchmark = False
    else:
        values = real_values
        default_source = "real"
        # 尝试用真实基准覆盖 relative_strength_vs_index
        rs_used_real_benchmark = False
        if benchmark_rows is not None:
            ordered_sym = sorted(
                rows_by_symbol.get(symbol, []),
                key=lambda r: str(r.get("bar_time", "")),
            )
            sym_closes = [float(r["close"]) for r in ordered_sym]
            rs_real = _relative_strength_from_benchmark(sym_closes, benchmark_rows)
            if rs_real is not None:
                values["relative_strength_vs_index"] = round(rs_real, 6)
                rs_used_real_benchmark = True

    for factor_name, raw_value in values.items():
        meta = FACTOR_METADATA[factor_name]
        if factor_name == "relative_strength_vs_index" and default_source == "real" and not rs_used_real_benchmark:
            row_source = "benchmark_proxy_fallback"
        else:
            row_source = default_source
        output_rows.append(
            {
                "as_of": as_of,
                "symbol": symbol,
                "factor_name": factor_name,
                "factor_version": meta["version"],
                "raw_value": raw_value,
                "direction": meta["direction"],
                "unit": meta["unit"],
                "missing_strategy": meta["missing_strategy"],
                "source": row_source,
            }
        )
```

- [ ] **Step 5: 运行全部因子测试**

```bash
cd quant && uv run python -m pytest tests/unit/factor/ -v
```

期望：全部 `PASSED`

- [ ] **Step 6: Commit**

```bash
git add quant/src/application/factor/basic_factor_service.py quant/tests/unit/factor/test_basic_factor_service.py
git commit -m "feat(l2): add benchmark_rows param for real relative_strength_vs_index calculation"
```

---

## Chunk 4: stability_metrics 稳定性监控

### Task 4: per-factor 稳定性指标计算

**Files:**
- Modify: `quant/src/application/factor/basic_factor_service.py`
- Test: `quant/tests/unit/factor/test_basic_factor_service.py`

- [ ] **Step 1: 写失败测试（stability_metrics 字段存在）**

```python
def test_stability_metrics_present_in_snapshot() -> None:
    from datetime import date

    bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01", symbols=["600519.SH"], bar_rows=bars
    )
    assert "stability_metrics" in out
    metrics = out["stability_metrics"]
    assert isinstance(metrics, list)
    assert len(metrics) == 6  # per factor
    m = metrics[0]
    assert "factor_name" in m
    assert "factor_version" in m
    assert "coverage_rate" in m
    assert "real_count" in m
    assert "fallback_count" in m
    assert "mean_value" in m
    assert "std_value" in m
    assert m["drift_flag"] is None   # no historical_baselines
    assert m["drift_z_score"] is None
    # 有足够 bars 时，real_count > 0，coverage_rate 应 > 0
    assert m["coverage_rate"] > 0.0


def test_stability_metrics_drift_flag_when_baselines_provided() -> None:
    from datetime import date

    bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    # 设置 momentum_20 基线均值为极端值，使 drift 触发
    baselines = {
        "momentum_20": {"mean": 0.0, "std": 0.001},  # 当日均值必然偏差 > 2σ
    }
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01",
        symbols=["600519.SH"],
        bar_rows=bars,
        historical_baselines=baselines,
    )
    m_momentum = next(m for m in out["stability_metrics"] if m["factor_name"] == "momentum_20")
    assert m_momentum["drift_flag"] is True
    assert m_momentum["drift_z_score"] is not None
    # 其他因子无基线，drift_flag 应为 None
    m_inv_vol = next(m for m in out["stability_metrics"] if m["factor_name"] == "inv_volatility_20")
    assert m_inv_vol["drift_flag"] is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd quant && uv run python -m pytest tests/unit/factor/ -k "stability" -v
```

期望：`FAILED` — `KeyError: 'stability_metrics'`

- [ ] **Step 3: 实现 `_compute_stability_metrics` 辅助函数**

注意：`_mean` 和 `_std` 已存在于 `basic_factor_service.py`（约第 42–53 行），直接复用即可。

在文件顶部 import 区域追加 `import logging`，然后在模块级新增 logger（`_FACTOR_NAMES` 定义之后）：

```python
import logging

_logger = logging.getLogger(__name__)
```

在 `compute_basic_factor_snapshot_from_bars` 之前新增：

```python
def _compute_stability_metrics(
    rows: list[dict],
    factor_names: tuple,
    historical_baselines: dict[str, dict] | None,
) -> list[dict]:
    from collections import defaultdict

    values_by_factor: dict[str, list[float]] = defaultdict(list)
    real_count_by_factor: dict[str, int] = defaultdict(int)
    fallback_count_by_factor: dict[str, int] = defaultdict(int)

    for row in rows:
        fn = row["factor_name"]
        values_by_factor[fn].append(row["raw_value"])
        if row.get("source") == "real":
            real_count_by_factor[fn] += 1
        else:
            fallback_count_by_factor[fn] += 1

    total_symbols = (
        (real_count_by_factor.get(factor_names[0], 0) + fallback_count_by_factor.get(factor_names[0], 0))
        if factor_names
        else 0
    )

    if historical_baselines:
        known_factor_set = set(factor_names)
        for key in historical_baselines:
            if key not in known_factor_set:
                _logger.warning(
                    "historical_baselines contains unknown factor key %r; skipping drift for it", key
                )

    result = []
    for fn in factor_names:
        vals = values_by_factor.get(fn, [])
        real_c = real_count_by_factor.get(fn, 0)
        fallback_c = fallback_count_by_factor.get(fn, 0)
        total = real_c + fallback_c
        coverage = round(real_c / total_symbols, 4) if total_symbols > 0 else 0.0
        mean_v = round(_mean(vals), 6) if vals else 0.0
        std_v = round(_std(vals), 6) if vals else 0.0

        drift_flag = None
        drift_z = None
        if historical_baselines and fn in historical_baselines:
            baseline = historical_baselines[fn]
            b_mean = float(baseline.get("mean", 0.0))
            b_std = float(baseline.get("std", 1e-6))
            drift_z = round((mean_v - b_mean) / max(b_std, 1e-6), 4)
            drift_flag = abs(drift_z) > 2.0

        result.append(
            {
                "factor_name": fn,
                "factor_version": FACTOR_METADATA[fn]["version"],
                "coverage_rate": coverage,
                "real_count": real_c,
                "fallback_count": fallback_c,
                "mean_value": mean_v,
                "std_value": std_v,
                "drift_flag": drift_flag,
                "drift_z_score": drift_z,
            }
        )
    return result
```

- [ ] **Step 4: 在 `compute_basic_factor_snapshot_from_bars` 末尾调用并加入返回值**

在 `return` 语句前：

```python
stability_metrics = _compute_stability_metrics(
    rows=output_rows,
    factor_names=_FACTOR_NAMES,
    historical_baselines=historical_baselines,
)

return {
    "factor_version": "l2-basic-v1.1",
    "factor_names": list(_FACTOR_NAMES),
    "coverage_rate": coverage_rate,
    "rows": output_rows,
    "stability_metrics": stability_metrics,
}
```

- [ ] **Step 5: 同样在 `compute_basic_factor_snapshot`（deterministic 路径）末尾加入 stability_metrics**

Deterministic 路径全部为 fallback，无历史基线时 drift 均为 None：

```python
stability_metrics = _compute_stability_metrics(
    rows=rows,
    factor_names=_FACTOR_NAMES,
    historical_baselines=None,
)

return {
    "factor_version": "l2-basic-v1.1",
    "factor_names": list(_FACTOR_NAMES),
    "coverage_rate": coverage_rate,
    "rows": rows,
    "stability_metrics": stability_metrics,
}
```

- [ ] **Step 6: 运行全部因子测试**

```bash
cd quant && uv run python -m pytest tests/unit/factor/ -v
```

期望：全部 `PASSED`

- [ ] **Step 7: Commit**

```bash
git add quant/src/application/factor/basic_factor_service.py quant/tests/unit/factor/test_basic_factor_service.py
git commit -m "feat(l2): add per-factor stability_metrics with coverage, drift detection"
```

---

## Chunk 5: FactorValue domain model 对齐 + Pydantic schemas 更新

### Task 5: 更新 FactorValue domain model

**Files:**
- Modify: `quant/src/hiveflow/factor/domain/factor_value.py`

- [ ] **Step 1: 直接更新（无独立测试，domain model 通过 service 集成覆盖）**

将 `factor_value.py` 改为：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class FactorValue:
    as_of: str
    symbol: str
    name: str
    value: float
    factor_version: str
    direction: int
    unit: str
    missing_strategy: str
    source: str  # "real" | "deterministic_fallback" | "benchmark_proxy_fallback"
```

- [ ] **Step 2: Commit**

```bash
git add quant/src/hiveflow/factor/domain/factor_value.py
git commit -m "fix(l2): align FactorValue domain model with actual row schema"
```

### Task 6: 更新 Pydantic schemas

**Files:**
- Modify: `quant/src/interfaces/http/schemas.py:32-44`

- [ ] **Step 1: 写失败测试（FactorRow 含新字段）**

在 `quant/tests/contract/test_http_factor_optimization_endpoint.py` 旁边，或直接在已有测试中，检查 daily endpoint 响应中的 row 字段。实际上 Pydantic model_validate 会在字段缺失时报错，运行现有 contract 测试即可触发。先运行：

```bash
cd quant && uv run python -m pytest tests/contract/ -v
```

观察是否有 validation error（Pydantic v2 默认 `extra="ignore"`，可能不报错）。

- [ ] **Step 2: 更新 `FactorRow` schema**

```python
class FactorRow(BaseModel):
    as_of: str
    symbol: str
    factor_name: str
    factor_version: str
    raw_value: float
    direction: int
    unit: str
    missing_strategy: str
    source: str
```

- [ ] **Step 3: 新增 `FactorStabilityMetric` 和更新 `FactorSnapshot`**

在 `FactorRow` 下方新增：

```python
class FactorStabilityMetric(BaseModel):
    factor_name: str
    factor_version: str
    coverage_rate: float
    real_count: int
    fallback_count: int
    mean_value: float
    std_value: float
    drift_flag: bool | None = None
    drift_z_score: float | None = None
```

更新 `FactorSnapshot`：

```python
class FactorSnapshot(BaseModel):
    factor_version: str
    factor_names: list[str]
    coverage_rate: float
    rows: list[FactorRow]
    stability_metrics: list[FactorStabilityMetric] = []
```

- [ ] **Step 4: 更新 `routes_daily_run.py` 中的 OpenAPI example**

将 `factor_snapshot.rows` 的示例 row 补上新字段：

```python
{"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "momentum_20",
 "factor_version": "l2-momentum-v1.0", "raw_value": 0.024,
 "direction": 1, "unit": "return", "missing_strategy": "deterministic_fallback",
 "source": "real"},
```

- [ ] **Step 5: 运行全量测试**

```bash
cd quant && uv run python -m pytest -q
```

期望：全部通过

- [ ] **Step 6: Commit**

```bash
git add quant/src/interfaces/http/schemas.py quant/src/interfaces/http/routes_daily_run.py
git commit -m "feat(l2): update FactorRow/FactorSnapshot Pydantic schemas with new L2 fields"
```

---

## Chunk 6: daily_run_service 接入 benchmark bars

### Task 7: 在 daily pipeline 中查询基准 bars 并传入

**Files:**
- Modify: `quant/src/application/daily_run_service.py:50-65`

- [ ] **Step 1: 写失败测试（integration: benchmark 接入）**

在 `quant/tests/unit/` 下新增或在现有 service 测试中加：

```python
def test_run_daily_passes_benchmark_rows_to_factor_service(monkeypatch) -> None:
    """验证 bar_store 有数据时，benchmark bars 被查询并传入 compute_basic_factor_snapshot_from_bars。"""
    from application.daily_run_service import run_daily

    captured = {}

    class FakeBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return []  # 空 bars，让 factor service 走 fallback

    import application.factor.basic_factor_service as svc

    original = svc.compute_basic_factor_snapshot_from_bars

    def patched(as_of, symbols, bar_rows, benchmark_rows=None, historical_baselines=None):
        captured["benchmark_rows"] = benchmark_rows
        return original(as_of=as_of, symbols=symbols, bar_rows=bar_rows,
                        benchmark_rows=benchmark_rows, historical_baselines=historical_baselines)

    monkeypatch.setattr(svc, "compute_basic_factor_snapshot_from_bars", patched)

    run_daily(as_of="2026-04-01", root=None, bar_store=FakeBarStore())
    # benchmark_rows 应被传入（即使是空列表，说明查询了）
    assert "benchmark_rows" in captured
```

- [ ] **Step 2: 运行测试，确认失败（或通过，取决于现有实现）**

```bash
cd quant && uv run python -m pytest tests/unit/ -k "benchmark_rows" -v
```

- [ ] **Step 3: 修改 `daily_run_service.py`**

在 `bar_store.list_bars(...)` 调用后，追加查询基准 bars：

```python
_BENCHMARK_SYMBOL = "000300.SH"

# ...existing bar_rows query...
bar_rows = bar_store.list_bars(
    symbols=symbols,
    timeframe="1d",
    start_date=start_date,
    end_date=as_of,
    limit=10000,
)

# 查询基准 bars（至少需 21 条，多查以确保足够）
try:
    benchmark_start = (date.fromisoformat(as_of) - timedelta(days=40)).isoformat()
    benchmark_rows = bar_store.list_bars(
        symbols=[_BENCHMARK_SYMBOL],
        timeframe="1d",
        start_date=benchmark_start,
        end_date=as_of,
        limit=60,
    )
except Exception:
    benchmark_rows = None

factor_snapshot = compute_basic_factor_snapshot_from_bars(
    as_of=as_of,
    symbols=symbols,
    bar_rows=bar_rows,
    benchmark_rows=benchmark_rows,
)
```

- [ ] **Step 4: 运行全量测试**

```bash
cd quant && uv run python -m pytest -q
```

期望：全部通过

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/daily_run_service.py quant/tests/unit/
git commit -m "feat(l2): query benchmark bars in daily pipeline and pass to factor service"
```

---

## Chunk 7: 全量验证

### Task 8: 跑 CI 全量检查

- [ ] **Step 1: 运行全量测试 + lint**

```bash
cd quant && uv run python -m pytest -q && uv run ruff check .
```

期望：`N passed, 0 warnings`，ruff 无报错

- [ ] **Step 2: 运行架构边界检查**

```bash
make architecture-check
```

- [ ] **Step 3: 运行 CLI output 校验（验证 CLI 信封结构）**

```bash
make validate-cli-output
```

注意：`make validate-cli-output` 只校验顶层 CLI 信封（`schema_version`、`status`、`source` 等），不校验 `factor_snapshot.rows` 内部字段。新 row 字段（`direction`、`unit` 等）的正确性由上述 pytest 测试覆盖。

- [ ] **Step 4: 最终整合 commit（如有遗漏文件）**

```bash
git status
# 确保无未 commit 文件
```

---

## 文件变更总表

| 文件 | 操作 |
|------|------|
| `quant/src/application/factor/basic_factor_service.py` | 主要修改 |
| `quant/src/hiveflow/factor/domain/factor_value.py` | 补字段 |
| `quant/src/interfaces/http/schemas.py` | 新增 `FactorStabilityMetric`，更新 `FactorRow`/`FactorSnapshot` |
| `quant/src/interfaces/http/routes_daily_run.py` | 更新 OpenAPI example |
| `quant/src/application/daily_run_service.py` | 接入 benchmark 查询 |
| `quant/tests/unit/factor/test_basic_factor_service.py` | 更新已有断言 + 新增测试 |
