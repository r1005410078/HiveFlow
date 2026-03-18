# Risk Analysis Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 HiveFlow 新增风险分析引擎，提供资产级（波动率、相关性矩阵、历史 MDD）与组合级（年化波动率、胜率、Calmar ratio）风险指标，通过 `hiveflow risk-analysis` 命令组与增强后的 `backtest show` 输出。

**Architecture:** 新增 `services/risk_engine.py`（纯计算，无 DB 依赖）+ `application/risk_analysis.py`（从 DB 读取数据，调用引擎），模式与现有 `backtest_engine.py` + `application/backtest.py` 完全对称。CLI 新增 `risk_analysis_app` 命令组，`backtest show` 追加风险指标节。

**Tech Stack:** Python 3.12+, typer, rich（已有依赖），SQLite + SQLModel（读现有 MarketBar / BacktestResult 表），无新增第三方依赖（手工实现统计计算，不用 numpy/pandas）。

---

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/hiveflow/services/risk_engine.py` | 新建 | 纯计算：波动率、相关性、MDD、组合风险 |
| `src/hiveflow/application/risk_analysis.py` | 新建 | DB 读取 + 引擎调用 + 视图对象 |
| `src/hiveflow/cli.py` | 修改 | 新增 `risk_analysis_app`；增强 `backtest show` |
| `tests/test_risk_engine.py` | 新建 | 服务层纯计算测试 |
| `tests/test_risk_analysis_cli.py` | 新建 | CLI 集成测试 |

---

## Chunk 1: Service Layer

### Task 1: `risk_engine.py` — 数据结构 + `compute_volatility`

**Files:**
- Create: `src/hiveflow/services/risk_engine.py`
- Test: `tests/test_risk_engine.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_risk_engine.py`，写前三个测试：

```python
"""风险引擎纯计算测试。"""
from __future__ import annotations

import math

from hiveflow.services.backtest_engine import PriceBar
from hiveflow.services.risk_engine import (
    AssetVolatility,
    compute_volatility,
)


def _make_bars(symbol: str, closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(symbol=symbol, timestamp=f"2026-01-{i+1:02d}T00:00:00Z", close=c)
        for i, c in enumerate(closes)
    ]


def test_compute_volatility_basic() -> None:
    """annual_vol == daily_vol × sqrt(365)，且 annual_vol > daily_vol。"""
    prices = {"BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0, 110.0])}
    results = compute_volatility(prices)
    assert len(results) == 1
    v = results[0]
    assert v.symbol == "BTC"
    assert v.periods == 5
    assert v.daily_vol >= 0.0
    assert abs(v.annual_vol - v.daily_vol * math.sqrt(365)) < 1e-9


def test_compute_volatility_sorts_descending() -> None:
    """结果按 annual_vol 降序排列。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0]),  # 较大波动
        "USDT": _make_bars("USDT", [1.0, 1.0, 1.0, 1.0]),          # 零波动
    }
    results = compute_volatility(prices)
    assert len(results) >= 1
    for i in range(len(results) - 1):
        assert results[i].annual_vol >= results[i + 1].annual_vol


def test_compute_volatility_insufficient_data() -> None:
    """少于 2 个价格点的资产应被跳过（不报错）。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0]),          # 只有 1 个点，跳过
        "ETH": _make_bars("ETH", [50.0, 55.0, 52.0]),  # 正常
    }
    results = compute_volatility(prices)
    symbols = [v.symbol for v in results]
    assert "BTC" not in symbols
    assert "ETH" in symbols
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m pytest tests/test_risk_engine.py -q
```

预期：`ImportError: cannot import name 'compute_volatility'`

- [ ] **Step 3: 新建 `src/hiveflow/services/risk_engine.py`，实现数据结构 + `compute_volatility`**

```python
"""风险分析引擎——纯计算，无 DB 依赖。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from hiveflow.services.backtest_engine import PriceBar


@dataclass(frozen=True)
class AssetVolatility:
    symbol: str
    annual_vol: float   # 年化标准差（daily_vol × sqrt(365)）
    daily_vol: float    # 日标准差（样本标准差，ddof=1）
    periods: int        # 价格条数（非收益率条数）


@dataclass(frozen=True)
class CorrelationMatrix:
    symbols: list[str]
    matrix: list[list[float]]   # n×n Pearson 矩阵；对角线 == 1.0；不足数据时填 nan


@dataclass(frozen=True)
class AssetDrawdown:
    symbol: str
    max_drawdown: float   # 非正数：有回撤时为负（如 -0.85），无回撤时为 0.0
    periods: int          # 价格条数


def compute_volatility(prices: dict[str, list[PriceBar]]) -> list[AssetVolatility]:
    """计算各资产日收益率的样本标准差（ddof=1），年化（× sqrt(365)）。

    - 数据点 < 2 的资产跳过（不报错）
    - 结果按 annual_vol 降序排列
    """
    results: list[AssetVolatility] = []
    for symbol, bars in prices.items():
        if len(bars) < 2:
            continue
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        returns = [
            sorted_bars[i].close / sorted_bars[i - 1].close - 1.0
            for i in range(1, len(sorted_bars))
            if sorted_bars[i - 1].close > 0
        ]
        if not returns:
            continue
        n = len(returns)
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / max(n - 1, 1)
        daily_vol = math.sqrt(variance)
        annual_vol = daily_vol * math.sqrt(365)
        results.append(AssetVolatility(
            symbol=symbol,
            annual_vol=annual_vol,
            daily_vol=daily_vol,
            periods=len(sorted_bars),
        ))
    return sorted(results, key=lambda x: x.annual_vol, reverse=True)
```

- [ ] **Step 4: 运行测试**

```bash
uv run python -m pytest tests/test_risk_engine.py -q
```

预期：3 passed

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/risk_engine.py tests/test_risk_engine.py
git commit -m "feat: 风险引擎 compute_volatility + 数据结构"
```

---

### Task 2: `compute_correlation`

**Files:**
- Modify: `src/hiveflow/services/risk_engine.py`
- Modify: `tests/test_risk_engine.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_risk_engine.py` 顶部 import 增加 `CorrelationMatrix, compute_correlation`，在文件末尾追加：

```python
from hiveflow.services.risk_engine import (
    AssetVolatility,
    CorrelationMatrix,
    compute_volatility,
    compute_correlation,
)
```

（替换原有 import 行）

追加测试：

```python
def test_compute_correlation_identity() -> None:
    """matrix[i][i] == 1.0（自相关为 1）。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0]),
        "ETH": _make_bars("ETH", [50.0, 55.0, 52.0, 57.0]),
    }
    result = compute_correlation(prices)
    assert result.symbols == ["BTC", "ETH"]
    assert result.matrix[0][0] == 1.0
    assert result.matrix[1][1] == 1.0


