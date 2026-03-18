# 量化策略动态回测实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `hiveflow backtest quant-run` 命令，支持量化策略动态再平衡回测——在回测窗口内每隔 N 天重新调用策略计算权重，测试策略真实的历史时间序列表现。

**Architecture:** CLI 层解析策略类并传给 application 层；`run_dynamic_backtest()` 在 `backtest_engine.py` 实现核心算法（按 rebalance_days 分块、等权重 warmup 降级、无未来偏差保证）；结果落入现有 `BacktestResult` 表（新增 `backtest_type` 字段区分 static/dynamic）。

**Tech Stack:** Python 3.11, typer, SQLModel, SQLite, rich, pandas（已依赖）

**Spec:** `docs/superpowers/specs/2026-03-18-dynamic-backtest-design.md`

---

## 文件改动一览

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/hiveflow/domain/backtests.py` | 修改 | 新增 `backtest_type` 字段 |
| `src/hiveflow/db.py` | 修改 | 轻量迁移补 `backtest_type` 列 |
| `src/hiveflow/services/backtest_engine.py` | 修改 | 新增 `run_dynamic_backtest()` |
| `src/hiveflow/application/backtest.py` | 修改 | 新增 `run_quant_backtest()`；更新 `BacktestResultView` + `_to_view()` |
| `src/hiveflow/cli.py` | 修改 | 新增 `backtest quant-run`；更新 `backtest list` 显示 `id` 和 `类型` 列 |
| `tests/test_dynamic_backtest.py` | 新建 | 完整测试套件 |

---

## Chunk 1：域模型 + 轻量迁移

### Task 1：`BacktestResult` 新增 `backtest_type` 字段 + 迁移

**Files:**
- Modify: `src/hiveflow/domain/backtests.py`
- Modify: `src/hiveflow/db.py`
- Test: `tests/test_dynamic_backtest.py`（新建，本任务写第一批测试）

- [ ] **Step 1：新建测试文件，写迁移相关失败测试**

创建 `tests/test_dynamic_backtest.py`：

```python
"""动态回测测试套件。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hiveflow.application.backtest import list_backtest_results, run_quant_backtest
from hiveflow.domain.backtests import BacktestResult
from hiveflow.db import create_all_tables, get_session
from hiveflow.services.backtest_engine import PriceBar, run_dynamic_backtest
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy
from hiveflow.services.strategies.momentum import MomentumStrategy


# ─── 辅助函数 ───────────────────────────────────────────────────────────────

def _make_bars(symbol: str, closes: list[float], base: str = "2026-01-") -> list[PriceBar]:
    """构造 PriceBar 列表，时间戳格式 2026-01-01T00:00:00Z 等。"""
    bars = []
    for i, close in enumerate(closes):
        day = str(i + 1).zfill(2)
        ts = f"{base}{day}T00:00:00Z"
        bars.append(PriceBar(symbol=symbol, timestamp=ts, close=close))
    return bars


def _make_prices(n_days: int = 20) -> dict[str, list[PriceBar]]:
    """构造 3 个 symbol 各 n_days 天的价格序列。"""
    import math
    btc = [100.0 * (1 + 0.01 * math.sin(i)) for i in range(n_days)]
    eth = [50.0 * (1 + 0.015 * math.cos(i)) for i in range(n_days)]
    sol = [20.0 * (1 + 0.02 * math.sin(i + 1)) for i in range(n_days)]
    return {
        "BTC": _make_bars("BTC", btc),
        "ETH": _make_bars("ETH", eth),
        "SOL": _make_bars("SOL", sol),
    }


# ─── Task 1 测试：backtest_type 字段存在 ─────────────────────────────────────

def test_backtest_result_has_backtest_type_field(tmp_path: Path, monkeypatch) -> None:
    """BacktestResult 应有 backtest_type 字段，默认值为 'static'。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name="TestStrategy",
            prices_file="DB:MarketBar",
            periods=10,
            total_return=0.05,
            max_drawdown=-0.03,
            sharpe=1.2,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.backtest_type == "static"
```

- [ ] **Step 2：运行测试，确认失败**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_backtest_result_has_backtest_type_field -v
```

