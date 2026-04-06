# L7 Walk-Forward Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 L7 回测/验证层的 Walk-Forward 模块，验证 L2→L5 链路在滚动窗口上的组合表现，输出 Go/No-Go 裁定。

**Architecture:** 独立 `WalkForwardService` 复用 `run_daily()`，从 `portfolio.target_weights` 读权重后用 `bar_store.list_bars()` 计算日收益；HTTP `POST /v1/walk-forward/run` + Rust CLI `hf walk-forward run`。

**Tech Stack:** Python (FastAPI), Rust (clap + reqwest), pytest, TimescaleDB

---

## 文件结构总览

| 文件 | 职责 |
|------|------|
| `quant/src/application/walk_forward_service.py` | 窗口生成、日收益计算、指标聚合、闸门判定 |
| `quant/tests/unit/test_walk_forward_service.py` | service 各函数 unit test |
| `quant/src/interfaces/http/routes_walk_forward.py` | HTTP 路由，thin wrapper |
| `quant/tests/contract/test_http_walk_forward.py` | HTTP 契约测试 |
| `cli/src/application/handlers/walk_forward.rs` | Rust handler，编排 + 输出格式 |
| `cli/src/application/requests.rs` | `WalkForwardRequest` 结构 |
| `cli/src/cmd/walk_forward.rs` | clap Args + `From` 实现 |
| `cli/src/application/handlers/mod.rs` | 注册 walk_forward 模块 |
| `cli/src/application/dispatch.rs` | 分发 `AppCommand::WalkForward` |
| `cli/src/cmd/mod.rs` | 注册顶层 `Commands::WalkForward` |
| `cli/src/infrastructure/http_client.rs` | `post_walk_forward_run()` 函数 |

---

## Task 1：Python Service — Window 生成与日收益计算

**Files:**
- Create: `quant/src/application/walk_forward_service.py`
- Test: `quant/tests/unit/test_walk_forward_service.py`

### Step 1: 写 window 生成的失败测试

创建 `quant/tests/unit/test_walk_forward_service.py`：

```python
from datetime import date, timedelta
import pytest
from application.walk_forward_service import generate_windows


def test_generate_windows_basic():
    """Test 3-window rolling with step=21"""
    windows = generate_windows(
        start_date="2025-01-01",
        end_date="2025-09-30",
        warm_up_days=180,
        test_window_days=63,
        step_days=21,
    )
    assert len(windows) >= 1
    assert windows[0]["warm_start"] == "2025-01-01"
    assert windows[0]["warm_end"] is not None
    assert windows[0]["test_start"] is not None
    assert windows[0]["test_end"] is not None


def test_generate_windows_order():
    """Windows 应按时间顺序，无重叠"""
    windows = generate_windows(
        start_date="2025-01-01",
        end_date="2025-12-31",
        warm_up_days=180,
        test_window_days=63,
        step_days=21,
    )
    prev_test_end = None
    for w in windows:
        if prev_test_end:
            # 下一个 warm_start 应接上一个 test_end
            assert w["warm_start"] <= w["test_start"]
        prev_test_end = w["test_end"]
```

### Step 2: 运行确认失败

```bash
cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/test_walk_forward_service.py::test_generate_windows_basic -v
```

Expected: 收集错误（模块不存在）

### Step 3: 实现 `walk_forward_service.py`

