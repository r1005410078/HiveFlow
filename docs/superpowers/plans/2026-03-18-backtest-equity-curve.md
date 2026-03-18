# Backtest Equity Curve Visualization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `hiveflow backtest` 新增 `show <id>` 和 `compare <id1> <id2> ...` 命令，在终端以 Unicode Sparkline 展示权益曲线并对比多个回测结果。

**Architecture:** 回测运行时将权益曲线（JSON 数组）存入 `BacktestResult.equity_curve` 列；`show`/`compare` 命令从 DB 读取后用 `_sparkline()` 函数渲染为 Unicode 块字符。无新增依赖，轻量 ALTER TABLE 迁移。

**Tech Stack:** Python 3.12+, typer, rich, SQLite + SQLModel（已有）

---

## Chunk 1: 数据模型 + DB 迁移

### Task 1: `BacktestResult` 新增 `equity_curve` 列 + DB 迁移

**Files:**
- Modify: `src/hiveflow/domain/backtests.py:10-32`
- Modify: `src/hiveflow/db.py:49-60`
- Test: `tests/test_backtest_show.py`（新建）

背景：`BacktestResult` 是 SQLModel ORM 模型，位于 `src/hiveflow/domain/backtests.py`。`db.py` 的 `_run_lightweight_migrations()` 函数在启动时检测并追加缺失列。

- [ ] **Step 1: 写失败测试**

新建文件 `tests/test_backtest_show.py`，写第一个测试：

```python
"""回测权益曲线可视化测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.backtests import BacktestResult


def _seed_record(tmp_path: Path, monkeypatch, equity_curve=None) -> int:
    """在临时 DB 中种入一条 BacktestResult，返回其 id。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name="TestStrategy",
            prices_file="DB:MarketBar",
            periods=10,
            total_return=0.12,
            max_drawdown=-0.05,
            sharpe=1.5,
            equity_curve=json.dumps(equity_curve) if equity_curve is not None else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def test_backtest_result_has_equity_curve_field(tmp_path: Path, monkeypatch) -> None:
    """BacktestResult 应有 equity_curve 字段，默认为 None。"""
    rid = _seed_record(tmp_path, monkeypatch)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    with get_session() as session:
        row = session.get(BacktestResult, rid)
        assert hasattr(row, "equity_curve")
        assert row.equity_curve is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_result_has_equity_curve_field -v
```

预期：`FAILED`，报 `TypeError` 或 `AttributeError`（`equity_curve` 不存在）。

- [ ] **Step 3: 在 `domain/backtests.py` 新增字段**

在 `BacktestResult` 类末尾，`created_at` 字段之前，添加：

```python
# 权益曲线 JSON 数组（如 [1.0, 1.02, ...]），旧记录为 None。
equity_curve: str | None = Field(default=None)
```

完整修改后的类（仅展示新增行）：

```python
class BacktestResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    strategy_name: str
    prices_file: str
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    weights_snapshot: str | None = Field(default=None)
    backtest_type: str = Field(default="static")
    equity_curve: str | None = Field(default=None)   # ← 新增
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: 在 `db.py` 添加迁移**

定位 `_run_lightweight_migrations()` 中的 `if "backtestresult" in tables:` 块（约第 50 行），在 `backtest_type` 迁移检查**之后**，同一 `if` 块内追加：

```python
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
            if "equity_curve" not in bt_col_names:          # ← 新增
                conn.exec_driver_sql(                        # ← 新增
                    "ALTER TABLE backtestresult ADD COLUMN equity_curve TEXT"  # ← 新增
                )                                            # ← 新增
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_result_has_equity_curve_field -v
```

预期：`PASSED`。

- [ ] **Step 6: 运行全量测试，确认无回归**

```bash
uv run python -m pytest -q
```

预期：全部通过（204 passed）。

- [ ] **Step 7: 提交**

```bash
git add src/hiveflow/domain/backtests.py src/hiveflow/db.py tests/test_backtest_show.py
git commit -m "feat: BacktestResult 新增 equity_curve 列及 DB 迁移"
```

---

## Chunk 2: 服务层 — BacktestMetrics + 两个回测函数

### Task 2: `BacktestMetrics` 新增 `curve` 字段，回测函数返回曲线

**Files:**
- Modify: `src/hiveflow/services/backtest_engine.py:21-29`（BacktestMetrics）
- Modify: `src/hiveflow/services/backtest_engine.py:52-99`（run_weighted_backtest）
- Modify: `src/hiveflow/services/backtest_engine.py:102-223`（run_dynamic_backtest）
- Test: `tests/test_backtest_show.py`

背景：`BacktestMetrics` 是 `@dataclass(frozen=True)`。两个回测函数内部已有 `curve` 列表（`equity = 1.0; curve = [equity]`，每期 append），只需把它加入返回值。`curve` 无默认值——构造时必须显式传入。

- [ ] **Step 1: 写失败测试**

在 `tests/test_backtest_show.py` 追加：

```python
from hiveflow.services.backtest_engine import (
    BacktestMetrics,
    PriceBar,
    run_dynamic_backtest,
    run_weighted_backtest,
)
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy


def _make_bars(symbol: str, closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(symbol=symbol, timestamp=f"2026-01-{i+1:02d}T00:00:00Z", close=c)
        for i, c in enumerate(closes)
    ]


def test_backtest_metrics_has_curve() -> None:
    """BacktestMetrics.curve 应存在，长度 == periods + 1，首值为 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 + i for i in range(10)]),
        "ETH": _make_bars("ETH", [50.0 + i * 0.5 for i in range(10)]),
    }
    weights = {"BTC": 0.6, "ETH": 0.4}
    m = run_weighted_backtest(prices=prices, weights=weights)
    assert hasattr(m, "curve")
    assert len(m.curve) == m.periods + 1
    assert m.curve[0] == 1.0


def test_run_weighted_backtest_curve() -> None:
    """上涨序列下 curve[-1] > 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 * (1 + 0.01 * i) for i in range(20)]),
        "ETH": _make_bars("ETH", [50.0 * (1 + 0.01 * i) for i in range(20)]),
    }
    weights = {"BTC": 0.5, "ETH": 0.5}
    m = run_weighted_backtest(prices=prices, weights=weights)
    assert m.curve[-1] > 1.0


def test_run_dynamic_backtest_curve() -> None:
    """动态回测 curve 长度 > 0，首值 == 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 + i for i in range(30)]),
        "ETH": _make_bars("ETH", [50.0 + i * 0.5 for i in range(30)]),
    }
    strategy = EqualWeightStrategy()
    (m, _) = run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=7)
    assert len(m.curve) > 0
    assert m.curve[0] == 1.0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_metrics_has_curve -v
```

预期：`FAILED`，`TypeError: BacktestMetrics.__init__() got an unexpected keyword argument 'curve'` 或类似。

- [ ] **Step 3: 在 `BacktestMetrics` 新增 `curve` 字段**

在 `src/hiveflow/services/backtest_engine.py` 第 21-28 行，修改 `BacktestMetrics`（`curve` 无默认值，必须显式传入）：

```python
@dataclass(frozen=True)
class BacktestMetrics:
    """回测指标结果。"""

    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    curve: list[float]  # 从 1.0 开始的逐期权益值；无默认值
```

- [ ] **Step 4: 更新 `run_weighted_backtest` 的返回值**

定位 `run_weighted_backtest` 末尾的 `return BacktestMetrics(...)` 语句（约第 94-99 行），在其中新增 `curve=curve`：

```python
    return BacktestMetrics(
        periods=len(returns),
        total_return=equity - 1.0,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        curve=curve,
    )
```

- [ ] **Step 5: 更新 `run_dynamic_backtest` 的返回值**

定位 `run_dynamic_backtest` 末尾的 `return (BacktestMetrics(...), final_weights)` 语句（约第 215-223 行），新增 `curve=curve`：

```python
    return (
        BacktestMetrics(
            periods=len(all_returns),
            total_return=equity - 1.0,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
            curve=curve,
        ),
        final_weights,
    )
```

- [ ] **Step 6: 运行三个新测试**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_metrics_has_curve tests/test_backtest_show.py::test_run_weighted_backtest_curve tests/test_backtest_show.py::test_run_dynamic_backtest_curve -v
```

预期：三个测试全部 `PASSED`。

- [ ] **Step 7: 运行全量测试，确认无回归**

```bash
uv run python -m pytest -q
```

预期：全部通过。

- [ ] **Step 8: 提交**

```bash
git add src/hiveflow/services/backtest_engine.py tests/test_backtest_show.py
git commit -m "feat: BacktestMetrics 新增 curve 字段，回测函数返回权益曲线"
```

---

## Chunk 3: Application 层

### Task 3: `BacktestResultView` + `get_backtest_result()` + 存储 curve

**Files:**
- Modify: `src/hiveflow/application/backtest.py:23-66`（BacktestResultView + _to_view）
- Modify: `src/hiveflow/application/backtest.py:81-120`（run_backtest_for_strategy）
- Modify: `src/hiveflow/application/backtest.py:134-189`（run_quant_backtest）
- Test: `tests/test_backtest_show.py`

背景：`BacktestResultView` 是 `@dataclass(frozen=True)`，有手工 `to_dict()` 和 `_to_view()` 映射函数。两个 use case 函数在创建 `BacktestResult` 时需要新增 `equity_curve=json.dumps(metrics.curve)`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_backtest_show.py` 追加：

```python
from hiveflow.application.backtest import (
    BacktestResultView,
    get_backtest_result,
    list_backtest_results,
    run_backtest_for_strategy,
)


def test_backtest_result_view_has_equity_curve() -> None:
    """BacktestResultView 应有 equity_curve 字段。"""
    assert "equity_curve" in BacktestResultView.__dataclass_fields__


def test_to_dict_includes_equity_curve(tmp_path: Path, monkeypatch) -> None:
    """to_dict() 应包含 equity_curve 键。"""
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=[1.0, 1.05, 1.1])
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    result = get_backtest_result(rid)
    d = result.to_dict()
    assert "equity_curve" in d
    assert d["equity_curve"] is not None


def test_get_backtest_result_not_found(tmp_path: Path, monkeypatch) -> None:
    """不存在的 ID 应抛 ValueError。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    with pytest.raises(ValueError, match="不存在"):
        get_backtest_result(999)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_result_view_has_equity_curve tests/test_backtest_show.py::test_to_dict_includes_equity_curve tests/test_backtest_show.py::test_get_backtest_result_not_found -v