期望：`FAILED` — `BacktestResult` 没有 `backtest_type` 字段。

- [ ] **Step 3：在 `BacktestResult` 新增 `backtest_type` 字段**

修改 `src/hiveflow/domain/backtests.py`：

```python
"""回测结果模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class BacktestResult(SQLModel, table=True):
    """策略回测结果记录。"""

    # 主键。
    id: int | None = Field(default=None, primary_key=True)
    # 策略名称。
    strategy_name: str
    # 数据文件路径。
    prices_file: str
    # 回测周期数。
    periods: int
    # 总收益（小数）。
    total_return: float
    # 最大回撤（小数，<=0）。
    max_drawdown: float
    # Sharpe 比率（简化版）。
    sharpe: float
    # 权重快照（JSON 字符串，如 {"BTC":0.4,"ETH":0.3,...}）。
    weights_snapshot: str | None = Field(default=None)
    # 回测类型："static"（静态权重）或 "dynamic"（动态再平衡）。
    backtest_type: str = Field(default="static")
    # 创建时间（UTC）。
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4：在 `db.py` 的 `_run_lightweight_migrations` 补迁移**

在 `src/hiveflow/db.py` 的 `_run_lightweight_migrations` 函数中，在 `backtestresult` 的 `weights_snapshot` 迁移块之后添加：

```python
        # backtestresult 表：backtest_type 列
        if "backtestresult" in tables:
            bt_cols = conn.exec_driver_sql("PRAGMA table_info('backtestresult')").fetchall()
            bt_col_names = {row[1] for row in bt_cols}
            if "backtest_type" not in bt_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE backtestresult ADD COLUMN backtest_type VARCHAR DEFAULT 'static'"
                )
```

注意：此块加在现有 `weights_snapshot` 迁移的 `if "backtest_type" not in bt_col_names:` 判断之外，但**在同一个 `if "backtestresult" in tables:` 块下**——两次 `PRAGMA` 调用是分开的，完整写法如下（替换原有 `backtestresult` 块）：

```python
        # backtestresult 表：weights_snapshot 列（独立于 strategy 表检查）
        if "backtestresult" in tables:
            bt_cols = conn.exec_driver_sql("PRAGMA table_info('backtestresult')").fetchall()
            bt_col_names = {row[1] for row in bt_cols}
            if "weights_snapshot" not in bt_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE backtestresult ADD COLUMN weights_snapshot TEXT"
                )
            if "backtest_type" not in bt_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE backtestresult ADD COLUMN backtest_type VARCHAR DEFAULT 'static'"
                )
```

- [ ] **Step 5：运行测试，确认通过**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_backtest_result_has_backtest_type_field -v
```

期望：`PASSED`

- [ ] **Step 6：运行全量测试，确认无回归**

```bash
uv run python -m pytest -q
```

期望：全部通过（193 passed）

- [ ] **Step 7：提交**

```bash
git add src/hiveflow/domain/backtests.py src/hiveflow/db.py tests/test_dynamic_backtest.py
git commit -m "feat: BacktestResult 新增 backtest_type 字段及轻量迁移"
```

---

## Chunk 2：`run_dynamic_backtest()` 核心算法

### Task 2：在 `backtest_engine.py` 实现动态回测引擎

**Files:**
- Modify: `src/hiveflow/services/backtest_engine.py`
- Test: `tests/test_dynamic_backtest.py`（续写）

- [ ] **Step 1：在测试文件中追加引擎测试**

在 `tests/test_dynamic_backtest.py` 末尾添加：

