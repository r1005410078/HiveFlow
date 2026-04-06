# L3 Signal Phase 2b Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cross-sectional median missing-value fill and industry dummy OLS neutralization to `compute_signal_matrix()`, improving L3 signal robustness for downstream L4 optimization.

**Architecture:** Two private helper functions (`_fill_missing_cross_sectional`, `_neutralize_industry`) are inserted into the existing pipeline in `signal_engineering_service.py` after direction alignment and before zscore. A guard in `_neutralize_industry` transparently passes through values when every industry has only one symbol (current state with 5 hardcoded symbols), so existing pipeline behaviour is unchanged until the symbol universe expands.

**Tech Stack:** Python, pandas, numpy (already dependencies). All changes in `quant/` — run commands from `quant/` directory using `uv run python -m pytest`.

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `quant/src/application/signal/signal_engineering_service.py` | Add `_INDUSTRY_MAP` constant, `_fill_missing_cross_sectional()`, `_neutralize_industry()`, wire both into `compute_signal_matrix()`, add `fill_count` to `transform_stats` |
| Modify | `quant/tests/unit/signal/test_signal_engineering.py` | Add 6 new tests for fill, neutralize, and end-to-end behaviour |

No other files change.

---

## Task 1: `_fill_missing_cross_sectional()` helper

**Files:**
- Modify: `quant/src/application/signal/signal_engineering_service.py`
- Test: `quant/tests/unit/signal/test_signal_engineering.py`

### Context

`signal_engineering_service.py` currently starts at line 1 with `from __future__ import annotations`. The module-level constants `_SIGNAL_VERSION` and `_BENCHMARK_SYMBOL` are defined at lines 18–19. New constants and helpers go directly below them.

The test file `quant/tests/unit/signal/test_signal_engineering.py` already has 8 passing tests. Append new tests at the bottom.

- [ ] **Step 1: Write the two failing tests**

Append to `quant/tests/unit/signal/test_signal_engineering.py`:

```python
def test_fill_missing_uses_cross_sectional_median():
    import math
    import pandas as pd
    from application.signal.signal_engineering_service import _fill_missing_cross_sectional

    wide = pd.DataFrame(
        {"factor_a": [1.0, 2.0, float("nan"), 4.0], "factor_b": [10.0, 20.0, 30.0, 40.0]},
        index=["A", "B", "C", "D"],
    )
    filled, counts = _fill_missing_cross_sectional(wide)

    # median of [1.0, 2.0, 4.0] = 2.0
    assert filled.loc["C", "factor_a"] == 2.0
    assert counts["factor_a"] == 1
    assert counts["factor_b"] == 0
    assert filled.loc["A", "factor_a"] == 1.0  # unchanged


def test_fill_missing_all_nan_column_stays_nan():
    import math
    import pandas as pd
    from application.signal.signal_engineering_service import _fill_missing_cross_sectional

    wide = pd.DataFrame(
        {"factor_a": [float("nan"), float("nan")]},
        index=["A", "B"],
    )
    filled, counts = _fill_missing_cross_sectional(wide)

    assert math.isnan(filled.loc["A", "factor_a"])
    assert math.isnan(filled.loc["B", "factor_a"])
    assert counts["factor_a"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py::test_fill_missing_uses_cross_sectional_median tests/unit/signal/test_signal_engineering.py::test_fill_missing_all_nan_column_stays_nan -v
```

Expected: FAIL with `ImportError: cannot import name '_fill_missing_cross_sectional'`

- [ ] **Step 3: Add `_INDUSTRY_MAP` constant and `_fill_missing_cross_sectional()` to the service**

In `quant/src/application/signal/signal_engineering_service.py`, add after line 19 (after `_BENCHMARK_SYMBOL = "000300.SH"`):

```python
_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}


def _fill_missing_cross_sectional(
    wide: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """对每个因子列，用该列横截面中位数填补 NaN。
    返回 (填补后 DataFrame, {factor_name: fill_count})。
    """
    filled = wide.copy()
    fill_counts: dict[str, int] = {}
    for col in filled.columns:
        n_missing = int(filled[col].isna().sum())
        if n_missing > 0:
            median = filled[col].median()  # skipna=True by default
            filled[col] = filled[col].fillna(median)
        fill_counts[col] = n_missing
    return filled, fill_counts
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py::test_fill_missing_uses_cross_sectional_median tests/unit/signal/test_signal_engineering.py::test_fill_missing_all_nan_column_stays_nan -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/signal/signal_engineering_service.py quant/tests/unit/signal/test_signal_engineering.py
git commit -m "feat(l3): add _fill_missing_cross_sectional helper with cross-sectional median fill"
```

---

## Task 2: `_neutralize_industry()` helper

**Files:**
- Modify: `quant/src/application/signal/signal_engineering_service.py`
- Test: `quant/tests/unit/signal/test_signal_engineering.py`

### Context

`_neutralize_industry` goes directly after `_fill_missing_cross_sectional` in the service file. It uses `np` (already imported at line 8) and `pd` (already imported at line 9). The `Counter` import is done locally inside the function to avoid polluting the module-level imports.

