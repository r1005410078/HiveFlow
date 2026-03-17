# M6 量化策略管理系统

**日期**：2026-03-17
**状态**：已通过用户确认

---

## 背景

M5 完成了完整的"同步 → 检查 → 调仓 → 执行"闭环。M6 的目标是引入**量化策略管理**能力——让用户可以定义和运行确定性的数学策略，由策略输出权重信号，再由 Agent/Skill 决定是否采用。

---

## 系统宗旨（设计约束）

> HiveFlow 是一个**为 AI Agent 提供高质量上下文的投资工具系统**。

- 量化策略 = **数学工具**（确定性，给定输入总是输出同样结果）
- 智能判断（是否采用某策略、如何组合信号）= **Agent/Skill 的职责**
- HiveFlow 只负责运行策略、记录结果、输出 JSON 上下文

---

## 命名说明

项目中已存在 `hiveflow strategies`（复数）命令组，用于管理**策略元数据记录**（名称、类型、维度，来自 CSV 导入）。

本 M6 新增 `hiveflow quant`（量化）命令组，用于**运行数学策略算法**，两者职责不同：

| 命令组 | 职责 |
|---|---|
| `hiveflow strategies` | 策略元数据管理（名称、类型、席位）|
| `hiveflow quant` | 量化策略算法运行（数学计算、输出权重信号）|

---

## 架构

```
用户 / Agent
      │
      ▼
hiveflow quant run --strategy Momentum --output json
      │
      ▼
src/hiveflow/services/strategies/
  __init__.py        ← 导出内置策略类
  base.py            ← BaseStrategy + StrategyContext
  momentum.py        ← MomentumStrategy（内置）
  mean_reversion.py  ← MeanReversionStrategy（内置）
  risk_parity.py     ← RiskParityStrategy（内置，需 PyPortfolioOpt）
      │
      ▼
src/hiveflow/application/quant_strategies.py   ← 用例逻辑
  ├── 从 MarketBar 表加载行情数据 → prices DataFrame
  ├── 从 Position 表加载当前自由持仓
  ├── 从 RiskSignal 表加载最新风险信号
  ├── 写入 StrategyRun 表（落库）
  └── 可选：写入 TargetAllocation 表（--apply）
      │
      ▼
src/hiveflow/domain/strategy_runs.py   ← StrategyRun 模型
```

---

## 接口设计

### BaseStrategy

```python
# src/hiveflow/services/strategies/base.py

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

### 用户自定义策略示例

```python
# ~/my_momentum.py
from hiveflow.services.strategies import MomentumStrategy

class MyMomentum(MomentumStrategy):
    params = {"lookback_days": 14, "top_k": 2, "min_usdt": 0.20}
```

---

## 数据加载（StrategyContext 构建）

`application/quant_strategies.py` 负责在执行策略前构建 `StrategyContext`：

1. **prices**：从 `MarketBar` 表查询，按 `(symbol, timestamp)` 构建 pivot DataFrame（index=date, columns=symbol）。加载天数取策略参数中最大窗口值（如 `lookback_days` 或 `window`）的 2 倍，最少 60 天。若某 symbol 在 MarketBar 中无数据，打印警告并从权重计算中排除。若数据不足（行数 < 窗口），抛出用户友好错误提示运行 `hiveflow market-data import`。

2. **current_positions**：从 `Position` 表读取，转换为 `{symbol: weight}` 字典（与 `positions list` 相同逻辑）。若无持仓，传入空字典。

3. **risk_signals**：从 `RiskSignal` 表读取最新一条（按 `synced_at` 降序），转换为 `{symbol: RiskSignal}` 字典。若无风险信号，传入空字典。

---

## `--param` 参数类型推导

CLI 通过 `--param key=value` 传入参数，值按以下顺序推导类型：先尝试 `int`，再尝试 `float`，失败则保留为 `str`。示例：`--param lookback_days=14` → `{"lookback_days": 14}`（int）。

---

## 内置策略

### MomentumStrategy

**逻辑**：按过去 `lookback_days` 天涨幅排名，前 `top_k` 名均分，USDT 保留最低 `min_usdt` 比例。

**参数**：
| 参数 | 默认值 | 说明 |
|---|---|---|
| `lookback_days` | 30 | 回望天数 |
| `top_k` | 3 | 持有排名前 K 的资产 |
| `min_usdt` | 0.10 | USDT 最低权重 |

### MeanReversionStrategy

**逻辑**：计算每个资产价格的 z-score（相对 `window` 日均值），z-score 越低权重越高（跌多了多配）。

**参数**：
| 参数 | 默认值 | 说明 |
|---|---|---|
| `window` | 20 | 均值/标准差计算窗口 |
| `min_usdt` | 0.10 | USDT 最低权重 |

### RiskParityStrategy

**逻辑**：按各资产波动率的倒数分配权重（等风险贡献）。使用 `PyPortfolioOpt` 实现。

**参数**：
| 参数 | 默认值 | 说明 |
|---|---|---|
| `window` | 30 | 波动率计算窗口 |
| `min_usdt` | 0.10 | USDT 最低权重 |

**依赖**：`PyPortfolioOpt`（可选依赖。不安装时降级为等权重分配并打印提示，不报错退出）。

---

## 数据模型

```python
# src/hiveflow/domain/strategy_runs.py

class StrategyRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    strategy_name: str          # "MomentumStrategy" 或自定义类名
    strategy_file: str | None   # 用户文件路径，内置策略为 None
    params: str                 # JSON 字符串，实际使用的参数
    weights: str                # JSON 字符串，输出权重 {"BTC": 0.4, ...}
    applied: bool = False       # 是否已写入 TargetAllocation
    run_at: datetime = Field(default_factory=utc_now)
```

`db.py` 的 `_run_lightweight_migrations` 需新增：若 `strategyrun` 表不存在则由 SQLModel 建表（与其他表处理方式一致）。

---

## `--apply` 行为

`hiveflow quant run --apply` 在落库后额外执行：

1. 以策略类名（如 `"MomentumStrategy"`）为 `strategy_name`，`replace` 模式写入 `TargetAllocation` 表（清除同策略旧记录，写入新权重）
2. 将 `StrategyRun.applied` 置为 `True`
3. 写入一条 `DecisionLog`，内容：`"quant run --apply: MomentumStrategy → {weights}"`

---

## CLI 命令

### `hiveflow quant list`

列出所有可用量化策略（内置 + 通过环境变量配置的用户策略）。

```
量化策略

  名称                   类型    描述
  MomentumStrategy      内置    动量策略（按涨幅排名分配权重）
  MeanReversionStrategy 内置    均值回归策略（z-score 反向加权）
  RiskParityStrategy    内置    风险平价策略（按波动率倒数分配）

用法：hiveflow quant run --strategy <名称>
自定义策略：hiveflow quant run --strategy-file <路径> --strategy <类名>
```

### `hiveflow quant run`

```bash
# 内置策略
hiveflow quant run --strategy MomentumStrategy
hiveflow quant run --strategy MomentumStrategy --output json

# 自定义参数（int/float 自动推导类型）
hiveflow quant run --strategy MomentumStrategy --param lookback_days=14 --param top_k=2

# 用户自定义策略文件
hiveflow quant run --strategy-file ~/my_momentum.py --strategy MyMomentum

# 运行后直接写入目标配比（replace 模式，写入 DecisionLog）
hiveflow quant run --strategy MomentumStrategy --apply
```

**JSON 输出示例（`--output json`）**：

```json
{
  "strategy": "MomentumStrategy",
  "params": {"lookback_days": 30, "top_k": 3, "min_usdt": 0.1},
  "weights": {
    "BTC": 0.45,
    "ETH": 0.30,
    "SOL": 0.15,
    "USDT": 0.10
  },
  "run_id": 7,
  "run_at": "2026-03-17T10:30:00Z"
}
```

### `hiveflow quant history`

```bash
hiveflow quant history                      # 最近 10 次运行
hiveflow quant history --limit 20
hiveflow quant history --id 7 --output json # 获取某次运行的完整输出
```

---

## Agent 使用链路

```
hiveflow quant run --strategy MomentumStrategy --output json
         ↓
Agent 分析输出（与当前持仓对比、结合风险信号判断）
         ↓
Agent 决定是否采用（可能调整权重、可能拒绝）
         ↓
（若采用）hiveflow quant run --strategy MomentumStrategy --apply
hiveflow rebalance preview --output json
hiveflow trade execute
```

或 Agent 自行调整权重后直接导入：

```
hiveflow targets import --file /tmp/adjusted_weights.csv --mode replace
hiveflow rebalance preview --output json
hiveflow trade execute
```

---

## 配置

用户可在 `.env` 中固化自定义策略路径：

```
HIVEFLOW_STRATEGY_FILE=~/my_strategies/momentum.py
HIVEFLOW_STRATEGY_CLASS=MyMomentum
```

---

## 测试策略

- `test_momentum_strategy.py`：mock prices DataFrame，验证权重之和为 1.0、top_k 约束、min_usdt 约束
- `test_mean_reversion_strategy.py`：验证 z-score 计算、权重归一化
- `test_risk_parity_strategy.py`：验证无 PyPortfolioOpt 时降级为等权重
- `test_quant_strategies.py`：mock 策略，验证落库、--apply 写入 TargetAllocation、DecisionLog 写入、applied 字段更新
- `test_quant_cli.py`：CLI 集成测试，验证 JSON 输出格式、--param 类型推导

---

## 不在 M6 范围

- 网格机器人创建/管理 → M7
- 合约交易 → M7
- 多交易所支持 → M7
- 定时自动调仓 → M7
- 多策略组合（加权混合多个策略输出）→ M7
