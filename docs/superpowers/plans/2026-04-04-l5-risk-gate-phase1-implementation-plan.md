# L5 Risk Gate Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-regime (normal/warning/crisis) risk gate that runs four hard-constraint checks (portfolio vol, single-asset concentration, industry concentration, turnover) after L4, with `POST /api/v1/risk/check` + `hf risk check` CLI + daily pipeline integration.

**Architecture:** Pure-function service `risk_gate_service.py` derives market regime from bar data at call time (no DB persistence), runs all four checks against regime-specific thresholds, and returns a standard CLI envelope. The service is wired into the FastAPI app via `routes_risk.py` + `dependencies.py`, into the daily pipeline via `daily_run_service.py`, and exposed in the Rust CLI via `cmd/risk.rs`.

**Tech Stack:** Python (FastAPI, numpy, pandas, existing `covariance_service`), Rust (clap, reqwest, comfy-table), pytest.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `quant/src/application/risk/__init__.py` | Create | Package marker |
| `quant/src/application/risk/risk_gate_service.py` | Create | Regime detection + 4 checks + `run_risk_check()` |
| `quant/src/interfaces/http/routes_risk.py` | Create | `POST /api/v1/risk/check` FastAPI router |
| `quant/src/interfaces/http/schemas.py` | Modify | Add `RiskCheckRequest`, `RiskCheckResponse` Pydantic models |
| `quant/src/interfaces/http/dependencies.py` | Modify | Add `RiskCheckService`, `get_risk_check_service()` |
| `quant/src/interfaces/http/app.py` | Modify | Register `routes_risk` router |
| `quant/src/application/daily_run_service.py` | Modify | Call `run_risk_check()` after L4, add `risk_gate` to data |
| `quant/tests/unit/risk/test_risk_gate_service.py` | Create | 12 unit tests |
| `quant/tests/fixtures/cli_output/valid/risk_check_ok.json` | Create | CLI fixture for CI |
| `cli/src/cmd/risk.rs` | Create | `hf risk check --as-of DATE [--output json\|table]` |
| `cli/src/application/handlers/risk_check.rs` | Create | Handle `RiskCheckRequest`, call HTTP, format output |
| `cli/src/infrastructure/http_client.rs` | Modify | Add `post_risk_check()` |
| `cli/src/infrastructure/table_renderer.rs` | Modify | Add `render_risk_check_table()` |
| `cli/src/application/requests.rs` | Modify | Add `RiskCheckRequest`, `AppCommand::RiskCheck` |
| `cli/src/application/handlers/mod.rs` | Modify | `pub mod risk_check;` |
| `cli/src/application/dispatch.rs` | Modify | Route `AppCommand::RiskCheck` |
| `cli/src/cmd/mod.rs` | Modify | Add `pub mod risk;`, add `Risk` to `Commands`, wire `From<Cli>` |
| `docs/CLI_OUTPUT_EXAMPLES.md` | Modify | Add `hf risk check` example |
| `AGENTS.md` | Modify | Update L5 status to ✅ Phase 1 完成 |

---

## Task 1: `risk_gate_service.py` — regime detection + four checks

**Files:**
- Create: `quant/src/application/risk/__init__.py`
- Create: `quant/src/application/risk/risk_gate_service.py`
- Create: `quant/tests/unit/risk/test_risk_gate_service.py`

### Context

The service must:

1. Detect market regime by computing annualised vol of last 20 daily returns:
   - Priority 1: 000300.SH from bar_store (fetch 30 bars → 29 returns → tail(20))
   - Priority 2: equal-weight of 5 default symbols (same bar_store, same window)
   - Priority 3: bar_store=None or data insufficient → `regime="normal"`, `regime_vol=None`, `regime_vol_source="none"`
2. Apply thresholds per regime:

   | check | normal | warning | crisis |
   |-------|--------|---------|--------|
   | portfolio_vol (σ_p) | ≤ 0.30 | ≤ 0.22 | ≤ 0.15 |
   | single_asset_max | ≤ 0.35 | ≤ 0.28 | ≤ 0.20 |
   | industry_max | ≤ 0.45 | ≤ 0.38 | ≤ 0.30 |
   | turnover | ≤ 0.80 | ≤ 0.55 | ≤ 0.30 |

3. Covariance matrix for σ_p:
   - `from application.portfolio.covariance_service import compute_covariance_matrix` — already annualised (×252 inside that function)
   - `sigma_p = float(np.sqrt(w_vec @ Sigma @ w_vec))` — **no** additional `sqrt(252)`
   - If bar_store=None: use diagonal fallback `0.04 * I`

4. Industry map (same as L4):
   ```python
   _INDUSTRY_MAP = {
       "000001.SZ": "banking", "600519.SH": "food_beverage",
       "300750.SZ": "new_energy", "601318.SH": "insurance", "000333.SZ": "appliance",
   }
   ```

5. Turnover: `sum(abs(w_new - w_prev))`. If `prev_weights` is None or `{}`, all prev values are 0, so turnover = 1.0 for a fully invested portfolio.

6. All 4 checks always run regardless of prior failures. `block_codes` collects all failures.

7. Return is a standard CLI envelope (use `ok_output` from `application.contracts.cli_output`). `status="warning"` when `risk_gate="block"`.

### Steps

- [ ] **Step 1: Create `__init__.py`**

```python
# quant/src/application/risk/__init__.py
```

Run: `touch quant/src/application/risk/__init__.py` (or create with empty content).

- [ ] **Step 2: Write 12 failing tests**

Create `quant/tests/unit/risk/test_risk_gate_service.py`:

```python
from __future__ import annotations

import math
import numpy as np


_SYMBOLS = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"]
_BENCHMARK = "000300.SH"

# ── bar_store helpers ───────────────────────────────────────────────────────

def _make_bar_store(symbol_returns: dict[str, list[float]], base_price: float = 100.0):
    """Build a mock bar_store whose list_bars returns synthetic daily bars.
    symbol_returns: {symbol: [r1, r2, ...]}  (daily returns, e.g. 0.01 = +1%)
    Generates len(returns)+1 bars so pct_change().dropna() has len(returns) rows.
    """
    rows = []
    for sym, rets in symbol_returns.items():
        price = base_price
        prices = [price]
        for r in rets:
            price = price * (1 + r)
            prices.append(price)
        for i, p in enumerate(prices):
            rows.append({
                "symbol": sym,
                "bar_time": f"2026-01-{i+1:02d}T15:00:00+08:00",
                "close": p,
            })

    class _MockBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return [r for r in rows if r["symbol"] in symbols]

    return _MockBarStore()


def _low_vol_returns(n: int = 29) -> list[float]:
    """Returns that produce ~5% annual vol — well below normal threshold."""
    return [0.003] * n  # ~5% annual


def _mid_vol_returns(n: int = 29) -> list[float]:
    """Returns that produce ~30% annual vol — in warning range."""
    return [0.019] * n  # ~30% annual


def _high_vol_returns(n: int = 29) -> list[float]:
    """Returns that produce ~48% annual vol — in crisis range."""
    return [0.030] * n  # ~48% annual


def _equal_weights() -> dict[str, float]:
    return {s: 0.20 for s in _SYMBOLS}


# ── regime tests ────────────────────────────────────────────────────────────

def test_regime_normal_when_low_vol():
    from application.risk.risk_gate_service import run_risk_check

    bar_store = _make_bar_store({_BENCHMARK: _low_vol_returns()})
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime"] == "normal"
    assert result["data"]["regime_vol_source"] == "benchmark"


def test_regime_warning_when_mid_vol():
    from application.risk.risk_gate_service import run_risk_check

    bar_store = _make_bar_store({_BENCHMARK: _mid_vol_returns()})
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime"] == "warning"
    assert result["data"]["regime_vol_source"] == "benchmark"


def test_regime_crisis_when_high_vol():
    from application.risk.risk_gate_service import run_risk_check

    bar_store = _make_bar_store({_BENCHMARK: _high_vol_returns()})
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime"] == "crisis"
    assert result["data"]["regime_vol_source"] == "benchmark"


def test_regime_fallback_to_equal_weight():
    """000300.SH has < 20 returns → fall back to equal-weight portfolio."""
    from application.risk.risk_gate_service import run_risk_check

    # Only 5 bars for benchmark → 4 returns, below threshold of 20
    bar_store = _make_bar_store({
        _BENCHMARK: [0.03] * 4,
        **{s: _low_vol_returns() for s in _SYMBOLS},
    })
    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights={},
        bar_store=bar_store,
    )
    assert result["data"]["regime_vol_source"] == "equal_weight"


def test_regime_defaults_normal_when_no_data():
    """bar_store=None → regime=normal, no exception."""
    from application.risk.risk_gate_service import run_risk_check

    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),
        prev_weights=None,
        bar_store=None,
    )
    assert result["data"]["regime"] == "normal"
    assert result["data"]["regime_vol_source"] == "none"
    assert result["data"]["regime_vol"] is None


# ── check tests ─────────────────────────────────────────────────────────────

def test_p1_portfolio_vol_block():
    """σ_p > normal threshold (0.30) → block + PORTFOLIO_VOL_EXCEEDED."""
    from application.risk.risk_gate_service import run_risk_check

    # equal weights 0.20 each, diagonal cov = 0.04 each → σ_p = sqrt(0.04) = 0.20
    # To exceed 0.30, use higher diagonal. We can't control the cov matrix directly,
    # but we can test with bar_store=None (diagonal 0.04) and expect PASS,
    # then verify BLOCK logic by calling _run_checks directly.
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {s: 0.20 for s in symbols}
    # Build cov with high diagonal variance (0.25 each → σ_p = sqrt(sum w²·var) = sqrt(5*0.04*0.25) = 0.224 < 0.30 normal)
    # Use 0.49 diagonal → σ_p = sqrt(5 * 0.04 * 0.49) = sqrt(0.098) ≈ 0.313 > 0.30 → BLOCK in normal
    n = len(symbols)
    Sigma = pd.DataFrame(0.49 * np.eye(n), index=symbols, columns=symbols)
    checks, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    assert any(c["name"] == "portfolio_vol" and not c["passed"] for c in checks)
    assert "PORTFOLIO_VOL_EXCEEDED" in block_codes


def test_p2_single_asset_block():
    """max weight > 0.35 (normal) → SINGLE_ASSET_CONCENTRATION."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {"000001.SZ": 0.40, "600519.SH": 0.20, "300750.SZ": 0.15, "601318.SH": 0.15, "000333.SZ": 0.10}
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    _, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    assert "SINGLE_ASSET_CONCENTRATION" in block_codes


def test_p3_industry_block():
    """industry sum > 0.45 (normal) → INDUSTRY_CONCENTRATION."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    # Give banking (000001.SZ) 0.50 of portfolio
    symbols = _SYMBOLS
    w = {"000001.SZ": 0.50, "600519.SH": 0.20, "300750.SZ": 0.15, "601318.SH": 0.10, "000333.SZ": 0.05}
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    _, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    assert "INDUSTRY_CONCENTRATION" in block_codes


def test_p4_turnover_block():
    """turnover > 0.80 (normal) → TURNOVER_EXCEEDED."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w_new = {s: 0.20 for s in symbols}
    # prev weights completely different → turnover = sum(|0.20 - prev|)
    w_prev = {"000001.SZ": 0.60, "600519.SH": 0.10, "300750.SZ": 0.10, "601318.SH": 0.10, "000333.SZ": 0.10}
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    _, block_codes = _run_checks(w_new, Sigma, prev_weights=w_prev, regime="normal")

    assert "TURNOVER_EXCEEDED" in block_codes


def test_all_checks_run_even_when_blocked():
    """Multiple failures → block_codes contains all of them."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    # High single-asset concentration AND high turnover
    w_new = {"000001.SZ": 0.50, "600519.SH": 0.20, "300750.SZ": 0.15, "601318.SH": 0.10, "000333.SZ": 0.05}
    w_prev = {s: 0.0 for s in symbols}  # turnover = 1.0 > 0.80
    n = len(symbols)
    Sigma = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)
    checks, block_codes = _run_checks(w_new, Sigma, prev_weights=w_prev, regime="normal")

    assert len(block_codes) >= 2
    assert "SINGLE_ASSET_CONCENTRATION" in block_codes
    assert "TURNOVER_EXCEEDED" in block_codes
    # All 4 checks must be present regardless
    check_names = {c["name"] for c in checks}
    assert check_names == {"portfolio_vol", "single_asset_max", "industry_max", "turnover"}


def test_pass_returns_ok_status():
    """All checks pass → risk_gate=pass, status=ok."""
    from application.risk.risk_gate_service import run_risk_check

    result = run_risk_check(
        as_of="2026-02-01",
        target_weights=_equal_weights(),  # 0.20 each — well within all thresholds
        prev_weights=_equal_weights(),    # same as new → turnover = 0
        bar_store=None,
    )
    assert result["data"]["risk_gate"] == "pass"
    assert result["status"] == "ok"
    assert result["data"]["block_codes"] == []


def test_prev_weights_empty_means_full_turnover():
    """prev_weights={} → all prev values are 0 → turnover = sum(w_new) = 1.0."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {s: 0.20 for s in symbols}
    Sigma = pd.DataFrame(0.04 * np.eye(len(symbols)), index=symbols, columns=symbols)
    checks, block_codes = _run_checks(w, Sigma, prev_weights={}, regime="normal")

    turnover_check = next(c for c in checks if c["name"] == "turnover")
    assert abs(turnover_check["value"] - 1.0) < 1e-6
    assert "TURNOVER_EXCEEDED" in block_codes  # 1.0 > 0.80


def test_crisis_tightens_thresholds():
    """Equal weights (0.20 each) pass in normal but block on portfolio_vol in crisis
    when diagonal var is set to 0.06 (σ_p ≈ 0.346 > crisis threshold 0.15)."""
    from application.risk.risk_gate_service import _run_checks
    import pandas as pd

    symbols = _SYMBOLS
    w = {s: 0.20 for s in symbols}
    # diagonal var=0.04 → σ_p = sqrt(5 * 0.04 * 0.04) = sqrt(0.008) ≈ 0.089
    # That's < 0.15 (crisis P1 threshold) so P1 passes — use higher var
    # var=0.15 → σ_p = sqrt(5 * 0.04 * 0.15) = sqrt(0.03) ≈ 0.173 > 0.15 → BLOCK in crisis, pass in normal
    Sigma = pd.DataFrame(0.15 * np.eye(len(symbols)), index=symbols, columns=symbols)
    _, block_normal = _run_checks(w, Sigma, prev_weights=w, regime="normal")
    _, block_crisis = _run_checks(w, Sigma, prev_weights=w, regime="crisis")

    assert "PORTFOLIO_VOL_EXCEEDED" not in block_normal
    assert "PORTFOLIO_VOL_EXCEEDED" in block_crisis
```