def test_compute_correlation_perfect_positive() -> None:
    """完全相同的收益率序列 → 相关系数 == 1.0。"""
    closes = [100.0, 110.0, 121.0, 133.1]
    prices = {
        "A": _make_bars("A", closes),
        "B": _make_bars("B", [c * 0.5 for c in closes]),  # 等比缩放 → 收益率完全相同
    }
    result = compute_correlation(prices)
    i = result.symbols.index("A")
    j = result.symbols.index("B")
    assert abs(result.matrix[i][j] - 1.0) < 1e-9


def test_compute_correlation_aligns_timestamps() -> None:
    """两资产时间戳错开时，只用共同时间点计算相关性（结果为有效浮点数）。"""
    # A 覆盖 day1~day4，B 覆盖 day3~day6
    a_closes = [100.0, 110.0, 120.0, 130.0]
    b_closes = [50.0, 55.0, 60.0, 65.0]
    a_bars = [
        PriceBar(symbol="A", timestamp=f"2026-01-0{i+1}T00:00:00Z", close=c)
        for i, c in enumerate(a_closes)
    ]
    b_bars = [
        PriceBar(symbol="B", timestamp=f"2026-01-0{i+3}T00:00:00Z", close=c)
        for i, c in enumerate(b_closes)
    ]
    result = compute_correlation({"A": a_bars, "B": b_bars})
    i = result.symbols.index("A")
    j = result.symbols.index("B")
    # 共同收益率时间点 day4（A: 130/120-1, B: 55/50-1）→ 只有 1 个点 → nan
    assert math.isnan(result.matrix[i][j])
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m pytest tests/test_risk_engine.py -k "correlation" -q
```

预期：`ImportError` 或 `NameError`

- [ ] **Step 3: 实现 `compute_correlation`**

在 `src/hiveflow/services/risk_engine.py` 末尾追加：

```python
def compute_correlation(prices: dict[str, list[PriceBar]]) -> CorrelationMatrix:
    """计算资产两两之间的 Pearson 相关系数矩阵。

    - 对齐到各对资产的共同收益率时间戳（return 归属到 price[t] 的 timestamp）
    - 共同点 < 2 → 对应位置填 float('nan')
    - symbols 按字母序排列；matrix[i][i] == 1.0
    """
    symbols = sorted(prices.keys())

    # 构建各资产收益率 dict: timestamp → return
    returns_map: dict[str, dict[str, float]] = {}
    for symbol, bars in prices.items():
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        sym_returns: dict[str, float] = {}
        for i in range(1, len(sorted_bars)):
            if sorted_bars[i - 1].close > 0:
                r = sorted_bars[i].close / sorted_bars[i - 1].close - 1.0
                sym_returns[sorted_bars[i].timestamp] = r
        returns_map[symbol] = sym_returns

    n = len(symbols)
    matrix: list[list[float]] = [[0.0] * n for _ in range(n)]

    for i, si in enumerate(symbols):
        for j, sj in enumerate(symbols):
            if i == j:
                matrix[i][j] = 1.0
                continue
            common_ts = sorted(set(returns_map[si]) & set(returns_map[sj]))
            if len(common_ts) < 2:
                matrix[i][j] = float("nan")
                continue
            xs = [returns_map[si][ts] for ts in common_ts]
            ys = [returns_map[sj][ts] for ts in common_ts]
            n_c = len(xs)
            mean_x = sum(xs) / n_c
            mean_y = sum(ys) / n_c
            cov = sum((xs[k] - mean_x) * (ys[k] - mean_y) for k in range(n_c))
            var_x = sum((xs[k] - mean_x) ** 2 for k in range(n_c))
            var_y = sum((ys[k] - mean_y) ** 2 for k in range(n_c))
            if var_x == 0 or var_y == 0:
                matrix[i][j] = float("nan")
            else:
                matrix[i][j] = cov / math.sqrt(var_x * var_y)

    return CorrelationMatrix(symbols=symbols, matrix=matrix)