```

预期：全部 `FAILED`。

- [ ] **Step 3: 更新 `BacktestResultView` dataclass**

在 `src/hiveflow/application/backtest.py` 第 23-36 行的 `BacktestResultView`，在 `created_at` 字段之前新增：

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
    equity_curve: str | None   # ← 新增
    created_at: str
```

- [ ] **Step 4: 更新 `to_dict()` 方法**

在 `to_dict()` 方法（约第 38-51 行）中，在 `"created_at"` 条目之前新增：

```python
    def to_dict(self) -> dict[str, str | float | int | None]:
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
            "equity_curve": self.equity_curve,   # ← 新增
            "created_at": self.created_at,
        }
```

- [ ] **Step 5: 更新 `_to_view()` 函数**

在 `_to_view()` 函数（约第 54-66 行）中，新增 `equity_curve` 映射：

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
        equity_curve=row.equity_curve,   # ← 新增
        created_at=row.created_at.isoformat(),
    )
```

- [ ] **Step 6: 新增 `get_backtest_result()` 函数**

在 `_to_view()` 函数之后，`_load_target_weights()` 之前，新增：

```python
def get_backtest_result(backtest_id: int, settings=None) -> BacktestResultView:
    """按 ID 查询单条回测结果，不存在时抛 ValueError。"""
    create_all_tables(settings)
    with get_session(settings) as session:
        row = session.get(BacktestResult, backtest_id)
        if row is None:
            raise ValueError(f"回测记录 #{backtest_id} 不存在。")
        return _to_view(row)
```

- [ ] **Step 7: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_result_view_has_equity_curve tests/test_backtest_show.py::test_to_dict_includes_equity_curve tests/test_backtest_show.py::test_get_backtest_result_not_found -v
```

预期：三个测试全部 `PASSED`。

- [ ] **Step 8: 更新 `run_backtest_for_strategy` 存储 `equity_curve`**

