# L4 Portfolio Optimization Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement L4 portfolio optimization (cvxpy QP) with standalone CLI command and daily pipeline integration, connecting L3 signals to target weights.

**Architecture:** Three-service split: `covariance_service` computes Σ from bars, `optimizer_service` solves cvxpy QP, `portfolio_optimize_service` orchestrates both. HTTP route + Rust CLI mirror the existing signal evaluate pattern.

**Tech Stack:** Python (cvxpy, pandas, numpy), Rust (clap, reqwest, comfy_table), FastAPI

---

## File Map

**Create:**
- `quant/src/domain/models/portfolio.py`
- `quant/src/application/portfolio/__init__.py`
- `quant/src/application/portfolio/covariance_service.py`
- `quant/src/application/portfolio/optimizer_service.py`
- `quant/src/application/portfolio/portfolio_optimize_service.py`
- `quant/src/interfaces/http/routes_portfolio.py`
- `quant/tests/unit/portfolio/test_covariance_service.py`
- `quant/tests/unit/portfolio/test_optimizer_service.py`
- `quant/tests/unit/portfolio/test_portfolio_optimize_service.py`
- `quant/tests/fixtures/cli_output/valid/portfolio_optimize_ok.json`
- `cli/src/cmd/portfolio.rs`
- `cli/src/application/handlers/portfolio_optimize.rs`

**Modify:**
- `quant/pyproject.toml` — add cvxpy
- `quant/src/interfaces/http/schemas.py` — add Portfolio* Pydantic models
- `quant/src/interfaces/http/dependencies.py` — add get_portfolio_optimize_service
- `quant/src/interfaces/http/app.py` — register portfolio router
- `quant/src/application/daily_run_service.py` — add L4 step after signal_matrix
- `quant/tests/architecture/test_layering_rules.py` — add portfolio rules
- `cli/src/application/requests.rs` — add PortfolioOptimizeRequest + AppCommand variant
- `cli/src/application/dispatch.rs` — add PortfolioOptimize arm
- `cli/src/application/handlers/mod.rs` — add portfolio_optimize module
- `cli/src/cmd/mod.rs` — add Portfolio to Commands
- `cli/src/infrastructure/http_client.rs` — add post_portfolio_optimize
- `cli/src/infrastructure/table_renderer.rs` — add render_portfolio_optimize_table
- `cli/tests/architecture_rules.rs` — add cmd/portfolio.rs to cmd_layer check
- `docs/CLI_OUTPUT_EXAMPLES.md` — add portfolio optimize example
- `AGENTS.md` — update §7.6, §7.8, §7.9

---

### Task 1: Add cvxpy dependency

**Files:**
- Modify: `quant/pyproject.toml`

- [ ] **Step 1: Add cvxpy to dependencies**

Edit `quant/pyproject.toml`, add `"cvxpy>=1.4.0"` to the `dependencies` list:

```toml
dependencies = [
    "akshare>=1.15.0",
    "cvxpy>=1.4.0",
    "fastapi>=0.115.0",
    "httpx>=0.28.0",
    "pandas>=2.2.0",
    "psycopg[binary]>=3.2.0",
    "pyarrow>=16.0.0",
    "pytest>=8.3.0",
    "ruff>=0.6.0",
    "scipy>=1.17.1",
    "uvicorn>=0.32.0",
]
```

- [ ] **Step 2: Sync dependencies**

```bash
cd quant && uv sync
```

Expected: cvxpy and its dependencies (CLARABEL, etc.) installed, no errors.

- [ ] **Step 3: Verify import**

```bash
cd quant && uv run python -c "import cvxpy; print(cvxpy.__version__)"
```

Expected: prints version string like `1.6.x`

- [ ] **Step 4: Commit**

```bash
git add quant/pyproject.toml quant/uv.lock
git commit -m "chore(l4): add cvxpy dependency for QP portfolio optimization"
```

---

### Task 2: Domain model

**Files:**
- Create: `quant/src/domain/models/portfolio.py`

- [ ] **Step 1: Write domain dataclasses**

Create `quant/src/domain/models/portfolio.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetWeightRow:
    symbol: str
    weight: float
    prev_weight: float
    delta: float


@dataclass(frozen=True)
class OptimizationReport:
    objective_value: float
    risk_contribution: float
    turnover_cost: float
    solver: str
    solve_time_ms: int


@dataclass(frozen=True)
class PortfolioOptimizationResult:
    as_of: str
    optimize_version: str
    optimization_status: str  # optimal|optimal_inaccurate|fallback_equal_weight|fallback_prev_weight
    fallback_reason: str | None
    target_weights: tuple[TargetWeightRow, ...]
    optimization_report: OptimizationReport
```

- [ ] **Step 2: Verify import**

```bash
cd quant && uv run python -c "from domain.models.portfolio import PortfolioOptimizationResult; print('ok')"
```

Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add quant/src/domain/models/portfolio.py
git commit -m "feat(l4): add PortfolioOptimizationResult domain model"
```

---

### Task 3: Covariance service + tests

**Files:**
- Create: `quant/src/application/portfolio/__init__.py`
- Create: `quant/src/application/portfolio/covariance_service.py`
- Create: `quant/tests/unit/portfolio/test_covariance_service.py`

- [ ] **Step 1: Write failing tests**

Create `quant/tests/unit/portfolio/__init__.py` (empty file).

Create `quant/tests/unit/portfolio/test_covariance_service.py`:

```python
from __future__ import annotations
import math
import pandas as pd


def _make_bar_store(rows: list[dict]):
    class _MockBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return [r for r in rows if r["symbol"] in symbols]
    return _MockBarStore()


def test_covariance_matrix_shape():
    """Returns square DataFrame with symbols as index and columns."""
    from application.portfolio.covariance_service import compute_covariance_matrix

    symbols = ["A", "B"]
    rows = []
    for i, sym in enumerate(["A", "B"]):
        for d in range(25):
            rows.append({
                "symbol": sym,
                "bar_time": f"2026-01-{d+1:02d}T15:00:00+08:00",
                "close": 100.0 + i * 10 + d * 0.5,
            })
    bar_store = _make_bar_store(rows)
    cov = compute_covariance_matrix(symbols=symbols, as_of="2026-02-01", bar_store=bar_store)

    assert isinstance(cov, pd.DataFrame)
    assert list(cov.index) == symbols
    assert list(cov.columns) == symbols
    assert cov.loc["A", "A"] > 0
    assert cov.loc["B", "B"] > 0


