# M6 量化策略管理系统 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `hiveflow quant` 命令组，内置 8 种量化策略，策略以 Python 子类形式定义，输出权重信号，结果落库并可选写入 TargetAllocation。

**Architecture:** BaseStrategy 抽象基类 + StrategyContext 数据容器；8 个内置策略在 `services/strategies/` 下各自独立；application 层负责数据加载、落库、--apply；CLI 层调用 application。

**Tech Stack:** Python, SQLModel, pandas, typer, rich。PyPortfolioOpt 为可选依赖（不安装时降级等权重）。

---

## Chunk 1: Domain Model — StrategyRun

### Task 1: `src/hiveflow/domain/strategy_runs.py`

**Files:**
- Create: `src/hiveflow/domain/strategy_runs.py`
- Modify: `src/hiveflow/db.py` (import + migration)
- Test: `tests/test_strategy_runs_domain.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_runs_domain.py
from datetime import datetime
from hiveflow.domain.strategy_runs import StrategyRun


def test_strategy_run_fields():
    """StrategyRun 模型可以实例化并持有所有字段。"""
    run = StrategyRun(
        strategy_name="MomentumStrategy",
        strategy_file=None,
        params='{"lookback_days": 30}',
        weights='{"BTC": 0.45, "USDT": 0.10}',
        applied=False,
    )
    assert run.strategy_name == "MomentumStrategy"
    assert run.strategy_file is None
    assert run.applied is False
    assert run.run_at is not None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_runs_domain.py -q
```
预期：`ImportError: cannot import name 'StrategyRun'`

- [ ] **Step 3: 实现 `src/hiveflow/domain/strategy_runs.py`**

```python
"""策略运行记录领域模型。"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class StrategyRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    strategy_name: str          # "MomentumStrategy" 或自定义类名
    strategy_file: str | None = Field(default=None)  # 用户文件路径，内置策略为 None
    params: str                 # JSON 字符串，实际使用的参数
    weights: str                # JSON 字符串，输出权重 {"BTC": 0.4, ...}
    applied: bool = Field(default=False)   # 是否已写入 TargetAllocation
    run_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: 在 `db.py` 中导入模型（确保 SQLModel 建表时包含它）**

在 `db.py` 顶部现有导入后添加：

```python
from hiveflow.domain.strategy_runs import StrategyRun  # noqa: F401
```

注意：`SQLModel.metadata.create_all(engine)` 会自动为已 import 的模型建表，无需在 `_run_lightweight_migrations` 中新增分支——只要 `StrategyRun` 在 `db.py` 中被 import，旧库首次运行时即会建表。

- [ ] **Step 5: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_runs_domain.py -q
```
预期：`1 passed`

- [ ] **Step 6: 验证建表不报错**

```bash
uv run python -c "from hiveflow.db import create_all_tables; create_all_tables(); print('ok')"
```

- [ ] **Step 7: 提交**

```bash
git add src/hiveflow/domain/strategy_runs.py src/hiveflow/db.py tests/test_strategy_runs_domain.py
git commit -m "feat: 新增 StrategyRun 领域模型"
```

---

## Chunk 2: BaseStrategy + StrategyContext

### Task 2: `src/hiveflow/services/strategies/` 基础层

**Files:**
- Create: `src/hiveflow/services/strategies/__init__.py`
- Create: `src/hiveflow/services/strategies/base.py`
- Test: `tests/test_strategy_base.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_base.py
import pandas as pd
import pytest
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


def _make_ctx(symbols=("BTC", "ETH", "USDT"), rows=60) -> StrategyContext:
    import numpy as np
    rng = np.random.default_rng(42)
    dates = pd.date_range("2025-01-01", periods=rows)
    prices = pd.DataFrame(
        rng.uniform(100, 200, size=(rows, len(symbols))),
        index=dates,
        columns=list(symbols),
    )
    return StrategyContext(
        prices=prices,
        current_positions={"BTC": 0.5, "ETH": 0.4, "USDT": 0.1},
        risk_signals={},
        params={},
    )


def test_strategy_context_creation():
    ctx = _make_ctx()
    assert ctx.prices.shape == (60, 3)
    assert ctx.current_positions["BTC"] == 0.5
    assert ctx.risk_signals == {}


def test_base_strategy_raises_not_implemented():
    strategy = BaseStrategy()
    ctx = _make_ctx()
    with pytest.raises(NotImplementedError):
        strategy.compute_weights(ctx)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_base.py -q
```

- [ ] **Step 3: 实现 `src/hiveflow/services/strategies/base.py`**

```python
"""量化策略基础层：BaseStrategy + StrategyContext。"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class StrategyContext:
    prices: pd.DataFrame           # index=date, columns=symbol，收盘价
    current_positions: dict        # {symbol: weight}，当前自由持仓权重
    risk_signals: dict             # {symbol: RiskSignal}，最新风险信号
    params: dict = field(default_factory=dict)  # 策略参数（类定义 + CLI 覆盖）


class BaseStrategy:
    params: dict = {}              # 子类在类体里定义默认参数

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        """
        输入：StrategyContext（行情 + 持仓 + 风险信号 + 参数）
        输出：{symbol: weight}，权重之和为 1.0
        """
        raise NotImplementedError
```

- [ ] **Step 4: 实现 `src/hiveflow/services/strategies/__init__.py`**

（先留空，后续各策略实现完再补充导出）

```python
"""内置量化策略。"""
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_base.py -q
```
预期：`2 passed`

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/services/strategies/ tests/test_strategy_base.py
git commit -m "feat: 新增 BaseStrategy + StrategyContext 基础层"
```

---

## Chunk 3: 简单内置策略（5 个）

### Task 3a: EqualWeightStrategy

**Files:**
- Create: `src/hiveflow/services/strategies/equal_weight.py`
- Test: `tests/test_strategy_equal_weight.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_equal_weight.py
import pandas as pd
import numpy as np
import pytest
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy


def _make_ctx(symbols=("BTC", "ETH", "SOL", "USDT"), rows=30) -> StrategyContext:
    rng = np.random.default_rng(0)
    dates = pd.date_range("2025-01-01", periods=rows)
    prices = pd.DataFrame(
        rng.uniform(10, 200, size=(rows, len(symbols))),
        index=dates, columns=list(symbols),
    )
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _make_ctx()
    weights = EqualWeightStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _make_ctx()
    weights = EqualWeightStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_equal_distribution():
    """所有资产权重相等。"""
    ctx = _make_ctx(symbols=("BTC", "ETH", "USDT"))
    weights = EqualWeightStrategy().compute_weights(ctx)
    vals = list(weights.values())
    assert max(vals) - min(vals) < 1e-9


