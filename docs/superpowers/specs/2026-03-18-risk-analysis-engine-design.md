# Risk Analysis Engine Design

## Goal

为 HiveFlow 新增风险分析引擎，覆盖三类场景：
1. 辅助调仓决策（当前持仓风险敞口）
2. 策略筛选（回测/策略风险指标对比）
3. 独立资产分析（波动率、相关性、MDD）

**核心指标**：波动率（年化标准差）、相关性矩阵、历史最大回撤（MDD）。VaR/CVaR 和 Beta 进 backlog。

## Architecture

**方案**：新增 `risk_engine.py` 服务 + `risk_analysis.py` 应用层，模式与 `backtest_engine.py` + `application/backtest.py` 完全对称。

**数据来源**：
- 资产级指标（波动率、相关性、MDD）← MarketBar 原始价格序列
- 组合级指标（组合波动率、胜率、Calmar ratio）← BacktestResult.equity_curve

## Tech Stack

- Python 3.12+, typer, rich（已有依赖）
- SQLite + SQLModel（读现有 MarketBar / BacktestResult 表）
- 无新增第三方依赖（不用 numpy/pandas，手工计算）

---

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/hiveflow/services/risk_engine.py` | 新建 | 纯计算函数：波动率、相关性、MDD、组合风险 |
| `src/hiveflow/application/risk_analysis.py` | 新建 | 从 DB 读数据，调用引擎，返回视图对象 |
| `src/hiveflow/cli.py` | 修改 | 新增 `risk_analysis_app` 命令组；增强 `backtest show` |
| `tests/test_risk_engine.py` | 新建 | 服务层纯计算测试 |
| `tests/test_risk_analysis_cli.py` | 新建 | CLI 命令集成测试 |

---

## Section 1: Service Layer

### `src/hiveflow/services/risk_engine.py`

复用 `backtest_engine.py` 中已有的 `PriceBar`。

#### 数据结构

```python
from __future__ import annotations
from dataclasses import dataclass
from hiveflow.services.backtest_engine import PriceBar


@dataclass(frozen=True)
class AssetVolatility:
    symbol: str
    annual_vol: float   # 年化标准差（× sqrt(365)）
    daily_vol: float    # 日标准差
    periods: int        # 数据点数（价格条数）


@dataclass(frozen=True)
class CorrelationMatrix:
    symbols: list[str]
    matrix: list[list[float]]   # n×n；matrix[i][j] = symbols[i] 与 symbols[j] 的 Pearson 相关系数


@dataclass(frozen=True)
class AssetDrawdown:
    symbol: str
    max_drawdown: float   # 历史最大回撤（非正数：回撤时为负数如 -0.85，无回撤时为 0.0）
    periods: int          # 数据点数
```

#### 计算函数

```python
def compute_volatility(prices: dict[str, list[PriceBar]]) -> list[AssetVolatility]:
    """计算各资产日收益率的标准差，年化（× sqrt(365)）。

    每个资产至少需要 2 个价格点；不足时跳过（不报错）。
    结果按 annual_vol 降序排列。
    """

def compute_correlation(prices: dict[str, list[PriceBar]]) -> CorrelationMatrix:
    """计算资产两两之间的 Pearson 相关系数矩阵。

    只使用各资产共同覆盖的时间段（对齐到 timestamp）。
    若共同数据点 < 2，对应位置填 float('nan')。
    symbols 按字母序排列，matrix[i][i] == 1.0。
    """

def compute_drawdown(prices: dict[str, list[PriceBar]]) -> list[AssetDrawdown]:
    """计算各资产在给定价格序列中的最大回撤（从峰值到谷值）。

    结果按 max_drawdown 升序排列（最大亏损在前）。
    """

def compute_portfolio_risk(curve: list[float]) -> dict:
    """从 equity curve 派生组合级风险指标。

    返回字段：
    - annual_vol: float       # 组合日收益率年化标准差
    - win_rate: float         # 正收益期比例（期数 = len(curve) - 1）
    - calmar_ratio: float     # total_return / |max_drawdown|；MDD==0 时为 float('inf')

    要求 len(curve) >= 2，否则抛 ValueError。
    """