def test_covariance_diagonal_fallback_when_insufficient_data():
    """When a symbol has <20 valid bars, its off-diagonals are zero and diagonal is default."""
    from application.portfolio.covariance_service import compute_covariance_matrix

    symbols = ["A", "B"]
    # Only 5 bars for A — below the 20-bar minimum
    rows = [
        {"symbol": "A", "bar_time": f"2026-01-{d+1:02d}T15:00:00+08:00", "close": 100.0 + d}
        for d in range(5)
    ]
    bar_store = _make_bar_store(rows)
    cov = compute_covariance_matrix(symbols=symbols, as_of="2026-02-01", bar_store=bar_store)

    # Off-diagonal involving A must be 0
    assert cov.loc["A", "B"] == 0.0
    assert cov.loc["B", "A"] == 0.0
    # Diagonal of A must be positive (default var)
    assert cov.loc["A", "A"] > 0


def test_covariance_empty_bars_returns_diagonal():
    """When bar_store returns no rows, returns diagonal matrix with default variance."""
    from application.portfolio.covariance_service import compute_covariance_matrix

    symbols = ["A", "B", "C"]
    bar_store = _make_bar_store([])
    cov = compute_covariance_matrix(symbols=symbols, as_of="2026-02-01", bar_store=bar_store)

    assert cov.shape == (3, 3)
    assert cov.loc["A", "B"] == 0.0
    for s in symbols:
        assert cov.loc[s, s] > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd quant && uv run python -m pytest tests/unit/portfolio/test_covariance_service.py -v
```

Expected: FAIL with `ModuleNotFoundError` or similar (service not yet implemented)

- [ ] **Step 3: Create `__init__.py` for application/portfolio**

Create `quant/src/application/portfolio/__init__.py` (empty).

- [ ] **Step 4: Implement covariance_service**

Create `quant/src/application/portfolio/covariance_service.py`:

```python
from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

_MIN_VALID_BARS = 20
_DEFAULT_ANNUAL_VAR = 0.04  # fallback: ~20% annual vol on the diagonal

_logger = logging.getLogger(__name__)


def compute_covariance_matrix(
    symbols: list[str],
    as_of: str,
    bar_store,
    lookback_days: int = 60,
) -> pd.DataFrame:
    """Return annualised sample covariance matrix (symbols x symbols).

    Symbols with fewer than _MIN_VALID_BARS daily returns are treated as
    independent with diagonal variance equal to the mean of all valid symbols,
    and off-diagonal entries set to 0.
    """
    start_date = (date.fromisoformat(as_of) - timedelta(days=lookback_days)).isoformat()
    rows = bar_store.list_bars(
        symbols=symbols,
        timeframe="1d",
        start_date=start_date,
        end_date=as_of,
        limit=lookback_days + 20,
    )
    n = len(symbols)
    if not rows:
        return pd.DataFrame(
            _DEFAULT_ANNUAL_VAR * np.eye(n), index=symbols, columns=symbols,
        )

    df = pd.DataFrame(rows)
    df["_date"] = pd.to_datetime(df["bar_time"]).dt.date
    pivot = (
        df.pivot_table(index="_date", columns="symbol", values="close", aggfunc="last")
        .sort_index()
    )
    returns = pivot.pct_change().iloc[1:]  # drop first NaN row after pct_change

    # Determine which symbols have enough valid returns
    valid: dict[str, bool] = {
        s: (s in returns.columns and int(returns[s].dropna().shape[0]) >= _MIN_VALID_BARS)
        for s in symbols
    }
    valid_symbols = [s for s in symbols if valid[s]]

    if valid_symbols:
        annual_cov = returns[valid_symbols].cov() * 252
        diag_vals = [float(annual_cov.loc[s, s]) for s in valid_symbols]
        default_var = float(np.mean(diag_vals)) if diag_vals else _DEFAULT_ANNUAL_VAR
    else:
        annual_cov = pd.DataFrame()
        default_var = _DEFAULT_ANNUAL_VAR

    result = pd.DataFrame(0.0, index=symbols, columns=symbols)
    for i, s in enumerate(symbols):
        for j, t in enumerate(symbols):
            if valid[s] and valid[t] and s in annual_cov.index and t in annual_cov.columns:
                result.loc[s, t] = float(annual_cov.loc[s, t])
            elif i == j:
                result.loc[s, t] = default_var

    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd quant && uv run python -m pytest tests/unit/portfolio/test_covariance_service.py -v
```

Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add quant/src/application/portfolio/__init__.py \
        quant/src/application/portfolio/covariance_service.py \
        quant/tests/unit/portfolio/__init__.py \
        quant/tests/unit/portfolio/test_covariance_service.py
git commit -m "feat(l4): add covariance_service with 60-day annualised Sigma + unit tests"
```

---

### Task 4: Optimizer service + tests

**Files:**
- Create: `quant/src/application/portfolio/optimizer_service.py`
- Create (extend): `quant/tests/unit/portfolio/test_optimizer_service.py`

- [ ] **Step 1: Write failing tests**

Create `quant/tests/unit/portfolio/test_optimizer_service.py`:

```python
from __future__ import annotations
import math
import numpy as np
import pandas as pd


def _cov_2x2(symbols: list[str], var: float = 0.04, corr: float = 0.3) -> pd.DataFrame:
    cov = pd.DataFrame(index=symbols, columns=symbols, dtype=float)
    for i, s in enumerate(symbols):
        for j, t in enumerate(symbols):
            cov.loc[s, t] = var if i == j else corr * var
    return cov


def test_weights_sum_to_one():
    """Target weights must sum to 1."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {s: float(i + 1) for i, s in enumerate(symbols)}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={})

    weights = [row["weight"] for row in result["target_weights"]]
    assert abs(sum(weights) - 1.0) < 1e-4


def test_single_asset_cap():
    """No individual weight may exceed w_max."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {"A": 10.0, "B": 0.1, "C": 0.1, "D": 0.1, "E": 0.1}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={}, w_max=0.30)

    for row in result["target_weights"]:
        assert row["weight"] <= 0.30 + 1e-4, f"{row['symbol']} weight {row['weight']} > 0.30"


def test_industry_constraint():
    """Sum of weights in one industry must not exceed ind_max."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C"]
    # A and B are in the same industry
    industry_map = {"A": "tech", "B": "tech", "C": "finance"}
    alpha = {"A": 5.0, "B": 4.0, "C": 1.0}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(
        alpha=alpha, cov_matrix=cov, prev_weights={},
        ind_max=0.60, industry_map=industry_map,
    )

    w = {row["symbol"]: row["weight"] for row in result["target_weights"]}
    assert w["A"] + w["B"] <= 0.60 + 1e-4


def test_fallback_equal_weight_when_infeasible():
    """When problem is infeasible and prev_weights are all zero, return equal weights."""
    from application.portfolio.optimizer_service import solve_portfolio

    # w_max=0.10 with 5 symbols: 5 * 0.10 = 0.50 < 1.0  →  infeasible
    symbols = ["A", "B", "C", "D", "E"]
    alpha = {s: 1.0 for s in symbols}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={}, w_max=0.10)

    assert result["optimization_status"] == "fallback_equal_weight"
    weights = [row["weight"] for row in result["target_weights"]]
    for w in weights:
        assert abs(w - 0.20) < 1e-6


def test_fallback_prev_weight_when_infeasible_with_prev():
    """When infeasible and prev_weights non-zero, return normalised prev weights."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {s: 1.0 for s in symbols}
    cov = _cov_2x2(symbols)
    prev = {"A": 0.3, "B": 0.3, "C": 0.2, "D": 0.1, "E": 0.1}
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights=prev, w_max=0.10)

    assert result["optimization_status"] == "fallback_prev_weight"
    w = {row["symbol"]: row["weight"] for row in result["target_weights"]}
    assert abs(w["A"] - 0.30) < 1e-6
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_no_short_selling():
    """All weights must be non-negative."""
    from application.portfolio.optimizer_service import solve_portfolio

    symbols = ["A", "B", "C", "D", "E"]
    alpha = {"A": -5.0, "B": 0.1, "C": 0.1, "D": 0.1, "E": 0.1}
    cov = _cov_2x2(symbols)
    result = solve_portfolio(alpha=alpha, cov_matrix=cov, prev_weights={})

    for row in result["target_weights"]:
        assert row["weight"] >= -1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd quant && uv run python -m pytest tests/unit/portfolio/test_optimizer_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement optimizer_service**

Create `quant/src/application/portfolio/optimizer_service.py`:

```python
from __future__ import annotations