```

- [ ] **Step 4: 运行测试**

```bash
uv run python -m pytest tests/test_risk_engine.py -q
```

预期：6 passed

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/risk_engine.py tests/test_risk_engine.py
git commit -m "feat: 风险引擎 compute_correlation"
```

---

### Task 3: `compute_drawdown` + `compute_portfolio_risk`

**Files:**
- Modify: `src/hiveflow/services/risk_engine.py`
- Modify: `tests/test_risk_engine.py`

- [ ] **Step 1: 追加失败测试**

更新 import（加 `AssetDrawdown, compute_drawdown, compute_portfolio_risk`），在文件末尾追加：

```python
from hiveflow.services.risk_engine import (
    AssetVolatility,
    CorrelationMatrix,
    AssetDrawdown,
    compute_volatility,
    compute_correlation,
    compute_drawdown,
    compute_portfolio_risk,
)
```

追加测试：

```python
def test_compute_drawdown_basic() -> None:
    """已知价格序列：峰值后跌去 50% → MDD == -0.5。"""
    # 100 → 200 → 100：从峰值 200 跌到 100，MDD = 100/200 - 1 = -0.5
    prices = {"BTC": _make_bars("BTC", [100.0, 200.0, 100.0])}
    results = compute_drawdown(prices)
    assert len(results) == 1
    assert abs(results[0].max_drawdown - (-0.5)) < 1e-9
    assert results[0].periods == 3


def test_compute_drawdown_flat() -> None:
    """平坦价格序列 → MDD == 0.0（无回撤）。"""
    prices = {"USDT": _make_bars("USDT", [1.0, 1.0, 1.0, 1.0])}
    results = compute_drawdown(prices)
    assert results[0].max_drawdown == 0.0


def test_compute_drawdown_sorts_ascending() -> None:
    """结果按 max_drawdown 升序（最大亏损在前）。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0, 200.0, 50.0]),   # MDD = -0.75
        "ETH": _make_bars("ETH", [100.0, 110.0, 100.0]),  # MDD ≈ -0.09
    }
    results = compute_drawdown(prices)
    assert results[0].max_drawdown <= results[1].max_drawdown


def test_compute_portfolio_risk_basic() -> None:
    """已知 curve，验证 win_rate 和 calmar_ratio 基本正确。"""
    # curve: 1.0 → 1.1 → 1.05 → 1.2
    # returns: [0.1, -0.0454, 0.1428]
    # win_rate: 2/3 ≈ 0.667
    # MDD: 1.05/1.1 - 1 ≈ -0.0454
    # total_return: 1.2/1.0 - 1 = 0.2
    # calmar: 0.2 / 0.0454 ≈ 4.4
    curve = [1.0, 1.1, 1.05, 1.2]
    result = compute_portfolio_risk(curve)
    assert "annual_vol" in result
    assert "win_rate" in result
    assert "calmar_ratio" in result
    assert abs(result["win_rate"] - 2 / 3) < 1e-9
    assert result["calmar_ratio"] > 0


def test_compute_portfolio_risk_too_short() -> None:
    """len(curve) < 2 应抛 ValueError。"""
    import pytest
    with pytest.raises(ValueError):
        compute_portfolio_risk([1.0])
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m pytest tests/test_risk_engine.py -k "drawdown or portfolio" -q
```