```python
# ─── Task 2 测试：run_dynamic_backtest ───────────────────────────────────────

def test_run_dynamic_backtest_basic() -> None:
    """基本动态回测：3 个 symbol，20 天数据，每7天再平衡。"""
    prices = _make_prices(n_days=20)
    strategy = EqualWeightStrategy()

    metrics, final_weights = run_dynamic_backtest(
        prices=prices,
        strategy=strategy,
        rebalance_days=7,
    )

    assert metrics.periods > 0
    assert isinstance(metrics.total_return, float)
    assert metrics.max_drawdown <= 0
    assert isinstance(metrics.sharpe, float)
    assert set(final_weights.keys()) == {"BTC", "ETH", "SOL"}
    assert abs(sum(final_weights.values()) - 1.0) < 1e-6


def test_warmup_fallback_equal_weight() -> None:
    """数据不足时（MomentumStrategy 需 30 天，只给 5 天），应降级为等权重，不抛出异常。"""
    prices = _make_prices(n_days=5)
    strategy = MomentumStrategy()  # 默认 lookback_days=30，数据不足

    # 不应抛出异常
    metrics, final_weights = run_dynamic_backtest(
        prices=prices,
        strategy=strategy,
        rebalance_days=7,
    )

    assert metrics.periods > 0
    # 等权重：3 个 symbol 各 1/3
    for w in final_weights.values():
        assert abs(w - 1 / 3) < 1e-6


def test_no_lookahead_bias() -> None:
    """验证每次调用 compute_weights 时，prices 只包含 block_start 之前的数据。"""
    prices = _make_prices(n_days=20)
    seen_max_timestamps: list[str] = []

    class RecordingStrategy(BaseStrategy):
        params = {}

        def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
            if ctx.prices.empty:
                raise ValueError("no data")
            # 记录当前 context 中最大的时间戳（通过 index 推断）
            # 我们用 DataFrame 列名获取 symbol，用 index 长度推断
            seen_max_timestamps.append(str(len(ctx.prices)))
            n = len(ctx.prices.columns)
            return {sym: 1.0 / n for sym in ctx.prices.columns}

    strategy = RecordingStrategy()
    # 运行回测，rebalance_days=5，20 天共 4 块
    run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=5)

    # 每个块调用一次（除第一块 history 为空触发 fallback）
    # 关键：第 k 块的 prices 行数 = 前 k*5 个时间戳的数量
    # Block 0 (start=ts0): history = ts < ts0 → 0 行 → RecordingStrategy raises → fallback（不记录）
    # Block 1 (start=ts5): history = ts0..ts4 → 5 行 → 记录 "5"
    # Block 2 (start=ts10): history = ts0..ts9 → 10 行 → 记录 "10"
    # Block 3 (start=ts15): history = ts0..ts14 → 15 行 → 记录 "15"
    assert seen_max_timestamps == ["5", "10", "15"]


def test_run_dynamic_backtest_with_fee() -> None:
    """交易成本不为零时 total_return 应低于无成本版本。"""
    prices = _make_prices(n_days=20)
    strategy = EqualWeightStrategy()

    metrics_no_fee, _ = run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=7, fee_bps=0.0)
    metrics_with_fee, _ = run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=7, fee_bps=50.0)

    assert metrics_with_fee.total_return < metrics_no_fee.total_return
```