定位 `run_backtest_for_strategy` 函数（约第 81-120 行）中创建 `BacktestResult` 的代码块。在 `weights_snapshot=...` 行之后新增 `equity_curve`：

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
            equity_curve=json.dumps(metrics.curve),   # ← 新增
        )
```

- [ ] **Step 9: 更新 `run_quant_backtest` 存储 `equity_curve`**

定位 `run_quant_backtest` 函数（约第 134-189 行）中创建 `BacktestResult` 的代码块，同样新增 `equity_curve`：

```python
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file="DB:MarketBar",
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            weights_snapshot=json.dumps(final_weights),
            backtest_type="dynamic",
            equity_curve=json.dumps(metrics.curve),   # ← 新增
        )
```

- [ ] **Step 10: 运行全量测试，确认无回归**

```bash
uv run python -m pytest -q
```

预期：全部通过。

- [ ] **Step 11: 提交**

```bash
git add src/hiveflow/application/backtest.py tests/test_backtest_show.py
git commit -m "feat: BacktestResultView 新增 equity_curve，application 层存储权益曲线"
```

---

## Chunk 4: CLI — sparkline 函数 + `backtest show`

### Task 4: `_sparkline()` 函数 + `backtest show` 命令

**Files:**
- Modify: `src/hiveflow/cli.py`（在文件顶部工具函数区新增 `_sparkline()`；在 `backtest_app` 区新增 `show` 命令）
- Test: `tests/test_backtest_show.py`

背景：`cli.py` 顶部有一批私有工具函数（如 `_validate_output_format`、`_build_json_envelope`）。`backtest_app` 的命令注册在 `backtest_app.command("run")`、`backtest_app.command("list")`、`backtest_app.command("quant-run")` 附近。新命令 `show` 和 `compare` 注册在 `quant-run` 之后，`app.add_typer(backtest_app, ...)` 之前。

- [ ] **Step 1: 写 sparkline 单元测试**

在 `tests/test_backtest_show.py` 追加：

```python
from hiveflow.cli import _sparkline


def test_sparkline_flat() -> None:
    """平坦曲线（全部相同值）应全部输出 '▁'。"""
    result = _sparkline([1.0] * 20)
    assert all(c == "▁" for c in result)
    assert len(result) > 0


def test_sparkline_rising() -> None:
    """上涨曲线末尾字符不低于首字符。"""
    curve = [1.0 + i * 0.01 for i in range(50)]
    result = _sparkline(curve, width=20)
    assert result[-1] >= result[0]


def test_sparkline_width() -> None:
    """输入长度 >= 40 的曲线，width=10 时输出恰好 10 字符。"""
    curve = [1.0 + i * 0.01 for i in range(50)]
    result = _sparkline(curve, width=10)
    assert len(result) == 10


def test_sparkline_short_curve() -> None:
    """输入长度 < width 时，输出长度为 len(curve)（不补齐）。"""
    curve = [1.0, 1.05, 1.1]
    result = _sparkline(curve, width=40)
    assert len(result) == 3