- [ ] **Step 3: 实现 `compute_drawdown` + `compute_portfolio_risk`**

在 `src/hiveflow/services/risk_engine.py` 末尾追加：

```python
def compute_drawdown(prices: dict[str, list[PriceBar]]) -> list[AssetDrawdown]:
    """计算各资产在给定价格序列中的最大回撤（从峰值到谷值）。

    - max_drawdown 为非正数（回撤为负，无回撤为 0.0）
    - 结果按 max_drawdown 升序（最大亏损在前）
    """
    results: list[AssetDrawdown] = []
    for symbol, bars in prices.items():
        if not bars:
            continue
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        closes = [b.close for b in sorted_bars]
        peak = closes[0]
        max_dd = 0.0
        for c in closes:
            if c > peak:
                peak = c
            if peak > 0:
                dd = c / peak - 1.0
                if dd < max_dd:
                    max_dd = dd
        results.append(AssetDrawdown(
            symbol=symbol,
            max_drawdown=max_dd,
            periods=len(sorted_bars),
        ))
    return sorted(results, key=lambda x: x.max_drawdown)


def compute_portfolio_risk(curve: list[float]) -> dict:
    """从 equity curve 派生组合级风险指标。

    返回: annual_vol（年化波动率）, win_rate（正收益期比例）, calmar_ratio（总收益/|MDD|）

    - len(curve) < 2 → 抛 ValueError
    - MDD == 0 时 calmar_ratio 为 float('inf')
    """
    if len(curve) < 2:
        raise ValueError("equity curve 至少需要 2 个数据点。")
    returns = [curve[i] / curve[i - 1] - 1.0 for i in range(1, len(curve))]
    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / max(n - 1, 1)
    daily_vol = math.sqrt(variance)
    annual_vol = daily_vol * math.sqrt(365)
    win_rate = sum(1 for r in returns if r > 0) / n
    # MDD from curve
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = v / peak - 1.0
            if dd < max_dd:
                max_dd = dd
    total_return = curve[-1] / curve[0] - 1.0
    calmar = total_return / abs(max_dd) if max_dd != 0.0 else float("inf")
    return {
        "annual_vol": annual_vol,
        "win_rate": win_rate,
        "calmar_ratio": calmar,
    }
```

- [ ] **Step 4: 运行全部 risk_engine 测试**

```bash
uv run python -m pytest tests/test_risk_engine.py -q
```

预期：11 passed

- [ ] **Step 5: 运行全量**

```bash
uv run python -m pytest -q
```

预期：232 passed（221 + 11），0 failures

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/services/risk_engine.py tests/test_risk_engine.py
git commit -m "feat: 风险引擎 compute_drawdown + compute_portfolio_risk"
```

---

## Chunk 2: Application Layer

### Task 4: `application/risk_analysis.py`

**Files:**
- Create: `src/hiveflow/application/risk_analysis.py`
- Create: `tests/test_risk_analysis_cli.py`

- [ ] **Step 1: 新建测试文件，写应用层测试**

新建 `tests/test_risk_analysis_cli.py`：

```python
"""风险分析应用层与 CLI 集成测试。"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.backtests import BacktestResult
from hiveflow.domain.market_data import MarketBar


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def _seed_market_bars(tmp_path: Path, monkeypatch, symbol_closes: dict[str, list[float]]) -> None:
    """在临时 DB 种入 MarketBar 数据。"""
    from datetime import datetime, timezone
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with get_session() as session:
        for symbol, closes in symbol_closes.items():
            for i, close in enumerate(closes):
                session.add(MarketBar(
                    symbol=symbol,
                    timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=1000.0,
                ))
        session.commit()


def _seed_backtest(tmp_path: Path, monkeypatch, equity_curve=None) -> int:
    """在临时 DB 种入一条 BacktestResult，返回 id。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name="TestStrategy",
            prices_file="DB:MarketBar",
            periods=10,
            total_return=0.15,
            max_drawdown=-0.05,
            sharpe=1.5,
            equity_curve=json.dumps(equity_curve) if equity_curve is not None else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


# ─── Task 4：应用层 ───────────────────────────────────────────────────────────