```python
# quant/src/application/walk_forward_service.py
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from application.contracts.cli_output import ok_output
from application.daily_run_service import run_daily
from domain.market_data.sse_calendar import is_sse_trading_day


_ANNUALIZATION_DAYS = 252
_DEFAULT_THRESHOLDS = {
    "annualized_return_mean_min": 0.06,
    "max_drawdown_max_max": 0.20,
    "sharpe_min_min": 0.5,
}


def generate_windows(
    start_date: str,
    end_date: str,
    warm_up_days: int,
    test_window_days: int,
    step_days: int,
) -> list[dict]:
    """
    生成滚动窗口列表。
    
    Args:
        start_date: "YYYY-MM-DD"
        end_date: "YYYY-MM-DD"
        warm_up_days: calendar days for warm-up
        test_window_days: calendar days for testing
        step_days: calendar days to roll forward
    
    Returns:
        [{"warm_start", "warm_end", "test_start", "test_end"}, ...]
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    
    windows = []
    current_test_start = start + timedelta(days=warm_up_days)
    
    while current_test_start < end:
        test_end = current_test_start + timedelta(days=test_window_days)
        if test_end > end:
            test_end = end
        
        warm_start = current_test_start - timedelta(days=warm_up_days)
        warm_end = current_test_start - timedelta(days=1)
        
        windows.append({
            "warm_start": warm_start.isoformat(),
            "warm_end": warm_end.isoformat(),
            "test_start": current_test_start.isoformat(),
            "test_end": test_end.isoformat(),
        })
        
        current_test_start += timedelta(days=step_days)
    
    return windows


def _coerce_finite_float(value: Any) -> float | None:
    """Convert to float, return None if NaN or inf."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _compute_daily_return(
    weights: dict[str, float],
    as_of: str,
    bar_store: Any,
    cost_bp: float,
) -> float | None:
    """
    从 bar_store 查 T 和 T+1 收盘价，计算加权日收益。
    
    Returns:
        Daily net return (after cost), or None if T+1 bar missing/错误.
    """
    if not weights:
        return None
    
    try:
        # 获取 as_of 和次日的 bar
        as_of_date = date.fromisoformat(as_of)
        next_date = as_of_date + timedelta(days=1)
        
        bars = bar_store.list_bars(
            symbols=list(weights.keys()),
            timeframe="1d",
            start_date=as_of,
            end_date=next_date.isoformat(),
            limit=1000,
        )
        
        if not bars:
            return None
        
        # 构造 {symbol: {date: close}} 映射
        close_map: dict[str, dict[str, float]] = {}
        for bar in bars:
            symbol = bar.get("symbol")
            bar_date = bar.get("date")
            close = _coerce_finite_float(bar.get("close"))
            if symbol and bar_date and close is not None:
                if symbol not in close_map:
                    close_map[symbol] = {}
                close_map[symbol][bar_date] = close
        
        # 计算加权日收益
        weighted_return = 0.0
        total_weight = 0.0
        has_valid_return = False
        
        for symbol, weight in weights.items():
            if weight <= 0:
                continue
            
            as_of_close = close_map.get(symbol, {}).get(as_of)
            next_close = close_map.get(symbol, {}).get(next_date.isoformat())
            
            if as_of_close and next_close and as_of_close > 0:
                daily_ret = next_close / as_of_close - 1.0
                weighted_return += weight * daily_ret
                total_weight += weight
                has_valid_return = True
        
        if not has_valid_return or total_weight <= 0:
            return None
        
        # 归一化权重并扣除成本
        gross_return = weighted_return / total_weight if total_weight > 0 else 0.0
        cost = cost_bp / 10000.0
        net_return = gross_return - cost
        
        return net_return
    except Exception:
        return None


def _build_window_metrics(daily_returns: list[float]) -> dict:
    """从日收益列表计算指标。"""
    if not daily_returns:
        return {
            "cumulative_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }
    
    equity_curve = 1.0
    peak = 1.0
    max_drawdown = 0.0
    wins = 0
    
    for daily_ret in daily_returns:
        equity_curve *= 1.0 + daily_ret
        peak = max(peak, equity_curve)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity_curve) / peak)
        if daily_ret > 0:
            wins += 1
    
    cumulative_return = equity_curve - 1.0
    annualized_return = (1.0 + cumulative_return) ** (_ANNUALIZATION_DAYS / len(daily_returns)) - 1.0 if daily_returns else 0.0
    
    mean_return = sum(daily_returns) / len(daily_returns)
    if len(daily_returns) > 1:
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        annualized_vol = math.sqrt(variance) * math.sqrt(_ANNUALIZATION_DAYS)
    else:
        annualized_vol = 0.0
    
    sharpe = (mean_return * _ANNUALIZATION_DAYS) / annualized_vol if annualized_vol > 0 else 0.0
    win_rate = wins / len(daily_returns) if daily_returns else 0.0
    
    return {
        "cumulative_return": round(cumulative_return, 6),
        "annualized_return": round(annualized_return, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "win_rate": round(win_rate, 6),
    }


def _run_test_window(
    test_start: str,
    test_end: str,
    bar_store: Any,
    cost_bp: float,
) -> dict:
    """运行测试窗口，逐日调用 run_daily 并计算收益。"""
    daily_returns: list[float] = []
    cost_total_bp = 0.0
    days_run = 0
    errors: list[dict] = []
    
    current = date.fromisoformat(test_start)
    end = date.fromisoformat(test_end)
    
    while current <= end:
        as_of = current.isoformat()
        
        if not is_sse_trading_day(as_of):
            current += timedelta(days=1)
            continue
        
        try:
            # 调用 run_daily（无 bar_store 时用 deterministic snapshot）
            result = run_daily(as_of=as_of, root=None, bar_store=bar_store)
            data = result.get("data", {})
            
            portfolio = data.get("portfolio")
            if portfolio is None:
                current += timedelta(days=1)
                continue
            
            target_weights = {
                item["symbol"]: item["weight"]
                for item in portfolio.get("target_weights", [])
            }
            
            if target_weights:
                daily_ret = _compute_daily_return(
                    weights=target_weights,
                    as_of=as_of,
                    bar_store=bar_store,
                    cost_bp=cost_bp,
                )
                if daily_ret is not None:
                    daily_returns.append(daily_ret)
                    cost_total_bp += cost_bp
                    days_run += 1
        except Exception as exc:
            errors.append({
                "date": as_of,
                "error": str(exc),
            })
        
        current += timedelta(days=1)
    
    metrics = _build_window_metrics(daily_returns)
    return {
        "days_run": days_run,
        "cost_total_bp": round(cost_total_bp, 2),
        **metrics,
        "errors": errors,
    }


def _aggregate_windows(windows_results: list[dict]) -> dict:
    """跨窗口聚合指标。"""
    if not windows_results:
        return {
            "window_count": 0,
            "annualized_return": {"mean": 0.0, "min": 0.0, "max": 0.0},
            "sharpe": {"mean": 0.0, "min": 0.0, "max": 0.0},
            "max_drawdown": {"mean": 0.0, "min": 0.0, "max": 0.0},
        }
    
    def _aggregate_metric(metric_name: str) -> dict:
        values = [w[metric_name] for w in windows_results if metric_name in w]
        return {
            "mean": round(sum(values) / len(values), 6) if values else 0.0,
            "min": round(min(values), 6) if values else 0.0,
            "max": round(max(values), 6) if values else 0.0,
        }
    
    return {
        "window_count": len(windows_results),
        "annualized_return": _aggregate_metric("annualized_return"),
        "sharpe": _aggregate_metric("sharpe"),
        "max_drawdown": _aggregate_metric("max_drawdown"),
    }


def _gate_check(aggregate: dict, thresholds: dict) -> tuple[str, list[str]]:
    """对照闸门阈值，返回 (verdict, failed_gates)。"""
    failed_gates = []
    
    ann_return_mean = aggregate.get("annualized_return", {}).get("mean", 0.0)
    if ann_return_mean < thresholds.get("annualized_return_mean_min", 0.06):
        failed_gates.append(
            f"annualized_return.mean ({ann_return_mean:.4f}) < {thresholds['annualized_return_mean_min']:.4f}"
        )
    
    mdd_max = aggregate.get("max_drawdown", {}).get("max", 0.0)
    if mdd_max > thresholds.get("max_drawdown_max_max", 0.20):
        failed_gates.append(
            f"max_drawdown.max ({mdd_max:.4f}) > {thresholds['max_drawdown_max_max']:.4f}"
        )
    
    sharpe_min = aggregate.get("sharpe", {}).get("min", 0.0)
    if sharpe_min < thresholds.get("sharpe_min_min", 0.5):
        failed_gates.append(
            f"sharpe.min ({sharpe_min:.4f}) < {thresholds['sharpe_min_min']:.4f}"
        )
    
    verdict = "pass" if not failed_gates else "no_go"
    return verdict, failed_gates


def run_walk_forward(
    start_date: str,
    end_date: str,
    warm_up_days: int = 180,
    test_window_days: int = 63,
    step_days: int = 21,
    cost_bp: float = 0.0,
    bar_store: Any = None,
    thresholds: dict | None = None,
) -> dict:
    """主入口函数。"""
    if thresholds is None:
        thresholds = _DEFAULT_THRESHOLDS
    
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    
    windows = generate_windows(
        start_date=start_date,
        end_date=end_date,
        warm_up_days=warm_up_days,
        test_window_days=test_window_days,
        step_days=step_days,
    )
    
    windows_results = []
    for w in windows:
        result = _run_test_window(
            test_start=w["test_start"],
            test_end=w["test_end"],
            bar_store=bar_store,
            cost_bp=cost_bp,
        )
        windows_results.append({**w, **result})
    
    aggregate = _aggregate_windows(windows_results)
    verdict, failed_gates = _gate_check(aggregate, thresholds)
    
    return ok_output(
        command="hf walk-forward run",
        run_id=f"wf_{start_date.replace('-', '')}_{end_date.replace('-', '')}",
        data={
            "start_date": start_date,
            "end_date": end_date,
            "warm_up_days": warm_up_days,
            "test_window_days": test_window_days,
            "step_days": step_days,
            "cost_bp": cost_bp,
            "thresholds": thresholds,
            "windows": windows_results,
            "aggregate": aggregate,
            "verdict": verdict,
            "failed_gates": failed_gates,
        },
    )
```