def test_sparkline_empty() -> None:
    """空曲线或长度 < 2 返回全 '─'。"""
    assert _sparkline([]) == "─" * 40
    assert _sparkline([1.0]) == "─" * 40
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_sparkline_flat -v
```

预期：`FAILED`，`ImportError: cannot import name '_sparkline' from 'hiveflow.cli'`。

- [ ] **Step 3: 在 `cli.py` 新增 `_sparkline()` 函数**

在 `cli.py` 顶部工具函数区（`_validate_output_format` 或 `_build_json_envelope` 附近），新增：

```python
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(curve: list[float], width: int = 40) -> str:
    """将权益曲线降采样到至多 width 个字符，映射到 8 级 Unicode 块字符。

    - len(curve) >= width → 输出恰好 width 个字符
    - len(curve) < width  → 输出 len(curve) 个字符（不补齐）
    - len(curve) < 2      → 返回 width 个 '─'
    """
    if not curve or len(curve) < 2:
        return "─" * width
    step = max(1, len(curve) // width)
    sampled = [
        sum(curve[i : i + step]) / len(curve[i : i + step])
        for i in range(0, len(curve), step)
    ][:width]
    lo, hi = min(sampled), max(sampled)
    if lo == hi:
        return _SPARK_CHARS[0] * len(sampled)
    bucket = (hi - lo) / (len(_SPARK_CHARS) - 1)
    return "".join(
        _SPARK_CHARS[min(int((v - lo) / bucket), len(_SPARK_CHARS) - 1)]
        for v in sampled
    )
```

- [ ] **Step 4: 运行 sparkline 测试，确认通过**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_sparkline_flat tests/test_backtest_show.py::test_sparkline_rising tests/test_backtest_show.py::test_sparkline_width tests/test_backtest_show.py::test_sparkline_short_curve tests/test_backtest_show.py::test_sparkline_empty -v
```

预期：5 个测试全部 `PASSED`。

- [ ] **Step 5: 写 `backtest show` CLI 测试**

在 `tests/test_backtest_show.py` 追加：

```python
from typer.testing import CliRunner

from hiveflow.cli import app


def test_backtest_show_cli(tmp_path: Path, monkeypatch) -> None:
    """backtest show <id> 应输出策略名、总收益、sparkline 字符。"""
    curve = [1.0 + i * 0.01 for i in range(50)]
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=curve)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    result = CliRunner().invoke(app, ["backtest", "show", str(rid)])
    assert result.exit_code == 0
    assert "TestStrategy" in result.output
    # sparkline 字符至少出现一个
    assert any(c in result.output for c in "▁▂▃▄▅▆▇█")


def test_backtest_show_no_curve(tmp_path: Path, monkeypatch) -> None:
    """equity_curve=NULL 的旧记录，exit_code=0，输出含降级提示。"""
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=None)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    result = CliRunner().invoke(app, ["backtest", "show", str(rid)])
    assert result.exit_code == 0
    assert "无曲线数据" in result.output


def test_backtest_show_missing_id(tmp_path: Path, monkeypatch) -> None:
    """不存在的 ID，exit_code=1，输出错误提示。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    result = CliRunner().invoke(app, ["backtest", "show", "9999"])
    assert result.exit_code == 1
    assert "不存在" in result.output


def test_backtest_show_json_output(tmp_path: Path, monkeypatch) -> None:
    """backtest show --output json 应输出含 strategy_name 和 equity_curve 的 dict。"""
    import json as _json
    curve = [1.0, 1.05, 1.1]
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=curve)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    result = CliRunner().invoke(app, ["backtest", "show", str(rid), "--output", "json"])
    assert result.exit_code == 0
    data = _json.loads(result.output)
    assert "strategy_name" in data
    assert "equity_curve" in data
```

- [ ] **Step 6: 运行 show 测试，确认失败**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_show_cli -v
```

预期：`FAILED`，`No such command 'show'`。

- [ ] **Step 7: 在 `cli.py` 新增 `backtest show` 命令**

在 `backtest_app.command("quant-run")` 函数定义之后（`backtest_quant_run_command` 函数结束后），新增：

```python
@backtest_app.command("show")
def backtest_show_command(
    backtest_id: int = typer.Argument(..., help="回测记录 ID（来自 backtest list）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """展示单条回测的权益曲线（Sparkline）和指标汇总。"""
    from hiveflow.application.backtest import get_backtest_result

    output_format = _validate_output_format(output)
    try:
        result = get_backtest_result(backtest_id=backtest_id, settings=Settings())
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if output_format == "json":
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    # pretty 输出
    type_label = "动态" if result.backtest_type == "dynamic" else "静态"
    console.print(
        f"\n[bold]回测 #{result.id} · {result.strategy_name} · {type_label} · {result.periods} 天[/bold]"
    )
    console.print(
        f"\n  总收益 [{'green' if result.total_return >= 0 else 'red'}]{result.total_return:+.2%}[/]"
        f"   最大回撤 [red]{result.max_drawdown:.2%}[/]"
        f"   Sharpe [yellow]{result.sharpe:.2f}[/]"
    )
    console.print()
    if result.equity_curve is None:
        console.print("  [dim]权益曲线[/dim]")
        console.print("  [dim][历史记录无曲线数据，重新运行回测可获得曲线][/dim]")
    else:
        curve = json.loads(result.equity_curve)
        spark = _sparkline(curve, width=40)
        console.print(f"  [dim]权益曲线（{result.periods} 期）[/dim]")
        console.print(f"  [green]{spark}[/green]")
        console.print(f"  [dim]创建：{result.created_at[:10]}[/dim]")
    console.print()
```

- [ ] **Step 8: 运行 show 测试，确认通过**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_show_cli tests/test_backtest_show.py::test_backtest_show_no_curve tests/test_backtest_show.py::test_backtest_show_missing_id tests/test_backtest_show.py::test_backtest_show_json_output -v
```

预期：4 个测试全部 `PASSED`。

- [ ] **Step 9: 运行全量测试，确认无回归**

```bash
uv run python -m pytest -q
```

预期：全部通过。

- [ ] **Step 10: 提交**

```bash
git add src/hiveflow/cli.py tests/test_backtest_show.py
git commit -m "feat: 新增 _sparkline() 函数与 backtest show 命令"
```

---

## Chunk 5: CLI — `backtest compare`

### Task 5: `backtest compare` 命令

**Files:**
- Modify: `src/hiveflow/cli.py`（在 `backtest show` 命令之后新增 `compare` 命令）
- Test: `tests/test_backtest_show.py`

- [ ] **Step 1: 写 `backtest compare` 测试**

在 `tests/test_backtest_show.py` 追加：

```python
def _seed_two_records(tmp_path: Path, monkeypatch) -> tuple[int, int]:
    """种入两条有 equity_curve 的记录，返回 (id1, id2)。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    curve_a = [1.0 + i * 0.01 for i in range(50)]
    curve_b = [1.0 + i * 0.02 for i in range(50)]
    with get_session() as session:
        r1 = BacktestResult(
            strategy_name="StratA", prices_file="DB:MarketBar",
            periods=49, total_return=0.49, max_drawdown=-0.05, sharpe=1.2,
            equity_curve=json.dumps(curve_a),
        )
        r2 = BacktestResult(
            strategy_name="StratB", prices_file="DB:MarketBar",
            periods=49, total_return=0.98, max_drawdown=-0.08, sharpe=1.8,
            equity_curve=json.dumps(curve_b),
        )
        session.add(r1)
        session.add(r2)
        session.commit()
        session.refresh(r1)
        session.refresh(r2)
        return r1.id, r2.id


def test_backtest_compare_cli(tmp_path: Path, monkeypatch) -> None:
    """backtest compare id1 id2 应输出含两行 sparkline 的结果。"""
    id1, id2 = _seed_two_records(tmp_path, monkeypatch)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    result = CliRunner().invoke(app, ["backtest", "compare", str(id1), str(id2)])
    assert result.exit_code == 0
    # 两行都含 sparkline 字符
    spark_chars = set("▁▂▃▄▅▆▇█")
    lines_with_spark = [l for l in result.output.splitlines() if any(c in l for c in spark_chars)]
    assert len(lines_with_spark) >= 2


def test_backtest_compare_missing_id(tmp_path: Path, monkeypatch) -> None:
    """含不存在的 ID，exit_code=1，输出列出无效 ID。"""
    id1, _ = _seed_two_records(tmp_path, monkeypatch)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    result = CliRunner().invoke(app, ["backtest", "compare", str(id1), "9999"])
    assert result.exit_code == 1
    assert "9999" in result.output


def test_backtest_compare_json_output(tmp_path: Path, monkeypatch) -> None:
    """backtest compare --output json 输出含 2 个元素的 list，每项含 strategy_name。"""
    import json as _json
    id1, id2 = _seed_two_records(tmp_path, monkeypatch)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    result = CliRunner().invoke(
        app, ["backtest", "compare", str(id1), str(id2), "--output", "json"]
    )
    assert result.exit_code == 0
    data = _json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 2
    assert "strategy_name" in data[0]
    assert "strategy_name" in data[1]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_compare_cli -v
```

预期：`FAILED`，`No such command 'compare'`。

- [ ] **Step 3: 在 `cli.py` 新增 `backtest compare` 命令**

在 `backtest show` 命令之后新增：

```python
@backtest_app.command("compare")
def backtest_compare_command(
    ids: list[int] = typer.Argument(..., help="要对比的回测 ID 列表（至少 2 个）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """并排对比多个回测的权益曲线和指标。"""
    from hiveflow.application.backtest import get_backtest_result

    output_format = _validate_output_format(output)

    # 全量预检：收集所有无效 ID，有任何无效则退出
    invalid_ids = []
    results = []
    for bid in ids:
        try:
            results.append(get_backtest_result(backtest_id=bid, settings=Settings()))
        except ValueError:
            invalid_ids.append(bid)
    if invalid_ids:
        typer.echo(f"错误：以下回测 ID 不存在：{', '.join(str(i) for i in invalid_ids)}")
        raise typer.Exit(code=1)

    if output_format == "json":
        typer.echo(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
        return

    # pretty 输出：指标对比表
    table = Table(title="策略对比", show_lines=False, box=box.SIMPLE)
    table.add_column("ID", justify="right")
    table.add_column("策略", style="bold")
    table.add_column("类型")
    table.add_column("周期", justify="right")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("Sharpe", justify="right")
    for r in results:
        type_label = "动态" if r.backtest_type == "dynamic" else "静态"
        ret_color = "green" if r.total_return >= 0 else "red"
        table.add_row(
            str(r.id),
            r.strategy_name,
            type_label,
            str(r.periods),
            f"[{ret_color}]{r.total_return:+.2%}[/{ret_color}]",
            f"[red]{r.max_drawdown:.2%}[/red]",
            f"{r.sharpe:.2f}",
        )
    console.print(table)

    # sparkline 对比行
    console.print("  [dim]权益曲线（各起点归一为 1.0）[/dim]")
    # 策略名最大宽度，用于对齐
    max_name_len = max(len(r.strategy_name) for r in results)
    for r in results:
        prefix = f"  #{r.id}  {r.strategy_name.ljust(max_name_len)}  "
        if r.equity_curve is None:
            spark = "[dim][无曲线数据][/dim]"
        else:
            curve = json.loads(r.equity_curve)
            spark = f"[green]{_sparkline(curve, width=28)}[/green]"
        console.print(prefix + spark)
    console.print()
```

- [ ] **Step 4: 运行 compare 测试，确认通过**

```bash
uv run python -m pytest tests/test_backtest_show.py::test_backtest_compare_cli tests/test_backtest_show.py::test_backtest_compare_missing_id tests/test_backtest_show.py::test_backtest_compare_json_output -v
```

预期：3 个测试全部 `PASSED`。

- [ ] **Step 5: 运行全量测试，确认无回归**

```bash
uv run python -m pytest -q
```

预期：全部通过（约 217 passed）。

- [ ] **Step 6: 手动验证 CLI 输出（可选但推荐）**

```bash
uv run hiveflow backtest --help
# 应看到 show 和 compare 两个新命令

uv run hiveflow backtest list
# 找到一个有效 ID（如 1）

uv run hiveflow backtest show 1
# 应看到权益曲线 sparkline（或"无曲线数据"提示）
```

- [ ] **Step 7: 提交**

```bash
git add src/hiveflow/cli.py tests/test_backtest_show.py
git commit -m "feat: 新增 backtest compare 命令，支持多回测权益曲线并排对比"
```

---

## Chunk 6: 收尾

### Task 6: 更新文档 + 最终验证

**Files:**
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/SESSION_LOG.md`

- [ ] **Step 1: 更新 `CURRENT_STATE.md`**

在"当前可用命令"列表中，将 `hiveflow backtest ...` 更新为：
```
- `hiveflow backtest ...`（含 `quant-run` 动态回测、`show` 权益曲线、`compare` 多策略对比）
```

在"全量测试最近结果"更新为最新通过数（约 `217 passed`）。

- [ ] **Step 2: 向 `SESSION_LOG.md` 追加本次会话记录**

在 `## 2026-03-18` 节末尾追加：

```markdown
- 完成 M7 Chunk A：新增 `backtest show / compare`，支持终端 Unicode Sparkline 权益曲线可视化与多策略并排对比。
- 全量测试：约 217 passed。
```

- [ ] **Step 3: 最终全量测试**

```bash
uv run python -m pytest -q
```

预期：全部通过，无任何失败。

- [ ] **Step 4: 提交**

```bash
git add docs/context/CURRENT_STATE.md docs/context/SESSION_LOG.md
git commit -m "docs: 更新文档，记录 M7 backtest show/compare 交付"
```