- [ ] **Step 3: Run tests to verify they all fail**

```bash
cd quant && uv run python -m pytest tests/unit/risk/test_risk_gate_service.py -v 2>&1 | head -40
```

Expected: All 12 tests FAIL with `ModuleNotFoundError: No module named 'application.risk'`

- [ ] **Step 4: Implement `risk_gate_service.py`**

Create `quant/src/application/risk/risk_gate_service.py`:

```python
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from uuid import uuid4

import numpy as np
import pandas as pd

from application.contracts.cli_output import ok_output

_logger = logging.getLogger(__name__)

_BENCHMARK_SYMBOL = "000300.SH"
_DEFAULT_SYMBOLS = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"]
_MIN_REGIME_RETURNS = 20
_REGIME_LOOKBACK_BARS = 31  # fetch 31 bars → 30 returns, take tail(20)

_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}

_THRESHOLDS: dict[str, dict[str, float]] = {
    "normal":  {"portfolio_vol": 0.30, "single_asset_max": 0.35, "industry_max": 0.45, "turnover": 0.80},
    "warning": {"portfolio_vol": 0.22, "single_asset_max": 0.28, "industry_max": 0.38, "turnover": 0.55},
    "crisis":  {"portfolio_vol": 0.15, "single_asset_max": 0.20, "industry_max": 0.30, "turnover": 0.30},
}

_BLOCK_CODES: dict[str, str] = {
    "portfolio_vol":    "PORTFOLIO_VOL_EXCEEDED",
    "single_asset_max": "SINGLE_ASSET_CONCENTRATION",
    "industry_max":     "INDUSTRY_CONCENTRATION",
    "turnover":         "TURNOVER_EXCEEDED",
}


def _compute_regime_vol_from_bars(
    symbols: list[str],
    as_of: str,
    bar_store,
) -> tuple[float | None, str]:
    """Try benchmark first, fall back to equal-weight. Returns (vol, source)."""
    start_date = (date.fromisoformat(as_of) - timedelta(days=60)).isoformat()

    # Priority 1: benchmark
    try:
        rows = bar_store.list_bars(
            symbols=[_BENCHMARK_SYMBOL],
            timeframe="1d",
            start_date=start_date,
            end_date=as_of,
            limit=_REGIME_LOOKBACK_BARS,
        )
        if rows:
            df = pd.DataFrame(rows)
            df["_date"] = pd.to_datetime(df["bar_time"]).dt.date
            prices = (
                df.pivot_table(index="_date", columns="symbol", values="close", aggfunc="last")
                .sort_index()
                .get(_BENCHMARK_SYMBOL)
            )
            if prices is not None:
                rets = prices.pct_change().dropna().tail(_MIN_REGIME_RETURNS)
                if len(rets) >= _MIN_REGIME_RETURNS:
                    vol = float(rets.std() * np.sqrt(252))
                    return vol, "benchmark"
    except Exception:
        _logger.debug("regime: benchmark fetch failed", exc_info=True)

    # Priority 2: equal-weight portfolio of default symbols
    try:
        rows = bar_store.list_bars(
            symbols=symbols,
            timeframe="1d",
            start_date=start_date,
            end_date=as_of,
            limit=_REGIME_LOOKBACK_BARS * len(symbols),
        )
        if rows:
            df = pd.DataFrame(rows)
            df["_date"] = pd.to_datetime(df["bar_time"]).dt.date
            pivot = (
                df.pivot_table(index="_date", columns="symbol", values="close", aggfunc="last")
                .sort_index()
            )
            eq_portfolio = pivot.mean(axis=1)
            rets = eq_portfolio.pct_change().dropna().tail(_MIN_REGIME_RETURNS)
            if len(rets) >= _MIN_REGIME_RETURNS:
                vol = float(rets.std() * np.sqrt(252))
                return vol, "equal_weight"
    except Exception:
        _logger.debug("regime: equal-weight fetch failed", exc_info=True)

    return None, "none"


def _detect_regime(bar_store, as_of: str) -> tuple[str, float | None, str]:
    """Return (regime, regime_vol, regime_vol_source)."""
    if bar_store is None:
        return "normal", None, "none"

    vol, source = _compute_regime_vol_from_bars(_DEFAULT_SYMBOLS, as_of, bar_store)
    if vol is None:
        return "normal", None, "none"

    if vol >= 0.40:
        regime = "crisis"
    elif vol >= 0.25:
        regime = "warning"
    else:
        regime = "normal"

    return regime, vol, source


def _run_checks(
    target_weights: dict[str, float],
    cov_matrix: pd.DataFrame,
    prev_weights: dict[str, float],
    regime: str,
) -> tuple[list[dict], list[str]]:
    """Run all 4 checks. Returns (checks_list, block_codes_list)."""
    thresholds = _THRESHOLDS[regime]
    symbols = list(target_weights.keys())
    w_vec = np.array([target_weights[s] for s in symbols], dtype=float)
    Sigma = cov_matrix.reindex(index=symbols, columns=symbols).fillna(0.0).values.astype(float)

    # P1: portfolio vol (Sigma already annualised)
    sigma_p = float(np.sqrt(w_vec @ Sigma @ w_vec))

    # P2: single asset max
    single_max = float(max(w_vec))

    # P3: industry max
    industry_groups: dict[str, list[int]] = {}
    for i, s in enumerate(symbols):
        ind = _INDUSTRY_MAP.get(s, "other")
        industry_groups.setdefault(ind, []).append(i)
    industry_max = max(
        float(sum(w_vec[i] for i in idxs)) for idxs in industry_groups.values()
    )

    # P4: turnover
    prev_w = prev_weights or {}
    turnover = float(sum(abs(target_weights.get(s, 0.0) - prev_w.get(s, 0.0)) for s in symbols))

    values = {
        "portfolio_vol":    sigma_p,
        "single_asset_max": single_max,
        "industry_max":     industry_max,
        "turnover":         turnover,
    }

    checks: list[dict] = []
    block_codes: list[str] = []
    for name, value in values.items():
        threshold = thresholds[name]
        passed = value <= threshold
        checks.append({"name": name, "value": round(value, 6), "threshold": threshold, "passed": passed})
        if not passed:
            block_codes.append(_BLOCK_CODES[name])

    return checks, block_codes


def run_risk_check(
    as_of: str,
    target_weights: dict[str, float],
    prev_weights: dict[str, float] | None = None,
    bar_store=None,
) -> dict:
    """L5 risk gate check. Returns standard CLI envelope.

    risk_gate: "pass" | "block"
    status: "ok" (pass) | "warning" (block)
    """
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"

    # Step 1: detect regime
    regime, regime_vol, regime_vol_source = _detect_regime(bar_store, as_of)

    # Step 2: covariance matrix for sigma_p
    symbols = list(target_weights.keys())
    cov_matrix: pd.DataFrame | None = None
    if bar_store is not None:
        try:
            from application.portfolio.covariance_service import compute_covariance_matrix
            cov_matrix = compute_covariance_matrix(
                symbols=symbols, as_of=as_of, bar_store=bar_store
            )
        except Exception:
            _logger.warning("risk gate: covariance computation failed, using diagonal", exc_info=True)

    if cov_matrix is None:
        n = len(symbols)
        cov_matrix = pd.DataFrame(0.04 * np.eye(n), index=symbols, columns=symbols)

    # Step 3: run all 4 checks
    prev_w = prev_weights or {}
    checks, block_codes = _run_checks(target_weights, cov_matrix, prev_w, regime)

    risk_gate = "block" if block_codes else "pass"
    warnings: list[dict] = []
    if risk_gate == "block":
        warnings.append({
            "code": "RISK_GATE_BLOCKED",
            "message": f"Risk gate blocked: {', '.join(block_codes)}",
        })

    data = {
        "as_of": as_of,
        "risk_gate": risk_gate,
        "regime": regime,
        "regime_vol": regime_vol,
        "regime_vol_source": regime_vol_source,
        "checks": checks,
        "block_codes": block_codes,
    }

    output = ok_output(
        command="hf risk check",
        run_id=run_id,
        data=data,
        warnings=warnings,
    )
    if risk_gate == "block":
        output["status"] = "warning"
    return output
```