```

#### 内部实现约定

- **日收益率**：`r[t] = price[t] / price[t-1] - 1`
- **标准差**：样本标准差（ddof=1）
- **年化因子**：`sqrt(365)`（加密市场 365 天/年）
- **Pearson 相关系数**：手工实现，不依赖 numpy

---

## Section 2: Application Layer

### `src/hiveflow/application/risk_analysis.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from hiveflow.db import create_all_tables, get_session
from hiveflow.services.backtest_engine import load_close_prices_from_db
from hiveflow.services.risk_engine import (
    compute_volatility, compute_correlation, compute_drawdown, compute_portfolio_risk,
    AssetVolatility, CorrelationMatrix, AssetDrawdown,
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

    symbols=None 时先查询 MarketBar 全部 distinct symbol（与 run_quant_backtest 相同模式），
    再调用 load_close_prices_from_db(symbols=resolved_symbols, settings=settings)。
    若解析后 symbols 为空或 MarketBar 无数据，抛 ValueError。
    """

def analyze_portfolio_risk(
    backtest_id: int,
    settings=None,
) -> dict | None:
    """从 BacktestResult.equity_curve 计算组合级风险。

    - backtest_id 不存在：抛 ValueError
    - equity_curve 为 NULL：返回 None（CLI 层负责输出降级提示，exit_code=0）
    - 正常：返回 compute_portfolio_risk() 的结果字典

    注意：NULL curve 返回 None 而非抛错，与 backtest show 处理 equity_curve is None
    的 CLI 层检查模式一致，避免将非错误场景映射为异常。
    """
```

**注意**：`analyze_asset_risk` 中 `symbols=None` 的处理步骤与 `run_quant_backtest`（`application/backtest.py` 第 154-157 行）完全对称：先 `session.exec(select(MarketBar.symbol).distinct())` 得到 `resolved_symbols`，再调用 `load_close_prices_from_db`。

---

## Section 3: CLI Commands

### 新命令组 `risk-analysis`

在 `src/hiveflow/cli.py` 中新增：

```python
risk_analysis_app = typer.Typer(name="risk-analysis", help="资产与组合风险分析。")
app.add_typer(risk_analysis_app, name="risk-analysis")
```

#### `hiveflow risk-analysis assets [--symbols BTC,ETH] [--output pretty/json]`

```
资产风险分析

  资产    年化波动率   日波动率   历史 MDD
  BTC       68.3%      3.6%    -83.4%
  ETH       72.1%      3.8%    -94.2%
  SOL       91.5%      4.8%    -97.1%

  相关性矩阵
       BTC   ETH   SOL
  BTC  1.00  0.87  0.79
  ETH  0.87  1.00  0.82
  SOL  0.79  0.82  1.00

  数据来源：MarketBar（各资产 N 条）
```

- `--symbols` 逗号分隔，不填时使用全部 MarketBar 资产
- `--output json`：`{"assets": [...], "correlation": {"symbols": [...], "matrix": [...]}}`

#### `hiveflow risk-analysis portfolio <backtest_id> [--output pretty/json]`

```
组合风险分析（回测 #3 · MomentumStrategy）

  年化波动率   18.2%
  胜率         61.5%
  Calmar       4.22
```

- 若 equity_curve 为 NULL：输出提示"重新运行回测可获得组合风险分析"，exit_code=0
- ID 不存在：`raise typer.Exit(code=1)`

### `backtest show` 增强

在现有 sparkline 输出之后追加：

```
  风险指标
  年化波动率   18.2%
  胜率         61.5%
  Calmar       4.22
```

equity_curve 为 NULL 时跳过这一节（不额外输出任何内容）。

---

## Error Handling

| 场景 | 行为 |
|---|---|
| MarketBar 无数据 | `ValueError`，CLI 输出错误信息 + `raise typer.Exit(code=1)` |
| backtest_id 不存在 | `ValueError`，CLI 输出错误信息 + `raise typer.Exit(code=1)` |
| equity_curve 为 NULL（portfolio 命令）| `analyze_portfolio_risk` 返回 `None`，CLI 输出降级提示，exit_code=0 |
| equity_curve 为 NULL（backtest show 增强）| 跳过风险指标节，不报错 |
| 某资产数据点 < 2 | 跳过该资产（不计入结果），不报错 |
| 共同数据点 < 2（相关性）| 对应矩阵位置填 `null`（JSON）或 `N/A`（pretty） |

---

## Testing

### `tests/test_risk_engine.py`（服务层纯计算）

| 测试 | 验证内容 |
|---|---|
| `test_compute_volatility_basic` | 已知价格序列，验证 annual_vol 计算正确 |
| `test_compute_volatility_sorts_descending` | 结果按 annual_vol 降序 |
| `test_compute_volatility_insufficient_data` | 少于 2 点的资产被跳过 |
| `test_compute_correlation_identity` | 单资产或完全相同序列，matrix[i][i] == 1.0 |
| `test_compute_correlation_perfect_positive` | 完全正相关序列，系数 == 1.0 |
| `test_compute_correlation_aligns_timestamps` | 两资产时间戳不完全对齐，只用共同时间点 |
| `test_compute_drawdown_basic` | 已知价格序列，验证 MDD 计算正确 |
| `test_compute_drawdown_flat` | 平坦价格序列，MDD == 0.0 |
| `test_compute_portfolio_risk_basic` | 已知 curve，验证 annual_vol / win_rate / calmar_ratio |
| `test_compute_portfolio_risk_too_short` | len(curve) < 2 抛 ValueError |

### `tests/test_risk_analysis_cli.py`（CLI 集成测试）

| 测试 | 验证内容 |
|---|---|
| `test_risk_assets_cli` | 种入 MarketBar，exit_code=0，输出含 annual_vol 数字和相关性矩阵标题 |
| `test_risk_assets_json` | `--output json`，可解析，含 `assets` 和 `correlation` 键 |
| `test_risk_assets_no_data` | MarketBar 空，exit_code=1 |
| `test_risk_portfolio_cli` | 种入含 equity_curve 的回测，exit_code=0，输出含胜率/Calmar |
| `test_risk_portfolio_no_curve` | equity_curve=NULL，exit_code=0，含降级提示 |
| `test_risk_portfolio_missing_id` | 不存在 ID，exit_code=1 |
| `test_backtest_show_includes_risk` | `backtest show` 含 equity_curve 时，输出含"风险指标"节 |
| `test_backtest_show_no_curve_skips_risk` | equity_curve=NULL 时，`backtest show` 不含"风险指标"节 |

---

## Constraints

- 无新增第三方依赖（不用 numpy/pandas/scipy）
- 年化因子固定 365（加密市场）
- `--output json` 与现有命令保持一致（直接输出，无 envelope）
- `risk-analysis portfolio` 的 equity_curve NULL 降级：exit_code=0（与 `backtest show` NULL 处理一致）