### Step 4: 运行测试确认通过

```bash
cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/test_walk_forward_service.py -v
```

Expected: PASS

### Step 5: 添加更多 unit tests

在 `quant/tests/unit/test_walk_forward_service.py` 中增加：

```python
from unittest.mock import MagicMock
from application.walk_forward_service import _compute_daily_return, _build_window_metrics, _gate_check


def test_compute_daily_return_full_coverage():
    """两个标的，T 和 T+1 都有 bar，都有涨幅"""
    bar_store = MagicMock()
    bar_store.list_bars.return_value = [
        {"symbol": "600519.SH", "date": "2026-04-06", "close": 100.0},
        {"symbol": "600519.SH", "date": "2026-04-07", "close": 102.0},
        {"symbol": "000300.SH", "date": "2026-04-06", "close": 5000.0},
        {"symbol": "000300.SH", "date": "2026-04-07", "close": 5100.0},
    ]
    weights = {"600519.SH": 0.5, "000300.SH": 0.5}
    result = _compute_daily_return(weights, "2026-04-06", bar_store, cost_bp=0)
    # (0.5 * 2/100 + 0.5 * 100/5000) = 0.5 * 0.02 + 0.5 * 0.02 = 0.02
    assert result is not None
    assert abs(result - 0.02) < 0.0001


def test_compute_daily_return_with_cost():
    """成本扣除"""
    bar_store = MagicMock()
    bar_store.list_bars.return_value = [
        {"symbol": "600519.SH", "date": "2026-04-06", "close": 100.0},
        {"symbol": "600519.SH", "date": "2026-04-07", "close": 102.0},
    ]
    weights = {"600519.SH": 1.0}
    result = _compute_daily_return(weights, "2026-04-06", bar_store, cost_bp=10)
    # gross = 2%, cost = 10 bp = 0.1%, net = 1.9%
    expected = 0.02 - 0.001
    assert result is not None
    assert abs(result - expected) < 0.0001


def test_compute_daily_return_missing_bar():
    """T+1 无 bar，返回 None"""
    bar_store = MagicMock()
    bar_store.list_bars.return_value = [
        {"symbol": "600519.SH", "date": "2026-04-06", "close": 100.0},
    ]
    weights = {"600519.SH": 1.0}
    result = _compute_daily_return(weights, "2026-04-06", bar_store, cost_bp=0)
    assert result is None


def test_build_window_metrics_full_window():
    """正常窗口"""
    returns = [0.01, 0.02, -0.01, 0.015, 0.005]
    metrics = _build_window_metrics(returns)
    assert metrics["cumulative_return"] > 0  # 正收益
    assert 0 <= metrics["max_drawdown"] <= 1
    assert metrics["win_rate"] == 0.8  # 5 中 4 日为正


def test_gate_check_pass():
    """所有指标过关"""
    aggregate = {
        "annualized_return": {"mean": 0.12, "min": 0.05, "max": 0.20},
        "sharpe": {"mean": 1.5, "min": 0.8, "max": 2.0},
        "max_drawdown": {"mean": 0.10, "min": 0.05, "max": 0.15},
    }
    verdict, failed_gates = _gate_check(aggregate, {
        "annualized_return_mean_min": 0.06,
        "max_drawdown_max_max": 0.20,
        "sharpe_min_min": 0.5,
    })
    assert verdict == "pass"
    assert failed_gates == []


def test_gate_check_no_go_mdd():
    """MDD 超标"""
    aggregate = {
        "annualized_return": {"mean": 0.12, "min": 0.05, "max": 0.20},
        "sharpe": {"mean": 1.5, "min": 0.8, "max": 2.0},
        "max_drawdown": {"mean": 0.10, "min": 0.05, "max": 0.25},  # > 0.20
    }
    verdict, failed_gates = _gate_check(aggregate, {
        "annualized_return_mean_min": 0.06,
        "max_drawdown_max_max": 0.20,
        "sharpe_min_min": 0.5,
    })
    assert verdict == "no_go"
    assert any("max_drawdown" in gate for gate in failed_gates)
```