- [ ] **Step 1: Write the two failing tests**

Append to `quant/tests/unit/signal/test_signal_engineering.py`:

```python
def test_neutralize_skips_when_one_symbol_per_industry():
    import pandas as pd
    from application.signal.signal_engineering_service import _neutralize_industry

    industry_map = {"A": "tech", "B": "finance", "C": "energy"}
    wide = pd.DataFrame({"factor_a": [1.0, 2.0, 3.0]}, index=["A", "B", "C"])

    result = _neutralize_industry(wide, industry_map)

    # Every industry has exactly 1 symbol → guard fires → return original values
    pd.testing.assert_frame_equal(result, wide)


def test_neutralize_removes_industry_mean_with_multi_symbol():
    import pandas as pd
    from application.signal.signal_engineering_service import _neutralize_industry

    # A and B share "tech" industry; C is alone in "finance"
    industry_map = {"A": "tech", "B": "tech", "C": "finance"}
    wide = pd.DataFrame({"factor_a": [3.0, 1.0, 5.0]}, index=["A", "B", "C"])

    result = _neutralize_industry(wide, industry_map)

    # Within "tech": A=3, B=1, industry mean=2 → residuals A=+1, B=-1, sum=0
    residual_sum = result.loc["A", "factor_a"] + result.loc["B", "factor_a"]
    assert abs(residual_sum) < 1e-9, f"industry residuals must sum to 0, got {residual_sum}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py::test_neutralize_skips_when_one_symbol_per_industry tests/unit/signal/test_signal_engineering.py::test_neutralize_removes_industry_mean_with_multi_symbol -v
```

Expected: FAIL with `ImportError: cannot import name '_neutralize_industry'`

- [ ] **Step 3: Add `_neutralize_industry()` to the service**

In `quant/src/application/signal/signal_engineering_service.py`, add directly after `_fill_missing_cross_sectional`:

```python
def _neutralize_industry(
    wide: pd.DataFrame,
    industry_map: dict[str, str],
) -> pd.DataFrame:
    """对每个因子列做行业哑变量 OLS 回归，返回残差矩阵。
    若标的不在 industry_map 中，归入 'other'。
    当每个行业只有 1 只标的时（守卫条件），直接透传原值。
    """
    from collections import Counter
    symbols = wide.index.tolist()
    industries = [industry_map.get(s, "other") for s in symbols]
    industry_counts = Counter(industries)

    # Guard: every industry has exactly 1 symbol → OLS residuals would be zero
    if max(industry_counts.values()) < 2:
        return wide.copy()

    X = pd.get_dummies(industries, dtype=float).values  # shape (n_symbols, n_industries)
    residuals = wide.copy()
    for col in wide.columns:
        y = wide[col].values.reshape(-1, 1)
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        residuals[col] = (y - X @ beta).flatten()
    return residuals
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py::test_neutralize_skips_when_one_symbol_per_industry tests/unit/signal/test_signal_engineering.py::test_neutralize_removes_industry_mean_with_multi_symbol -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/signal/signal_engineering_service.py quant/tests/unit/signal/test_signal_engineering.py
git commit -m "feat(l3): add _neutralize_industry helper with OLS industry dummy neutralization"
```

---

## Task 3: Wire both steps into `compute_signal_matrix()`

**Files:**
- Modify: `quant/src/application/signal/signal_engineering_service.py`
- Test: `quant/tests/unit/signal/test_signal_engineering.py`

### Context

Inside `compute_signal_matrix()`, after direction alignment (lines 67–69) and before `signal_wide = pd.DataFrame(index=wide.index)` (line 71), insert the fill + neutralize calls. In the per-factor loop (lines 74–94), switch from `wide[fn]` to `neutral_wide[fn]` for zscore input while keeping `wide[fn]` for `pre_stats` (raw values) and `raw_val` (signal_rows). Add `fill_count` to each `transform_stats` entry.

Current lines 67–94 (the section to replace):

```python
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
            post_stats = _series_stats(signal_col)
            non_nan_raw = col.dropna()
            if len(non_nan_raw) > 0:
                post_stats["count"] = int(len(non_nan_raw))
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
```

- [ ] **Step 1: Write the two failing end-to-end tests**

Append to `quant/tests/unit/signal/test_signal_engineering.py`:

```python
def test_compute_signal_matrix_fill_count_in_transform_stats():
    """transform_stats entries must include fill_count when a value is missing."""
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"symbol": sym, "factor_name": "f1", "factor_version": "v1",
         "raw_value": float("nan") if sym == "C" else float(i + 1),
         "direction": 1, "unit": "ratio", "missing_strategy": "none", "source": "real"}
        for i, sym in enumerate(["A", "B", "C", "D", "E"])
    ]
    snapshot = {"rows": rows, "factor_names": ["f1"], "coverage_rate": 0.8}
    result = compute_signal_matrix(snapshot)

    ts = result["transform_stats"][0]
    assert "fill_count" in ts, "fill_count must be present in transform_stats entry"
    assert ts["fill_count"] == 1, f"expected 1 fill, got {ts['fill_count']}"


def test_compute_signal_matrix_end_to_end_no_nan_composite():
    """When a factor value is missing, fill restores coverage so composite_score is not NaN."""
    import math
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"symbol": sym, "factor_name": "f1", "factor_version": "v1",
         "raw_value": float("nan") if sym == "C" else float(i + 1),
         "direction": 1, "unit": "ratio", "missing_strategy": "none", "source": "real"}
        for i, sym in enumerate(["A", "B", "C", "D", "E"])
    ]
    snapshot = {"rows": rows, "factor_names": ["f1"], "coverage_rate": 0.8}
    result = compute_signal_matrix(snapshot)

    for cs in result["composite_scores"]:
        assert not math.isnan(cs["composite_score"]), (
            f"{cs['symbol']} composite_score is NaN after fill should have restored it"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py::test_compute_signal_matrix_fill_count_in_transform_stats tests/unit/signal/test_signal_engineering.py::test_compute_signal_matrix_end_to_end_no_nan_composite -v
```

Expected: FAIL — `test_fill_count` fails with `KeyError: 'fill_count'`; `test_no_nan_composite` fails because `C` has NaN composite_score

- [ ] **Step 3: Replace the direction-align + zscore block in `compute_signal_matrix()`**

In `quant/src/application/signal/signal_engineering_service.py`, replace this exact block:

```python
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
            post_stats = _series_stats(signal_col)
            non_nan_raw = col.dropna()
            if len(non_nan_raw) > 0:
                post_stats["count"] = int(len(non_nan_raw))
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
```

With this updated block:

```python
    for fn in active_factors:
        if direction_map.get(fn, 1) == -1:
            wide[fn] = wide[fn] * -1

    # Phase 2b: fill missing values then neutralize industry exposure
    filled_wide, fill_counts = _fill_missing_cross_sectional(wide[active_factors])
    neutral_wide = _neutralize_industry(filled_wide, _INDUSTRY_MAP)

    signal_wide = pd.DataFrame(index=wide.index)
    transform_stats: list[dict] = []

    for fn in active_factors:
        col = neutral_wide[fn]                  # zscore input: neutralized values
        pre_stats = _series_stats(wide[fn])     # pre-stats: original direction-aligned raw values

        if col.dropna().nunique() <= 1:
            signal_col = pd.Series(np.nan, index=col.index)
            post_stats = _series_stats(signal_col)
            non_nan_raw = col.dropna()
            if len(non_nan_raw) > 0:
                post_stats["count"] = int(len(non_nan_raw))
        else:
            signal_col = winsorize_then_zscore(col.dropna())
            signal_col = signal_col.reindex(col.index)
            post_stats = _series_stats(signal_col)
        signal_wide[fn] = signal_col

        transform_stats.append({
            "factor_name": fn,
            "fill_count": fill_counts.get(fn, 0),
            "pre_winsorize": pre_stats,
            "post_zscore": post_stats,
        })
```

- [ ] **Step 4: Run all signal engineering tests**

```bash
cd quant && uv run python -m pytest tests/unit/signal/test_signal_engineering.py -v
```

Expected: all tests pass (original 8 + 6 new = 14 total)

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/signal/signal_engineering_service.py quant/tests/unit/signal/test_signal_engineering.py
git commit -m "feat(l3): wire fill_missing + neutralize_industry into compute_signal_matrix"
```

---

## Task 4: Final CI gate

**Files:** none (validation only)

- [ ] **Step 1: Run the full CI check**

```bash
cd /Users/rongts/HiveFlow && make check
```

Expected output ends with: `All checks passed!`

If `ruff` reports unused imports or other lint issues, fix them and re-run `make check` before committing.

- [ ] **Step 2: If lint fix needed, commit the fix**

```bash
git add quant/src/application/signal/signal_engineering_service.py
git commit -m "fix(l3): address lint issues from make check"
```

- [ ] **Step 3: Update AGENTS.md completion table**

In `AGENTS.md`, find the L3 row in the §7.8 completion table and update it:

```
| L3 | 信号工程 | ✅ Phase 2b 完成 | Phase 1: winsorize+zscore+等权 composite、signal_matrix、snapshot CLI；Phase 2a: Rank IC（per-factor+composite）、信号分布漂移检测、`POST /api/v1/signal/evaluate` + `hf signal evaluate`；Phase 2b: 横截面中位数缺失值填补 + 行业哑变量 OLS 中性化框架（守卫：单行业单标的时透传） |
```

Also update `当前工作位置` to:

```
**当前工作位置**：L3 Phase 2b（缺失值填补 + 行业中性化框架）已合入 master → L5 风险门控待 spec；或扩展标的池使行业中性化生效待 spec。
```

- [ ] **Step 4: Commit docs update**

```bash
git add AGENTS.md
git commit -m "docs(l3): update AGENTS.md L3 Phase 2b completion status"
```