def test_analyze_asset_risk_basic(tmp_path: Path, monkeypatch) -> None:
    """analyze_asset_risk 返回资产视图列表 + CorrelationView。"""
    from hiveflow.application.risk_analysis import analyze_asset_risk
    _seed_market_bars(tmp_path, monkeypatch, {
        "BTC": [100.0, 110.0, 105.0, 115.0, 110.0],
        "ETH": [50.0, 55.0, 52.0, 57.0, 54.0],
    })
    assets, corr = analyze_asset_risk()
    assert len(assets) == 2
    symbols = [a.symbol for a in assets]
    assert "BTC" in symbols
    assert "ETH" in symbols
    assert corr.symbols == ["BTC", "ETH"]
    assert len(corr.matrix) == 2


def test_analyze_asset_risk_no_data(tmp_path: Path, monkeypatch) -> None:
    """MarketBar 无数据时抛 ValueError。"""
    from hiveflow.application.risk_analysis import analyze_asset_risk
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with pytest.raises(ValueError, match="没有数据"):
        analyze_asset_risk()


def test_analyze_portfolio_risk_basic(tmp_path: Path, monkeypatch) -> None:
    """analyze_portfolio_risk 返回含三个键的 dict。"""
    from hiveflow.application.risk_analysis import analyze_portfolio_risk
    curve = [1.0, 1.05, 1.02, 1.1, 1.08, 1.15]
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=curve)
    result = analyze_portfolio_risk(rid)
    assert result is not None
    assert "annual_vol" in result
    assert "win_rate" in result
    assert "calmar_ratio" in result


def test_analyze_portfolio_risk_null_curve(tmp_path: Path, monkeypatch) -> None:
    """equity_curve=NULL 时返回 None（不抛错）。"""
    from hiveflow.application.risk_analysis import analyze_portfolio_risk
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=None)
    result = analyze_portfolio_risk(rid)
    assert result is None


def test_analyze_portfolio_risk_missing_id(tmp_path: Path, monkeypatch) -> None:
    """ID 不存在时抛 ValueError。"""
    from hiveflow.application.risk_analysis import analyze_portfolio_risk
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with pytest.raises(ValueError, match="不存在"):
        analyze_portfolio_risk(9999)
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m pytest tests/test_risk_analysis_cli.py -k "analyze" -q
```

预期：`ImportError: cannot import name 'analyze_asset_risk'`

- [ ] **Step 3: 新建 `src/hiveflow/application/risk_analysis.py`**

```python
"""风险分析应用服务。"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.services.backtest_engine import load_close_prices_from_db
from hiveflow.services.risk_engine import (
    compute_correlation,
    compute_drawdown,
    compute_portfolio_risk,
    compute_volatility,
)


@dataclass(frozen=True)
class AssetRiskView:
    symbol: str
    annual_vol: float
    daily_vol: float
    max_drawdown: float
    periods: int


@dataclass(frozen=True)
class CorrelationView:
    symbols: list[str]
    matrix: list[list[float]]


def analyze_asset_risk(
    symbols: list[str] | None = None,
    settings=None,
) -> tuple[list[AssetRiskView], CorrelationView]:
    """从 MarketBar 读取价格序列，返回各资产风险视图 + 相关性矩阵。

    symbols=None 时先查询所有 distinct symbol（与 run_quant_backtest 相同模式），
    再调用 load_close_prices_from_db。MarketBar 无数据时抛 ValueError。
    """
    from hiveflow.domain.market_data import MarketBar

    create_all_tables(settings)

    if symbols is None:
        with get_session(settings) as session:
            rows = session.exec(select(MarketBar.symbol).distinct()).all()
        symbols = list(rows)

    if not symbols:
        raise ValueError("MarketBar 中没有数据，请先运行 hiveflow market-data import。")

    prices = load_close_prices_from_db(symbols=symbols, settings=settings)
    if not prices:
        raise ValueError("指定 symbol 在 MarketBar 中无数据。")

    vols = compute_volatility(prices)
    dds = compute_drawdown(prices)
    corr = compute_correlation(prices)

    dd_by_symbol = {d.symbol: d for d in dds}
    asset_views = [
        AssetRiskView(
            symbol=v.symbol,
            annual_vol=v.annual_vol,
            daily_vol=v.daily_vol,
            max_drawdown=dd_by_symbol[v.symbol].max_drawdown if v.symbol in dd_by_symbol else 0.0,
            periods=v.periods,
        )
        for v in vols
    ]
    return asset_views, CorrelationView(symbols=corr.symbols, matrix=corr.matrix)


def analyze_portfolio_risk(
    backtest_id: int,
    settings=None,
) -> dict | None:
    """从 BacktestResult.equity_curve 计算组合级风险指标。

    - backtest_id 不存在 → 抛 ValueError
    - equity_curve 为 NULL → 返回 None（CLI 层输出降级提示，exit_code=0）
    - 正常 → 返回 compute_portfolio_risk() 的结果字典
    """
    from hiveflow.domain.backtests import BacktestResult

    create_all_tables(settings)
    with get_session(settings) as session:
        row = session.get(BacktestResult, backtest_id)
        if row is None:
            raise ValueError(f"回测记录 #{backtest_id} 不存在。")
        equity_curve_str = row.equity_curve

    if equity_curve_str is None:
        return None

    curve = _json.loads(equity_curve_str)
    return compute_portfolio_risk(curve)
```

- [ ] **Step 4: 运行应用层测试**

```bash
uv run python -m pytest tests/test_risk_analysis_cli.py -k "analyze" -q
```

预期：5 passed

- [ ] **Step 5: 运行全量**

```bash
uv run python -m pytest -q
```

预期：237 passed，0 failures

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/application/risk_analysis.py tests/test_risk_analysis_cli.py
git commit -m "feat: 风险分析应用层 analyze_asset_risk + analyze_portfolio_risk"
```

---

## Chunk 3: CLI Commands

### Task 5: `risk-analysis assets` 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Modify: `tests/test_risk_analysis_cli.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_risk_analysis_cli.py` 末尾追加：

```python
# ─── Task 5：risk-analysis assets CLI ────────────────────────────────────────

def test_risk_assets_cli(tmp_path: Path, monkeypatch) -> None:
    """risk-analysis assets exit_code=0，输出含资产名与相关性矩阵标题。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    _seed_market_bars(tmp_path, monkeypatch, {
        "BTC": [100.0, 110.0, 105.0, 115.0, 110.0],
        "ETH": [50.0, 55.0, 52.0, 57.0, 54.0],
    })
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "assets"])
    assert result.exit_code == 0, result.output
    assert "BTC" in result.output
    assert "相关性" in result.output