### Step 6: 运行全量 unit tests

```bash
cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/test_walk_forward_service.py -v
```

Expected: PASS

### Step 7: 提交

```bash
cd /Users/rongts/HiveFlow && git add quant/src/application/walk_forward_service.py quant/tests/unit/test_walk_forward_service.py && git commit -m "feat: L7 walk-forward service core implementation"
```

---

## Task 2：HTTP 端点与契约测试

**Files:**
- Create: `quant/src/interfaces/http/routes_walk_forward.py`
- Modify: `quant/src/interfaces/http/app.py`
- Create: `quant/tests/contract/test_http_walk_forward.py`

### Step 1: 写契约测试（失败）

```python
# quant/tests/contract/test_http_walk_forward.py
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from interfaces.http.app import app

client = TestClient(app)


def test_run_ok():
    """正常请求返回 200 + verdict"""
    with patch("interfaces.http.routes_walk_forward.has_db_config", return_value=True), \
         patch("interfaces.http.routes_walk_forward.open_db_connection_from_env"), \
         patch("interfaces.http.routes_walk_forward.TimescaleBarStore"), \
         patch("interfaces.http.routes_walk_forward.run_walk_forward") as mock_wf:
        mock_wf.return_value = {
            "verdict": "pass",
            "failed_gates": [],
            "windows": [],
            "aggregate": {},
            "data": {},
        }
        resp = client.post("/v1/walk-forward/run", json={
            "start_date": "2025-01-01",
            "end_date": "2026-04-01",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert "verdict" in body


def test_run_db_unavailable():
    """无 DB 配置返回 503"""
    with patch("interfaces.http.routes_walk_forward.has_db_config", return_value=False):
        resp = client.post("/v1/walk-forward/run", json={
            "start_date": "2025-01-01",
            "end_date": "2026-04-01",
        })
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "WALK_FORWARD_DB_UNAVAILABLE"


def test_run_invalid_dates():
    """start > end 返回 422"""
    with patch("interfaces.http.routes_walk_forward.has_db_config", return_value=True), \
         patch("interfaces.http.routes_walk_forward.open_db_connection_from_env"), \
         patch("interfaces.http.routes_walk_forward.TimescaleBarStore"):
        resp = client.post("/v1/walk-forward/run", json={
            "start_date": "2026-04-01",
            "end_date": "2025-01-01",
        })
    assert resp.status_code == 422
```

