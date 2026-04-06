# L7 Walk-Forward Backtest Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 L7 回测/验证层的 Walk-Forward 模块，在历史区间上用滚动窗口验证 L2→L5 完整链路的组合表现，输出逐窗口指标与跨窗口 Go/No-Go 裁定，作为策略上线的前置闸门。

**Architecture:** 独立 `WalkForwardService`，复用现有 `run_daily()`，从 `portfolio.target_weights` 读权重后用 `bar_store.list_bars()` 查次日收盘价计算日收益；换手成本可选（默认 0）；HTTP `POST /v1/walk-forward/run` + Rust `hf walk-forward run`，与现有架构完全一致。

**Tech Stack:** Python (FastAPI, application layer), Rust (clap + reqwest), TimescaleDB (BarStore `list_bars`)

---

## 数据流

```
WalkForwardService.run(start, end, warm_up, test_window, step, cost_bp)
  │
  ├─ generate_windows() → [(warm_start, warm_end, test_start, test_end), ...]
  │
  └─ for each window:
       for each trading day in test_window:
         run_daily(as_of) → portfolio.target_weights   ← 复用现有
         bar_store.list_bars(as_of ~ as_of+1) → 次日收盘价
         daily_return = Σ weight_i × (close_T+1 / close_T - 1) - cost_bp/10000
       → per_window_metrics: sharpe / mdd / cumulative_return / win_rate
  │
  └─ aggregate_metrics: mean/min/max across windows
  └─ gate_check: 对照阈值输出 pass / no_go + reason_codes
```

**关键约定：**
- warm_up 窗口仅保证 bar 数据就绪（180 天因子窗口），不运行 pipeline，不出指标
- 返回计算用 `list_bars` 查 T 和 T+1 日收盘价，T+1 无 bar（停牌/非交易日）时该日跳过
- `cost_bp` 为单边手续费（basis points，1 bp = 0.01%），每个有效交易日均扣除（因 `run_daily` 每日重新调仓），即 `net_return = gross_return - cost_bp / 10000`，默认 0

---

## 文件结构

| 文件 | 操作 |
|------|------|
| `quant/src/application/walk_forward_service.py` | 新增：核心逻辑 |
| `quant/src/interfaces/http/routes_walk_forward.py` | 新增：`POST /v1/walk-forward/run` |
| `quant/src/interfaces/http/app.py` | 修改：注册新路由 |
| `quant/tests/unit/test_walk_forward_service.py` | 新增：unit tests |
| `quant/tests/contract/test_http_walk_forward.py` | 新增：contract tests |
| `cli/src/application/handlers/walk_forward.rs` | 新增：Rust handler |
| `cli/src/application/handlers/mod.rs` | 修改：注册 |
| `cli/src/application/requests.rs` | 修改：`WalkForwardRequest` |
| `cli/src/application/dispatch.rs` | 修改：分发 |
| `cli/src/cmd/walk_forward.rs` | 新增：clap 命令定义 |
| `cli/src/cmd/mod.rs` | 修改：注册顶层命令 |
| `cli/src/infrastructure/http_client.rs` | 修改：`post_walk_forward_run` |

---

## Section 1：HTTP 接口

```
POST /v1/walk-forward/run
Content-Type: application/json

{
  "start_date": "2025-01-01",
  "end_date": "2026-04-01",
  "warm_up_days": 180,
  "test_window_days": 63,
  "step_days": 21,
  "cost_bp": 0.0
}
```

响应（200）：
```json
{
  "verdict": "pass",
  "failed_gates": [],
  "windows": [...],
  "aggregate": {...},
  "params": {...}
}
```

错误：
- 503：无 DB 配置（`WALK_FORWARD_DB_UNAVAILABLE`）
- 422：`start_date > end_date` 或窗口参数非法（`WALK_FORWARD_INVALID_PARAMS`）

---

## Section 2：CLI

```bash
hf walk-forward run \
  --start-date 2025-01-01 --end-date 2026-04-01 \
  [--warm-up-days 180] [--test-window 63] [--step 21] \
  [--cost-bp 10] [--output json|table]
```

`--output table` 打印摘要：