def test_risk_assets_json(tmp_path: Path, monkeypatch) -> None:
    """--output json 输出含 assets 和 correlation 键的 dict。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    _seed_market_bars(tmp_path, monkeypatch, {
        "BTC": [100.0, 110.0, 105.0, 115.0],
        "ETH": [50.0, 55.0, 52.0, 57.0],
    })
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "assets", "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "assets" in data
    assert "correlation" in data
    assert isinstance(data["assets"], list)


def test_risk_assets_no_data(tmp_path: Path, monkeypatch) -> None:
    """MarketBar 空时 exit_code=1。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "assets"])
    assert result.exit_code == 1
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m pytest tests/test_risk_analysis_cli.py -k "assets" -q
```

预期：`Exit code 2`（命令不存在）

- [ ] **Step 3: 在 `src/hiveflow/cli.py` 新增 `risk_analysis_app`**

在 `cli.py` 顶部 import 区（现有 `from hiveflow.application.backtest import ...` 附近）追加：

```python
from hiveflow.application.risk_analysis import analyze_asset_risk, analyze_portfolio_risk
```

在 `quant_app` 定义行（`quant_app = typer.Typer(...)`）之后，追加：

```python
risk_analysis_app = typer.Typer(help="资产与组合风险分析。")
```

在文件末尾 `app.add_typer(quant_app, name="quant")` 之后追加：

```python
app.add_typer(risk_analysis_app, name="risk-analysis")
```

在 `quant_app` 命令之后（`backtest_app` 命令区末尾，`quant_app` 区末尾之后）追加 `risk-analysis assets` 命令：

```python
@risk_analysis_app.command("assets")
def risk_assets_command(
    symbols: str | None = typer.Option(None, "--symbols", help="资产列表，逗号分隔（不填则用 MarketBar 全部）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """分析各资产年化波动率、历史最大回撤与相关性矩阵。"""
    import math as _math
    output_format = _validate_output_format(output)
    symbols_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else None
    )
    try:
        asset_views, corr_view = analyze_asset_risk(symbols=symbols_list, settings=Settings())
    except ValueError as exc:
        typer.echo(f"错误：{exc}")
        raise typer.Exit(code=1)

    if output_format == "json":
        payload = {
            "assets": [
                {
                    "symbol": v.symbol,
                    "annual_vol": round(v.annual_vol, 6),
                    "daily_vol": round(v.daily_vol, 6),
                    "max_drawdown": round(v.max_drawdown, 6),
                    "periods": v.periods,
                }
                for v in asset_views
            ],
            "correlation": {
                "symbols": corr_view.symbols,
                "matrix": [
                    [
                        round(val, 4) if not _math.isnan(val) else None
                        for val in row
                    ]
                    for row in corr_view.matrix
                ],
            },
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo("资产风险分析\n")
    tbl = Table(show_lines=False, box=box.SIMPLE)
    tbl.add_column("资产")
    tbl.add_column("年化波动率", justify="right")
    tbl.add_column("日波动率", justify="right")
    tbl.add_column("历史 MDD", justify="right")
    tbl.add_column("数据点", justify="right")
    for v in asset_views:
        tbl.add_row(
            v.symbol,
            f"{v.annual_vol:.1%}",
            f"{v.daily_vol:.2%}",
            f"{v.max_drawdown:.1%}",
            str(v.periods),
        )
    console.print(tbl)

    typer.echo("\n  相关性矩阵")
    header = "        " + "  ".join(f"{s:>6}" for s in corr_view.symbols)
    typer.echo(header)
    for i, row in enumerate(corr_view.matrix):
        row_str = f"  {corr_view.symbols[i]:>5}  " + "  ".join(
            f"{val:>6.2f}" if not _math.isnan(val) else "   N/A"
            for val in row
        )
        typer.echo(row_str)
```

- [ ] **Step 4: 运行测试**

```bash
uv run python -m pytest tests/test_risk_analysis_cli.py -k "assets" -q
```

预期：3 passed

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/cli.py tests/test_risk_analysis_cli.py
git commit -m "feat: 新增 risk-analysis assets 命令"
```

---

### Task 6: `risk-analysis portfolio` 命令 + `backtest show` 增强

**Files:**
- Modify: `src/hiveflow/cli.py`
- Modify: `tests/test_risk_analysis_cli.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_risk_analysis_cli.py` 末尾追加：

```python
# ─── Task 6：risk-analysis portfolio + backtest show 增强 ─────────────────────

def test_risk_portfolio_cli(tmp_path: Path, monkeypatch) -> None:
    """risk-analysis portfolio exit_code=0，输出含胜率/Calmar。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    curve = [1.0, 1.05, 1.02, 1.1, 1.08, 1.15]
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=curve)
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "portfolio", str(rid)])
    assert result.exit_code == 0, result.output
    assert "胜率" in result.output or "win" in result.output.lower()
    assert "Calmar" in result.output or "calmar" in result.output.lower()