### Step 2: 运行确认失败

```bash
cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/contract/test_http_walk_forward.py::test_run_ok -v
```

Expected: FAIL（模块不存在）

### Step 3: 创建 HTTP 路由

```python
# quant/src/interfaces/http/routes_walk_forward.py
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from application.walk_forward_service import run_walk_forward as run_wf
from interfaces.adapters.market_data.db_connection import has_db_config, open_db_connection_from_env
from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore

router = APIRouter(prefix="/v1/walk-forward", tags=["walk-forward"])


@router.post(
    "/run",
    summary="运行 walk-forward 回测",
    description="在滚动窗口上验证 L2→L5 链路的组合表现",
)
def run_walk_forward(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    warm_up_days: int = Query(default=180, ge=1),
    test_window_days: int = Query(default=63, ge=1),
    step_days: int = Query(default=21, ge=1),
    cost_bp: float = Query(default=0.0, ge=0.0),
) -> dict:
    if not has_db_config():
        raise HTTPException(
            status_code=503,
            detail={"code": "WALK_FORWARD_DB_UNAVAILABLE", "message": "no database configured"},
        )
    
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "WALK_FORWARD_INVALID_PARAMS", "message": "start_date must be on or before end_date"},
        )
    
    try:
        bar_store = TimescaleBarStore(open_db_connection_from_env())
        return run_wf(
            start_date=start_date,
            end_date=end_date,
            warm_up_days=warm_up_days,
            test_window_days=test_window_days,
            step_days=step_days,
            cost_bp=cost_bp,
            bar_store=bar_store,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "WALK_FORWARD_INVALID_PARAMS", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "WALK_FORWARD_ERROR", "message": str(exc)},
        ) from exc
```