```
Walk-Forward: 8 windows | 2025-01-01 → 2026-04-01
Verdict: PASS

Window             Annualized  Sharpe  MDD
2025-07-30~09-29   +32.1%      1.40    7.2%
2025-08-20~10-20   +18.4%      0.92    9.1%
...

Aggregate (mean/min/max)
  Annualized:  +18.0% / +4.2% / +32.1%
  Sharpe:       1.10  /  0.62 /  1.80
  Max Drawdown: 9.0%  /  3.1% / 18.0%
```

---

## Section 3：核心 Service 结构

```python
# quant/src/application/walk_forward_service.py

def generate_windows(
    start_date: str,
    end_date: str,
    warm_up_days: int,
    test_window_days: int,
    step_days: int,
) -> list[dict]:
    """返回 [{"warm_start", "warm_end", "test_start", "test_end"}, ...]"""

def _run_test_window(
    test_start: str,
    test_end: str,
    warm_start: str,
    bar_store,
    cost_bp: float,
) -> dict:
    """逐日运行 run_daily，计算日收益，聚合 per-window 指标"""

def _compute_daily_return(
    weights: dict[str, float],
    as_of: str,
    bar_store,
    cost_bp: float,
) -> float | None:
    """从 bar_store 取 T 和 T+1 收盘价，计算加权收益后扣除 cost_bp/10000"""

def _build_window_metrics(daily_returns: list[float], cost_total_bp: float) -> dict:
    """cumulative_return / annualized_return / sharpe / max_drawdown / win_rate"""

def _gate_check(aggregate: dict, thresholds: dict) -> dict:
    """对照阈值返回 verdict + failed_gates"""

def run_walk_forward(
    start_date: str,
    end_date: str,
    warm_up_days: int = 180,
    test_window_days: int = 63,
    step_days: int = 21,
    cost_bp: float = 0.0,
    bar_store=None,
    thresholds: dict | None = None,
) -> dict:
    """入口函数，返回完整结果字典"""
```

默认闸门阈值（`thresholds` 未传时使用）：
```python
_DEFAULT_THRESHOLDS = {
    "annualized_return_mean_min": 0.06,   # 跨窗口均值 ≥ 6%
    "max_drawdown_max_max": 0.20,          # 最差窗口 MDD ≤ 20%
    "sharpe_min_min": 0.5,                 # 最差窗口 Sharpe ≥ 0.5
}
```

---

## Section 4：per-window 与 aggregate 输出结构

**per-window：**
```json
{
  "warm_start": "2025-01-01",
  "warm_end": "2025-07-29",
  "test_start": "2025-07-30",
  "test_end": "2025-09-29",
  "days_run": 42,
  "cumulative_return": 0.08,
  "annualized_return": 0.32,
  "sharpe": 1.4,
  "max_drawdown": 0.07,
  "win_rate": 0.55,
  "cost_total_bp": 120.0
}
```

**aggregate：**
```json
{
  "window_count": 8,
  "annualized_return": {"mean": 0.18, "min": 0.04, "max": 0.35},
  "sharpe":            {"mean": 1.1,  "min": 0.6,  "max": 1.8},
  "max_drawdown":      {"mean": 0.09, "min": 0.03, "max": 0.18}
}
```

---

## Section 5：测试策略

### Unit tests（`test_walk_forward_service.py`）

| 用例 | 验证点 |
|------|--------|
| `test_generate_windows` | 窗口数量、起止日期正确 |
| `test_single_window_full_coverage` | 全持仓次日有 bar → 收益正确累积 |
| `test_single_window_missing_bar` | T+1 无 bar → 该日跳过，不崩溃 |
| `test_cost_deduction` | `cost_bp=10` → 扣费后净收益更低 |
| `test_gate_pass` | 指标全过阈值 → `verdict="pass"` |
| `test_gate_no_go` | MDD 超标 → `verdict="no_go"`, `failed_gates` 含 `max_drawdown` |

`run_daily` 和 `bar_store` 均用 monkeypatch/MagicMock，不依赖真实数据。

### Contract tests（`test_http_walk_forward.py`）

| 用例 | 验证点 |
|------|--------|
| `test_run_ok` | 200，返回 `verdict` 字段 |
| `test_run_db_unavailable` | 无 DB 配置 → 503 |
| `test_run_invalid_dates` | start > end → 422 |