import logging
import time

import cvxpy as cp
import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)

_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}


def solve_portfolio(
    alpha: dict[str, float],
    cov_matrix: pd.DataFrame,
    prev_weights: dict[str, float],
    lambda_risk: float = 1.0,
    lambda_tc: float = 0.001,
    w_max: float = 0.30,
    ind_max: float = 0.40,
    industry_map: dict[str, str] | None = None,
) -> dict:
    """Solve mean-variance QP with turnover penalty.

    Returns dict with keys: optimization_status, fallback_reason,
    target_weights (list of dicts), optimization_report (dict).
    """
    symbols = list(alpha.keys())
    n = len(symbols)
    imap = industry_map if industry_map is not None else _INDUSTRY_MAP

    alpha_vec = np.array([alpha[s] for s in symbols], dtype=float)
    Sigma = cov_matrix.reindex(index=symbols, columns=symbols).fillna(0.0).values.astype(float)
    w_prev_vec = np.array([prev_weights.get(s, 0.0) for s in symbols], dtype=float)

    # Group symbols by industry for industry constraints
    industry_groups: dict[str, list[int]] = {}
    for i, s in enumerate(symbols):
        ind = imap.get(s, "other")
        industry_groups.setdefault(ind, []).append(i)

    w = cp.Variable(n)
    t = cp.Variable(n)  # auxiliary for |w - w_prev| linearisation

    objective = cp.Maximize(
        alpha_vec @ w
        - lambda_risk * cp.quad_form(w, Sigma)
        - lambda_tc * cp.sum(t)
    )

    constraints: list = [
        cp.sum(w) == 1,
        w >= 0,
        w <= w_max,
        t >= w - w_prev_vec,
        t >= w_prev_vec - w,
        t >= 0,
    ]
    for idxs in industry_groups.values():
        if len(idxs) > 1:
            constraints.append(cp.sum(w[idxs]) <= ind_max)

    prob = cp.Problem(objective, constraints)
    t0 = time.perf_counter()
    try:
        prob.solve(solver=cp.CLARABEL)
    except Exception as exc:
        _logger.warning("cvxpy solve raised exception: %s", exc)
        prob._status = "solver_error"  # noqa: SLF001
    solve_time_ms = max(1, int((time.perf_counter() - t0) * 1000))

    is_ok = prob.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)

    if is_ok:
        w_val = np.clip(w.value, 0.0, 1.0)
        w_total = float(w_val.sum())
        w_val = w_val / w_total if w_total > 1e-9 else np.ones(n) / n
        opt_status = "optimal" if prob.status == cp.OPTIMAL else "optimal_inaccurate"
        target_weights = [
            {
                "symbol": symbols[i],
                "weight": round(float(w_val[i]), 6),
                "prev_weight": round(float(w_prev_vec[i]), 6),
                "delta": round(float(w_val[i] - w_prev_vec[i]), 6),
            }
            for i in range(n)
        ]
        risk_contrib = round(float(w_val @ Sigma @ w_val), 6)
        turnover_cost = round(float(np.sum(np.abs(w_val - w_prev_vec))) * lambda_tc, 6)
        report = {
            "objective_value": round(float(prob.value) if prob.value is not None else 0.0, 6),
            "risk_contribution": risk_contrib,
            "turnover_cost": turnover_cost,
            "solver": "CLARABEL",
            "solve_time_ms": solve_time_ms,
        }
        return {
            "optimization_status": opt_status,
            "fallback_reason": None,
            "target_weights": target_weights,
            "optimization_report": report,
        }

    # Fallback
    fallback_reason = str(prob.status)
    prev_total = float(w_prev_vec.sum())
    if prev_total < 1e-9:
        w_fb = np.ones(n) / n
        opt_status = "fallback_equal_weight"
    else:
        w_fb = w_prev_vec / prev_total
        opt_status = "fallback_prev_weight"

    target_weights = [
        {
            "symbol": symbols[i],
            "weight": round(float(w_fb[i]), 6),
            "prev_weight": round(float(w_prev_vec[i]), 6),
            "delta": round(float(w_fb[i] - w_prev_vec[i]), 6),
        }
        for i in range(n)
    ]
    report = {
        "objective_value": 0.0,
        "risk_contribution": 0.0,
        "turnover_cost": 0.0,
        "solver": "CLARABEL",
        "solve_time_ms": solve_time_ms,
    }
    return {
        "optimization_status": opt_status,
        "fallback_reason": fallback_reason,
        "target_weights": target_weights,
        "optimization_report": report,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd quant && uv run python -m pytest tests/unit/portfolio/test_optimizer_service.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/portfolio/optimizer_service.py \
        quant/tests/unit/portfolio/test_optimizer_service.py
git commit -m "feat(l4): add optimizer_service (cvxpy QP + fallback) with unit tests"
```

---

### Task 5: Portfolio optimize service + tests

**Files:**
- Create: `quant/src/application/portfolio/portfolio_optimize_service.py`
- Create: `quant/tests/unit/portfolio/test_portfolio_optimize_service.py`

- [ ] **Step 1: Write failing tests**

Create `quant/tests/unit/portfolio/test_portfolio_optimize_service.py`:

```python
from __future__ import annotations
import math


def _make_bar_store_with_25_bars():
    """Bar store with 25 bars per symbol — enough for covariance."""
    symbols = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"]
    rows = []
    for i, sym in enumerate(symbols):
        for d in range(25):
            rows.append({
                "symbol": sym,
                "bar_time": f"2026-01-{d+1:02d}T15:00:00+08:00",
                "close": 100.0 + i * 5 + d * 0.3,
            })

    class _MockBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return [r for r in rows if r["symbol"] in symbols]

    return _MockBarStore()


def test_run_portfolio_optimize_returns_valid_schema():
    """Output must conform to CLI envelope and target_weights must sum to 1."""
    from application.portfolio.portfolio_optimize_service import run_portfolio_optimize

    bar_store = _make_bar_store_with_25_bars()
    alpha = {
        "000001.SZ": 0.5,
        "600519.SH": 1.2,
        "300750.SZ": 0.9,
        "601318.SH": 0.7,
        "000333.SZ": 0.3,
    }
    result = run_portfolio_optimize(as_of="2026-02-01", alpha=alpha, bar_store=bar_store)

    assert result["schema_version"] == "1.0.0"
    assert result["command"] == "hf portfolio optimize"
    assert result["source"] == "system"
    assert result["advice_only"] is False
    assert result["decision_weight"] == 1
    assert "data" in result

    data = result["data"]
    assert data["as_of"] == "2026-02-01"
    assert data["optimization_status"] in (
        "optimal", "optimal_inaccurate", "fallback_equal_weight", "fallback_prev_weight"
    )
    weights = [row["weight"] for row in data["target_weights"]]
    assert abs(sum(weights) - 1.0) < 1e-4


def test_fallback_produces_warning_status():
    """When solver fallback occurs, CLI envelope status must be 'warning'."""
    from application.portfolio.portfolio_optimize_service import run_portfolio_optimize

    # w_max=0.05 makes problem infeasible for 5 symbols  (5 * 0.05 = 0.25 < 1)
    alpha = {
        "000001.SZ": 1.0, "600519.SH": 1.0, "300750.SZ": 1.0,
        "601318.SH": 1.0, "000333.SZ": 1.0,
    }
    result = run_portfolio_optimize(as_of="2026-02-01", alpha=alpha, w_max=0.05)

    assert result["status"] == "warning"
    assert result["data"]["optimization_status"] == "fallback_equal_weight"
    assert any(w["code"] == "PORTFOLIO_OPTIMIZATION_FALLBACK" for w in result["warnings"])


def test_alpha_defaults_from_l3_when_not_provided():
    """When alpha is None, service must derive it from L3 signal snapshot."""
    from application.portfolio.portfolio_optimize_service import run_portfolio_optimize

    # Without bar_store, signal snapshot uses deterministic factor snapshot
    result = run_portfolio_optimize(as_of="2026-02-01", alpha=None)

    data = result["data"]
    assert len(data["target_weights"]) > 0
    weights = [row["weight"] for row in data["target_weights"]]
    assert abs(sum(weights) - 1.0) < 1e-4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd quant && uv run python -m pytest tests/unit/portfolio/test_portfolio_optimize_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement portfolio_optimize_service**

Create `quant/src/application/portfolio/portfolio_optimize_service.py`:

```python
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd

from application.contracts.cli_output import ok_output
from application.portfolio.covariance_service import compute_covariance_matrix
from application.portfolio.optimizer_service import solve_portfolio
from application.signal.signal_engineering_service import run_signal_snapshot

_OPTIMIZE_VERSION = "l4-optimize-v1.0"
_DEFAULT_SYMBOLS = [
    "000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ",
]
_DIAGONAL_VAR = 0.04  # fallback annual variance when bar_store unavailable

_logger = logging.getLogger(__name__)


def run_portfolio_optimize(
    as_of: str,
    alpha: dict[str, float] | None = None,
    prev_weights: dict[str, float] | None = None,
    lambda_risk: float = 1.0,
    lambda_tc: float = 0.001,
    w_max: float = 0.30,
    ind_max: float = 0.40,
    lookback_days: int = 60,
    bar_store=None,
) -> dict:
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"

    if alpha is None:
        snapshot = run_signal_snapshot(as_of=as_of, bar_store=bar_store)
        composite_scores = snapshot.get("data", {}).get("composite_scores", [])
        alpha = {
            cs["symbol"]: float(cs["composite_score"])
            for cs in composite_scores
            if not math.isnan(float(cs["composite_score"]))
        }
        if not alpha:
            alpha = {s: 1.0 for s in _DEFAULT_SYMBOLS}

    symbols = list(alpha.keys())
    prev_w = prev_weights or {}

    cov_matrix: pd.DataFrame | None = None
    if bar_store is not None:
        try:
            cov_matrix = compute_covariance_matrix(
                symbols=symbols,
                as_of=as_of,
                bar_store=bar_store,
                lookback_days=lookback_days,
            )
        except Exception:
            _logger.warning(
                "portfolio optimize: covariance computation failed, using diagonal",
                exc_info=True,
            )

    if cov_matrix is None:
        n = len(symbols)
        cov_matrix = pd.DataFrame(
            _DIAGONAL_VAR * np.eye(n), index=symbols, columns=symbols,
        )

    result = solve_portfolio(
        alpha=alpha,
        cov_matrix=cov_matrix,
        prev_weights=prev_w,
        lambda_risk=lambda_risk,
        lambda_tc=lambda_tc,
        w_max=w_max,
        ind_max=ind_max,
    )

    is_fallback = result["optimization_status"].startswith("fallback")
    warnings: list[dict] = []
    if is_fallback:
        warnings.append({
            "code": "PORTFOLIO_OPTIMIZATION_FALLBACK",
            "message": f"Optimizer fallback ({result['optimization_status']}): {result['fallback_reason']}",
        })

    data = {
        "as_of": as_of,
        "optimize_version": _OPTIMIZE_VERSION,
        "optimization_status": result["optimization_status"],
        "fallback_reason": result["fallback_reason"],
        "target_weights": result["target_weights"],
        "optimization_report": result["optimization_report"],
    }

    output = ok_output(
        command="hf portfolio optimize",
        run_id=run_id,
        data=data,
        warnings=warnings,
    )
    if is_fallback:
        output["status"] = "warning"
    return output
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd quant && uv run python -m pytest tests/unit/portfolio/test_portfolio_optimize_service.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/portfolio/portfolio_optimize_service.py \
        quant/tests/unit/portfolio/test_portfolio_optimize_service.py
git commit -m "feat(l4): add portfolio_optimize_service (orchestration + fallback) with unit tests"
```

---

### Task 6: HTTP schemas

**Files:**
- Modify: `quant/src/interfaces/http/schemas.py`

- [ ] **Step 1: Add Portfolio* Pydantic models**

Append to the end of `quant/src/interfaces/http/schemas.py`:

```python
class PortfolioOptimizeRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")
    alpha: dict[str, float] | None = Field(
        default=None,
        description="标的 alpha 字典 {symbol: value}；缺省时自动从 L3 signal snapshot 取 composite_score",
    )
    prev_weights: dict[str, float] | None = Field(
        default=None,
        description="上期权重 {symbol: weight}；缺省时视为全零向量（首次运行）",
    )
    lambda_risk: float = Field(default=1.0, gt=0, description="风险厌恶系数，默认 1.0")
    lambda_tc: float = Field(default=0.001, ge=0, description="交易成本系数，默认 0.001")
    w_max: float = Field(default=0.30, gt=0, le=1.0, description="单标的权重上限，默认 0.30")
    ind_max: float = Field(default=0.40, gt=0, le=1.0, description="单行业权重上限，默认 0.40")
    lookback_days: int = Field(default=60, ge=20, le=252, description="协方差计算窗口（日历天），默认 60")


class PortfolioTargetWeightRow(BaseModel):
    symbol: str
    weight: float
    prev_weight: float
    delta: float


class PortfolioOptimizationReport(BaseModel):
    objective_value: float
    risk_contribution: float
    turnover_cost: float
    solver: str
    solve_time_ms: int


class PortfolioOptimizeData(BaseModel):
    as_of: str
    optimize_version: str
    optimization_status: str
    fallback_reason: str | None
    target_weights: list[PortfolioTargetWeightRow]
    optimization_report: PortfolioOptimizationReport


class PortfolioOptimizeResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: PortfolioOptimizeData
    warnings: list[dict]
    errors: list[dict]
```

- [ ] **Step 2: Verify Pydantic schemas import correctly**

```bash
cd quant && uv run python -c "from interfaces.http.schemas import PortfolioOptimizeRequest, PortfolioOptimizeResponse; print('ok')"
```

Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add quant/src/interfaces/http/schemas.py
git commit -m "feat(l4): add PortfolioOptimize* Pydantic schemas"
```

---

### Task 7: HTTP route + dependencies + app registration

**Files:**
- Create: `quant/src/interfaces/http/routes_portfolio.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/app.py`

- [ ] **Step 1: Create routes_portfolio.py**

Create `quant/src/interfaces/http/routes_portfolio.py`:

```python
from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    PortfolioOptimizeService,
    get_portfolio_optimize_service,
)
from interfaces.http.schemas import (
    PortfolioOptimizeRequest,
    PortfolioOptimizeResponse,
)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.post(
    "/optimize",
    summary="L4 组合优化（均值-方差 QP）",
    description=(
        "对指定日期计算目标权重。目标函数：max αᵀw - λ_risk·wᵀΣw - λ_tc·Σ|wᵢ-w_prev_i|，"
        "含单标的上限、行业上限约束。协方差从 DB bar 数据计算（需服务端已连接 DB）。"
        "alpha 缺省时自动从 L3 signal snapshot 取 composite_score。"
    ),
    response_description="目标权重 + 优化报告（含求解状态、风险贡献、换手成本）",
)
def post_portfolio_optimize(
    req: PortfolioOptimizeRequest,
    service: PortfolioOptimizeService = Depends(get_portfolio_optimize_service),
) -> PortfolioOptimizeResponse:
    return PortfolioOptimizeResponse.model_validate(
        service(
            req.as_of,
            req.alpha,
            req.prev_weights,
            req.lambda_risk,
            req.lambda_tc,
            req.w_max,
            req.ind_max,
            req.lookback_days,
        )
    )