### Step 4: 在 app.py 中注册路由

修改 `quant/src/interfaces/http/app.py`，在路由注册部分增加：

```python
# 在现有路由注册代码之后（如 routes_factor_optimization）
from interfaces.http.routes_walk_forward import router as walk_forward_router
app.include_router(walk_forward_router)
```

### Step 5: 运行契约测试

```bash
cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/contract/test_http_walk_forward.py -v
```

Expected: PASS

### Step 6: 提交

```bash
cd /Users/rongts/HiveFlow && git add quant/src/interfaces/http/routes_walk_forward.py quant/src/interfaces/http/app.py quant/tests/contract/test_http_walk_forward.py && git commit -m "feat: L7 walk-forward HTTP endpoint + contract tests"
```

---

## Task 3：Rust CLI 实现

**Files:**
- Modify: `cli/src/application/requests.rs`
- Create: `cli/src/cmd/walk_forward.rs`
- Modify: `cli/src/cmd/mod.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Create: `cli/src/application/handlers/walk_forward.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/infrastructure/http_client.rs`

### Step 1: 添加 `WalkForwardRequest` 结构

在 `cli/src/application/requests.rs` 中添加：

```rust
pub struct WalkForwardRequest {
    pub start_date: String,
    pub end_date: String,
    pub warm_up_days: Option<u32>,
    pub test_window_days: Option<u32>,
    pub step_days: Option<u32>,
    pub cost_bp: Option<f64>,
    pub output: Option<String>,
    pub timeout_ms: Option<u64>,
}

// 在 AppCommand enum 中添加
pub enum AppCommand {
    // ... existing variants ...
    WalkForward(WalkForwardRequest),
}
```

### Step 2: 创建 walk_forward.rs 命令定义

```rust
// cli/src/cmd/walk_forward.rs
use clap::Parser;
use crate::application::requests::WalkForwardRequest;

#[derive(Parser, Debug)]
pub struct WalkForwardArgs {
    #[arg(long, help = "Start date (YYYY-MM-DD)")]
    pub start_date: String,

    #[arg(long, help = "End date (YYYY-MM-DD)")]
    pub end_date: String,

    #[arg(long, default_value = "180", help = "Warm-up days")]
    pub warm_up_days: u32,

    #[arg(long, default_value = "63", help = "Test window days")]
    pub test_window_days: u32,

    #[arg(long, default_value = "21", help = "Step days")]
    pub step_days: u32,