- [ ] **Step 5: Run tests — expect all 12 to pass**

```bash
cd quant && uv run python -m pytest tests/unit/risk/test_risk_gate_service.py -v
```

Expected: 12 passed.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
cd quant && uv run python -m pytest -q
```

Expected: All tests pass (≥ 202 before this task; now ≥ 214).

- [ ] **Step 7: Commit**

```bash
git add quant/src/application/risk/__init__.py \
        quant/src/application/risk/risk_gate_service.py \
        quant/tests/unit/risk/test_risk_gate_service.py
git commit -m "feat(l5): add risk_gate_service with three-regime market state machine and four checks"
```

---

## Task 2: Python HTTP interface — `POST /api/v1/risk/check`

**Files:**
- Modify: `quant/src/interfaces/http/schemas.py`
- Create: `quant/src/interfaces/http/routes_risk.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/src/interfaces/http/app.py`

### Context

Follow the exact same pattern as `routes_portfolio.py` / `get_portfolio_optimize_service()`.

Look at how `PortfolioOptimizeRequest`, `PortfolioOptimizeResponse`, and `get_portfolio_optimize_service` are structured — `routes_risk.py` follows that exactly.

The `RiskCheckResponse` must be a passthrough Pydantic model (all fields `Any` or loosely typed is fine, but mirroring existing responses with explicit models is preferred). Given the `data` structure is complex, use a nested model approach.

`prev_weights` is optional in the request (defaults to `{}`).

### Steps

- [ ] **Step 1: Add Pydantic schemas to `schemas.py`**

Append to `quant/src/interfaces/http/schemas.py`:

```python
class RiskCheckRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")
    target_weights: dict[str, float] = Field(
        description="目标权重 {symbol: weight}，由 L4 portfolio optimize 输出"
    )
    prev_weights: dict[str, float] | None = Field(
        default=None,
        description="上期权重 {symbol: weight}；缺省时视为从零建仓（换手率 = 1.0）",
    )