```

- [ ] **Step 2: Add provider to dependencies.py**

In `quant/src/interfaces/http/dependencies.py`, add after the `SignalEvaluateService` type alias and `get_signal_evaluate_service` function:

```python
from application.portfolio.portfolio_optimize_service import run_portfolio_optimize

PortfolioOptimizeService = Callable[..., dict]


def get_portfolio_optimize_service() -> PortfolioOptimizeService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of, alpha, prev_weights, lambda_risk, lambda_tc, w_max, ind_max, lookback_days: run_portfolio_optimize(
        as_of=as_of,
        alpha=alpha,
        prev_weights=prev_weights,
        lambda_risk=lambda_risk,
        lambda_tc=lambda_tc,
        w_max=w_max,
        ind_max=ind_max,
        lookback_days=lookback_days,
        bar_store=bar_store,
    )
```

- [ ] **Step 3: Register router in app.py**

In `quant/src/interfaces/http/app.py`, add the portfolio router import and registration:

```python
from interfaces.http.routes_daily_run import router as daily_router
from interfaces.http.routes_factor_optimization import router as factor_optimization_router
from interfaces.http.routes_market_data import router as market_data_router
from interfaces.http.routes_portfolio import router as portfolio_router
from interfaces.http.routes_signal import router as signal_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="HiveFlow Quant Service",
        version="0.1.0",
        description=(
            "HiveFlow 量化核心服务 API。\n\n"
            "提供日频策略流水线（因子计算、候选排名、执行计划）"
            "与行情数据管理（同步、查询、K 线）两大模块。\n\n"
            "已纳入统一 envelope 管理的输出遵循 CLI Output Schema v1.0.0，"
            "字段含义参见 `docs/CLI_OUTPUT_SCHEMA.json`。"
        ),
        contact={"name": "HiveFlow", "email": ""},
        license_info={"name": "Private"},
    )
    app.include_router(daily_router)
    app.include_router(factor_optimization_router)
    app.include_router(market_data_router)
    app.include_router(portfolio_router)
    app.include_router(signal_router)
    return app