    #[arg(long, default_value = "0", help = "Transaction cost (basis points)")]
    pub cost_bp: f64,

    #[arg(long, default_value = "json", help = "Output format")]
    pub output: String,

    #[arg(long, help = "Request timeout (ms)")]
    pub timeout_ms: Option<u64>,
}

impl From<WalkForwardArgs> for WalkForwardRequest {
    fn from(args: WalkForwardArgs) -> Self {
        WalkForwardRequest {
            start_date: args.start_date,
            end_date: args.end_date,
            warm_up_days: Some(args.warm_up_days),
            test_window_days: Some(args.test_window_days),
            step_days: Some(args.step_days),
            cost_bp: Some(args.cost_bp),
            output: Some(args.output),
            timeout_ms: args.timeout_ms,
        }
    }
}
```

### Step 3: 在 cmd/mod.rs 中注册

```rust
// cli/src/cmd/mod.rs
pub mod walk_forward;

// 在 pub enum Commands 中添加：
pub enum Commands {
    // ... existing variants ...
    WalkForward(walk_forward::WalkForwardArgs),
}

// 在 Commands::from_args() 或相应的分发逻辑中，转换为 AppCommand
```

### Step 4: 创建 handler

```rust
// cli/src/application/handlers/walk_forward.rs
use crate::application::requests::WalkForwardRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_walk_forward_run;
use serde_json::Value;

pub fn handle(args: WalkForwardRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);

    let result = post_walk_forward_run(
        &cfg.server_url,
        &args.start_date,
        &args.end_date,
        args.warm_up_days.unwrap_or(180),
        args.test_window_days.unwrap_or(63),
        args.step_days.unwrap_or(21),
        args.cost_bp.unwrap_or(0.0),
        timeout_ms,
    )?;

    match args.output.as_deref() {
        Some("table") => print_table(&result),
        _ => println!("{}", serde_json::to_string_pretty(&result).unwrap_or_default()),
    }
    Ok(())
}