def test_risk_portfolio_no_curve(tmp_path: Path, monkeypatch) -> None:
    """equity_curve=NULL → exit_code=0，含降级提示。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=None)
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "portfolio", str(rid)])
    assert result.exit_code == 0, result.output
    assert "重新运行" in result.output or "无曲线" in result.output


def test_risk_portfolio_missing_id(tmp_path: Path, monkeypatch) -> None:
    """ID 不存在 → exit_code=1。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "portfolio", "9999"])
    assert result.exit_code == 1


def test_risk_portfolio_json(tmp_path: Path, monkeypatch) -> None:
    """--output json 输出含 annual_vol / win_rate / calmar_ratio 键的 dict。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    curve = [1.0, 1.1, 1.05, 1.2]
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=curve)
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "portfolio", str(rid), "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "annual_vol" in data
    assert "win_rate" in data
    assert "calmar_ratio" in data


def test_backtest_show_includes_risk(tmp_path: Path, monkeypatch) -> None:
    """`backtest show` 含 equity_curve 时，输出含"风险指标"节。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    curve = [1.0 + i * 0.01 for i in range(20)]
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=curve)
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "show", str(rid)])
    assert result.exit_code == 0, result.output
    assert "风险指标" in result.output


def test_backtest_show_no_curve_skips_risk(tmp_path: Path, monkeypatch) -> None:
    """equity_curve=NULL 时，`backtest show` 不含"风险指标"节。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=None)
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "show", str(rid)])
    assert result.exit_code == 0, result.output
    assert "风险指标" not in result.output
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m pytest tests/test_risk_analysis_cli.py -k "portfolio or backtest_show" -q
```

- [ ] **Step 3: 在 `cli.py` 追加 `risk-analysis portfolio` 命令**

在 `risk_assets_command` 之后追加：

```python
@risk_analysis_app.command("portfolio")
def risk_portfolio_command(
    backtest_id: int = typer.Argument(..., help="回测记录 ID"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从回测 equity curve 计算组合年化波动率、胜率与 Calmar ratio。"""
    output_format = _validate_output_format(output)
    try:
        risk = analyze_portfolio_risk(backtest_id, settings=Settings())
    except ValueError as exc:
        typer.echo(f"错误：{exc}")
        raise typer.Exit(code=1)

    if risk is None:
        typer.echo("  [历史记录无曲线数据，重新运行回测可获得组合风险分析]")
        return

    if output_format == "json":
        typer.echo(json.dumps(
            {k: (v if v != float("inf") else None) for k, v in risk.items()},
            ensure_ascii=False,
            indent=2,
        ))
        return

    typer.echo(f"组合风险分析（回测 #{backtest_id}）\n")
    typer.echo(f"  年化波动率   {risk['annual_vol']:.1%}")
    typer.echo(f"  胜率         {risk['win_rate']:.1%}")
    calmar_str = f"{risk['calmar_ratio']:.2f}" if risk["calmar_ratio"] != float("inf") else "∞"
    typer.echo(f"  Calmar       {calmar_str}")