```

- [ ] **Step 4: Verify app starts without error**

```bash
cd quant && uv run python -c "from interfaces.http.app import create_app; app = create_app(); print('routes:', [r.path for r in app.routes if hasattr(r, 'path') and 'portfolio' in r.path])"
```

Expected: prints `routes: ['/api/v1/portfolio/optimize']`

- [ ] **Step 5: Commit**

```bash
git add quant/src/interfaces/http/routes_portfolio.py \
        quant/src/interfaces/http/dependencies.py \
        quant/src/interfaces/http/app.py
git commit -m "feat(l4): add POST /api/v1/portfolio/optimize HTTP route"
```

---

### Task 8: CLI output fixture + contract validation

**Files:**
- Create: `quant/tests/fixtures/cli_output/valid/portfolio_optimize_ok.json`

- [ ] **Step 1: Create valid fixture**

Create `quant/tests/fixtures/cli_output/valid/portfolio_optimize_ok.json`:

```json
{
  "schema_version": "1.0.0",
  "command": "hf portfolio optimize",
  "run_id": "run_20260401_abc12345",
  "status": "ok",
  "generated_at": "2026-04-01T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "optimize_version": "l4-optimize-v1.0",
    "optimization_status": "optimal",
    "fallback_reason": null,
    "target_weights": [
      {"symbol": "600519.SH", "weight": 0.298700, "prev_weight": 0.0, "delta": 0.298700},
      {"symbol": "000001.SZ", "weight": 0.234100, "prev_weight": 0.0, "delta": 0.234100},
      {"symbol": "300750.SZ", "weight": 0.182300, "prev_weight": 0.0, "delta": 0.182300},
      {"symbol": "601318.SH", "weight": 0.152100, "prev_weight": 0.0, "delta": 0.152100},
      {"symbol": "000333.SZ", "weight": 0.132800, "prev_weight": 0.0, "delta": 0.132800}
    ],
    "optimization_report": {
      "objective_value": 0.423100,
      "risk_contribution": 0.031200,
      "turnover_cost": 0.001800,
      "solver": "CLARABEL",
      "solve_time_ms": 42
    }
  },
  "warnings": [],
  "errors": []
}
```

- [ ] **Step 2: Run contract validation**

```bash
make validate-cli-output-one FILE=quant/tests/fixtures/cli_output/valid/portfolio_optimize_ok.json
```

Expected: PASS (valid schema)

- [ ] **Step 3: Run full fixture validation**

```bash
make validate-cli-output
```

Expected: all fixtures pass

- [ ] **Step 4: Commit**

```bash
git add quant/tests/fixtures/cli_output/valid/portfolio_optimize_ok.json
git commit -m "test(l4): add CLI output fixture for portfolio optimize"
```

---

### Task 9: Python architecture tests

**Files:**
- Modify: `quant/tests/architecture/test_layering_rules.py`

- [ ] **Step 1: Add portfolio architecture tests**

Append to `quant/tests/architecture/test_layering_rules.py`:

```python
def test_application_portfolio_does_not_import_interfaces():
    """application.portfolio 禁止依赖 interfaces 层"""
    portfolio_dir = APP_DIR / "portfolio"
    if not portfolio_dir.exists():
        return
    violations: list[str] = []
    for py in portfolio_dir.rglob("*.py"):
        imports = _imports(py)
        if any(name == "interfaces" or name.startswith("interfaces.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"application.portfolio must not import interfaces: {violations}"


def test_domain_portfolio_does_not_import_application():
    """domain.models.portfolio 禁止依赖 application"""
    portfolio_file = SRC / "domain" / "models" / "portfolio.py"
    if not portfolio_file.exists():
        return
    imports = _imports(portfolio_file)
    violations = [name for name in imports if name == "application" or name.startswith("application.")]
    assert not violations, f"domain.models.portfolio must not import application: {violations}"
```

- [ ] **Step 2: Run architecture tests**

```bash
cd quant && uv run python -m pytest tests/architecture/ -v
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add quant/tests/architecture/test_layering_rules.py
git commit -m "test(l4): add architecture boundary tests for application.portfolio and domain.models.portfolio"
```

---

### Task 10: Rust requests + dispatch

**Files:**
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/application/dispatch.rs`

- [ ] **Step 1: Add PortfolioOptimizeRequest to requests.rs**

In `cli/src/application/requests.rs`, append before the closing of the file (after `SignalEvaluateRequest`):

```rust
#[derive(Debug, Clone)]
pub struct PortfolioOptimizeRequest {
    pub as_of: String,
    pub output: String,
}
```

Also add `PortfolioOptimize` variant to the `AppCommand` enum:

```rust
pub enum AppCommand {
    PipelineDaily(PipelineDailyRequest),
    PipelineCompare(PipelineCompareRequest),
    FactorOptimize(FactorOptimizeRequest),
    FactorReplay(FactorReplayRequest),
    DataSync(DataSyncRequest),
    DataUniverseSync(DataUniverseSyncRequest),
    DataQuery(DataQueryRequest),
    DataBars(DataBarsRequest),
    SignalSnapshot(SignalSnapshotRequest),
    SignalEvaluate(SignalEvaluateRequest),
    PortfolioOptimize(PortfolioOptimizeRequest),
}
```

- [ ] **Step 2: Add dispatch arm**

In `cli/src/application/dispatch.rs`, update the imports and match arm:

```rust
use crate::application::handlers::{
    data_bars, data_query, data_sync, data_universe_sync, factor_optimize, factor_replay,
    pipeline_compare, pipeline_daily, portfolio_optimize, signal_evaluate, signal_snapshot,
};
use crate::application::requests::AppCommand;
use crate::error::AppError;

pub fn run(command: AppCommand) -> Result<(), AppError> {
    match command {
        AppCommand::PipelineDaily(args) => pipeline_daily::handle(args),
        AppCommand::PipelineCompare(args) => pipeline_compare::handle(args),
        AppCommand::FactorOptimize(args) => factor_optimize::handle(args),
        AppCommand::FactorReplay(args) => factor_replay::handle(args),
        AppCommand::DataSync(args) => data_sync::handle(args),
        AppCommand::DataUniverseSync(args) => data_universe_sync::handle(args),
        AppCommand::DataQuery(args) => data_query::handle(args),
        AppCommand::DataBars(args) => data_bars::handle(args),
        AppCommand::SignalSnapshot(args) => signal_snapshot::handle(args),
        AppCommand::SignalEvaluate(args) => signal_evaluate::handle(args),
        AppCommand::PortfolioOptimize(args) => portfolio_optimize::handle(args),
    }
}
```

- [ ] **Step 3: Verify compile (will fail until handler exists — that's OK)**

```bash
cd cli && cargo check 2>&1 | head -20
```

Expected: errors about missing `portfolio_optimize` module — this is expected.

- [ ] **Step 4: Commit**

```bash
git add cli/src/application/requests.rs cli/src/application/dispatch.rs
git commit -m "feat(l4): add PortfolioOptimizeRequest and AppCommand::PortfolioOptimize"
```

---

### Task 11: Rust cmd/portfolio.rs + cmd/mod.rs

**Files:**
- Create: `cli/src/cmd/portfolio.rs`
- Modify: `cli/src/cmd/mod.rs`

- [ ] **Step 1: Create cmd/portfolio.rs**

Create `cli/src/cmd/portfolio.rs`:

```rust
use crate::application::requests::PortfolioOptimizeRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(
    about = "L4 组合优化：从 L3 信号生成目标权重（需 quant HTTP 服务）"
)]
pub struct PortfolioArgs {
    #[command(subcommand)]
    pub command: PortfolioSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum PortfolioSubcommand {
    #[command(
        about = "均值-方差 QP 组合优化，返回 target_weights + optimization_report",
        long_about = "调用 POST /api/v1/portfolio/optimize。\
alpha 缺省时自动从 L3 signal snapshot 取 composite_score。\
目标函数：max αᵀw - λ_risk·wᵀΣw - λ_tc·Σ|wᵢ-w_prev|，含单标的/行业权重上限约束。\
求解失败时自动降级为等权或维持上期权重。"
    )]
    Optimize(OptimizeArgs),
}

const OPTIMIZE_AFTER_HELP: &str = "\
示例:
  hf portfolio optimize --as-of 2026-04-01
  hf portfolio optimize --as-of 2026-04-01 --output table

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- portfolio optimize --as-of 2026-04-01

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务（如 http://127.0.0.1:8000）";

#[derive(Debug, Args)]
#[command(after_long_help = OPTIMIZE_AFTER_HELP)]
pub struct OptimizeArgs {
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
        help = "输出形式：json = 标准 CLI envelope（默认）；table = 终端中文表格"
    )]
    pub output: String,
}

impl From<OptimizeArgs> for PortfolioOptimizeRequest {
    fn from(args: OptimizeArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
```

- [ ] **Step 2: Update cmd/mod.rs**

Replace the full content of `cli/src/cmd/mod.rs`:

```rust
pub mod data;
pub mod factor;
pub mod pipeline;
pub mod portfolio;
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
    /// L3 信号工程：因子截面 → signal_matrix（需 quant 服务与 ~/.hiveflow/config.toml）
    Signal(signal::SignalArgs),
    /// L4 组合优化：信号 → 目标权重（需 quant 服务与 ~/.hiveflow/config.toml）
    Portfolio(portfolio::PortfolioArgs),
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
                signal::SignalSubcommand::Evaluate(evaluate) => {
                    AppCommand::SignalEvaluate(evaluate.into())
                }
            },
            Commands::Portfolio(args) => match args.command {
                portfolio::PortfolioSubcommand::Optimize(optimize) => {
                    AppCommand::PortfolioOptimize(optimize.into())
                }
            },
        }
    }
}
```

- [ ] **Step 3: Verify compile (still errors on missing handler module)**

```bash
cd cli && cargo check 2>&1 | grep "error\[" | head -10
```

Expected: errors only about missing `portfolio_optimize` module in `handlers/`.

- [ ] **Step 4: Commit**

```bash
git add cli/src/cmd/portfolio.rs cli/src/cmd/mod.rs
git commit -m "feat(l4): add hf portfolio optimize CLI subcommand (cmd layer)"
```

---

### Task 12: Rust http_client

**Files:**
- Modify: `cli/src/infrastructure/http_client.rs`

- [ ] **Step 1: Add post_portfolio_optimize**

Append to `cli/src/infrastructure/http_client.rs`:

```rust
pub fn post_portfolio_optimize(
    server_url: &str,
    as_of: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/api/v1/portfolio/optimize",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({ "as_of": as_of }))
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

- [ ] **Step 2: Commit**

```bash
git add cli/src/infrastructure/http_client.rs
git commit -m "feat(l4): add post_portfolio_optimize HTTP client function"
```

---

### Task 13: Rust handler + mod registration

**Files:**
- Create: `cli/src/application/handlers/portfolio_optimize.rs`
- Modify: `cli/src/application/handlers/mod.rs`

- [ ] **Step 1: Create portfolio_optimize handler**

Create `cli/src/application/handlers/portfolio_optimize.rs`:

```rust
use crate::application::requests::PortfolioOptimizeRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_portfolio_optimize_table;

pub fn handle(args: PortfolioOptimizeRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_portfolio_optimize(
        &cfg.server_url,
        &args.as_of,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_portfolio_optimize_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for portfolio optimize: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
```

- [ ] **Step 2: Register module in handlers/mod.rs**

Replace the full content of `cli/src/application/handlers/mod.rs`:

```rust
pub mod data_bars;
pub mod data_query;
pub mod data_sync;
pub mod data_universe_sync;
pub mod factor_optimize;
pub mod factor_replay;
pub mod pipeline_compare;
pub mod pipeline_daily;
pub mod portfolio_optimize;
pub mod signal_evaluate;
pub mod signal_snapshot;
```

- [ ] **Step 3: Verify compile (will fail on missing render function — that's OK)**

```bash
cd cli && cargo check 2>&1 | grep "error\[" | head -10
```

Expected: error about `render_portfolio_optimize_table` not found in `table_renderer`.

- [ ] **Step 4: Commit**

```bash
git add cli/src/application/handlers/portfolio_optimize.rs \
        cli/src/application/handlers/mod.rs
git commit -m "feat(l4): add portfolio_optimize handler"
```

---

### Task 14: Rust table renderer

**Files:**
- Modify: `cli/src/infrastructure/table_renderer.rs`

- [ ] **Step 1: Add render_portfolio_optimize_table**

Append to the end of `cli/src/infrastructure/table_renderer.rs`:

```rust
pub fn render_portfolio_optimize_table(payload: &Value) -> String {
    let data = payload.get("data");
    let as_of = as_str(data.and_then(|d| d.get("as_of")));
    let opt_status = as_str(data.and_then(|d| d.get("optimization_status")));
    let fallback_reason = as_str(data.and_then(|d| d.get("fallback_reason")));

    let report = data.and_then(|d| d.get("optimization_report"));
    let solver = as_str(report.and_then(|r| r.get("solver")));
    let solve_ms = as_i64(report.and_then(|r| r.get("solve_time_ms")));
    let obj_val = as_f64(report.and_then(|r| r.get("objective_value")));
    let risk_contrib = as_f64(report.and_then(|r| r.get("risk_contribution")));
    let turnover_cost = as_f64(report.and_then(|r| r.get("turnover_cost")));

    let mut header = Table::new();
    header
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("日期"),
            Cell::new("求解状态"),
            Cell::new("求解器"),
            Cell::new("耗时(ms)"),
            Cell::new("目标值"),
            Cell::new("风险贡献"),
            Cell::new("换手成本"),
        ]);
    header.add_row(vec![
        as_of.clone(),
        opt_status.clone(),
        solver,
        solve_ms,
        obj_val,
        risk_contrib,
        turnover_cost,
    ]);

    let mut weights_table = Table::new();
    weights_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("目标权重"),
            Cell::new("上期权重"),
            Cell::new("变动"),
        ]);

    if let Some(rows) = data
        .and_then(|d| d.get("target_weights"))
        .and_then(Value::as_array)
    {
        for row in rows {
            let w = row.get("weight").and_then(Value::as_f64).unwrap_or(0.0);
            let pw = row.get("prev_weight").and_then(Value::as_f64).unwrap_or(0.0);
            let delta = row.get("delta").and_then(Value::as_f64).unwrap_or(0.0);
            let delta_str = if delta >= 0.0 {
                format!("+{:.2}%", delta * 100.0)
            } else {
                format!("{:.2}%", delta * 100.0)
            };
            weights_table.add_row(vec![
                as_str(row.get("symbol")),
                format!("{:.2}%", w * 100.0),
                format!("{:.2}%", pw * 100.0),
                delta_str,
            ]);
        }
    }

    let fallback_note = if !fallback_reason.is_empty() {
        format!("\n[降级原因: {fallback_reason}]")
    } else {
        String::new()
    };

    format!(
        "组合优化结果（{as_of}）  求解状态: {opt_status}\n{}\n目标权重\n{}{}\n",
        header, weights_table, fallback_note
    )
}
```

- [ ] **Step 2: Verify full compile succeeds**

```bash
cd cli && cargo build 2>&1 | tail -5
```

Expected: `Finished dev [unoptimized + debuginfo] target(s)` — no errors.

- [ ] **Step 3: Run Rust tests**

```bash
make rust-test
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add cli/src/infrastructure/table_renderer.rs
git commit -m "feat(l4): add render_portfolio_optimize_table for --output table"
```

---

### Task 15: Rust architecture test

**Files:**
- Modify: `cli/tests/architecture_rules.rs`

- [ ] **Step 1: Add portfolio.rs to cmd layer check**

In `cli/tests/architecture_rules.rs`, update the `cmd_layer_must_not_import_infrastructure` test to include `cmd/portfolio.rs`:

```rust
#[test]
fn cmd_layer_must_not_import_infrastructure() {
    let cmd_files = [
        "cmd/data.rs",
        "cmd/pipeline.rs",
        "cmd/factor.rs",
        "cmd/signal.rs",
        "cmd/portfolio.rs",
    ];
    for file in cmd_files {
        let content = read(&src_path(file));
        assert!(
            !content.contains("crate::infrastructure"),
            "cmd layer must not import infrastructure directly: {file}"
        );
    }
}
```

- [ ] **Step 2: Run architecture tests**

```bash
make rust-test
```

Expected: all Rust tests PASS

- [ ] **Step 3: Commit**

```bash
git add cli/tests/architecture_rules.rs
git commit -m "test(l4): add cmd/portfolio.rs to Rust architecture boundary check"
```

---

### Task 16: Pipeline integration

**Files:**
- Modify: `quant/src/application/daily_run_service.py`

- [ ] **Step 1: Add portfolio optimize step to run_daily**

In `quant/src/application/daily_run_service.py`, add the import at the top (with other imports):

```python
from application.portfolio.portfolio_optimize_service import run_portfolio_optimize
```

Then in `run_daily()`, after the `signal_matrix` computation block (after the `except` block that appends `SIGNAL_MATRIX_FAILED`), add:

```python
    portfolio = None
    if signal_matrix is not None:
        try:
            composite_scores = signal_matrix.get("composite_scores", [])
            alpha = {
                cs["symbol"]: float(cs["composite_score"])
                for cs in composite_scores
                if not math.isnan(float(cs["composite_score"]))
            }
            if alpha:
                portfolio_result = run_portfolio_optimize(
                    as_of=as_of,
                    alpha=alpha,
                    bar_store=bar_store,
                )
                portfolio = portfolio_result.get("data")
        except Exception:
            _logger.warning(
                "daily run: portfolio optimization failed",
                exc_info=True,
            )
            warnings.append({
                "code": "PORTFOLIO_OPTIMIZATION_FAILED",
                "message": "L4 portfolio optimization failed; portfolio set to null",
            })
```

Also add `import math` at the top of the file if not already present.

Update the return statement to include `portfolio`:

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
            "portfolio": portfolio,
        },
        warnings=warnings,
    )
```

- [ ] **Step 2: Verify daily run service still works**

```bash
cd quant && uv run python -m pytest tests/unit/test_daily_run_service.py -v
```

Expected: all existing tests PASS

- [ ] **Step 3: Run full Python test suite**

```bash
cd quant && uv run python -m pytest -q
```

Expected: all tests PASS (or only pre-existing failures)

- [ ] **Step 4: Commit**

```bash
git add quant/src/application/daily_run_service.py
git commit -m "feat(l4): integrate portfolio optimize into daily pipeline (data.portfolio field)"
```

---

### Task 17: Update docs

**Files:**
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add portfolio optimize example to CLI_OUTPUT_EXAMPLES.md**

Find the section for signal evaluate in `docs/CLI_OUTPUT_EXAMPLES.md` and append a new section after it:

```markdown
## `hf portfolio optimize`

### JSON output (`--output json`)

```json
{
  "schema_version": "1.0.0",
  "command": "hf portfolio optimize",
  "run_id": "run_20260401_abc12345",
  "status": "ok",
  "generated_at": "2026-04-01T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "optimize_version": "l4-optimize-v1.0",
    "optimization_status": "optimal",
    "fallback_reason": null,
    "target_weights": [
      {"symbol": "600519.SH", "weight": 0.298700, "prev_weight": 0.0, "delta": 0.298700},
      {"symbol": "000001.SZ", "weight": 0.234100, "prev_weight": 0.0, "delta": 0.234100},
      {"symbol": "300750.SZ", "weight": 0.182300, "prev_weight": 0.0, "delta": 0.182300},
      {"symbol": "601318.SH", "weight": 0.152100, "prev_weight": 0.0, "delta": 0.152100},
      {"symbol": "000333.SZ", "weight": 0.132800, "prev_weight": 0.0, "delta": 0.132800}
    ],
    "optimization_report": {
      "objective_value": 0.423100,
      "risk_contribution": 0.031200,
      "turnover_cost": 0.001800,
      "solver": "CLARABEL",
      "solve_time_ms": 42
    }
  },
  "warnings": [],
  "errors": []
}
```
```