fn print_table(v: &Value) {
    let verdict = v["verdict"].as_str().unwrap_or("unknown");
    let start = v["start_date"].as_str().unwrap_or("");
    let end = v["end_date"].as_str().unwrap_or("");
    let agg = &v["aggregate"];
    let window_count = agg["window_count"].as_u64().unwrap_or(0);

    println!("Walk-Forward: {} windows | {} → {}", window_count, start, end);
    println!("Verdict: {}", verdict.to_uppercase());

    if let Some(gates) = v["failed_gates"].as_array() {
        if !gates.is_empty() {
            println!("\nFailed gates:");
            for gate in gates {
                if let Some(s) = gate.as_str() {
                    println!("  - {}", s);
                }
            }
        }
    }

    println!("\nAggregate (mean / min / max)");
    if let Some(ret) = agg["annualized_return"].as_object() {
        let mean = ret["mean"].as_f64().unwrap_or(0.0) * 100.0;
        let min = ret["min"].as_f64().unwrap_or(0.0) * 100.0;
        let max = ret["max"].as_f64().unwrap_or(0.0) * 100.0;
        println!("  Annualized:  {:.2}% / {:.2}% / {:.2}%", mean, min, max);
    }
    if let Some(sharpe) = agg["sharpe"].as_object() {
        let mean = sharpe["mean"].as_f64().unwrap_or(0.0);
        let min = sharpe["min"].as_f64().unwrap_or(0.0);
        let max = sharpe["max"].as_f64().unwrap_or(0.0);
        println!("  Sharpe:      {:.2} / {:.2} / {:.2}", mean, min, max);
    }
    if let Some(mdd) = agg["max_drawdown"].as_object() {
        let mean = mdd["mean"].as_f64().unwrap_or(0.0) * 100.0;
        let min = mdd["min"].as_f64().unwrap_or(0.0) * 100.0;
        let max = mdd["max"].as_f64().unwrap_or(0.0) * 100.0;
        println!("  Max Drawdown: {:.2}% / {:.2}% / {:.2}%", mean, min, max);
    }
}
```

### Step 5: 在 handlers/mod.rs 中注册

```rust
// cli/src/application/handlers/mod.rs
pub mod walk_forward;
// ...other modules
```

### Step 6: 在 dispatch.rs 中分发

```rust
// cli/src/application/dispatch.rs
// 在 match cmd 的分发逻辑中添加：
AppCommand::WalkForward(req) => walk_forward::handle(req),
```

### Step 7: 在 http_client.rs 中添加请求函数

```rust
// cli/src/infrastructure/http_client.rs
pub fn post_walk_forward_run(
    server_url: &str,
    start_date: &str,
    end_date: &str,
    warm_up_days: u32,
    test_window_days: u32,
    step_days: u32,
    cost_bp: f64,
    timeout_ms: u64,
) -> Result<serde_json::Value, AppError> {
    let url = format!("{}/v1/walk-forward/run", server_url);
    
    let query_params = vec![
        ("start_date", start_date),
        ("end_date", end_date),
        ("warm_up_days", &warm_up_days.to_string()),
        ("test_window_days", &test_window_days.to_string()),
        ("step_days", &step_days.to_string()),
        ("cost_bp", &cost_bp.to_string()),
    ];

    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .query(&query_params)
        .timeout(std::time::Duration::from_millis(timeout_ms))
        .send()
        .map_err(|e| AppError::Upstream(e.to_string()))?;

    match resp.status() {
        reqwest::StatusCode::OK => {
            let body = resp.text().map_err(|e| AppError::Upstream(e.to_string()))?;
            serde_json::from_str(&body).map_err(|e| AppError::Upstream(e.to_string()))
        }
        status => {
            let body = resp.text().unwrap_or_default();
            Err(AppError::Upstream(format!(
                "status {}: {}",
                status, body
            )))
        }
    }
}
```

### Step 8: 编译与测试

```bash
cd /Users/rongts/HiveFlow && make rust-test
```

Expected: PASS

### Step 9: 提交

```bash
cd /Users/rongts/HiveFlow && git add cli/src/application/requests.rs cli/src/cmd/walk_forward.rs cli/src/cmd/mod.rs cli/src/application/handlers/walk_forward.rs cli/src/application/handlers/mod.rs cli/src/application/dispatch.rs cli/src/infrastructure/http_client.rs && git commit -m "feat: CLI walk-forward command implementation"
```

---

## Task 4：全量验证

**Files:** 无新增，仅运行检查

### Step 1: 架构门禁

```bash
cd /Users/rongts/HiveFlow && make architecture-check
```

Expected: PASS

### Step 2: 全量 check

```bash
cd /Users/rongts/HiveFlow && make check
```

Expected: PASS

### Step 3: 手工测试 CLI（可选，需服务端运行）

```bash
# 终端 1：启动服务端
cd /Users/rongts/HiveFlow && make db-up && make run-server

# 终端 2：运行 CLI
cd /Users/rongts/HiveFlow && cargo build -p hf-cli
./cli/target/debug/hf walk-forward run \
  --start-date 2025-06-01 --end-date 2026-04-01 \
  --warm-up-days 126 --test-window 63 --step 21 \
  --cost-bp 10 --output table
```

Expected: 输出 walk-forward 摘要表，verdict pass/no_go

### Step 4: 提交

```bash
cd /Users/rongts/HiveFlow && git add -A && git commit -m "feat: L7 walk-forward backtest complete implementation"
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 1（架构数据流） → Task 1 Step 3
- ✅ Section 2（文件结构） → Task 2/3 的文件变更
- ✅ Section 3（HTTP） → Task 2
- ✅ Section 4（CLI） → Task 3
- ✅ Section 5（测试） → Task 1 Step 5，Task 2 Step 1

**Placeholder scan:** 无 TBD、无"类似 Task N"、所有代码完整。

**Type consistency:** 
- `WalkForwardRequest` 定义于 requests.rs，handler/dispatch 中正确使用
- Service 返回 dict 包含 `verdict`，HTTP 端点和 CLI 都正确提取

**Gaps:** 无

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-06-l7-walk-forward-backtest-implementation-plan.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