- [ ] **Step 2：运行测试，确认失败**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_run_dynamic_backtest_basic tests/test_dynamic_backtest.py::test_warmup_fallback_equal_weight tests/test_dynamic_backtest.py::test_no_lookahead_bias tests/test_dynamic_backtest.py::test_run_dynamic_backtest_with_fee -v
```

期望：全部 `FAILED` — `run_dynamic_backtest` 不存在。

- [ ] **Step 3：在 `backtest_engine.py` 实现 `run_dynamic_backtest`**

在 `src/hiveflow/services/backtest_engine.py` 末尾追加：

```python
def run_dynamic_backtest(
    prices: dict[str, list[PriceBar]],
    strategy: "BaseStrategy",
    rebalance_days: int = 7,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> "tuple[BacktestMetrics, dict[str, float]]":
    """动态再平衡回测：每隔 rebalance_days 天重新调用策略计算权重。

    - 每个块的起始时点之前的历史数据传给策略（无未来偏差）
    - 历史数据不足（策略抛异常）时降级为等权重
    - 交易成本（fee_bps + slippage_bps）在每个块的第一个周期扣除
    """
    import pandas as pd
    from hiveflow.services.strategies.base import StrategyContext

    symbols = sorted(prices.keys())
    if not symbols:
        raise ValueError("没有可用的价格序列。")

    # 收集所有时间戳（跨 symbol 并集，排序）
    all_timestamps = sorted({
        bar.timestamp
        for sym in symbols
        for bar in prices[sym]
    })
    if len(all_timestamps) < 2:
        raise ValueError("价格序列至少需要 2 个时点。")

    # 构建 symbol → {timestamp: close} 快速查表
    bar_maps: dict[str, dict[str, float]] = {
        sym: {bar.timestamp: bar.close for bar in prices[sym]}
        for sym in symbols
    }

    # 按 rebalance_days 切分块
    blocks: list[tuple[str, list[str]]] = []
    for i in range(0, len(all_timestamps), rebalance_days):
        block_start = all_timestamps[i]
        block_ts = all_timestamps[i : i + rebalance_days]
        blocks.append((block_start, block_ts))

    per_trade_cost = (fee_bps + slippage_bps) / 10000.0
    equity = 1.0
    curve = [equity]
    all_returns: list[float] = []
    # 初始等权重（用于第一个块的 fallback）
    equal_weights: dict[str, float] = {sym: 1.0 / len(symbols) for sym in symbols}
    final_weights = dict(equal_weights)

    for block_start, block_ts in blocks:
        # 截取 block_start 之前的历史数据
        hist_ts = [ts for ts in all_timestamps if ts < block_start]

        # 构建 pd.DataFrame(index=range, columns=symbol)
        if hist_ts:
            df = pd.DataFrame(
                {sym: [bar_maps[sym].get(ts, float("nan")) for ts in hist_ts] for sym in symbols}
            )
        else:
            df = pd.DataFrame(columns=symbols)

        # 调用策略；失败时降级为等权重
        try:
            ctx = StrategyContext(
                prices=df,
                current_positions={},
                risk_signals={},
                params=strategy.params,
            )
            weights = strategy.compute_weights(ctx)
            final_weights = dict(weights)
        except Exception:
            weights = dict(equal_weights)
            final_weights = dict(equal_weights)

        # 模拟本块内逐日收益
        for ts_idx in range(1, len(block_ts)):
            prev_ts = block_ts[ts_idx - 1]
            curr_ts = block_ts[ts_idx]
            period_return = 0.0
            for sym in symbols:
                w = weights.get(sym, 0.0)
                if w == 0.0:
                    continue
                prev_close = bar_maps[sym].get(prev_ts)
                curr_close = bar_maps[sym].get(curr_ts)
                if prev_close is None or curr_close is None or prev_close <= 0:
                    continue
                period_return += w * (curr_close / prev_close - 1.0)
            # 每块首日扣除再平衡交易成本
            if ts_idx == 1:
                period_return -= per_trade_cost
            all_returns.append(period_return)
            equity *= 1.0 + period_return
            curve.append(equity)

    if not all_returns:
        raise ValueError("无法生成收益序列，请检查数据。")

    # 最大回撤
    peak = curve[0]
    max_drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        dd = value / peak - 1.0
        max_drawdown = min(max_drawdown, dd)

    # Sharpe（与 run_weighted_backtest 公式一致）
    mean_ret = sum(all_returns) / len(all_returns)
    variance = sum((r - mean_ret) ** 2 for r in all_returns) / max(len(all_returns) - 1, 1)
    std_ret = math.sqrt(variance)
    sharpe = mean_ret / std_ret * math.sqrt(len(all_returns)) if std_ret > 0 else 0.0

    return (
        BacktestMetrics(
            periods=len(all_returns),
            total_return=equity - 1.0,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
        ),
        final_weights,
    )
```

注意：`BaseStrategy` 通过字符串类型注解 `"BaseStrategy"` 避免循环导入（`backtest_engine.py` 属于 services，不应 import services/strategies）；`StrategyContext` 在函数内部延迟 import。

- [ ] **Step 4：运行测试，确认通过**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_run_dynamic_backtest_basic tests/test_dynamic_backtest.py::test_warmup_fallback_equal_weight tests/test_dynamic_backtest.py::test_no_lookahead_bias tests/test_dynamic_backtest.py::test_run_dynamic_backtest_with_fee -v
```

期望：全部 `PASSED`

- [ ] **Step 5：运行全量测试**

```bash
uv run python -m pytest -q
```

期望：全部通过

- [ ] **Step 6：提交**

```bash
git add src/hiveflow/services/backtest_engine.py tests/test_dynamic_backtest.py
git commit -m "feat: backtest_engine 新增 run_dynamic_backtest 动态回测算法"
```

---

## Chunk 3：Application 层

### Task 3：更新 `BacktestResultView` + 新增 `run_quant_backtest()`

**Files:**
- Modify: `src/hiveflow/application/backtest.py`
- Test: `tests/test_dynamic_backtest.py`（续写）

- [ ] **Step 1：追加应用层测试**

在 `tests/test_dynamic_backtest.py` 末尾添加：

```python
# ─── Task 3 测试：application 层 ─────────────────────────────────────────────

def _seed_market_bars(tmp_path: Path, monkeypatch, n_days: int = 20) -> None:
    """将测试价格写入 MarketBar 表（MarketBar 所有非空字段均需填写）。"""
    from datetime import datetime, timezone
    from hiveflow.domain.market_data import MarketBar
    from hiveflow.db import create_all_tables, get_session
    import math

    create_all_tables()
    with get_session() as session:
        for day in range(n_days):
            ts = datetime(2026, 1, day + 1, tzinfo=timezone.utc)
            btc_close = 100.0 * (1 + 0.01 * math.sin(day))
            eth_close = 50.0 * (1 + 0.015 * math.cos(day))
            session.add(MarketBar(
                symbol="BTC", timestamp=ts,
                open=btc_close, high=btc_close, low=btc_close, close=btc_close, volume=0.0,
            ))
            session.add(MarketBar(
                symbol="ETH", timestamp=ts,
                open=eth_close, high=eth_close, low=eth_close, close=eth_close, volume=0.0,
            ))
        session.commit()


def test_run_quant_backtest_persists(tmp_path: Path, monkeypatch) -> None:
    """run_quant_backtest 应写入 BacktestResult，backtest_type='dynamic'。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    _seed_market_bars(tmp_path, monkeypatch)

    strategy = EqualWeightStrategy()
    result = run_quant_backtest(strategy=strategy, rebalance_days=7)

    assert result.strategy_name == "EqualWeightStrategy"
    assert result.backtest_type == "dynamic"
    assert result.periods > 0
    assert result.weights_snapshot is not None
    weights = json.loads(result.weights_snapshot)
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_backtest_list_shows_backtest_type(tmp_path: Path, monkeypatch) -> None:
    """`list_backtest_results()` 返回含 backtest_type 字段的视图。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    _seed_market_bars(tmp_path, monkeypatch)

    strategy = EqualWeightStrategy()
    run_quant_backtest(strategy=strategy, rebalance_days=7)

    rows = list_backtest_results()
    assert len(rows) == 1
    assert rows[0].backtest_type == "dynamic"
    # to_dict 也应包含该字段
    d = rows[0].to_dict()
    assert "backtest_type" in d
    assert d["backtest_type"] == "dynamic"
```

- [ ] **Step 2：运行测试，确认失败**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_run_quant_backtest_persists tests/test_dynamic_backtest.py::test_backtest_list_shows_backtest_type -v
```

期望：`FAILED` — `run_quant_backtest` 不存在，`BacktestResultView` 无 `backtest_type`。

- [ ] **Step 3a：在 `BacktestResultView` 中新增 `backtest_type` 字段，并更新 `_to_view` 和 `to_dict`**

在 `src/hiveflow/application/backtest.py` 中做以下精确替换：

**（1）为文件添加 `from __future__ import annotations`**（若尚未有），在文件第一行之后插入。

**（2）替换 `BacktestResultView` dataclass**：

旧代码（精确匹配）：
```python
@dataclass(frozen=True)
class BacktestResultView:
    """回测结果视图。"""

    id: int | None
    strategy_name: str
    prices_file: str
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    weights_snapshot: str | None
    created_at: str

    def to_dict(self) -> dict[str, str | float | int | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "prices_file": self.prices_file,
            "periods": self.periods,
            "total_return": round(self.total_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "sharpe": round(self.sharpe, 6),
            "weights_snapshot": self.weights_snapshot,
            "created_at": self.created_at,
        }
```

新代码：
```python
@dataclass(frozen=True)
class BacktestResultView:
    """回测结果视图。"""

    id: int | None
    strategy_name: str
    prices_file: str
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    weights_snapshot: str | None
    backtest_type: str
    created_at: str

    def to_dict(self) -> dict[str, str | float | int | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "prices_file": self.prices_file,
            "periods": self.periods,
            "total_return": round(self.total_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "sharpe": round(self.sharpe, 6),
            "weights_snapshot": self.weights_snapshot,
            "backtest_type": self.backtest_type,
            "created_at": self.created_at,
        }
```

**（3）替换 `_to_view` 函数**：

旧代码（精确匹配）：
```python
def _to_view(row: BacktestResult) -> BacktestResultView:
    return BacktestResultView(
        id=row.id,
        strategy_name=row.strategy_name,
        prices_file=row.prices_file,
        periods=row.periods,
        total_return=row.total_return,
        max_drawdown=row.max_drawdown,
        sharpe=row.sharpe,
        weights_snapshot=row.weights_snapshot,
        created_at=row.created_at.isoformat(),
    )
```

新代码：
```python
def _to_view(row: BacktestResult) -> BacktestResultView:
    return BacktestResultView(
        id=row.id,
        strategy_name=row.strategy_name,
        prices_file=row.prices_file,
        periods=row.periods,
        total_return=row.total_return,
        max_drawdown=row.max_drawdown,
        sharpe=row.sharpe,
        weights_snapshot=row.weights_snapshot,
        backtest_type=row.backtest_type,
        created_at=row.created_at.isoformat(),
    )
```

**（4）在 `run_backtest_for_strategy` 中，给 `BacktestResult(...)` 构造增加 `backtest_type="static"`**：

旧代码（精确匹配）：
```python
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file=source,
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            weights_snapshot=json.dumps(weights),
        )
```

新代码：
```python
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file=source,
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            weights_snapshot=json.dumps(weights),
            backtest_type="static",
        )
```

- [ ] **Step 3b：在文件末尾追加 `run_quant_backtest` 函数**

在 `src/hiveflow/application/backtest.py` 文件末尾追加：

```python
def run_quant_backtest(
    strategy: "BaseStrategy",
    rebalance_days: int = 7,
    symbols: list[str] | None = None,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    settings=None,
) -> BacktestResultView:
    """执行量化策略动态回测并持久化结果。

    strategy: 已实例化的 BaseStrategy 子类
    rebalance_days: 再平衡周期（天）
    symbols: 指定资产池；None 时自动从 MarketBar 读取所有 symbol
    """
    from hiveflow.domain.market_data import MarketBar
    from hiveflow.services.backtest_engine import run_dynamic_backtest

    create_all_tables(settings)

    # 解析资产池
    if symbols is None:
        with get_session(settings) as session:
            rows = session.exec(select(MarketBar.symbol).distinct()).all()
        symbols = list(rows)
    if not symbols:
        raise ValueError("MarketBar 中没有数据，请先运行 hiveflow market-data import。")

    prices = load_close_prices_from_db(symbols=symbols, settings=settings)
    if not prices:
        raise ValueError("指定 symbol 在 MarketBar 中无数据，请先运行 hiveflow market-data import。")

    metrics, final_weights = run_dynamic_backtest(
        prices=prices,
        strategy=strategy,
        rebalance_days=rebalance_days,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    strategy_name = type(strategy).__name__

    with get_session(settings) as session:
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file="DB:MarketBar",
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            weights_snapshot=json.dumps(final_weights),
            backtest_type="dynamic",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return _to_view(row)
```

- [ ] **Step 4：运行测试，确认通过**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_run_quant_backtest_persists tests/test_dynamic_backtest.py::test_backtest_list_shows_backtest_type -v
```

期望：全部 `PASSED`

- [ ] **Step 5：运行全量测试**

```bash
uv run python -m pytest -q
```

期望：全部通过

- [ ] **Step 6：提交**

```bash
git add src/hiveflow/application/backtest.py tests/test_dynamic_backtest.py
git commit -m "feat: application 层新增 run_quant_backtest，BacktestResultView 补 backtest_type"
```

---

## Chunk 4：CLI 命令

### Task 4：`backtest quant-run` 命令 + `backtest list` 更新

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_dynamic_backtest.py`（续写）

- [ ] **Step 1：追加 CLI 测试**

在 `tests/test_dynamic_backtest.py` 末尾添加：

```python
# ─── Task 4 测试：CLI ─────────────────────────────────────────────────────────

def test_cli_backtest_quant_run(tmp_path: Path, monkeypatch) -> None:
    """CLI `backtest quant-run` 应输出策略名和指标。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app

    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    _seed_market_bars(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "quant-run", "--strategy", "EqualWeightStrategy"])

    assert result.exit_code == 0, result.output
    assert "EqualWeightStrategy" in result.output
    assert "dynamic" in result.output


def test_cli_backtest_quant_run_json(tmp_path: Path, monkeypatch) -> None:
    """`--output json` 输出包含 backtest_type=dynamic 的 JSON。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app

    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    _seed_market_bars(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "quant-run", "--strategy", "EqualWeightStrategy", "--output", "json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["backtest_type"] == "dynamic"
    assert data["strategy"] == "EqualWeightStrategy"


def test_cli_backtest_list_shows_type(tmp_path: Path, monkeypatch) -> None:
    """`backtest list` 表格应显示 backtest_type 列。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app

    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    _seed_market_bars(tmp_path, monkeypatch)

    runner = CliRunner()
    # 先运行一次动态回测
    runner.invoke(app, ["backtest", "quant-run", "--strategy", "EqualWeightStrategy"])
    # 再 list
    result = runner.invoke(app, ["backtest", "list"])

    assert result.exit_code == 0, result.output
    assert "dynamic" in result.output


def test_cli_backtest_quant_run_unknown_strategy(tmp_path: Path, monkeypatch) -> None:
    """未知策略名应以非零退出码退出并显示错误。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app

    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "quant-run", "--strategy", "NonExistentStrategy"])
    assert result.exit_code != 0
    assert "NonExistentStrategy" in result.output or "未知" in result.output
```

- [ ] **Step 2：运行测试，确认失败**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_cli_backtest_quant_run tests/test_dynamic_backtest.py::test_cli_backtest_quant_run_json tests/test_dynamic_backtest.py::test_cli_backtest_list_shows_type -v
```

期望：`FAILED` — 命令不存在。

- [ ] **Step 3：在 `cli.py` 新增 `backtest quant-run` 命令**

在 `src/hiveflow/cli.py` 中，找到 `@backtest_app.command("list")` 函数定义（约 1658 行）的末尾之后，在下一个 `@app.command()` 之前插入：

```python
@backtest_app.command("quant-run")
def backtest_quant_run_command(
    strategy: str = typer.Option(..., "--strategy", "-s", help="量化策略类名（如 MomentumStrategy）"),
    rebalance_days: int = typer.Option(7, "--rebalance-days", help="再平衡周期（天，默认 7）"),
    symbols: str | None = typer.Option(None, "--symbols", help="资产池，逗号分隔（不填则用 MarketBar 全部）"),
    fee_bps: float = typer.Option(0.0, "--fee-bps", help="单次再平衡手续费（基点）"),
    slippage_bps: float = typer.Option(0.0, "--slippage-bps", help="单次再平衡滑点（基点）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """运行量化策略动态回测（每隔 N 天重新计算权重）。"""
    from hiveflow.application.backtest import run_quant_backtest

    output_format = _validate_output_format(output)

    # 解析策略类
    if strategy not in _BUILTIN_STRATEGIES:
        console.print(f"[red]未知策略：{strategy}，可用策略请运行 'hiveflow quant list'[/red]")
        raise typer.Exit(1)
    strategy_class, _ = _BUILTIN_STRATEGIES[strategy]
    strategy_instance = strategy_class()

    # 解析 symbols
    symbols_list: list[str] | None = None
    if symbols:
        symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    try:
        result = run_quant_backtest(
            strategy=strategy_instance,
            rebalance_days=rebalance_days,
            symbols=symbols_list,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
    except ValueError as exc:
        console.print(f"[red]回测失败：{exc}[/red]")
        raise typer.Exit(1)

    if output_format == "json":
        payload = result.to_dict()
        payload["strategy"] = result.strategy_name  # 增加冗余字段方便 Agent 消费
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="动态回测结果", show_lines=False, box=box.SIMPLE)
    table.add_column("策略", style="bold")
    table.add_column("类型")
    table.add_column("再平衡周期")
    table.add_column("总周期数", justify="right")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_row(
        result.strategy_name,
        result.backtest_type,
        f"{rebalance_days} 天",
        str(result.periods),
        f"{result.total_return:.2%}",
        f"{result.max_drawdown:.2%}",
        f"{result.sharpe:.2f}",
    )
    console.print(table)
    console.print(f"[dim]回测 ID：{result.id}（可用 'hiveflow targets set-from-backtest {result.id}' 应用）[/dim]")
```

- [ ] **Step 4：更新 `backtest list` 命令，新增 `ID` 和 `类型` 列**

在 `src/hiveflow/cli.py` 中找到以下代码块（约 1673–1688 行）并完整替换：

旧代码（精确匹配）：
```python
    table = Table(title="回测记录", show_lines=False, box=box.SIMPLE)
    table.add_column("策略", justify="left")
    table.add_column("周期", justify="right")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("时间", justify="left")
    for item in rows:
        table.add_row(
            item.strategy_name,
            str(item.periods),
            f"{item.total_return:.2%}",
            f"{item.max_drawdown:.2%}",
            f"{item.sharpe:.2f}",
            item.created_at,
        )
```

新代码：
```python
    table = Table(title="回测记录", show_lines=False, box=box.SIMPLE)
    table.add_column("ID", justify="right")
    table.add_column("策略", justify="left")
    table.add_column("类型")
    table.add_column("周期", justify="right")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("时间", justify="left")
    for item in rows:
        table.add_row(
            str(item.id) if item.id is not None else "-",
            item.strategy_name,
            item.backtest_type,
            str(item.periods),
            f"{item.total_return:.2%}",
            f"{item.max_drawdown:.2%}",
            f"{item.sharpe:.2f}",
            item.created_at,
        )
```

- [ ] **Step 5：运行测试，确认通过**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py::test_cli_backtest_quant_run tests/test_dynamic_backtest.py::test_cli_backtest_quant_run_json tests/test_dynamic_backtest.py::test_cli_backtest_list_shows_type tests/test_dynamic_backtest.py::test_cli_backtest_quant_run_unknown_strategy -v
```

期望：全部 `PASSED`

- [ ] **Step 6：运行完整测试文件**

```bash
uv run python -m pytest tests/test_dynamic_backtest.py -v
```

期望：全部通过（10 个测试）

- [ ] **Step 7：运行全量测试**

```bash
uv run python -m pytest -q
```

期望：203+ passed，无失败

- [ ] **Step 8：手动验证 CLI（可选）**

```bash
uv run hiveflow backtest --help          # 应显示 quant-run 命令
uv run hiveflow backtest list            # 应显示 ID 和 类型 列
```

- [ ] **Step 9：提交**

```bash
git add src/hiveflow/cli.py tests/test_dynamic_backtest.py
git commit -m "feat: CLI 新增 backtest quant-run 命令，backtest list 补 ID 和类型列"
```

---

## Chunk 5：收尾

### Task 5：更新文档

**Files:**
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/SESSION_LOG.md`

- [ ] **Step 1：更新 `CURRENT_STATE.md`**

在"当前可用命令（核心）"中添加：
```
- `hiveflow backtest quant-run` — 量化策略动态回测
```

在"下一步建议"更新：
```
1. M7：网格机器人创建/管理
2. 多交易所支持
3. 多策略组合（加权混合多个策略输出）
4. 回测 equity curve 可视化
```

- [ ] **Step 2：向 `SESSION_LOG.md` 追加今日记录**

```markdown
- 完成动态回测：新增 `backtest quant-run --strategy <StrategyName>`，支持每隔 N 天重新计算量化策略权重并回测，结果落库 BacktestResult（backtest_type=dynamic）；backtest list 新增 ID 和类型列。
- 全量测试：203+ passed。
```

- [ ] **Step 3：提交**

```bash
git add docs/context/CURRENT_STATE.md docs/context/SESSION_LOG.md
git commit -m "docs: 更新 CURRENT_STATE 和 SESSION_LOG，记录动态回测完成"
```