class RiskCheckItem(BaseModel):
    name: str
    value: float
    threshold: float
    passed: bool


class RiskCheckData(BaseModel):
    as_of: str
    risk_gate: str
    regime: str
    regime_vol: float | None
    regime_vol_source: str
    checks: list[RiskCheckItem]
    block_codes: list[str]


class RiskCheckResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: RiskCheckData
    warnings: list[dict]
    errors: list[dict]
```

Also update the import at the top of `schemas.py` — `from typing import Literal` is already there; no new imports needed.

- [ ] **Step 2: Add dependency to `dependencies.py`**

Add after the existing `get_portfolio_optimize_service` function (around line 134):

```python
RiskCheckService = Callable[..., dict]


def get_risk_check_service() -> RiskCheckService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of, target_weights, prev_weights: run_risk_check(
        as_of=as_of,
        target_weights=target_weights,
        prev_weights=prev_weights,
        bar_store=bar_store,
    )
```

Also add the import at the top of `dependencies.py` alongside the other application imports:

```python
from application.risk.risk_gate_service import run_risk_check
```

- [ ] **Step 3: Create `routes_risk.py`**

Create `quant/src/interfaces/http/routes_risk.py`:

```python
from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    RiskCheckService,
    get_risk_check_service,
)
from interfaces.http.schemas import (
    RiskCheckRequest,
    RiskCheckResponse,
)

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.post(
    "/check",
    summary="L5 风险门控检查",
    description=(
        "对 L4 目标权重执行风险硬约束检查。"
        "自动检测市场状态（normal/warning/crisis）并应用对应阈值，"
        "执行四项检查：组合年化波动率、单标的集中度、行业集中度、单日换手率。"
        "任意一项超阈值返回 risk_gate=block，status=warning。"
    ),
    response_description="风险门控结果，含市场状态、各项检查明细与拒单码",
)
def post_risk_check(
    req: RiskCheckRequest,
    service: RiskCheckService = Depends(get_risk_check_service),
) -> RiskCheckResponse:
    return RiskCheckResponse.model_validate(
        service(req.as_of, req.target_weights, req.prev_weights)
    )
```

- [ ] **Step 4: Register router in `app.py`**

In `quant/src/interfaces/http/app.py`, add the import and `include_router` call:

```python
from interfaces.http.routes_risk import router as risk_router
```

And inside `create_app()`, after `app.include_router(signal_router)`:

```python
app.include_router(risk_router)
```

- [ ] **Step 5: Run tests to confirm nothing broke**

```bash
cd quant && uv run python -m pytest -q
```

Expected: All tests pass.

- [ ] **Step 6: Run lint**

```bash
cd quant && uv run ruff check .
```

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add quant/src/interfaces/http/schemas.py \
        quant/src/interfaces/http/routes_risk.py \
        quant/src/interfaces/http/dependencies.py \
        quant/src/interfaces/http/app.py
git commit -m "feat(l5): add POST /api/v1/risk/check HTTP endpoint"
```

