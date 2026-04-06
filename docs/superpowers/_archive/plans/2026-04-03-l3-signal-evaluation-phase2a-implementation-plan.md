# L3 信号评估 Phase 2a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 L3 信号层增加 IC（per-factor + composite Rank IC）和信号分布漂移检测，以独立离线评估命令 `hf signal evaluate` 提供。

**Architecture:** 新增 `application/signal/signal_evaluate_service.py` 作为核心评估服务，遍历日期范围逐日重算 L3 信号 + 查前瞻收益 → 计算 Spearman Rank IC + 漂移 z-score。HTTP `POST /api/v1/signal/evaluate` 和 Rust CLI `hf signal evaluate` 提供查询入口。不修改 daily pipeline，不引入持久化。

**Tech Stack:** Python (pandas, pydantic, FastAPI), Rust (clap, reqwest, comfy_table, serde_json)

**Spec:** `docs/superpowers/specs/2026-04-03-l3-signal-evaluation-phase2a-design.md`

**Important notes:**
- IC 评估**必须有 DB 中的真实 bar 数据**，不降级到 deterministic（确定性因子对所有日期值相同，IC 无意义）。
- Spearman 相关用 `pandas Series.corr(method='spearman')`，无需新增 scipy 依赖。
- 漂移检测基于 pre_winsorize 原始统计量（post_zscore 截面均值/标准差恒定，无法反映时序变化）。

---

### Task 1: Domain Models — IC & Drift dataclasses + Unit Tests

**Files:**
- Modify: `quant/src/domain/models/signal.py`
- Test: `quant/tests/unit/signal/test_domain_signal.py`

- [ ] **Step 1: Write the failing tests**

Append to `quant/tests/unit/signal/test_domain_signal.py`:

```python
from domain.models.signal import (
    DailyICEntry,
    FactorDriftResult,
    FactorICResult,
    RankTurnoverResult,
)


def test_daily_ic_entry():
    entry = DailyICEntry(date="2026-03-03", ic=0.12)
    assert entry.date == "2026-03-03"
    assert entry.ic == 0.12


def test_factor_ic_result():
    daily = (DailyICEntry(date="2026-03-03", ic=0.12),)
    r = FactorICResult(
        factor_name="momentum_20",
        mean_ic=0.12,
        ic_std=0.05,
        ic_ir=2.4,
        hit_rate=1.0,
        daily_ic=daily,
    )
    assert r.factor_name == "momentum_20"
    assert r.ic_ir == 2.4
    assert len(r.daily_ic) == 1


def test_factor_drift_result():
    d = FactorDriftResult(
        factor_name="momentum_20",
        baseline_mean=0.04,
        baseline_std=0.008,
        recent_mean=0.06,
        drift_z=2.5,
        drift_flag=True,
    )
    assert d.drift_flag is True
    assert d.drift_z == 2.5


def test_rank_turnover_result():
    r = RankTurnoverResult(mean_turnover=0.2, max_turnover=0.4, stable=True)
    assert r.stable is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_domain_signal.py -v -k "ic_entry or factor_ic or factor_drift or rank_turnover"`
Expected: FAIL with `ImportError: cannot import name 'DailyICEntry'`

- [ ] **Step 3: Write the implementation**

Append to `quant/src/domain/models/signal.py` (after the existing `CompositeScore` class):