```

- [ ] **Step 4: 增强 `backtest show` 命令**

在 `backtest_show_command` 中，找到以下代码段末尾（`typer.echo(f"  创建：{created_date}")`这行之后）：

当前代码结尾是：
```python
    else:
        curve = json.loads(result.equity_curve)
        spark = _sparkline(curve, width=40)
        typer.echo(f"  权益曲线（{result.periods} 期）")
        typer.echo(f"  {spark}")
        created_date = result.created_at[:10]
        typer.echo(f"  创建：{created_date}")
```

将其替换为：
```python
    else:
        curve = json.loads(result.equity_curve)
        spark = _sparkline(curve, width=40)
        typer.echo(f"  权益曲线（{result.periods} 期）")
        typer.echo(f"  {spark}")
        created_date = result.created_at[:10]
        typer.echo(f"  创建：{created_date}")
        # 风险指标节（从 equity curve 派生）
        try:
            risk = analyze_portfolio_risk(result.id, settings=Settings())
        except ValueError:
            risk = None
        if risk is not None:
            typer.echo("")
            typer.echo("  风险指标")
            typer.echo(f"  年化波动率   {risk['annual_vol']:.1%}")
            typer.echo(f"  胜率         {risk['win_rate']:.1%}")
            calmar_str = f"{risk['calmar_ratio']:.2f}" if risk["calmar_ratio"] != float("inf") else "∞"
            typer.echo(f"  Calmar       {calmar_str}")
```

- [ ] **Step 5: 运行 CLI 测试**

```bash
uv run python -m pytest tests/test_risk_analysis_cli.py -q
```

预期：全部通过（约 14 个测试）

- [ ] **Step 6: 运行全量测试**

```bash
uv run python -m pytest -q
```

预期：约 246 passed，0 failures

- [ ] **Step 7: 提交**

```bash
git add src/hiveflow/cli.py tests/test_risk_analysis_cli.py
git commit -m "feat: 新增 risk-analysis portfolio 命令，增强 backtest show 风险指标节"
```

---

## Chunk 4: Docs Update

### Task 7: 更新文档

**Files:**
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/SESSION_LOG.md`
- Modify: `docs/context/ROADMAP.md`

- [ ] **Step 1: 更新 `CURRENT_STATE.md`**

将"最近完成重点"中追加：
```
  - **M8：`risk-analysis assets` + `risk-analysis portfolio`** 资产波动率/相关性矩阵/MDD + 组合年化波动率/胜率/Calmar；`backtest show` 追加风险指标节
```

将"当前可用命令"中 `hiveflow backtest ...` 行改为：
```
- `hiveflow backtest ...`（含 `quant-run`、`show`、`compare`）
- `hiveflow risk-analysis ...`（`assets` / `portfolio`）
```

将"全量测试最近结果"更新为实际通过数。

- [ ] **Step 2: 向 `SESSION_LOG.md` 追加记录**

追加到 `## 2026-03-18` 段：
```
- 完成 M8：风险分析引擎。新增 `services/risk_engine.py`（compute_volatility / compute_correlation / compute_drawdown / compute_portfolio_risk），`application/risk_analysis.py`（analyze_asset_risk / analyze_portfolio_risk）。新增 `hiveflow risk-analysis assets`（资产波动率、相关性矩阵、历史 MDD）与 `risk-analysis portfolio <id>`（组合年化波动率、胜率、Calmar ratio）。`backtest show` 追加风险指标节。全量测试：N passed。
```

- [ ] **Step 3: 更新 `ROADMAP.md`**

将 M8 候选方向改为"已完成"，新增 M9 候选方向段（网格机器人管理、多策略组合、实盘绩效追踪）。

- [ ] **Step 4: 提交**

```bash
git add docs/context/CURRENT_STATE.md docs/context/SESSION_LOG.md docs/context/ROADMAP.md
git commit -m "docs: 更新文档记录 M8 风险分析引擎交付"
```