---

## Task 3: Daily pipeline integration + CLI fixture

**Files:**
- Modify: `quant/src/application/daily_run_service.py`
- Modify: `quant/src/interfaces/http/schemas.py` (add `risk_gate` field to `DailyRunData`)
- Create: `quant/tests/fixtures/cli_output/valid/risk_check_ok.json`
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`

### Context

In `daily_run_service.py`, the existing `portfolio` variable holds the output dict from `run_portfolio_optimize()` (specifically `portfolio_result.get("data")`). After computing `portfolio`, call `run_risk_check()` with weights extracted from `portfolio["target_weights"]`.

`DailyRunData` in `schemas.py` currently has `signal_matrix: SignalMatrix | None = None`. Add `portfolio: dict | None = None` and `risk_gate: dict | None = None` after it.

The fixture `risk_check_ok.json` feeds the `make validate-cli-output` CI check. It must satisfy `CLI_OUTPUT_SCHEMA.json` (envelope fields required, `source="system"`, `advice_only=false`, `decision_weight=1`).

### Steps

- [ ] **Step 1: Write a test for pipeline integration**

Add to `quant/tests/unit/test_daily_run_service.py`:

```python
def test_daily_run_includes_risk_gate():
    """daily run output must include data.risk_gate when portfolio succeeds."""
    from application.daily_run_service import run_daily

    result = run_daily(as_of="2026-04-01", root=None, bar_store=None)
    data = result["data"]
    # risk_gate may be None only if portfolio is None; if portfolio exists, risk_gate must be a dict
    if data.get("portfolio") is not None:
        assert data.get("risk_gate") is not None
        assert "risk_gate" in data["risk_gate"]  # "pass" or "block"
        assert "regime" in data["risk_gate"]
        assert "checks" in data["risk_gate"]
```

- [ ] **Step 2: Run the new test — expect FAIL**

```bash
cd quant && uv run python -m pytest tests/unit/test_daily_run_service.py::test_daily_run_includes_risk_gate -v
```

Expected: FAIL — `KeyError: 'risk_gate'` or AssertionError.

- [ ] **Step 3: Update `daily_run_service.py`**

Add the import at the top of `daily_run_service.py` alongside other imports:

```python
from application.risk.risk_gate_service import run_risk_check
```

After the `portfolio` computation block (after the `except Exception` that appends `PORTFOLIO_OPTIMIZATION_FAILED`), add:

```python
    risk_gate_result = None
    if portfolio is not None:
        try:
            risk_gate_result = run_risk_check(
                as_of=as_of,
                target_weights={r["symbol"]: r["weight"] for r in portfolio["target_weights"]},
                prev_weights={},   # Phase 1: no historical weights
                bar_store=bar_store,
            )
        except Exception:
            _logger.warning("daily run: risk gate failed", exc_info=True)
            warnings.append({
                "code": "RISK_GATE_FAILED",
                "message": "L5 risk gate computation failed; risk_gate set to null",
            })
```

Update the `return ok_output(...)` call's `data` dict to add `portfolio` and `risk_gate`:

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
            "risk_gate": risk_gate_result.get("data") if risk_gate_result else None,
        },
        warnings=warnings,
    )
```

- [ ] **Step 4: Update `DailyRunData` in `schemas.py`**

Find the existing `DailyRunData` class (around line 349) and add two fields:

```python
class DailyRunData(BaseModel):
    as_of: str
    data_manifest_id: str
    factor_snapshot: FactorSnapshot
    execution_plan: ExecutionPlan
    l2_decision: L2Decision
    signal_matrix: SignalMatrix | None = None
    portfolio: dict | None = None
    risk_gate: dict | None = None
```

- [ ] **Step 5: Run the new test — expect PASS**

```bash
cd quant && uv run python -m pytest tests/unit/test_daily_run_service.py -v
```

Expected: All tests in this file pass.

- [ ] **Step 6: Create CLI fixture**

Create `quant/tests/fixtures/cli_output/valid/risk_check_ok.json`:

```json
{
  "schema_version": "1.0.0",
  "command": "hf risk check",
  "run_id": "run_20260404_abc12345",
  "status": "ok",
  "generated_at": "2026-04-04T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-04",
    "risk_gate": "pass",
    "regime": "normal",
    "regime_vol": 0.182,
    "regime_vol_source": "benchmark",
    "checks": [
      {"name": "portfolio_vol",    "value": 0.22, "threshold": 0.30, "passed": true},
      {"name": "single_asset_max", "value": 0.28, "threshold": 0.35, "passed": true},
      {"name": "industry_max",     "value": 0.35, "threshold": 0.45, "passed": true},
      {"name": "turnover",         "value": 0.45, "threshold": 0.80, "passed": true}
    ],
    "block_codes": []
  },
  "warnings": [],
  "errors": []
}
```

- [ ] **Step 7: Validate fixture**

```bash
make validate-cli-output-one FILE=quant/tests/fixtures/cli_output/valid/risk_check_ok.json
```

Expected: `✓ valid` (exit code 0).

- [ ] **Step 8: Update `CLI_OUTPUT_EXAMPLES.md`**

Append a new section to `docs/CLI_OUTPUT_EXAMPLES.md` (after the last existing example section):