```python
@dataclass(frozen=True)
class DailyICEntry:
    date: str
    ic: float


@dataclass(frozen=True)
class FactorICResult:
    factor_name: str
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: tuple[DailyICEntry, ...]


@dataclass(frozen=True)
class FactorDriftResult:
    factor_name: str
    baseline_mean: float
    baseline_std: float
    recent_mean: float
    drift_z: float
    drift_flag: bool


@dataclass(frozen=True)
class RankTurnoverResult:
    mean_turnover: float
    max_turnover: float
    stable: bool
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_domain_signal.py -v`
Expected: 8 passed (4 existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add quant/src/domain/models/signal.py quant/tests/unit/signal/test_domain_signal.py
git commit -m "feat(l3): add IC and drift domain models (DailyICEntry, FactorICResult, FactorDriftResult, RankTurnoverResult)"
```

---

### Task 2: Signal Evaluate Service — Core IC + Drift computation + Unit Tests

**Files:**
- Create: `quant/src/application/signal/signal_evaluate_service.py`
- Test: `quant/tests/unit/signal/test_signal_evaluate.py`

- [ ] **Step 1: Write the failing tests**

Create `quant/tests/unit/signal/test_signal_evaluate.py`:

```python
import math
from unittest.mock import MagicMock

import pytest


def _make_bar_store(bars_by_call: list[list[dict]]):
    """Mock bar_store that returns bars_by_call entries in order."""
    store = MagicMock()
    store.list_bars = MagicMock(side_effect=bars_by_call)
    return store


def _make_bars_for_date(symbols: list[str], date: str, prices: dict[str, float]) -> list[dict]:
    """Create bar dicts for one date."""
    return [
        {
            "symbol": s,
            "timeframe": "1d",
            "bar_time": f"{date}T15:00:00+08:00",
            "open": prices[s],
            "high": prices[s],
            "low": prices[s],
            "close": prices[s],
            "volume": 10000.0,
            "amount": prices[s] * 10000.0,
            "adj_factor": 1.0,
            "data_source": "test",
        }
        for s in symbols
    ]


def _make_multi_day_bars(
    symbols: list[str],
    dates: list[str],
    price_series: dict[str, list[float]],
) -> list[dict]:
    """Create bars spanning multiple dates for all symbols."""
    bars = []
    for i, d in enumerate(dates):
        for s in symbols:
            bars.append({
                "symbol": s,
                "timeframe": "1d",
                "bar_time": f"{d}T15:00:00+08:00",
                "open": price_series[s][i],
                "high": price_series[s][i],
                "low": price_series[s][i],
                "close": price_series[s][i],
                "volume": 10000.0,
                "amount": price_series[s][i] * 10000.0,
                "adj_factor": 1.0,
                "data_source": "test",
            })
    return bars


def test_ic_perfect_positive():
    """When signal order perfectly predicts return order, IC should be ~1.0."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 1.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": 2.0},
            {"symbol": "C", "factor_name": "f1", "signal_value": 3.0},
            {"symbol": "D", "factor_name": "f1", "signal_value": 4.0},
            {"symbol": "E", "factor_name": "f1", "signal_value": 5.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 1.0},
            {"symbol": "B", "composite_score": 2.0},
            {"symbol": "C", "composite_score": 3.0},
            {"symbol": "D", "composite_score": 4.0},
            {"symbol": "E", "composite_score": 5.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert abs(result["f1"] - 1.0) < 0.01
    assert abs(result["composite"] - 1.0) < 0.01


def test_ic_perfect_negative():
    """When signal order is perfectly opposite to return order, IC should be ~-1.0."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 5.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": 4.0},
            {"symbol": "C", "factor_name": "f1", "signal_value": 3.0},
            {"symbol": "D", "factor_name": "f1", "signal_value": 2.0},
            {"symbol": "E", "factor_name": "f1", "signal_value": 1.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 5.0},
            {"symbol": "B", "composite_score": 4.0},
            {"symbol": "C", "composite_score": 3.0},
            {"symbol": "D", "composite_score": 2.0},
            {"symbol": "E", "composite_score": 1.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert abs(result["f1"] - (-1.0)) < 0.01
    assert abs(result["composite"] - (-1.0)) < 0.01


def test_ic_insufficient_pairs():
    """IC should be NaN when < 3 valid pairs."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 1.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": 2.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 1.0},
            {"symbol": "B", "composite_score": 2.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert math.isnan(result["f1"])
    assert math.isnan(result["composite"])


def test_ic_nan_signal_excluded():
    """NaN signal values should be excluded from IC computation."""
    from application.signal.signal_evaluate_service import _compute_daily_ic

    signal_matrix = {
        "factor_names": ["f1"],
        "rows": [
            {"symbol": "A", "factor_name": "f1", "signal_value": 1.0},
            {"symbol": "B", "factor_name": "f1", "signal_value": float("nan")},
            {"symbol": "C", "factor_name": "f1", "signal_value": 3.0},
            {"symbol": "D", "factor_name": "f1", "signal_value": 4.0},
        ],
        "composite_scores": [
            {"symbol": "A", "composite_score": 1.0},
            {"symbol": "B", "composite_score": float("nan")},
            {"symbol": "C", "composite_score": 3.0},
            {"symbol": "D", "composite_score": 4.0},
        ],
    }
    forward_returns = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04}
    result = _compute_daily_ic(signal_matrix, forward_returns)
    assert not math.isnan(result["f1"])


def test_ic_ir_calculation():
    """IC IR = mean_ic / ic_std."""
    from application.signal.signal_evaluate_service import _aggregate_ic_series

    daily_ics = [0.1, 0.2, 0.3, -0.1, 0.15]
    result = _aggregate_ic_series(daily_ics)
    expected_mean = sum(daily_ics) / len(daily_ics)
    assert abs(result["mean_ic"] - expected_mean) < 1e-6
    assert abs(result["ic_ir"] - result["mean_ic"] / result["ic_std"]) < 1e-6


def test_hit_rate():
    """hit_rate = count(IC > 0) / total."""
    from application.signal.signal_evaluate_service import _aggregate_ic_series

    daily_ics = [0.1, -0.05, 0.2, 0.0, -0.1]
    result = _aggregate_ic_series(daily_ics)
    assert abs(result["hit_rate"] - 0.4) < 1e-6  # 2 out of 5 are > 0


def test_drift_flag_triggered():
    """When recent data deviates significantly from baseline, drift_flag should be True."""
    from application.signal.signal_evaluate_service import _compute_factor_drift

    baseline_means = [0.04, 0.042, 0.038, 0.041, 0.039, 0.04, 0.041]
    recent_means = [0.08, 0.082, 0.079]
    result = _compute_factor_drift("momentum_20", baseline_means, recent_means)
    assert result["drift_flag"] is True
    assert abs(result["drift_z"]) > 2.0


def test_drift_no_flag():
    """Stable data should not trigger drift."""
    from application.signal.signal_evaluate_service import _compute_factor_drift

    baseline_means = [0.04, 0.042, 0.038, 0.041, 0.039, 0.04, 0.041]
    recent_means = [0.040, 0.041, 0.039]
    result = _compute_factor_drift("momentum_20", baseline_means, recent_means)
    assert result["drift_flag"] is False


def test_drift_baseline_std_zero():
    """When baseline std is 0, drift_z should be 0 and no flag."""
    from application.signal.signal_evaluate_service import _compute_factor_drift

    baseline_means = [0.04, 0.04, 0.04, 0.04, 0.04]
    recent_means = [0.08, 0.08, 0.08]
    result = _compute_factor_drift("momentum_20", baseline_means, recent_means)
    assert result["drift_z"] == 0.0
    assert result["drift_flag"] is False


def test_rank_turnover_identical():
    """Identical rankings should give turnover = 0."""
    from application.signal.signal_evaluate_service import _kendall_tau_distance

    assert _kendall_tau_distance(["A", "B", "C", "D", "E"], ["A", "B", "C", "D", "E"]) == 0.0


def test_rank_turnover_reversed():
    """Fully reversed rankings should give turnover = 1.0."""
    from application.signal.signal_evaluate_service import _kendall_tau_distance

    assert _kendall_tau_distance(["A", "B", "C", "D", "E"], ["E", "D", "C", "B", "A"]) == 1.0


def test_rank_turnover_partial():
    """Partial reversal should give 0 < turnover < 1."""
    from application.signal.signal_evaluate_service import _kendall_tau_distance

    d = _kendall_tau_distance(["A", "B", "C", "D", "E"], ["B", "A", "C", "D", "E"])
    assert 0 < d < 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_signal_evaluate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.signal.signal_evaluate_service'`

- [ ] **Step 3: Write the implementation**

Create `quant/src/application/signal/signal_evaluate_service.py`:

```python
from __future__ import annotations

import logging
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pandas as pd

from application.contracts.cli_output import ok_output
from application.factor.basic_factor_service import compute_basic_factor_snapshot_from_bars
from application.signal.signal_engineering_service import compute_signal_matrix

_EVAL_VERSION = "l3-eval-v1.0"
_BENCHMARK_SYMBOL = "000300.SH"
_DEFAULT_SYMBOLS = [
    "000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ",
]
_MIN_SPEARMAN_PAIRS = 3
_DRIFT_THRESHOLD = 2.0
_TURNOVER_STABLE_THRESHOLD = 0.5
_MIN_DAYS_FOR_DRIFT = 5
_FACTOR_BAR_LOOKBACK_DAYS = 180

_logger = logging.getLogger(__name__)


def _compute_daily_ic(signal_matrix: dict, forward_returns: dict[str, float]) -> dict:
    result: dict[str, float] = {}
    fwd_series = pd.Series(forward_returns)

    for factor in signal_matrix.get("factor_names", []):
        signal_series = pd.Series({
            r["symbol"]: r["signal_value"]
            for r in signal_matrix["rows"]
            if r["factor_name"] == factor and not math.isnan(r["signal_value"])
        })
        common = signal_series.index.intersection(fwd_series.index)
        if len(common) >= _MIN_SPEARMAN_PAIRS:
            ic = signal_series[common].corr(fwd_series[common], method="spearman")
            result[factor] = round(float(ic), 6) if not math.isnan(ic) else float("nan")
        else:
            result[factor] = float("nan")

    composite_series = pd.Series({
        cs["symbol"]: cs["composite_score"]
        for cs in signal_matrix.get("composite_scores", [])
        if not math.isnan(cs["composite_score"])
    })
    common = composite_series.index.intersection(fwd_series.index)
    if len(common) >= _MIN_SPEARMAN_PAIRS:
        ic = composite_series[common].corr(fwd_series[common], method="spearman")
        result["composite"] = round(float(ic), 6) if not math.isnan(ic) else float("nan")
    else:
        result["composite"] = float("nan")

    return result


def _aggregate_ic_series(daily_ics: list[float]) -> dict:
    valid = [v for v in daily_ics if not math.isnan(v)]
    if not valid:
        return {"mean_ic": float("nan"), "ic_std": float("nan"), "ic_ir": float("nan"), "hit_rate": float("nan")}
    mean_ic = statistics.mean(valid)
    ic_std = statistics.pstdev(valid) if len(valid) > 1 else 0.0
    ic_ir = round(mean_ic / ic_std, 6) if ic_std > 0 else 0.0
    hit_rate = sum(1 for v in valid if v > 0) / len(valid)
    return {
        "mean_ic": round(mean_ic, 6),
        "ic_std": round(ic_std, 6),
        "ic_ir": ic_ir,
        "hit_rate": round(hit_rate, 6),
    }


def _compute_factor_drift(
    factor_name: str,
    baseline_means: list[float],
    recent_means: list[float],
) -> dict:
    bl_valid = [v for v in baseline_means if not math.isnan(v)]
    rc_valid = [v for v in recent_means if not math.isnan(v)]

    if not bl_valid or not rc_valid:
        return {
            "factor_name": factor_name,
            "baseline_mean": 0.0, "baseline_std": 0.0,
            "recent_mean": 0.0, "drift_z": 0.0, "drift_flag": False,
        }

    bl_mean = statistics.mean(bl_valid)
    bl_std = statistics.pstdev(bl_valid) if len(bl_valid) > 1 else 0.0
    rc_mean = statistics.mean(rc_valid)

    if bl_std == 0.0:
        drift_z = 0.0
    else:
        drift_z = (rc_mean - bl_mean) / bl_std

    return {
        "factor_name": factor_name,
        "baseline_mean": round(bl_mean, 6),
        "baseline_std": round(bl_std, 6),
        "recent_mean": round(rc_mean, 6),
        "drift_z": round(drift_z, 4),
        "drift_flag": abs(drift_z) > _DRIFT_THRESHOLD,
    }


def _kendall_tau_distance(ranking_a: list[str], ranking_b: list[str]) -> float:
    n = len(ranking_a)
    if n < 2:
        return 0.0
    index_b = {s: i for i, s in enumerate(ranking_b)}
    discordant = 0
    pairs = n * (n - 1) // 2
    for i in range(n):
        for j in range(i + 1, n):
            a_i, a_j = ranking_a[i], ranking_a[j]
            if index_b.get(a_i, 0) > index_b.get(a_j, 0):
                discordant += 1
    return discordant / pairs


def _get_forward_returns(
    bar_store, symbols: list[str], as_of: str, forward_days: int,
) -> dict[str, float]:
    end = (date.fromisoformat(as_of) + timedelta(days=forward_days + 5)).isoformat()
    bars = bar_store.list_bars(
        symbols=symbols, timeframe="1d",
        start_date=as_of, end_date=end, limit=len(symbols) * (forward_days + 10),
    )

    by_symbol: dict[str, list[dict]] = {}
    for b in bars:
        by_symbol.setdefault(b["symbol"], []).append(b)

    result: dict[str, float] = {}
    for sym, sym_bars in by_symbol.items():
        sorted_bars = sorted(sym_bars, key=lambda b: b["bar_time"])
        base_bars = [b for b in sorted_bars if b["bar_time"][:10] <= as_of]
        fwd_bars = [b for b in sorted_bars if b["bar_time"][:10] > as_of]
        if not base_bars or len(fwd_bars) < forward_days:
            continue
        base_close = base_bars[-1]["close"]
        fwd_close = fwd_bars[forward_days - 1]["close"]
        if base_close == 0:
            continue
        result[sym] = round((fwd_close / base_close) - 1.0, 6)

    return result


def _compute_signal_for_date(bar_store, symbols: list[str], as_of: str) -> dict | None:
    try:
        start = (date.fromisoformat(as_of) - timedelta(days=_FACTOR_BAR_LOOKBACK_DAYS)).isoformat()
        bar_rows = bar_store.list_bars(
            symbols=symbols, timeframe="1d",
            start_date=start, end_date=as_of, limit=len(symbols) * 200,
        )
        if not bar_rows or len(bar_rows) < len(symbols) * 61:
            return None
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
        return compute_signal_matrix(factor_snapshot)
    except Exception:
        _logger.warning("signal evaluate: failed for %s", as_of, exc_info=True)
        return None


def _get_composite_ranking(signal_matrix: dict) -> list[str]:
    scores = signal_matrix.get("composite_scores", [])
    valid = [(cs["symbol"], cs["composite_score"]) for cs in scores if not math.isnan(cs["composite_score"])]
    valid.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in valid]


def run_signal_evaluation(
    start_date: str,
    end_date: str,
    forward_days: int,
    bar_store,
) -> dict:
    if bar_store is None:
        return {
            "schema_version": "1.0.0",
            "command": "hf signal evaluate",
            "run_id": f"run_eval_{str(uuid4())[:8]}",
            "status": "error",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {},
            "warnings": [],
            "errors": [{"code": "BAR_STORE_REQUIRED", "message": "Signal evaluation requires database with real bar data"}],
        }

    symbols = list(_DEFAULT_SYMBOLS)
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)

    if d_start >= d_end:
        return {
            "schema_version": "1.0.0",
            "command": "hf signal evaluate",
            "run_id": f"run_eval_{str(uuid4())[:8]}",
            "status": "error",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {},
            "warnings": [],
            "errors": [{"code": "INVALID_DATE_RANGE", "message": f"start_date ({start_date}) must be before end_date ({end_date})"}],
        }

    current = d_start
    daily_results: list[dict] = []
    warnings: list[dict] = []

    while current <= d_end - timedelta(days=forward_days):
        as_of = current.isoformat()
        signal_matrix = _compute_signal_for_date(bar_store, symbols, as_of)
        if signal_matrix is None:
            warnings.append({
                "code": "SKIPPED_DATE_INSUFFICIENT_BARS",
                "message": f"Skipped {as_of}: insufficient bar data for factor computation",
            })
            current += timedelta(days=1)
            continue

        fwd_returns = _get_forward_returns(bar_store, symbols, as_of, forward_days)
        if not fwd_returns:
            warnings.append({
                "code": "SKIPPED_DATE_NO_FORWARD_RETURNS",
                "message": f"Skipped {as_of}: no forward returns available",
            })
            current += timedelta(days=1)
            continue

        ic_result = _compute_daily_ic(signal_matrix, fwd_returns)
        pre_stats = {
            ts["factor_name"]: ts["pre_winsorize"]["mean"]
            for ts in signal_matrix.get("transform_stats", [])
        }
        ranking = _get_composite_ranking(signal_matrix)

        daily_results.append({
            "date": as_of,
            "ic": ic_result,
            "pre_winsorize_means": pre_stats,
            "coverage_rate": signal_matrix.get("coverage_rate", 0.0),
            "ranking": ranking,
        })

        current += timedelta(days=1)

    if not daily_results:
        return ok_output(
            command="hf signal evaluate",
            run_id=f"run_eval_{str(uuid4())[:8]}",
            data={
                "eval_version": _EVAL_VERSION,
                "start_date": start_date, "end_date": end_date,
                "forward_days": forward_days,
                "trading_days_evaluated": 0,
                "symbols": symbols,
                "ic_report": None, "drift_diagnostics": None,
            },
            warnings=warnings + [{"code": "NO_VALID_EVALUATION_DAYS", "message": "No dates had sufficient data for evaluation"}],
        )

    factor_names = list(daily_results[0]["ic"].keys())
    factor_names = [f for f in factor_names if f != "composite"]

    per_factor_ic: list[dict] = []
    for fn in factor_names:
        daily_ics = [d["ic"].get(fn, float("nan")) for d in daily_results]
        agg = _aggregate_ic_series(daily_ics)
        per_factor_ic.append({
            "factor_name": fn,
            **agg,
            "daily_ic": [
                {"date": d["date"], "ic": d["ic"].get(fn, float("nan"))}
                for d in daily_results
            ],
        })

    composite_daily_ics = [d["ic"].get("composite", float("nan")) for d in daily_results]
    composite_agg = _aggregate_ic_series(composite_daily_ics)
    composite_report = {
        **composite_agg,
        "daily_ic": [
            {"date": d["date"], "ic": d["ic"].get("composite", float("nan"))}
            for d in daily_results
        ],
    }

    ic_report = {"per_factor": per_factor_ic, "composite": composite_report}

    drift_diagnostics = None
    n_days = len(daily_results)
    if n_days >= _MIN_DAYS_FOR_DRIFT:
        drift_window = max(3, n_days // 4)
        baseline_days = n_days - drift_window

        factor_drift: list[dict] = []
        for fn in factor_names:
            bl_means = [d["pre_winsorize_means"].get(fn, float("nan")) for d in daily_results[:baseline_days]]
            rc_means = [d["pre_winsorize_means"].get(fn, float("nan")) for d in daily_results[baseline_days:]]
            factor_drift.append(_compute_factor_drift(fn, bl_means, rc_means))

        bl_cov = [d["coverage_rate"] for d in daily_results[:baseline_days]]
        rc_cov = [d["coverage_rate"] for d in daily_results[baseline_days:]]
        bl_cov_valid = [v for v in bl_cov if not math.isnan(v)]
        rc_cov_valid = [v for v in rc_cov if not math.isnan(v)]
        bl_cov_mean = statistics.mean(bl_cov_valid) if bl_cov_valid else 0.0
        bl_cov_std = statistics.pstdev(bl_cov_valid) if len(bl_cov_valid) > 1 else 0.0
        rc_cov_mean = statistics.mean(rc_cov_valid) if rc_cov_valid else 0.0
        cov_drift_z = ((rc_cov_mean - bl_cov_mean) / bl_cov_std) if bl_cov_std > 0 else 0.0

        turnovers: list[float] = []
        for i in range(1, n_days):
            prev_rank = daily_results[i - 1]["ranking"]
            curr_rank = daily_results[i]["ranking"]
            if prev_rank and curr_rank and set(prev_rank) == set(curr_rank):
                turnovers.append(_kendall_tau_distance(prev_rank, curr_rank))

        mean_turnover = round(statistics.mean(turnovers), 4) if turnovers else 0.0
        max_turnover = round(max(turnovers), 4) if turnovers else 0.0

        drift_diagnostics = {
            "drift_window": drift_window,
            "baseline_days": baseline_days,
            "factor_drift": factor_drift,
            "coverage_drift": {
                "baseline_mean": round(bl_cov_mean, 4),
                "recent_mean": round(rc_cov_mean, 4),
                "drift_z": round(cov_drift_z, 4),
                "drift_flag": abs(cov_drift_z) > _DRIFT_THRESHOLD,
            },
            "rank_turnover": {
                "mean_turnover": mean_turnover,
                "max_turnover": max_turnover,
                "stable": mean_turnover < _TURNOVER_STABLE_THRESHOLD,
            },
        }
    else:
        warnings.append({
            "code": "INSUFFICIENT_DAYS_FOR_DRIFT",
            "message": f"Need at least {_MIN_DAYS_FOR_DRIFT} evaluation days for drift detection, got {n_days}",
        })

    data = {
        "eval_version": _EVAL_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "forward_days": forward_days,
        "trading_days_evaluated": n_days,
        "symbols": symbols,
        "ic_report": ic_report,
        "drift_diagnostics": drift_diagnostics,
    }

    return ok_output(
        command="hf signal evaluate",
        run_id=f"run_eval_{start_date.replace('-', '')}_{end_date.replace('-', '')}_{str(uuid4())[:8]}",
        data=data,
        warnings=warnings if warnings else None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd quant && uv run python -m pytest tests/unit/signal/test_signal_evaluate.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/signal/signal_evaluate_service.py quant/tests/unit/signal/test_signal_evaluate.py
git commit -m "feat(l3): add signal evaluate service with IC computation and drift detection"
```

---

### Task 3: Pydantic Schemas for Signal Evaluation

**Files:**
- Modify: `quant/src/interfaces/http/schemas.py`

- [ ] **Step 1: Add SignalEvaluate Pydantic models**

In `quant/src/interfaces/http/schemas.py`, add the following classes **after** the `SignalSnapshotResponse` class (line 164):

```python
class SignalEvaluateRequest(BaseModel):
    start_date: str = Field(description="评估起始日期，YYYY-MM-DD")
    end_date: str = Field(description="评估结束日期，YYYY-MM-DD")
    forward_days: int = Field(default=1, ge=1, le=10, description="前瞻天数")


class DailyIC(BaseModel):
    date: str
    ic: float


class FactorICReport(BaseModel):
    factor_name: str
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: list[DailyIC]


class CompositeICReport(BaseModel):
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: list[DailyIC]


class ICReport(BaseModel):
    per_factor: list[FactorICReport]
    composite: CompositeICReport


class FactorDrift(BaseModel):
    factor_name: str
    baseline_mean: float
    baseline_std: float
    recent_mean: float
    drift_z: float
    drift_flag: bool


class CoverageDrift(BaseModel):
    baseline_mean: float
    recent_mean: float
    drift_z: float
    drift_flag: bool


class RankTurnover(BaseModel):
    mean_turnover: float
    max_turnover: float
    stable: bool


class DriftDiagnostics(BaseModel):
    drift_window: int
    baseline_days: int
    factor_drift: list[FactorDrift]
    coverage_drift: CoverageDrift
    rank_turnover: RankTurnover


class SignalEvaluation(BaseModel):
    eval_version: str
    start_date: str
    end_date: str
    forward_days: int
    trading_days_evaluated: int
    symbols: list[str]
    ic_report: ICReport | None
    drift_diagnostics: DriftDiagnostics | None


class SignalEvaluateResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: SignalEvaluation
    warnings: list[dict]
    errors: list[dict]
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `cd quant && uv run python -m pytest -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add quant/src/interfaces/http/schemas.py
git commit -m "feat(l3): add SignalEvaluate Pydantic schemas (IC report + drift diagnostics)"
```

---

### Task 4: HTTP Endpoint + Dependency Injection

**Files:**
- Modify: `quant/src/interfaces/http/routes_signal.py`
- Modify: `quant/src/interfaces/http/dependencies.py`

- [ ] **Step 1: Add provider to dependencies.py**

In `quant/src/interfaces/http/dependencies.py`, add the import at the top (alongside the existing `run_signal_snapshot` import):

```python
from application.signal.signal_evaluate_service import run_signal_evaluation
```

Add the type alias after the existing `SignalSnapshotService` alias (line 28):

```python
SignalEvaluateService = Callable[[str, str, int], dict]
```

Add the provider function after `get_signal_snapshot_service` (after line 83):

```python
def get_signal_evaluate_service() -> SignalEvaluateService:
    if not has_db_config():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BAR_STORE_REQUIRED",
                "message": "Signal evaluation requires database with real bar data",
            },
        )
    try:
        bar_store = TimescaleBarStore(open_db_connection_from_env())
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BAR_STORE_REQUIRED",
                "message": f"Signal evaluation requires database: {exc}",
            },
        ) from exc
    return lambda start, end, fwd: run_signal_evaluation(
        start_date=start, end_date=end, forward_days=fwd, bar_store=bar_store,
    )
```

- [ ] **Step 2: Add route to routes_signal.py**

Replace the entire `quant/src/interfaces/http/routes_signal.py` with:

```python
from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    SignalEvaluateService,
    SignalSnapshotService,
    get_signal_evaluate_service,
    get_signal_snapshot_service,
)
from interfaces.http.schemas import (
    SignalEvaluateRequest,
    SignalEvaluateResponse,
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


@router.post(
    "/evaluate",
    summary="L3 信号质量评估（IC + 漂移检测）",
    description=(
        "对指定日期范围逐日重算 L3 信号，计算 Rank IC（per-factor + composite）"
        "和信号分布漂移诊断。需要 DB 中的真实 bar 数据。"
    ),
    response_description="IC 报告 + 漂移诊断",
)
def post_signal_evaluate(
    req: SignalEvaluateRequest,
    service: SignalEvaluateService = Depends(get_signal_evaluate_service),
) -> SignalEvaluateResponse:
    return SignalEvaluateResponse.model_validate(
        service(req.start_date, req.end_date, req.forward_days)
    )
```

- [ ] **Step 3: Run all Python tests**

Run: `cd quant && uv run python -m pytest -q`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add quant/src/interfaces/http/routes_signal.py quant/src/interfaces/http/dependencies.py
git commit -m "feat(l3): add POST /api/v1/signal/evaluate HTTP endpoint"
```

---

### Task 5: Architecture Tests Update

**Files:**
- Modify: `quant/tests/architecture/test_layering_rules.py`

- [ ] **Step 1: Verify existing architecture tests cover signal layer**

The existing `test_application_signal_does_not_import_interfaces` already covers all files in `application/signal/` (including the new `signal_evaluate_service.py`). The existing `test_domain_signal_does_not_import_application` covers `domain/models/signal.py`. No new architecture tests needed — the existing glob patterns already cover the new files.

Run: `cd quant && uv run python -m pytest tests/architecture/ -v`
Expected: all pass (including the L3 tests added in Phase 1)

- [ ] **Step 2: Commit** (only if changes were needed — skip if all existing tests pass)

---

### Task 6: Rust CLI — `hf signal evaluate`

**Files:**
- Modify: `cli/src/cmd/signal.rs`
- Modify: `cli/src/cmd/mod.rs`
- Modify: `cli/src/application/requests.rs`
- Create: `cli/src/application/handlers/signal_evaluate.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`

- [ ] **Step 1: Add SignalEvaluateRequest to requests.rs**

In `cli/src/application/requests.rs`, add the struct after `SignalSnapshotRequest`:

```rust
#[derive(Debug, Clone)]
pub struct SignalEvaluateRequest {
    pub start_date: String,
    pub end_date: String,
    pub forward_days: u32,
    pub output: String,
}
```

Add to the `AppCommand` enum:

```rust
    SignalEvaluate(SignalEvaluateRequest),
```

- [ ] **Step 2: Add Evaluate subcommand to cmd/signal.rs**

Replace `cli/src/cmd/signal.rs` with:

```rust
use crate::application::requests::{SignalEvaluateRequest, SignalSnapshotRequest};
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(
    about = "L3 信号工程：将 L2 因子截面标准化为 signal_matrix（需 quant HTTP 服务）"
)]
pub struct SignalArgs {
    #[command(subcommand)]
    pub command: SignalSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum SignalSubcommand {
    #[command(
        about = "请求服务端计算指定日期的标准化信号矩阵，并打印 JSON 或表格",
        long_about = "调用 POST /api/v1/signal/snapshot。\
data 内为 signal_matrix：含 rows（逐标的×因子信号）、composite_scores（等权综合分）、\
transform_stats（去极值前后诊断）。\
l2_decision / 排序逻辑不受影响，本命令仅用于观测与联调。"
    )]
    Snapshot(SnapshotArgs),

    #[command(
        about = "评估 L3 信号质量：Rank IC（per-factor + composite）+ 漂移检测",
        long_about = "调用 POST /api/v1/signal/evaluate。\
遍历日期范围逐日重算信号并计算 T+N 收益的 Spearman Rank IC，\
同时检测信号分布漂移。需要 DB 中的真实 bar 数据。"
    )]
    Evaluate(EvaluateArgs),
}

const SNAPSHOT_AFTER_HELP: &str = "\
示例:
  hf signal snapshot --as-of 2026-04-01
  hf signal snapshot --as-of 2026-04-01 --output table

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- signal snapshot --as-of 2026-04-01
  cargo run -p hf-cli -- signal snapshot --as-of 2026-04-01 --output json

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务（如 http://127.0.0.1:8000）";

#[derive(Debug, Args)]
#[command(after_long_help = SNAPSHOT_AFTER_HELP)]
pub struct SnapshotArgs {
    #[arg(
        long,
        value_name = "YYYY-MM-DD",
        help = "截面日期（PIT：只使用该日及之前已发布/可得的数据）"
    )]
    pub as_of: String,
    #[arg(
        long,
        default_value = "json",
        value_name = "MODE",
        help = "输出形式：json = 标准 CLI envelope（默认）；table = 终端中文表（概要 + 明细 + 综合分）"
    )]
    pub output: String,
}

const EVALUATE_AFTER_HELP: &str = "\
示例:
  hf signal evaluate --start-date 2026-03-01 --end-date 2026-04-01
  hf signal evaluate --start-date 2026-03-01 --end-date 2026-04-01 --forward-days 3 --output table

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- signal evaluate --start-date 2026-03-01 --end-date 2026-04-01

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务；
  需要 DB 中有真实 bar 数据（make db-up && make run-server）";

#[derive(Debug, Args)]
#[command(after_long_help = EVALUATE_AFTER_HELP)]
pub struct EvaluateArgs {
    #[arg(long, value_name = "YYYY-MM-DD", help = "评估起始日期")]
    pub start_date: String,
    #[arg(long, value_name = "YYYY-MM-DD", help = "评估结束日期")]
    pub end_date: String,
    #[arg(long, default_value = "1", help = "前瞻天数（默认 1）")]
    pub forward_days: u32,
    #[arg(long, default_value = "json", value_name = "MODE", help = "输出形式：json | table")]
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

impl From<EvaluateArgs> for SignalEvaluateRequest {
    fn from(args: EvaluateArgs) -> Self {
        Self {
            start_date: args.start_date,
            end_date: args.end_date,
            forward_days: args.forward_days,
            output: args.output,
        }
    }
}
```

- [ ] **Step 3: Update cmd/mod.rs dispatch**

In `cli/src/cmd/mod.rs`, update the `Signal` match arm:

```rust
            Commands::Signal(args) => match args.command {
                signal::SignalSubcommand::Snapshot(snapshot) => {
                    AppCommand::SignalSnapshot(snapshot.into())
                }
                signal::SignalSubcommand::Evaluate(evaluate) => {
                    AppCommand::SignalEvaluate(evaluate.into())
                }
            },
```

- [ ] **Step 4: Add http_client function**

In `cli/src/infrastructure/http_client.rs`, add after `post_signal_snapshot`:

```rust
pub fn post_signal_evaluate(
    server_url: &str,
    start_date: &str,
    end_date: &str,
    forward_days: u32,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!("{}/api/v1/signal/evaluate", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({
            "start_date": start_date,
            "end_date": end_date,
            "forward_days": forward_days,
        }))
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
fn ic_rating(ic_ir: f64) -> &'static str {
    if ic_ir >= 0.5 {
        "良好"
    } else if ic_ir >= 0.2 {
        "中等"
    } else {
        "偏弱"
    }
}

pub fn render_signal_evaluate_table(payload: &Value) -> String {
    let data = payload.get("data");
    let start = as_str(data.and_then(|d| d.get("start_date")));
    let end = as_str(data.and_then(|d| d.get("end_date")));
    let fwd = as_i64(data.and_then(|d| d.get("forward_days")));
    let days = as_i64(data.and_then(|d| d.get("trading_days_evaluated")));

    let mut header = Table::new();
    header
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("区间"),
            Cell::new("前瞻"),
            Cell::new("评估天数"),
        ]);
    header.add_row(vec![
        format!("{start} → {end}"),
        format!("T+{fwd}"),
        days,
    ]);

    let mut ic_table = Table::new();
    ic_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("因子"),
            Cell::new("均值IC"),
            Cell::new("IC_IR"),
            Cell::new("命中率"),
            Cell::new("评级"),
        ]);

    if let Some(ic_report) = data.and_then(|d| d.get("ic_report")) {
        if let Some(factors) = ic_report.get("per_factor").and_then(Value::as_array) {
            for f in factors {
                let ir_val = f.get("ic_ir").and_then(Value::as_f64).unwrap_or(0.0);
                ic_table.add_row(vec![
                    as_str(f.get("factor_name")),
                    as_f64(f.get("mean_ic")),
                    as_f64(f.get("ic_ir")),
                    format!(
                        "{:.1}%",
                        f.get("hit_rate").and_then(Value::as_f64).unwrap_or(0.0) * 100.0
                    ),
                    ic_rating(ir_val).to_string(),
                ]);
            }
        }
        if let Some(comp) = ic_report.get("composite") {
            let ir_val = comp.get("ic_ir").and_then(Value::as_f64).unwrap_or(0.0);
            ic_table.add_row(vec![
                "★ 综合信号".to_string(),
                as_f64(comp.get("mean_ic")),
                as_f64(comp.get("ic_ir")),
                format!(
                    "{:.1}%",
                    comp.get("hit_rate").and_then(Value::as_f64).unwrap_or(0.0) * 100.0
                ),
                ic_rating(ir_val).to_string(),
            ]);
        }
    }

    let mut drift_table = Table::new();
    drift_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("指标"),
            Cell::new("漂移Z"),
            Cell::new("状态"),
        ]);

    if let Some(drift) = data.and_then(|d| d.get("drift_diagnostics")) {
        if let Some(factors) = drift.get("factor_drift").and_then(Value::as_array) {
            for f in factors {
                let flag = f.get("drift_flag").and_then(Value::as_bool).unwrap_or(false);
                drift_table.add_row(vec![
                    as_str(f.get("factor_name")),
                    as_f64(f.get("drift_z")),
                    if flag { "⚠ 漂移" } else { "✓ 正常" }.to_string(),
                ]);
            }
        }
        if let Some(cov) = drift.get("coverage_drift") {
            let flag = cov.get("drift_flag").and_then(Value::as_bool).unwrap_or(false);
            drift_table.add_row(vec![
                "覆盖率".to_string(),
                as_f64(cov.get("drift_z")),
                if flag { "⚠ 漂移" } else { "✓ 正常" }.to_string(),
            ]);
        }
        if let Some(rt) = drift.get("rank_turnover") {
            let stable = rt.get("stable").and_then(Value::as_bool).unwrap_or(true);
            drift_table.add_row(vec![
                "排名周转率".to_string(),
                as_f64(rt.get("mean_turnover")),
                if stable { "✓ 稳定" } else { "⚠ 不稳定" }.to_string(),
            ]);
        }
    }

    format!(
        "L3 信号评估\n{}\nIC 报告\n{}\n漂移诊断\n{}\n",
        header, ic_table, drift_table
    )
}
```

- [ ] **Step 6: Create handler**

Create `cli/src/application/handlers/signal_evaluate.rs`:

```rust
use crate::application::requests::SignalEvaluateRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_signal_evaluate_table;

pub fn handle(args: SignalEvaluateRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_signal_evaluate(
        &cfg.server_url,
        &args.start_date,
        &args.end_date,
        args.forward_days,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_signal_evaluate_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for signal evaluate: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
```

- [ ] **Step 7: Register handler module**

In `cli/src/application/handlers/mod.rs`, add:

```rust
pub mod signal_evaluate;
```

- [ ] **Step 8: Add dispatch arm**

In `cli/src/application/dispatch.rs`, update the import:

```rust
use crate::application::handlers::{
    data_bars, data_query, data_sync, data_universe_sync, factor_optimize, factor_replay,
    pipeline_compare, pipeline_daily, signal_evaluate, signal_snapshot,
};
```

Add the match arm:

```rust
        AppCommand::SignalEvaluate(args) => signal_evaluate::handle(args),
```

- [ ] **Step 9: Build and test**

Run: `cd cli && cargo build`
Expected: compiles with no errors

Run: `cd cli && cargo test`
Expected: all tests pass

- [ ] **Step 10: Commit**

```bash
git add cli/src/cmd/signal.rs cli/src/cmd/mod.rs cli/src/application/requests.rs cli/src/application/handlers/signal_evaluate.rs cli/src/application/handlers/mod.rs cli/src/application/dispatch.rs cli/src/infrastructure/http_client.rs cli/src/infrastructure/table_renderer.rs
git commit -m "feat(l3): add hf signal evaluate CLI command (json|table) with IC + drift"
```

---

### Task 7: Documentation Update

**Files:**
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`

- [ ] **Step 1: Add signal evaluate example**

In `docs/CLI_OUTPUT_EXAMPLES.md`, add a new section after the signal snapshot section. The section should include:

1. A `### hf signal evaluate` heading
2. A JSON example showing the evaluate output with the standard envelope wrapper and a `SignalEvaluation` `data` block containing:
   - `eval_version`, `start_date`, `end_date`, `forward_days`, `trading_days_evaluated`, `symbols`
   - `ic_report` with 1-2 sample `FactorICReport` entries (with truncated `daily_ic` arrays) and a `composite` entry
   - `drift_diagnostics` with 1-2 sample `FactorDrift` entries, `coverage_drift`, and `rank_turnover`

- [ ] **Step 2: Run CLI output validation**

Run: `make validate-cli-output`
Expected: pass (new example should validate against schema; `data` is free-form in the schema)

- [ ] **Step 3: Commit**

```bash
git add docs/CLI_OUTPUT_EXAMPLES.md
git commit -m "docs(l3): add signal evaluate example to CLI_OUTPUT_EXAMPLES"
```

---

### Task 8: Final Verification

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

- [ ] **Step 5: Verify CLI help includes evaluate command**

Run: `cd cli && cargo run -- signal --help`
Expected: shows `snapshot` and `evaluate` subcommands

Run: `cd cli && cargo run -- signal evaluate --help`
Expected: shows `--start-date`, `--end-date`, `--forward-days`, `--output` flags

---

## Self-Review Checklist

1. **Spec coverage**: All 13 spec sections mapped to tasks — domain models (§9→T1), core service IC+drift (§5→T2), pydantic schemas (§8→T3), HTTP endpoint (§6→T4), architecture tests (§11.3→T5), Rust CLI (§7→T6), docs (§12 docs row→T7), verification (§13→T8). Output schema (§4) is covered by T2 implementation + T3 pydantic.

2. **Placeholder scan**: No TBD/TODO. All steps have complete code. T5 is conditional (existing tests may already cover).

3. **Type consistency**: `_compute_daily_ic` signature consistent between T2 tests and implementation. `SignalEvaluateRequest` (Python Pydantic) vs `SignalEvaluateRequest` (Rust struct) — same name, different languages. `_aggregate_ic_series` and `_compute_factor_drift` and `_kendall_tau_distance` are tested directly in T2 and used in the main service.

4. **Direction note**: `forward_days` defaults to 1 everywhere (Python service, Pydantic schema `ge=1, le=10`, Rust clap default "1", http_client JSON body).