- [ ] **Step 2: Update AGENTS.md**

In `AGENTS.md` §7.6 (主要 HTTP 接口), add the new endpoint:

```markdown
- `POST /api/v1/portfolio/optimize`：L4 组合优化（均值-方差 QP，含换手成本惩罚）
```

In §7.8 (各层完成度), update L4 row:

```markdown
| L4 | 组合优化 | ✅ Phase 1 完成 | 均值-方差 QP（cvxpy CLARABEL）+ 换手成本惩罚 + 单标的/行业约束；`POST /api/v1/portfolio/optimize` + `hf portfolio optimize`；daily pipeline 接入（data.portfolio 字段） |
```

Update §7.9 (已交付能力摘要) to add:

```markdown
- **L4 组合优化**：`POST /api/v1/portfolio/optimize` + `hf portfolio optimize --as-of DATE [--output json|table]`；均值-方差 QP（cvxpy CLARABEL）；目标函数含 alpha、风险惩罚（协方差矩阵）、换手成本惩罚；单标的上限 30%、行业上限 40%；首次运行等权 fallback；daily pipeline 自动调用（data.portfolio 字段）
```

Update 当前工作位置:

```markdown
**当前工作位置**：L4 Phase 1（组合优化）已合入 master → L5 风险门控待 spec；或 L3 Phase 2b（缺失值/行业中性化）待 spec。
```

- [ ] **Step 3: Commit**

```bash
git add docs/CLI_OUTPUT_EXAMPLES.md AGENTS.md
git commit -m "docs(l4): update CLI examples, AGENTS.md with L4 portfolio optimize"
```

---

### Task 18: Final CI gate

- [ ] **Step 1: Run full check**

```bash
make check
```

Expected: all gates pass — Python tests, lint, architecture-check, validate-cli-output, Rust tests.

- [ ] **Step 2: Fix any failures**

If `ruff` lint fails: run `cd quant && uv run ruff check . --fix` and re-commit.

If `validate-cli-output` fails: check fixture schema matches `docs/CLI_OUTPUT_SCHEMA.json`.

If architecture tests fail: trace the import path and fix the violation.

- [ ] **Step 3: Final commit if fixes were needed**

```bash
git add -p  # stage only the fixes
git commit -m "fix(l4): address make check findings"
```