```markdown
## hf risk check（L5 风险门控）

```bash
hf risk check --as-of 2026-04-04
hf risk check --as-of 2026-04-04 --output table
```

Pass 示例（`status=ok`，`risk_gate=pass`）：

```json
{
  "schema_version": "1.0.0",
  "command": "hf risk check",
  "run_id": "run_20260404_abc12345",
  "status": "ok",
  "generated_at": "2026-04-04T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-04",
    "risk_gate": "pass",
    "regime": "normal",
    "regime_vol": 0.182,
    "regime_vol_source": "benchmark",
    "checks": [
      {"name": "portfolio_vol",    "value": 0.22, "threshold": 0.30, "passed": true},
      {"name": "single_asset_max", "value": 0.28, "threshold": 0.35, "passed": true},
      {"name": "industry_max",     "value": 0.35, "threshold": 0.45, "passed": true},
      {"name": "turnover",         "value": 0.45, "threshold": 0.80, "passed": true}
    ],
    "block_codes": []
  },
  "warnings": [],
  "errors": []
}
```
```

- [ ] **Step 9: Run full test suite + CI gate**

```bash
cd quant && uv run python -m pytest -q && make validate-cli-output
```

Expected: All tests pass, all fixtures valid.

- [ ] **Step 10: Commit**

```bash
git add quant/src/application/daily_run_service.py \
        quant/src/interfaces/http/schemas.py \
        quant/tests/fixtures/cli_output/valid/risk_check_ok.json \
        docs/CLI_OUTPUT_EXAMPLES.md
git commit -m "feat(l5): integrate risk gate into daily pipeline; add CLI fixture and example"
```

---

## Task 4: Rust CLI — `hf risk check`

**Files:**
- Create: `cli/src/cmd/risk.rs`
- Create: `cli/src/application/handlers/risk_check.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/cmd/mod.rs`

### Context

Follow the exact pattern of `hf portfolio optimize`:
- `cmd/portfolio.rs` → `cmd/risk.rs`
- `handlers/portfolio_optimize.rs` → `handlers/risk_check.rs`
- `http_client::post_portfolio_optimize()` → `http_client::post_risk_check()`
- `table_renderer::render_portfolio_optimize_table()` → `table_renderer::render_risk_check_table()`

The HTTP POST body is `{"as_of": "<date>"}` (no `prev_weights` — CLI Phase 1 does not expose prev_weights; the server defaults to `{}`).

The table output shows: regime line, then a 4-row checks table, then the gate result.

### Steps

- [ ] **Step 1: Add `RiskCheckRequest` to `requests.rs`**

Append to `cli/src/application/requests.rs`:

```rust
#[derive(Debug, Clone)]
pub struct RiskCheckRequest {
    pub as_of: String,
    pub output: String,
}
```

Also add `RiskCheck(RiskCheckRequest)` to the `AppCommand` enum:

```rust
pub enum AppCommand {
    // ... existing variants ...
    RiskCheck(RiskCheckRequest),
}
```

- [ ] **Step 2: Create `cmd/risk.rs`**

Create `cli/src/cmd/risk.rs`:

```rust
use crate::application::requests::RiskCheckRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(
    about = "L5 风险门控：对 L4 目标权重执行硬约束检查（需 quant HTTP 服务）"
)]
pub struct RiskArgs {
    #[command(subcommand)]
    pub command: RiskSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum RiskSubcommand {
    #[command(
        about = "执行风险门控检查，返回 risk_gate=pass|block + 四项检查明细",
        long_about = "调用 POST /api/v1/risk/check。\
自动从最新 L3 signal snapshot 获取目标权重（通过 L4 portfolio optimize 中转）。\
检测市场状态（normal/warning/crisis）并应用分态阈值，\
执行：组合年化波动率、单标的集中度、行业集中度、单日换手率四项检查。"
    )]
    Check(CheckArgs),
}

const CHECK_AFTER_HELP: &str = "\
示例:
  hf risk check --as-of 2026-04-04
  hf risk check --as-of 2026-04-04 --output table

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- risk check --as-of 2026-04-04

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务（如 http://127.0.0.1:8000）";

#[derive(Debug, Args)]
#[command(after_long_help = CHECK_AFTER_HELP)]
pub struct CheckArgs {
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
        help = "输出形式：json = 标准 CLI envelope（默认）；table = 终端表格"
    )]
    pub output: String,
}

impl From<CheckArgs> for RiskCheckRequest {
    fn from(args: CheckArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
```

- [ ] **Step 3: Create `handlers/risk_check.rs`**

Create `cli/src/application/handlers/risk_check.rs`:

```rust
use crate::application::requests::RiskCheckRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_risk_check_table;

pub fn handle(args: RiskCheckRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_risk_check(
        &cfg.server_url,
        &args.as_of,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_risk_check_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for risk check: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
```

- [ ] **Step 4: Add `post_risk_check` to `http_client.rs`**

Append to `cli/src/infrastructure/http_client.rs` (after `post_portfolio_optimize`):