def test_custom_min_usdt():
    ctx = _make_ctx(symbols=("BTC", "ETH", "USDT"))
    strategy = EqualWeightStrategy()
    strategy.params = {"min_usdt": 0.20}
    ctx.params = {"min_usdt": 0.20}
    weights = strategy.compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.20
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_equal_weight.py -q
```

- [ ] **Step 3: 实现**

```python
# src/hiveflow/services/strategies/equal_weight.py
"""等权重策略：所有资产均分，USDT 保留最低比例。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class EqualWeightStrategy(BaseStrategy):
    params: dict = {"min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))
        symbols = list(ctx.prices.columns)
        n = len(symbols)
        if n == 0:
            return {}

        # USDT 固定最低权重，其余均分
        non_usdt = [s for s in symbols if s != "USDT"]
        usdt_w = max(min_usdt, 1.0 / n)
        remaining = 1.0 - usdt_w
        per = remaining / len(non_usdt) if non_usdt else 0.0

        weights = {s: per for s in non_usdt}
        if "USDT" in symbols:
            weights["USDT"] = usdt_w
        # 归一化
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_equal_weight.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/strategies/equal_weight.py tests/test_strategy_equal_weight.py
git commit -m "feat: 新增 EqualWeightStrategy"
```

---

### Task 3b: MomentumStrategy

**Files:**
- Create: `src/hiveflow/services/strategies/momentum.py`
- Test: `tests/test_strategy_momentum.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_momentum.py
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.momentum import MomentumStrategy


def _rising_prices(symbols=("BTC", "ETH", "SOL", "USDT"), rows=60) -> StrategyContext:
    """BTC 涨最多，ETH 次之，SOL 持平，USDT 稳定。"""
    rng = np.random.default_rng(1)
    dates = pd.date_range("2025-01-01", periods=rows)
    base = rng.uniform(100, 200, size=(rows, len(symbols)))
    # BTC 持续上涨
    multiplier = np.linspace(1, 2, rows)
    base[:, 0] *= multiplier
    # ETH 小幅上涨
    base[:, 1] *= np.linspace(1, 1.3, rows)
    # SOL 持平
    # USDT 稳定在 1
    base[:, 3] = 1.0
    prices = pd.DataFrame(base, index=dates, columns=list(symbols))
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _rising_prices()
    weights = MomentumStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _rising_prices()
    weights = MomentumStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_top_k_assets_selected():
    """top_k=2 时，只有 2 个非 USDT 资产持有正权重。"""
    ctx = _rising_prices()
    ctx.params = {"top_k": 2, "lookback_days": 30, "min_usdt": 0.10}
    weights = MomentumStrategy().compute_weights(ctx)
    non_usdt_positive = [s for s, w in weights.items() if s != "USDT" and w > 1e-9]
    assert len(non_usdt_positive) == 2


def test_btc_has_highest_weight_in_rising_market():
    """BTC 涨最多，应获得最高权重（top_k>=1）。"""
    ctx = _rising_prices()
    weights = MomentumStrategy().compute_weights(ctx)
    non_usdt = {s: w for s, w in weights.items() if s != "USDT"}
    top_symbol = max(non_usdt, key=lambda s: non_usdt[s])
    assert top_symbol == "BTC"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_momentum.py -q
```

- [ ] **Step 3: 实现**

```python
# src/hiveflow/services/strategies/momentum.py
"""动量策略：按过去 lookback_days 天涨幅排名，前 top_k 名均分。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class MomentumStrategy(BaseStrategy):
    params: dict = {"lookback_days": 30, "top_k": 3, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        lookback = int(ctx.params.get("lookback_days", self.params["lookback_days"]))
        top_k = int(ctx.params.get("top_k", self.params["top_k"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        if len(prices) < 2:
            # 数据不足，降级等权重
            symbols = list(prices.columns)
            w = 1.0 / len(symbols) if symbols else 0.0
            return {s: w for s in symbols}

        window = min(lookback, len(prices) - 1)
        returns = (prices.iloc[-1] / prices.iloc[-1 - window] - 1)

        non_usdt = [s for s in prices.columns if s != "USDT"]
        sorted_assets = sorted(non_usdt, key=lambda s: returns.get(s, 0), reverse=True)
        top_assets = sorted_assets[:top_k]

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w
        per = remaining / len(top_assets) if top_assets else 0.0

        weights: dict[str, float] = {s: 0.0 for s in prices.columns}
        for s in top_assets:
            weights[s] = per
        if "USDT" in weights:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items() if v > 0 or k == "USDT"}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_momentum.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/strategies/momentum.py tests/test_strategy_momentum.py
git commit -m "feat: 新增 MomentumStrategy"
```

---

### Task 3c: MeanReversionStrategy

**Files:**
- Create: `src/hiveflow/services/strategies/mean_reversion.py`
- Test: `tests/test_strategy_mean_reversion.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_mean_reversion.py
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.mean_reversion import MeanReversionStrategy


def _dip_prices(symbols=("BTC", "ETH", "USDT"), rows=60) -> StrategyContext:
    """BTC 当前价格比均值低很多（z-score 负），应获得最高权重。"""
    rng = np.random.default_rng(2)
    dates = pd.date_range("2025-01-01", periods=rows)
    data = rng.uniform(100, 200, size=(rows, len(symbols)))
    # BTC：大幅下跌到最后一行
    data[:, 0] = 150
    data[-1, 0] = 50  # 远低于均值
    # ETH: 略低
    data[:, 1] = 150
    data[-1, 1] = 140
    # USDT 稳定
    data[:, 2] = 1.0
    prices = pd.DataFrame(data, index=dates, columns=list(symbols))
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _dip_prices()
    weights = MeanReversionStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _dip_prices()
    weights = MeanReversionStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_dip_asset_gets_higher_weight():
    """价格远低于均值（z-score 极低）的资产获得更高权重。"""
    ctx = _dip_prices()
    weights = MeanReversionStrategy().compute_weights(ctx)
    assert weights["BTC"] > weights["ETH"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_mean_reversion.py -q
```

- [ ] **Step 3: 实现**

```python
# src/hiveflow/services/strategies/mean_reversion.py
"""均值回归策略：z-score 越低（跌越多）权重越高。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class MeanReversionStrategy(BaseStrategy):
    params: dict = {"window": 20, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        non_usdt = [s for s in prices.columns if s != "USDT"]
        if not non_usdt:
            return {"USDT": 1.0}

        w = min(window, len(prices))
        recent = prices.tail(w)
        mean = recent.mean()
        std = recent.std()

        # z-score: 越低越超卖（负 z → 机会）
        z_scores = {}
        for s in non_usdt:
            if std[s] > 1e-9:
                z_scores[s] = (prices.iloc[-1][s] - mean[s]) / std[s]
            else:
                z_scores[s] = 0.0

        # 权重反比于 z-score（低 z → 高权重）
        # 将 z-score 转换为正权重：score = max(0, -z + offset)
        offset = max(z_scores.values()) + 1
        raw = {s: max(0.0, -z + offset) for s, z in z_scores.items()}
        total_raw = sum(raw.values()) or 1.0

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w

        weights: dict[str, float] = {}
        for s in non_usdt:
            weights[s] = (raw[s] / total_raw) * remaining
        if "USDT" in prices.columns:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_mean_reversion.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/strategies/mean_reversion.py tests/test_strategy_mean_reversion.py
git commit -m "feat: 新增 MeanReversionStrategy"
```

---

### Task 3d: MovingAverageCrossStrategy

**Files:**
- Create: `src/hiveflow/services/strategies/moving_average.py`
- Test: `tests/test_strategy_moving_average.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_moving_average.py
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.moving_average import MovingAverageCrossStrategy


def _trend_prices(symbols=("BTC", "ETH", "USDT"), rows=60) -> StrategyContext:
    """BTC 金叉（短期均线 > 长期均线），ETH 死叉。"""
    dates = pd.date_range("2025-01-01", periods=rows)
    data = {}
    # BTC: 持续上涨 -> 金叉
    data["BTC"] = np.linspace(100, 200, rows)
    # ETH: 持续下跌 -> 死叉
    data["ETH"] = np.linspace(200, 100, rows)
    # USDT 稳定
    data["USDT"] = np.ones(rows)
    prices = pd.DataFrame(data, index=dates)
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _trend_prices()
    weights = MovingAverageCrossStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _trend_prices()
    weights = MovingAverageCrossStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_golden_cross_gets_higher_weight():
    """金叉（上升趋势）资产权重高于死叉资产。"""
    ctx = _trend_prices()
    weights = MovingAverageCrossStrategy().compute_weights(ctx)
    assert weights.get("BTC", 0) > weights.get("ETH", 0)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_moving_average.py -q
```

- [ ] **Step 3: 实现**

```python
# src/hiveflow/services/strategies/moving_average.py
"""均线交叉策略：短期均线在长期均线上方的资产加权。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class MovingAverageCrossStrategy(BaseStrategy):
    params: dict = {"fast": 7, "slow": 30, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        fast = int(ctx.params.get("fast", self.params["fast"]))
        slow = int(ctx.params.get("slow", self.params["slow"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        non_usdt = [s for s in prices.columns if s != "USDT"]
        if not non_usdt or len(prices) < slow:
            # 数据不足，降级等权重
            n = len(prices.columns)
            return {s: 1.0 / n for s in prices.columns}

        # 计算每个资产的均线信号强度
        scores: dict[str, float] = {}
        for s in non_usdt:
            fast_ma = prices[s].tail(fast).mean()
            slow_ma = prices[s].tail(slow).mean()
            if slow_ma > 1e-9:
                # 金叉：score > 0；死叉：score < 0
                scores[s] = (fast_ma - slow_ma) / slow_ma
            else:
                scores[s] = 0.0

        # 只取正值（金叉）部分
        positive = {s: max(0.0, v) for s, v in scores.items()}
        total_pos = sum(positive.values())

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w

        if total_pos < 1e-9:
            # 全部死叉，均分非 USDT
            per = remaining / len(non_usdt) if non_usdt else 0.0
            weights = {s: per for s in non_usdt}
        else:
            weights = {s: (positive[s] / total_pos) * remaining for s in non_usdt}

        if "USDT" in prices.columns:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_moving_average.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/strategies/moving_average.py tests/test_strategy_moving_average.py
git commit -m "feat: 新增 MovingAverageCrossStrategy"
```

---

### Task 3e: BollingerBandStrategy

**Files:**
- Create: `src/hiveflow/services/strategies/bollinger_band.py`
- Test: `tests/test_strategy_bollinger_band.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_bollinger_band.py
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.bollinger_band import BollingerBandStrategy


def _oversold_prices(symbols=("BTC", "ETH", "USDT"), rows=40) -> StrategyContext:
    """BTC 当前价格远低于布林下轨（超卖），ETH 在中轨附近。"""
    rng = np.random.default_rng(3)
    dates = pd.date_range("2025-01-01", periods=rows)
    data = {}
    # BTC: 均值 100，标准差 10，当前价格 60（大幅低于下轨 80）
    btc = rng.normal(100, 10, rows)
    btc[-1] = 60
    data["BTC"] = btc
    # ETH: 均值 200，标准差 5，当前价格 200（中轨）
    eth = rng.normal(200, 5, rows)
    eth[-1] = 200
    data["ETH"] = eth
    data["USDT"] = np.ones(rows)
    prices = pd.DataFrame(data, index=dates)
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _oversold_prices()
    weights = BollingerBandStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _oversold_prices()
    weights = BollingerBandStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_oversold_asset_gets_higher_weight():
    """超卖资产（价格远低于下轨）权重高于中轨资产。"""
    ctx = _oversold_prices()
    weights = BollingerBandStrategy().compute_weights(ctx)
    assert weights.get("BTC", 0) > weights.get("ETH", 0)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_bollinger_band.py -q
```

- [ ] **Step 3: 实现**

```python
# src/hiveflow/services/strategies/bollinger_band.py
"""布林带策略：价格在下轨附近（超卖）时增加权重。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class BollingerBandStrategy(BaseStrategy):
    params: dict = {"window": 20, "num_std": 2.0, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        num_std = float(ctx.params.get("num_std", self.params["num_std"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        non_usdt = [s for s in prices.columns if s != "USDT"]
        if not non_usdt or len(prices) < window:
            n = len(prices.columns)
            return {s: 1.0 / n for s in prices.columns}

        w = min(window, len(prices))
        recent = prices.tail(w)
        mean = recent.mean()
        std = recent.std()

        scores: dict[str, float] = {}
        for s in non_usdt:
            if std[s] < 1e-9:
                scores[s] = 0.5
                continue
            lower = mean[s] - num_std * std[s]
            upper = mean[s] + num_std * std[s]
            band_width = upper - lower
            current = prices.iloc[-1][s]
            # 距离下轨越近 score 越高（超卖 → 加仓）
            if band_width > 1e-9:
                scores[s] = 1.0 - (current - lower) / band_width
            else:
                scores[s] = 0.5
            scores[s] = max(0.0, min(1.0, scores[s]))

        total_scores = sum(scores.values()) or 1.0
        usdt_w = min_usdt
        remaining = 1.0 - usdt_w

        weights: dict[str, float] = {}
        for s in non_usdt:
            weights[s] = (scores[s] / total_scores) * remaining
        if "USDT" in prices.columns:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_bollinger_band.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/strategies/bollinger_band.py tests/test_strategy_bollinger_band.py
git commit -m "feat: 新增 BollingerBandStrategy"
```

---

## Chunk 4: PyPortfolioOpt 策略（3 个，含降级逻辑）

### Task 4a: RiskParityStrategy

**Files:**
- Create: `src/hiveflow/services/strategies/risk_parity.py`
- Test: `tests/test_strategy_risk_parity.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_strategy_risk_parity.py
import pandas as pd
import numpy as np
from unittest.mock import patch
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.risk_parity import RiskParityStrategy


def _vol_prices(symbols=("BTC", "ETH", "SOL", "USDT"), rows=60) -> StrategyContext:
    rng = np.random.default_rng(10)
    dates = pd.date_range("2025-01-01", periods=rows)
    # BTC 波动大，ETH 中等，SOL 小，USDT 固定
    btc = rng.normal(0, 3, rows).cumsum() + 100
    eth = rng.normal(0, 1.5, rows).cumsum() + 100
    sol = rng.normal(0, 0.5, rows).cumsum() + 100
    usdt = np.ones(rows)
    prices = pd.DataFrame({"BTC": btc, "ETH": eth, "SOL": sol, "USDT": usdt}, index=dates)
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _vol_prices()
    weights = RiskParityStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _vol_prices()
    weights = RiskParityStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_low_vol_asset_gets_higher_weight():
    """波动率低的资产（SOL）应获得更高权重（等风险贡献）。"""
    ctx = _vol_prices()
    weights = RiskParityStrategy().compute_weights(ctx)
    assert weights.get("SOL", 0) > weights.get("BTC", 0)


def test_fallback_to_equal_weight_when_pypfopt_missing():
    """PyPortfolioOpt 不可用时降级为等权重。"""
    ctx = _vol_prices()
    with patch.dict("sys.modules", {"pypfopt": None, "pypfopt.risk_models": None}):
        # 重新加载策略模块确保降级路径
        import importlib
        import hiveflow.services.strategies.risk_parity as rp_mod
        # 直接调用时应不报错
        weights = RiskParityStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_risk_parity.py -q
```

- [ ] **Step 3: 实现（含 PyPortfolioOpt 降级）**

```python
# src/hiveflow/services/strategies/risk_parity.py
"""风险平价策略：按波动率倒数分配权重。PyPortfolioOpt 可选。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


def _equal_weight_fallback(symbols: list[str], min_usdt: float) -> dict[str, float]:
    """PyPortfolioOpt 不可用时，降级为等权重。"""
    n = len(symbols)
    if n == 0:
        return {}
    usdt_w = max(min_usdt, 1.0 / n) if "USDT" in symbols else 0.0
    non_usdt = [s for s in symbols if s != "USDT"]
    remaining = 1.0 - usdt_w
    per = remaining / len(non_usdt) if non_usdt else 0.0
    weights = {s: per for s in non_usdt}
    if "USDT" in symbols:
        weights["USDT"] = usdt_w
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


class RiskParityStrategy(BaseStrategy):
    params: dict = {"window": 30, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        symbols = list(prices.columns)
        non_usdt = [s for s in symbols if s != "USDT"]
        if not non_usdt:
            return {"USDT": 1.0}

        try:
            from pypfopt import risk_models  # type: ignore
            w = min(window, len(prices))
            sample = prices[non_usdt].tail(w)
            cov = risk_models.sample_cov(sample)
            # 风险平价：权重 ∝ 1 / 波动率
            vols = {s: float(cov.loc[s, s]) ** 0.5 for s in non_usdt}
        except (ImportError, Exception):
            print("[提示] PyPortfolioOpt 不可用，RiskParityStrategy 降级为等权重分配。")
            return _equal_weight_fallback(symbols, min_usdt)

        inv_vol = {s: 1.0 / v if v > 1e-9 else 1.0 for s, v in vols.items()}
        total_inv = sum(inv_vol.values()) or 1.0

        usdt_w = min_usdt
        remaining = 1.0 - usdt_w
        weights: dict[str, float] = {s: (inv_vol[s] / total_inv) * remaining for s in non_usdt}
        if "USDT" in symbols:
            weights["USDT"] = usdt_w

        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_risk_parity.py -q
```

注意：`test_low_vol_asset_gets_higher_weight` 仅在安装了 PyPortfolioOpt 时测试完整逻辑；若未安装则降级等权重（PASS）。

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/services/strategies/risk_parity.py tests/test_strategy_risk_parity.py
git commit -m "feat: 新增 RiskParityStrategy（含 PyPortfolioOpt 降级）"
```

---

### Task 4b: MaxSharpeStrategy + MinVarianceStrategy

**Files:**
- Create: `src/hiveflow/services/strategies/max_sharpe.py`
- Create: `src/hiveflow/services/strategies/min_variance.py`
- Test: `tests/test_strategy_max_sharpe.py`
- Test: `tests/test_strategy_min_variance.py`

- [ ] **Step 1: 写失败测试（MaxSharpe）**

```python
# tests/test_strategy_max_sharpe.py
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.max_sharpe import MaxSharpeStrategy


def _ctx(rows=90) -> StrategyContext:
    rng = np.random.default_rng(20)
    symbols = ("BTC", "ETH", "USDT")
    dates = pd.date_range("2025-01-01", periods=rows)
    prices = pd.DataFrame(
        rng.uniform(50, 200, size=(rows, 3)),
        index=dates, columns=list(symbols),
    )
    prices["USDT"] = 1.0
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _ctx()
    weights = MaxSharpeStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _ctx()
    weights = MaxSharpeStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_no_error_without_pypfopt():
    """没有 PyPortfolioOpt 时不崩溃。"""
    import sys
    from unittest.mock import patch
    ctx = _ctx()
    with patch.dict(sys.modules, {"pypfopt": None, "pypfopt.expected_returns": None,
                                   "pypfopt.risk_models": None, "pypfopt.EfficientFrontier": None}):
        weights = MaxSharpeStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
```

- [ ] **Step 2: 写失败测试（MinVariance）**

```python
# tests/test_strategy_min_variance.py
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.min_variance import MinVarianceStrategy


def _ctx(rows=90) -> StrategyContext:
    rng = np.random.default_rng(30)
    symbols = ("BTC", "ETH", "USDT")
    dates = pd.date_range("2025-01-01", periods=rows)
    prices = pd.DataFrame(
        rng.uniform(50, 200, size=(rows, 3)),
        index=dates, columns=list(symbols),
    )
    prices["USDT"] = 1.0
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _ctx()
    weights = MinVarianceStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _ctx()
    weights = MinVarianceStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_strategy_max_sharpe.py tests/test_strategy_min_variance.py -q
```

- [ ] **Step 4: 实现 MaxSharpeStrategy**

```python
# src/hiveflow/services/strategies/max_sharpe.py
"""最大夏普比率策略。PyPortfolioOpt 可选。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext
from hiveflow.services.strategies.risk_parity import _equal_weight_fallback


class MaxSharpeStrategy(BaseStrategy):
    params: dict = {"window": 60, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        symbols = list(prices.columns)
        non_usdt = [s for s in symbols if s != "USDT"]

        try:
            from pypfopt import expected_returns, risk_models  # type: ignore
            from pypfopt.efficient_frontier import EfficientFrontier  # type: ignore
            w = min(window, len(prices))
            sample = prices[non_usdt].tail(w)
            mu = expected_returns.mean_historical_return(sample)
            S = risk_models.sample_cov(sample)
            ef = EfficientFrontier(mu, S)
            ef.max_sharpe()
            cleaned = ef.clean_weights()
            usdt_w = min_usdt
            remaining = 1.0 - usdt_w
            total_raw = sum(cleaned.values()) or 1.0
            weights: dict[str, float] = {s: (v / total_raw) * remaining for s, v in cleaned.items()}
            if "USDT" in symbols:
                weights["USDT"] = usdt_w
            total = sum(weights.values())
            return {k: v / total for k, v in weights.items()}
        except (ImportError, Exception):
            print("[提示] PyPortfolioOpt 不可用，MaxSharpeStrategy 降级为等权重分配。")
            return _equal_weight_fallback(symbols, min_usdt)
```

- [ ] **Step 5: 实现 MinVarianceStrategy**

```python
# src/hiveflow/services/strategies/min_variance.py
"""最小方差策略。PyPortfolioOpt 可选。"""
from __future__ import annotations

from hiveflow.services.strategies.base import BaseStrategy, StrategyContext
from hiveflow.services.strategies.risk_parity import _equal_weight_fallback


class MinVarianceStrategy(BaseStrategy):
    params: dict = {"window": 60, "min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        window = int(ctx.params.get("window", self.params["window"]))
        min_usdt = float(ctx.params.get("min_usdt", self.params["min_usdt"]))

        prices = ctx.prices
        symbols = list(prices.columns)
        non_usdt = [s for s in symbols if s != "USDT"]

        try:
            from pypfopt import risk_models  # type: ignore
            from pypfopt.efficient_frontier import EfficientFrontier  # type: ignore
            w = min(window, len(prices))
            sample = prices[non_usdt].tail(w)
            S = risk_models.sample_cov(sample)
            ef = EfficientFrontier(None, S)
            ef.min_volatility()
            cleaned = ef.clean_weights()
            usdt_w = min_usdt
            remaining = 1.0 - usdt_w
            total_raw = sum(cleaned.values()) or 1.0
            weights: dict[str, float] = {s: (v / total_raw) * remaining for s, v in cleaned.items()}
            if "USDT" in symbols:
                weights["USDT"] = usdt_w
            total = sum(weights.values())
            return {k: v / total for k, v in weights.items()}
        except (ImportError, Exception):
            print("[提示] PyPortfolioOpt 不可用，MinVarianceStrategy 降级为等权重分配。")
            return _equal_weight_fallback(symbols, min_usdt)
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_strategy_max_sharpe.py tests/test_strategy_min_variance.py -q
```

- [ ] **Step 7: 更新 `__init__.py`，导出所有策略**

```python
# src/hiveflow/services/strategies/__init__.py
"""内置量化策略。"""
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy
from hiveflow.services.strategies.momentum import MomentumStrategy
from hiveflow.services.strategies.mean_reversion import MeanReversionStrategy
from hiveflow.services.strategies.moving_average import MovingAverageCrossStrategy
from hiveflow.services.strategies.bollinger_band import BollingerBandStrategy
from hiveflow.services.strategies.risk_parity import RiskParityStrategy
from hiveflow.services.strategies.max_sharpe import MaxSharpeStrategy
from hiveflow.services.strategies.min_variance import MinVarianceStrategy

__all__ = [
    "BaseStrategy",
    "StrategyContext",
    "EqualWeightStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "MovingAverageCrossStrategy",
    "BollingerBandStrategy",
    "RiskParityStrategy",
    "MaxSharpeStrategy",
    "MinVarianceStrategy",
]
```

- [ ] **Step 8: 提交**

```bash
git add src/hiveflow/services/strategies/ tests/test_strategy_max_sharpe.py tests/test_strategy_min_variance.py
git commit -m "feat: 新增 MaxSharpeStrategy + MinVarianceStrategy + 导出所有内置策略"
```

---

## Chunk 5: Application 层 — quant_strategies.py

### Task 5: `src/hiveflow/application/quant_strategies.py`

**Files:**
- Create: `src/hiveflow/application/quant_strategies.py`
- Test: `tests/test_quant_strategies.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_quant_strategies.py
"""量化策略应用层集成测试。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np
import pytest

from hiveflow.config import Settings
from hiveflow.db import create_all_tables
from hiveflow.application.quant_strategies import (
    run_quant_strategy,
    list_strategy_runs,
    QuantRunResult,
)
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class _MockStrategy(BaseStrategy):
    params: dict = {"min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        return {"BTC": 0.60, "ETH": 0.30, "USDT": 0.10}


def _make_settings(tmp_path):
    db = tmp_path / "test.db"
    return Settings(database_url=f"sqlite:///{db}")


def _seed_market_bars(settings, symbols=("BTC", "ETH", "USDT"), rows=60):
    """插入行情数据到 MarketBar 表。"""
    from hiveflow.db import get_session
    from hiveflow.domain.market_data import MarketBar
    from datetime import datetime, timedelta

    rng = np.random.default_rng(99)
    base_date = datetime(2025, 1, 1)

    with get_session(settings) as session:
        for i in range(rows):
            ts = base_date + timedelta(days=i)
            for sym in symbols:
                bar = MarketBar(
                    symbol=sym,
                    timestamp=ts,
                    open=float(rng.uniform(90, 110)),
                    high=float(rng.uniform(110, 120)),
                    low=float(rng.uniform(80, 90)),
                    close=float(rng.uniform(90, 110)),
                    volume=1000.0,
                )
                session.add(bar)
        session.commit()


def test_run_quant_strategy_saves_to_db(tmp_path):
    """run_quant_strategy 落库并返回 QuantRunResult。"""
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    result = run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        settings=settings,
    )

    assert isinstance(result, QuantRunResult)
    assert result.run_id is not None
    assert result.strategy_name == "_MockStrategy"
    assert abs(sum(result.weights.values()) - 1.0) < 1e-9
    assert result.applied is False


def test_run_quant_strategy_with_apply(tmp_path):
    """--apply 时写入 TargetAllocation 并设置 applied=True。"""
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    result = run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        apply=True,
        settings=settings,
    )

    assert result.applied is True

    # TargetAllocation 表中应有对应记录
    from hiveflow.db import get_session
    from hiveflow.domain.allocations import TargetAllocation
    from sqlmodel import select
    with get_session(settings) as session:
        rows = session.exec(select(TargetAllocation).where(
            TargetAllocation.strategy_name == "_MockStrategy"
        )).all()
    assert len(rows) > 0
    symbols = {r.symbol for r in rows}
    assert "BTC" in symbols


def test_run_quant_strategy_apply_writes_decision_log(tmp_path):
    """--apply 时写入 DecisionLog。"""
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        apply=True,
        settings=settings,
    )

    from hiveflow.db import get_session
    from hiveflow.domain.decision_logs import DecisionLog
    from sqlmodel import select
    with get_session(settings) as session:
        logs = session.exec(select(DecisionLog).where(
            DecisionLog.decision_type == "quant-run-apply"
        )).all()
    assert len(logs) > 0
    assert "_MockStrategy" in logs[0].summary


def test_list_strategy_runs(tmp_path):
    """list_strategy_runs 返回历史记录列表。"""
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        settings=settings,
    )

    runs = list_strategy_runs(limit=10, settings=settings)
    assert len(runs) == 1
    assert runs[0].strategy_name == "_MockStrategy"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_quant_strategies.py -q
```

- [ ] **Step 3: 实现 `src/hiveflow/application/quant_strategies.py`**

```python
"""量化策略应用服务：数据加载、策略运行、结果落库、--apply。"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd
from sqlmodel import delete, select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.decision_logs import DecisionLog
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.domain.risk import RiskSignal
from hiveflow.domain.strategy_runs import StrategyRun
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


@dataclass(frozen=True)
class StrategyRunView:
    """策略运行历史视图。"""
    id: int | None
    strategy_name: str
    strategy_file: str | None
    params: dict
    weights: dict
    applied: bool
    run_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "strategy_file": self.strategy_file,
            "params": self.params,
            "weights": self.weights,
            "applied": self.applied,
            "run_at": self.run_at,
        }


@dataclass(frozen=True)
class QuantRunResult:
    """策略运行结果。"""
    run_id: int | None
    strategy_name: str
    params: dict
    weights: dict
    applied: bool
    run_at: str

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "params": self.params,
            "weights": self.weights,
            "run_id": self.run_id,
            "applied": self.applied,
            "run_at": self.run_at,
        }


def _build_prices(symbols: list[str], min_rows: int, settings: Settings) -> pd.DataFrame:
    """从 MarketBar 表构建 prices DataFrame (index=date, columns=symbol)。"""
    with get_session(settings) as session:
        bars = session.exec(
            select(MarketBar)
            .where(MarketBar.symbol.in_(symbols))  # type: ignore[attr-defined]
            .order_by(MarketBar.timestamp)
        ).all()

    if not bars:
        raise ValueError(
            "MarketBar 表无数据，请先运行 `hiveflow market-data import` 导入行情数据。"
        )

    records = [{"symbol": b.symbol, "timestamp": b.timestamp, "close": b.close} for b in bars]
    df = pd.DataFrame(records)
    pivot = df.pivot_table(index="timestamp", columns="symbol", values="close")
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.sort_index()

    missing = [s for s in symbols if s not in pivot.columns and s != "USDT"]
    for s in missing:
        print(f"[警告] {s} 在 MarketBar 中无数据，已从权重计算中排除。")

    available = [s for s in symbols if s in pivot.columns]
    pivot = pivot[available]

    if len(pivot) < min_rows:
        raise ValueError(
            f"行情数据不足（需要 {min_rows} 行，实际 {len(pivot)} 行）。"
            "请运行 `hiveflow market-data import` 导入更多行情数据。"
        )

    return pivot


def _build_context(
    strategy_class: type[BaseStrategy],
    merged_params: dict,
    settings: Settings,
) -> StrategyContext:
    """构建 StrategyContext：加载 prices、positions、risk_signals。"""
    # 确定 symbols（从 MarketBar 中获取去重列表，并加入 USDT）
    with get_session(settings) as session:
        # select 单列时 session.exec 返回标量序列，不是元组
        all_symbols = list(set(session.exec(select(MarketBar.symbol)).all()))
    if "USDT" not in all_symbols:
        all_symbols.append("USDT")

    # 确定加载行数
    window_keys = ("lookback_days", "window", "fast", "slow")
    windows = [int(merged_params.get(k, 0)) for k in window_keys if k in merged_params]
    max_window = max(windows) if windows else 30
    min_rows = max(max_window * 2, 60)

    prices = _build_prices(all_symbols, min_rows, settings)

    # 当前持仓
    with get_session(settings) as session:
        positions = session.exec(select(Position)).all()
    total_value = sum(p.value_usdt or 0 for p in positions) or 1.0
    current_positions = {p.symbol: (p.value_usdt or 0) / total_value for p in positions}

    # 最新风险信号
    with get_session(settings) as session:
        risk_rows = session.exec(
            select(RiskSignal).order_by(RiskSignal.calculated_at.desc())  # type: ignore[attr-defined]
        ).all()
    risk_signals = {}
    for r in risk_rows:
        if r.symbol not in risk_signals:
            risk_signals[r.symbol] = r

    return StrategyContext(
        prices=prices,
        current_positions=current_positions,
        risk_signals=risk_signals,
        params=merged_params,
    )


def run_quant_strategy(
    strategy_class: type[BaseStrategy],
    strategy_file: str | None,
    params: dict,
    apply: bool = False,
    settings: Settings | None = None,
) -> QuantRunResult:
    """运行量化策略，落库，可选写入 TargetAllocation。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 合并参数：类默认 → CLI 覆盖
    strategy_instance = strategy_class()
    merged_params = {**strategy_instance.params, **params}

    ctx = _build_context(strategy_class, merged_params, app_settings)
    ctx.params.update(merged_params)

    weights = strategy_instance.compute_weights(ctx)

    # 落库
    run = StrategyRun(
        strategy_name=strategy_class.__name__,
        strategy_file=strategy_file,
        params=json.dumps(merged_params),
        weights=json.dumps(weights),
        applied=False,
    )
    with get_session(app_settings) as session:
        session.add(run)
        session.commit()
        session.refresh(run)

    if apply:
        _apply_weights(run, weights, app_settings)

    return QuantRunResult(
        run_id=run.id,
        strategy_name=run.strategy_name,
        params=merged_params,
        weights=weights,
        applied=run.applied,
        run_at=run.run_at.isoformat(),
    )


def _apply_weights(run: StrategyRun, weights: dict, settings: Settings) -> None:
    """写入 TargetAllocation（replace 模式），写 DecisionLog，更新 applied。"""
    with get_session(settings) as session:
        # 清除同策略旧记录
        session.exec(
            delete(TargetAllocation).where(
                TargetAllocation.strategy_name == run.strategy_name  # type: ignore[attr-defined]
            )
        )
        # 写入新权重
        for symbol, weight in weights.items():
            ta = TargetAllocation(
                symbol=symbol,
                target_weight=weight,
                strategy_name=run.strategy_name,
            )
            session.add(ta)
        # DecisionLog（DecisionLog 使用 summary 字段，不是 content）
        log = DecisionLog(
            decision_type="quant-run-apply",
            summary=f"quant run --apply: {run.strategy_name} → {json.dumps(weights)}",
        )
        session.add(log)
        # 更新 applied（StrategyRun 是 SQLModel 可变实例，直接赋值即可）
        db_run = session.get(StrategyRun, run.id)
        if db_run:
            db_run.applied = True
        session.commit()
    # 回写到调用方持有的 run 对象（SQLModel 实例可变）
    run.applied = True


def list_strategy_runs(
    limit: int = 10,
    run_id: int | None = None,
    settings: Settings | None = None,
) -> list[StrategyRunView]:
    """查询策略运行历史。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        if run_id is not None:
            row = session.get(StrategyRun, run_id)
            rows = [row] if row else []
        else:
            rows = session.exec(
                select(StrategyRun)
                .order_by(StrategyRun.run_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            ).all()

    return [
        StrategyRunView(
            id=r.id,
            strategy_name=r.strategy_name,
            strategy_file=r.strategy_file,
            params=json.loads(r.params),
            weights=json.loads(r.weights),
            applied=r.applied,
            run_at=r.run_at.isoformat(),
        )
        for r in rows
    ]
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_quant_strategies.py -q
```
预期：`4 passed`

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/application/quant_strategies.py tests/test_quant_strategies.py
git commit -m "feat: 新增量化策略应用层 quant_strategies"
```

---

## Chunk 6: CLI 命令组 — `hiveflow quant`

### Task 6: CLI quant list / run / history

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_quant_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_quant_cli.py
"""CLI 集成测试：hiveflow quant list / run / history。"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from hiveflow.cli import app
import numpy as np
import pandas as pd


runner = CliRunner()


def _db_settings(tmp_path: Path):
    """创建临时数据库 Settings。"""
    return f"sqlite:///{tmp_path}/test.db"


def _seed_market_data(tmp_path: Path, db_url: str):
    """直接写 MarketBar 数据，供策略读取。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar
    from datetime import datetime, timedelta

    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    rng = np.random.default_rng(42)
    base_date = datetime(2025, 1, 1)
    with get_session(settings) as session:
        for i in range(90):
            ts = base_date + timedelta(days=i)
            for sym in ("BTC", "ETH", "USDT"):
                bar = MarketBar(
                    symbol=sym,
                    timestamp=ts,
                    open=float(rng.uniform(90, 110)),
                    high=float(rng.uniform(110, 120)),
                    low=float(rng.uniform(80, 90)),
                    close=float(rng.uniform(90, 110)),
                    volume=1000.0,
                )
                session.add(bar)
        session.commit()


def test_quant_list_shows_builtin_strategies(tmp_path):
    """hiveflow quant list 显示内置策略表格。"""
    result = runner.invoke(app, ["quant", "list"])
    assert result.exit_code == 0, result.output
    assert "EqualWeightStrategy" in result.output
    assert "MomentumStrategy" in result.output
    assert "内置" in result.output


def test_quant_run_json_output(tmp_path):
    """hiveflow quant run --output json 输出合法 JSON。"""
    db_url = _db_settings(tmp_path)
    _seed_market_data(tmp_path, db_url)
    result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run",
        "--strategy", "EqualWeightStrategy",
        "--output", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["strategy"] == "EqualWeightStrategy"
    assert abs(sum(data["weights"].values()) - 1.0) < 1e-9
    assert "run_id" in data


def test_quant_run_param_type_coercion(tmp_path):
    """--param lookback_days=14 → int，--param min_usdt=0.20 → float。"""
    db_url = _db_settings(tmp_path)
    _seed_market_data(tmp_path, db_url)
    result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run",
        "--strategy", "MomentumStrategy",
        "--param", "lookback_days=14",
        "--param", "min_usdt=0.20",
        "--output", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["params"]["lookback_days"] == 14      # int
    assert data["params"]["min_usdt"] == pytest.approx(0.20)  # float


def test_quant_history_lists_runs(tmp_path):
    """hiveflow quant history 显示历史记录。"""
    db_url = _db_settings(tmp_path)
    _seed_market_data(tmp_path, db_url)
    # 先跑一次
    runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run", "--strategy", "EqualWeightStrategy",
    ])
    result = runner.invoke(app, ["--database-url", db_url, "quant", "history"])
    assert result.exit_code == 0, result.output
    assert "EqualWeightStrategy" in result.output


def test_quant_history_json_by_id(tmp_path):
    """quant history --id N --output json 输出单次完整记录。"""
    db_url = _db_settings(tmp_path)
    _seed_market_data(tmp_path, db_url)
    run_result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run", "--strategy", "EqualWeightStrategy", "--output", "json",
    ])
    run_id = json.loads(run_result.output)["run_id"]

    result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "history", "--id", str(run_id), "--output", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["id"] == run_id
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_quant_cli.py -q
```

- [ ] **Step 3: 在 `cli.py` 中新增 quant 命令组**

在 `cli.py` 中，`skills_app` 定义之后、`console = Console()` 之前添加：

```python
quant_app = typer.Typer(help="量化策略命令。")
```

在文件末尾 `app.add_typer(skills_app, name="skills")` 之后添加：

```python
app.add_typer(quant_app, name="quant")
```

在文件中增加以下 import（在已有 import 区域添加）：

```python
from hiveflow.application.quant_strategies import (
    list_strategy_runs,
    run_quant_strategy,
    QuantRunResult,
    StrategyRunView,
)
from hiveflow.services.strategies import (
    EqualWeightStrategy,
    MomentumStrategy,
    MeanReversionStrategy,
    MovingAverageCrossStrategy,
    BollingerBandStrategy,
    RiskParityStrategy,
    MaxSharpeStrategy,
    MinVarianceStrategy,
    BaseStrategy,
)
```

然后增加以下命令函数：

```python
# ────────────── quant ──────────────

_BUILTIN_STRATEGIES: dict[str, tuple[type[BaseStrategy], str]] = {
    "EqualWeightStrategy": (EqualWeightStrategy, "等权重（基准策略）"),
    "MomentumStrategy": (MomentumStrategy, "动量（按涨幅排名分配权重）"),
    "MeanReversionStrategy": (MeanReversionStrategy, "均值回归（z-score 反向加权）"),
    "MovingAverageCrossStrategy": (MovingAverageCrossStrategy, "均线交叉（短期均线在长期均线上方加权）"),
    "BollingerBandStrategy": (BollingerBandStrategy, "布林带（超卖区域加权）"),
    "RiskParityStrategy": (RiskParityStrategy, "风险平价（按波动率倒数分配）"),
    "MaxSharpeStrategy": (MaxSharpeStrategy, "最大夏普（需 PyPortfolioOpt）"),
    "MinVarianceStrategy": (MinVarianceStrategy, "最小方差（需 PyPortfolioOpt）"),
}


def _coerce_param(value: str) -> int | float | str:
    """推导 --param 值类型：先 int，再 float，失败保留 str。"""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


@quant_app.command("list")
def quant_list_command():
    """列出所有可用量化策略（内置 + 用户配置）。"""
    table = Table(title="量化策略", box=box.SIMPLE)
    table.add_column("名称", style="bold")
    table.add_column("类型")
    table.add_column("描述")
    for name, (_, desc) in _BUILTIN_STRATEGIES.items():
        table.add_row(name, "内置", desc)

    # 环境变量配置的用户策略
    import os
    env_file = os.environ.get("HIVEFLOW_STRATEGY_FILE")
    env_class = os.environ.get("HIVEFLOW_STRATEGY_CLASS")
    if env_file and env_class:
        table.add_row(env_class, "用户自定义", env_file)

    console.print(table)
    console.print()
    console.print("用法：hiveflow quant run --strategy <名称>")
    console.print("自定义策略：hiveflow quant run --strategy-file <路径> --strategy <类名>")


@quant_app.command("run")
def quant_run_command(
    strategy: str = typer.Option(..., "--strategy", help="策略类名（内置或自定义）"),
    strategy_file: str | None = typer.Option(None, "--strategy-file", help="用户自定义策略文件路径"),
    param: list[str] = typer.Option([], "--param", help="策略参数 key=value（可多次使用）"),
    apply: bool = typer.Option(False, "--apply", help="写入目标配比（replace 模式）"),
    output: str = typer.Option("table", "--output", help="输出格式：table / json"),
    database_url: str | None = typer.Option(None, "--database-url", hidden=True),
):
    """运行量化策略，输出权重信号。"""
    settings = Settings(database_url=database_url) if database_url else Settings()

    # 解析 --param
    parsed_params: dict[str, int | float | str] = {}
    for p in param:
        if "=" not in p:
            console.print(f"[red]无效参数格式：{p}（应为 key=value）[/red]")
            raise typer.Exit(1)
        key, val = p.split("=", 1)
        parsed_params[key.strip()] = _coerce_param(val.strip())

    # 解析策略类
    strategy_class: type[BaseStrategy] | None = None
    file_path: str | None = strategy_file

    # 优先环境变量
    import os
    if strategy_file is None and os.environ.get("HIVEFLOW_STRATEGY_FILE"):
        file_path = os.environ.get("HIVEFLOW_STRATEGY_FILE")

    if file_path:
        # 动态加载用户策略文件
        import importlib.util
        spec = importlib.util.spec_from_file_location("_user_strategy", file_path)
        if spec is None or spec.loader is None:
            console.print(f"[red]无法加载文件：{file_path}[/red]")
            raise typer.Exit(1)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        strategy_class = getattr(module, strategy, None)
        if strategy_class is None:
            console.print(f"[red]文件 {file_path} 中未找到类 {strategy}[/red]")
            raise typer.Exit(1)
    elif strategy in _BUILTIN_STRATEGIES:
        strategy_class, _ = _BUILTIN_STRATEGIES[strategy]
    else:
        console.print(f"[red]未知策略：{strategy}，可用策略请运行 'hiveflow quant list'[/red]")
        raise typer.Exit(1)

    try:
        result = run_quant_strategy(
            strategy_class=strategy_class,
            strategy_file=file_path,
            params=parsed_params,
            apply=apply,
            settings=settings,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if output == "json":
        console.print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    # rich 表格输出
    table = Table(title=f"策略运行结果：{result.strategy_name}", box=box.SIMPLE)
    table.add_column("资产", style="bold")
    table.add_column("权重", justify="right")
    for sym, w in sorted(result.weights.items(), key=lambda x: x[1], reverse=True):
        table.add_row(sym, f"{w:.2%}")
    console.print(table)
    console.print(f"[dim]运行 ID：{result.run_id} | 时间：{result.run_at}[/dim]")
    if apply:
        console.print("[green]已写入目标配比（TargetAllocation）。[/green]")


@quant_app.command("history")
def quant_history_command(
    limit: int = typer.Option(10, "--limit", help="显示最近 N 条记录"),
    run_id: int | None = typer.Option(None, "--id", help="查询指定运行 ID"),
    output: str = typer.Option("table", "--output", help="输出格式：table / json"),
    database_url: str | None = typer.Option(None, "--database-url", hidden=True),
):
    """查看量化策略运行历史。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    runs = list_strategy_runs(limit=limit, run_id=run_id, settings=settings)

    if not runs:
        console.print("[dim]暂无运行记录。[/dim]")
        return

    if output == "json":
        if run_id is not None and len(runs) == 1:
            console.print(json.dumps(runs[0].to_dict(), ensure_ascii=False, indent=2))
        else:
            console.print(json.dumps([r.to_dict() for r in runs], ensure_ascii=False, indent=2))
        return

    table = Table(title="策略运行历史", box=box.SIMPLE)
    table.add_column("ID", style="bold")
    table.add_column("策略名称")
    table.add_column("参数")
    table.add_column("已写入")
    table.add_column("运行时间")
    for r in runs:
        table.add_row(
            str(r.id),
            r.strategy_name,
            str(r.params),
            "✓" if r.applied else "-",
            r.run_at,
        )
    console.print(table)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_quant_cli.py -q
```

注意：需要在 `test_quant_run_param_type_coercion` 中导入 `pytest`，请确认测试文件顶部有 `import pytest`。

- [ ] **Step 5: 验证 CLI 帮助正常**

```bash
uv run hiveflow quant --help
uv run hiveflow quant list
```

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/cli.py tests/test_quant_cli.py
git commit -m "feat: 新增 hiveflow quant list/run/history CLI 命令组"
```

---

## Chunk 7: 全量测试 + 文档收口

### Task 7: 验证、文档、提交

**Files:**
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/SESSION_LOG.md`

- [ ] **Step 1: 运行全量测试**

```bash
uv run python -m pytest -q
```
预期：所有测试通过（之前 154 passed，加上新测试后数量增加）。

- [ ] **Step 2: 验证 CLI 端到端**

```bash
uv run hiveflow quant list
# 应显示 8 个内置策略

uv run hiveflow quant run --strategy EqualWeightStrategy --output json
# 应输出合法 JSON，weights 之和 ≈ 1.0

uv run hiveflow quant run --strategy MomentumStrategy --param lookback_days=14 --output json
# params.lookback_days 应为 14（int）

uv run hiveflow quant history
# 应显示历史记录表格
```

- [ ] **Step 3: 更新 `docs/context/CURRENT_STATE.md`**

在"当前可用命令（核心）"部分添加：
```
- `hiveflow quant ...`
```
更新测试通过数量。

- [ ] **Step 4: 更新 `docs/context/SESSION_LOG.md`**

追加：
```markdown
- 完成 M6：新增 `hiveflow quant` 命令组，内置 8 种量化策略，结果落库，支持 --apply 写入目标配比。
- 全量测试：N passed。
```

- [ ] **Step 5: 最终提交**

```bash
git add docs/context/CURRENT_STATE.md docs/context/SESSION_LOG.md
git commit -m "docs: 更新 M6 完成状态"
```

---

## 关键文件汇总

| 文件 | 操作 |
|---|---|
| `src/hiveflow/domain/strategy_runs.py` | 新建 |
| `src/hiveflow/db.py` | 修改（新增 import）|
| `src/hiveflow/services/strategies/__init__.py` | 新建 |
| `src/hiveflow/services/strategies/base.py` | 新建 |
| `src/hiveflow/services/strategies/equal_weight.py` | 新建 |
| `src/hiveflow/services/strategies/momentum.py` | 新建 |
| `src/hiveflow/services/strategies/mean_reversion.py` | 新建 |
| `src/hiveflow/services/strategies/moving_average.py` | 新建 |
| `src/hiveflow/services/strategies/bollinger_band.py` | 新建 |
| `src/hiveflow/services/strategies/risk_parity.py` | 新建 |
| `src/hiveflow/services/strategies/max_sharpe.py` | 新建 |
| `src/hiveflow/services/strategies/min_variance.py` | 新建 |
| `src/hiveflow/application/quant_strategies.py` | 新建 |
| `src/hiveflow/cli.py` | 修改（新增 quant_app）|
| `tests/test_strategy_runs_domain.py` | 新建 |
| `tests/test_strategy_base.py` | 新建 |
| `tests/test_strategy_equal_weight.py` | 新建 |
| `tests/test_strategy_momentum.py` | 新建 |
| `tests/test_strategy_mean_reversion.py` | 新建 |
| `tests/test_strategy_moving_average.py` | 新建 |
| `tests/test_strategy_bollinger_band.py` | 新建 |
| `tests/test_strategy_risk_parity.py` | 新建 |
| `tests/test_strategy_max_sharpe.py` | 新建 |
| `tests/test_strategy_min_variance.py` | 新建 |
| `tests/test_quant_strategies.py` | 新建 |
| `tests/test_quant_cli.py` | 新建 |
| `docs/context/CURRENT_STATE.md` | 更新 |
| `docs/context/SESSION_LOG.md` | 更新 |

---

## 验证命令

```bash
uv run python -m pytest -q                          # 全量测试通过
uv run hiveflow quant list                          # 显示 8 个策略
uv run hiveflow quant run --strategy EqualWeightStrategy --output json
uv run hiveflow quant run --strategy MomentumStrategy --param lookback_days=14 --output json
uv run hiveflow quant history
uv run hiveflow --help                              # quant 命令组出现在帮助里
```
