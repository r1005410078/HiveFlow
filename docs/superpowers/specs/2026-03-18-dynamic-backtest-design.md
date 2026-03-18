# 量化策略动态回测设计

**日期**：2026-03-18
**状态**：已通过用户确认

---

## 背景

M6 实现了 8 种量化策略（`hiveflow quant run`），每次运行只计算"当前时刻"的权重，不验证策略在历史上的时间序列表现。本功能在现有回测基础设施上新增**动态再平衡回测**——在回测窗口内每隔 N 天重新调用策略，测试策略真实的历史表现。

---

## 系统宗旨

> HiveFlow 是一个**为 AI Agent 提供高质量上下文的投资工具系统**。

- 动态回测 = **确定性工具**（给定输入，总是输出相同结果）
- 是否采纳某策略的结论 = **Agent/用户判断**
- HiveFlow 只负责运行、记录、输出上下文

---

## 命令接口

```bash
# 最简用法（默认每7天再平衡）
hiveflow backtest quant-run --strategy MomentumStrategy

# 指定再平衡周期
hiveflow backtest quant-run --strategy MomentumStrategy --rebalance-days 14

# 限制资产池
hiveflow backtest quant-run --strategy MomentumStrategy --symbols BTC,ETH,SOL,USDT

# 加入交易成本
hiveflow backtest quant-run --strategy MomentumStrategy --fee-bps 10 --slippage-bps 5

# JSON 输出（供 Agent 消费）
hiveflow backtest quant-run --strategy MomentumStrategy --output json

# 结果查询（与静态回测统一）
hiveflow backtest list
hiveflow targets set-from-backtest <id>  # 兼容现有命令
```

---

## 架构

```
CLI: hiveflow backtest quant-run
      │
      ▼
application/backtest.py
  run_quant_backtest(strategy_name, rebalance_days, symbols, fee_bps, ...)
      │
      ├─ 从 MarketBar 表加载所有（或指定）symbol 的 PriceBar
      ├─ 从 BUILTIN_STRATEGIES 实例化策略对象
      └─ 调用 run_dynamic_backtest(prices, strategy, rebalance_days, ...)
           │
           ▼
      services/backtest_engine.py
        run_dynamic_backtest()
           │
           ├─ 将所有时间戳排序，按 rebalance_days 切分为若干期
           ├─ 对每期：
           │    ├─ 用截止当前时点的 prices 构建 StrategyContext（无未来偏差）
           │    ├─ 调用 strategy.compute_weights(ctx)
           │    │    └─ 若数据不足（< lookback），等权重兜底
           │    └─ 用本期权重模拟该期内每日收益，扣除交易成本
           └─ 汇总 equity curve → BacktestMetrics + final_weights
      │
      ▼
application/backtest.py
  写入 BacktestResult（backtest_type="dynamic"，weights_snapshot=最终期权重）
  返回 BacktestResultView
```

---

## 核心算法（`run_dynamic_backtest`）

```python
def run_dynamic_backtest(
    prices: dict[str, list[PriceBar]],
    strategy: BaseStrategy,
    rebalance_days: int = 7,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> tuple[BacktestMetrics, dict[str, float]]:
    ...
```

**执行步骤：**

1. 提取所有 symbol 的公共时间戳，排序后按 `rebalance_days` 分块
2. 对每个时间块：
   - 截取该块起始时点前的所有历史 prices 构建 `StrategyContext`
   - 调用 `strategy.compute_weights(ctx)`；若抛出异常或数据不足，降级为等权重
   - 用本块的 prices 逐日模拟持有收益（固定权重，不漂移），扣除单次交易成本
3. 积累 equity curve，计算：
   - `total_return = equity_final - 1.0`
   - `max_drawdown = min(value/peak - 1.0)`
   - `sharpe = mean_daily_ret / std_daily_ret * sqrt(n)`
4. 返回 `(BacktestMetrics, final_weights)`，其中 `final_weights` 为最后一期权重

**无未来偏差保证**：构建 `StrategyContext` 时，`prices` 只包含当前再平衡点**之前**的数据。

---

## 数据模型变更

### `BacktestResult`（新增字段）

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
    backtest_type: str = Field(default="static")   # ← 新增："static" | "dynamic"
    created_at: datetime = Field(default_factory=utc_now)
```

### 轻量迁移（`db.py`）

在 `_run_lightweight_migrations()` 中新增：

```python
# BacktestResult 表补 backtest_type 列
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE backcastresult ADD COLUMN backtest_type TEXT DEFAULT 'static'"))
        conn.commit()
    except Exception:
        pass
```

（与现有其他字段迁移逻辑保持一致）

---

## CLI 命令

**文件**：`src/hiveflow/cli.py`，在现有 `backtest_app` 下新增：

```python
@backtest_app.command("quant-run")
def backtest_quant_run(
    strategy: str = typer.Option(..., "--strategy", "-s", help="量化策略类名"),
    rebalance_days: int = typer.Option(7, "--rebalance-days", help="再平衡周期（天）"),
    symbols: str | None = typer.Option(None, "--symbols", help="资产池，逗号分隔"),
    fee_bps: float = typer.Option(0.0, "--fee-bps"),
    slippage_bps: float = typer.Option(0.0, "--slippage-bps"),
    output: str = typer.Option("table", "--output"),
):
    """运行量化策略动态回测（每隔 N 天重新计算权重）。"""
```

**`backtest list` 输出新增 `类型` 列：**

```
ID  策略                  类型     周期   总收益   最大回撤  夏普   时间
1   保守版               static   120   +18.2%  -12.1%   1.2   2026-03-17
2   MomentumStrategy    dynamic  117   +24.5%  -18.3%   1.5   2026-03-18
```

---

## `set_targets_from_backtest` 兼容性

动态回测的 `weights_snapshot` 存储**最后一期的再平衡权重**（格式与静态回测相同），现有 `hiveflow targets set-from-backtest <id>` 无需修改即可使用。

---

## 测试策略

**`tests/test_dynamic_backtest.py`**（新建）：

- `test_run_dynamic_backtest_basic`：3 个 symbol，20 天数据，每7天再平衡，验证：
  - 返回 `BacktestMetrics`；`periods` > 0
  - `total_return`、`max_drawdown`（≤ 0）、`sharpe` 类型正确
  - `final_weights` 权重之和为 1.0

- `test_warmup_fallback_equal_weight`：构造 5 天数据（不足 MomentumStrategy 的 30 天 lookback），验证：
  - 不抛出异常
  - 使用等权重继续回测

- `test_no_lookahead_bias`：验证每期 `StrategyContext.prices` 的最后时间戳 ≤ 当前再平衡时点

- `test_run_quant_backtest_persists`（集成）：调用 `run_quant_backtest()`，验证：
  - `BacktestResult` 入库，`backtest_type == "dynamic"`
  - `weights_snapshot` 非空，可 JSON 解析，权重之和为 1.0

- `test_backtest_list_shows_type`（集成）：`list_backtest_results()` 返回结果含 `backtest_type` 字段

- `test_cli_quant_run`（CLI）：通过 `CliRunner` 调用 `backtest quant-run`，验证输出含策略名和指标

---

## 不在本次范围

- 多策略同时比较（同一命令跑多个策略）→ 可用 `backtest list` 事后对比
- 回测期间的 equity curve 可视化 → 后续功能
- 合约/杠杆回测 → M7
- 自定义策略文件（`--strategy-file`）→ 后续扩展