```rust
pub fn post_risk_check(
    server_url: &str,
    as_of: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/api/v1/risk/check",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({ "as_of": as_of, "target_weights": {} }))
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

**Note:** The CLI sends `target_weights: {}` — the server will derive weights from L3 signal snapshot automatically (same as `hf portfolio optimize` with no explicit alpha). This is acceptable for Phase 1 (the server-side `run_risk_check` receives `{}` and proceeds; the interesting path is `hf portfolio optimize | hf risk check`). If the server raises a 422 on empty weights, the handler will return an `AppError::Upstream` — update the server-side to handle empty `target_weights` gracefully in that case by deriving from L3. For now, the CLI fixture test will confirm the JSON envelope shape.

- [ ] **Step 5: Add `render_risk_check_table` to `table_renderer.rs`**

Append to `cli/src/infrastructure/table_renderer.rs`:

```rust
pub fn render_risk_check_table(payload: &Value) -> String {
    let data = payload.get("data");
    let as_of = as_str(data.and_then(|d| d.get("as_of")));
    let risk_gate = as_str(data.and_then(|d| d.get("risk_gate")));
    let regime = as_str(data.and_then(|d| d.get("regime")));
    let regime_vol = data
        .and_then(|d| d.get("regime_vol"))
        .and_then(Value::as_f64)
        .map(|v| format!("{:.1}%", v * 100.0))
        .unwrap_or_else(|| "n/a".to_string());

    let mut checks_table = Table::new();
    checks_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("检查项"),
            Cell::new("实际值"),
            Cell::new("阈值"),
            Cell::new("状态"),
        ]);

    if let Some(checks) = data
        .and_then(|d| d.get("checks"))
        .and_then(Value::as_array)
    {
        for check in checks {
            let name = as_str(check.get("name"));
            let value = check.get("value").and_then(Value::as_f64).unwrap_or(0.0);
            let threshold = check.get("threshold").and_then(Value::as_f64).unwrap_or(0.0);
            let passed = check.get("passed").and_then(Value::as_bool).unwrap_or(false);
            let status_str = if passed { "✓" } else { "✗ BLOCK" };
            checks_table.add_row(vec![
                name,
                format!("{:.1}%", value * 100.0),
                format!("{:.1}%", threshold * 100.0),
                status_str.to_string(),
            ]);
        }
    }

    let gate_line = if risk_gate == "pass" {
        "风险门控: PASS ✓".to_string()
    } else {
        let block_codes = data
            .and_then(|d| d.get("block_codes"))
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join(", ")
            })
            .unwrap_or_default();
        format!("风险门控: BLOCK ✗  [{block_codes}]")
    };

    format!(
        "风险门控检查（{as_of}）  市场状态: {regime}（波动率={regime_vol}）\n{}\n{}\n",
        checks_table, gate_line
    )
}
```

- [ ] **Step 6: Wire up `mod.rs`, `dispatch.rs`, `cmd/mod.rs`**

In `cli/src/application/handlers/mod.rs`, add:

```rust
pub mod risk_check;
```

In `cli/src/application/dispatch.rs`, add the import and arm:

```rust
use crate::application::handlers::{
    // ... existing ...
    risk_check,
};
```

And in the `match` block:

```rust
AppCommand::RiskCheck(args) => risk_check::handle(args),
```

In `cli/src/cmd/mod.rs`:

Add `pub mod risk;` at the top with the other modules.

Add `Risk` to `Commands`:

```rust
/// L5 风险门控：目标权重硬约束检查（需 quant 服务与 ~/.hiveflow/config.toml）
Risk(risk::RiskArgs),
```

Add the `From` arm in `impl From<Cli> for AppCommand`:

```rust
Commands::Risk(args) => match args.command {
    risk::RiskSubcommand::Check(check) => AppCommand::RiskCheck(check.into()),
},
```

- [ ] **Step 7: Build Rust CLI**

```bash
cd cli && cargo build 2>&1 | tail -5
```

Expected: `Finished dev [unoptimized + debuginfo] target(s)` with no errors.

- [ ] **Step 8: Run Rust tests**

```bash
cd cli && cargo test 2>&1 | tail -10
```

Expected: All Rust tests pass.

- [ ] **Step 9: Smoke-test help output**

```bash
./cli/target/debug/hf risk --help
./cli/target/debug/hf risk check --help
```

Expected: Both print usage without errors.

- [ ] **Step 10: Run full CI gate**

```bash
make check
```

Expected: All Python tests pass, all fixtures valid, Rust tests pass, architecture checks pass.

- [ ] **Step 11: Commit**

```bash
git add cli/src/cmd/risk.rs \
        cli/src/application/handlers/risk_check.rs \
        cli/src/infrastructure/http_client.rs \
        cli/src/infrastructure/table_renderer.rs \
        cli/src/application/requests.rs \
        cli/src/application/handlers/mod.rs \
        cli/src/application/dispatch.rs \
        cli/src/cmd/mod.rs
git commit -m "feat(l5): add hf risk check CLI command (json|table)"
```

---

## Task 5: Update AGENTS.md

**Files:**
- Modify: `AGENTS.md`

### Steps

- [ ] **Step 1: Update AGENTS.md**

Find the L5 row in the implementation status table and change it from:

```
| L5 | 风险门控 | 🔲 未开始 | — |
```

to:

```
| L5 | 风险门控 | ✅ Phase 1 完成 | 三态市场状态机（normal/warning/crisis，基于近 20 日年化波动率）+ 四项硬约束检查（组合年化波动率、单标的/行业集中度、单日换手率）；`POST /api/v1/risk/check` + `hf risk check --as-of DATE [--output json\|table]`；daily pipeline 集成（data.risk_gate 字段） |
```

Update **当前工作位置**:

```
**当前工作位置**：L5 Phase 1（三态风险门控 + 四项硬约束检查）已合入 master → L5.5 预交易模拟待 spec；或 L5 Phase 2（状态持久化 / warning 升级条件 / 因子暴露集中度检查）待 spec。
```

- [ ] **Step 2: Run final CI gate**

```bash
make check
```

Expected: All checks pass.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md L5 Phase 1 完成度"
```
