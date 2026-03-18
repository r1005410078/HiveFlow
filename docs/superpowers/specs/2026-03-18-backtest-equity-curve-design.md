# Backtest Equity Curve Visualization Design

## Goal

为 `hiveflow backtest` 命令组新增两个子命令：
- `backtest show <id>`：展示单条回测的权益曲线（终端 Sparkline）+ 指标汇总
- `backtest compare <id1> <id2> ...`：多回测并排对比（多行 Sparkline + 指标对比表）

## Architecture

**方案选择**：运行时存储曲线，show/compare 时直接从 DB 读取渲染。
理由：按需重算方案在动态回测场景下不可行（`rebalance_days` 未存储），独立表过度设计。

**输出格式**：终端 Unicode Sparkline（`▁▂▃▄▅▆▇█`），无外部依赖。

## Tech Stack

- Python 3.12+, typer, rich（已有依赖）
- SQLite + SQLModel（轻量迁移，ALTER TABLE 追加列）
- 无新增第三方依赖

---

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/hiveflow/domain/backtests.py` | 修改 | 新增 `equity_curve: str \| None` 字段 |
| `src/hiveflow/db.py` | 修改 | 迁移：`ALTER TABLE backtestresult ADD COLUMN equity_curve TEXT` |
| `src/hiveflow/services/backtest_engine.py` | 修改 | `BacktestMetrics` 新增 `curve: list[float]`；两个回测函数返回完整 curve |
| `src/hiveflow/application/backtest.py` | 修改 | `BacktestResultView` 新增 `equity_curve`；存曲线；新增 `get_backtest_result()` |
| `src/hiveflow/cli.py` | 修改 | 新增 `_sparkline()` 函数；新增 `backtest show` / `backtest compare` 命令 |
| `tests/test_backtest_show.py` | 新建 | 覆盖数据模型、sparkline 渲染、CLI 命令的全量测试 |

---

## Section 1: Data Model

### `BacktestMetrics`（`backtest_engine.py`）

新增 `curve` 字段，表示从初始净值 1.0 开始的逐期权益值序列：

```python
@dataclass(frozen=True)
class BacktestMetrics:
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    curve: list[float]   # 新增；len(curve) == periods + 1，curve[0] == 1.0
```

### `BacktestResult`（`domain/backtests.py`）

新增列：
```python
equity_curve: str | None = Field(default=None)
# 存储 JSON 数组，如 [1.0, 1.02, 0.99, ...]
# 旧记录为 NULL，show 时降级提示
```

### `BacktestResultView`（`application/backtest.py`）

同步新增：
```python
@dataclass(frozen=True)
class BacktestResultView:
    ...
    equity_curve: str | None   # 新增
```

### DB 迁移（`db.py`）

在 `_run_lightweight_migrations()` 中追加：
```python
if "equity_curve" not in bt_col_names:
    conn.exec_driver_sql(
        "ALTER TABLE backtestresult ADD COLUMN equity_curve TEXT"
    )
```

---

## Section 2: Service Layer + CLI

### `backtest_engine.py`：curve 填充

两个函数内部已有 `curve` 列表（`curve = [1.0]; curve.append(equity)` 模式），直接塞入返回的 `BacktestMetrics`：

**`run_weighted_backtest`** 返回：
```python
return BacktestMetrics(
    periods=len(returns),
    total_return=equity - 1.0,
    max_drawdown=max_drawdown,
    sharpe=sharpe,
    curve=curve,   # 新增
)
```

**`run_dynamic_backtest`** 返回：
```python
return (
    BacktestMetrics(
        periods=len(all_returns),
        total_return=equity - 1.0,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        curve=curve,   # 新增
    ),
    final_weights,
)
```

### Sparkline 渲染（`cli.py`）

```python
_SPARK_CHARS = "▁▂▃▄▅▆▇█"

def _sparkline(curve: list[float], width: int = 40) -> str:
    """将权益曲线降采样到 width 个字符，映射到 8 级 Unicode 块字符。"""
    if not curve or len(curve) < 2:
        return "─" * width
    # 降采样：每 step 个点取平均
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

### Application 层：`get_backtest_result()`

新增函数供 `show` 命令使用：
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

### Application 层：存储 curve

`run_backtest_for_strategy` 和 `run_quant_backtest` 存储时新增：
```python
equity_curve=json.dumps(metrics.curve),
```

### `backtest show <id>` 输出

```
回测 #3 · Momentum · 动态 · 180 天

  总收益     最大回撤    Sharpe
  +34.2%    -8.1%       1.84

  权益曲线
  ▁▂▂▃▃▄▃▄▅▅▆▅▆▇▇▇▆▇██▇▇█████
  2025-09-01 ──────────────── 2026-03-18
```

旧记录（`equity_curve=NULL`）时输出：
```
  权益曲线
  [历史记录无曲线数据，重新运行回测可获得曲线]
```

### `backtest compare <id1> <id2> ...` 输出

```
策略对比

  ID  策略             类型   周期   总收益    最大回撤   Sharpe
   1  EqualWeight      静态   180   +12.3%    -5.2%     0.92
   2  Momentum         动态   180   +34.2%    -8.1%     1.84
   3  BollingerBand    动态   180   +28.7%    -6.9%     1.56

  权益曲线（各起点归一为 1.0）
  #1  EqualWeight     ▁▁▂▂▂▃▃▃▃▃▄▄▄▅▅▅▅▅▅▅▅
  #2  Momentum        ▁▂▂▃▃▄▃▄▅▅▆▅▆▇▇▇▆▇██▇▇█████
  #3  BollingerBand   ▁▂▂▂▃▃▃▄▄▄▅▅▅▆▆▆▇▇▇▇████
```

---

## Section 3: Testing

**文件**：`tests/test_backtest_show.py`

| 测试名 | 验证内容 |
|---|---|
| `test_backtest_metrics_has_curve` | `BacktestMetrics.curve` 长度 = `periods + 1`，`curve[0] == 1.0` |
| `test_run_weighted_backtest_curve` | 上涨价格序列下 `curve[-1] > 1.0` |
| `test_run_dynamic_backtest_curve` | 动态回测 `curve` 长度 > 0，`curve[0] == 1.0` |
| `test_sparkline_flat` | 平坦曲线全部输出 `▁` |
| `test_sparkline_rising` | 上涨曲线末尾字符不低于首字符 |
| `test_sparkline_width` | `width=10` 时输出恰好 10 字符 |
| `test_backtest_show_cli` | `backtest show <id>` exit_code=0，输出含策略名、总收益数字、sparkline 字符 |
| `test_backtest_show_no_curve` | `equity_curve=NULL` 的旧记录，exit_code=0，输出含"无曲线数据"提示 |
| `test_backtest_show_missing_id` | 不存在 ID，exit_code=1，输出含错误提示 |
| `test_backtest_compare_cli` | `backtest compare <id1> <id2>` exit_code=0，输出含两行 sparkline |
| `test_backtest_compare_missing_id` | 含不存在 ID，exit_code=1 |

---

## Error Handling

- `backtest show <id>`：ID 不存在 → exit_code=1，`错误：回测记录 #N 不存在。`
- `backtest compare`：任意 ID 不存在 → exit_code=1，列出所有无效 ID
- `equity_curve=NULL`：降级提示，不报错

## Constraints

- 不新增第三方依赖
- sparkline 字符数固定 width=40（compare 模式下缩短到 28 以适配多行）
- `--output json` 支持：`backtest show` 输出完整 `BacktestResultView` dict（含 `equity_curve` JSON 字符串）
