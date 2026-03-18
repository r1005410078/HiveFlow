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
    curve: list[float]   # 新增；无默认值；len(curve) == periods + 1，curve[0] == 1.0
```

### `BacktestResult`（`domain/backtests.py`）

新增列：
```python
equity_curve: str | None = Field(default=None)
# 存储 JSON 数组，如 [1.0, 1.02, 0.99, ...]
# 旧记录为 NULL，show 时降级提示
```

### `BacktestResultView`（`application/backtest.py`）

同步修改三处：

1. 在 `BacktestResultView` dataclass 新增字段：
```python
@dataclass(frozen=True)
class BacktestResultView:
    ...
    equity_curve: str | None   # 新增
```

2. 在 `_to_view()` 中新增映射：
```python
def _to_view(row: BacktestResult) -> BacktestResultView:
    return BacktestResultView(
        ...
        equity_curve=row.equity_curve,   # 新增
    )
```

3. 在 `to_dict()` 中新增字段（`--output json` 依赖此方法）：
```python
def to_dict(self) -> dict:
    return {
        ...
        "equity_curve": self.equity_curve,   # 新增
    }
```

### DB 迁移（`db.py`）

在 `_run_lightweight_migrations()` 中，**在现有 `if "backtestresult" in tables:` 块内部**，`bt_col_names` 已构建后，追加：
```python
if "equity_curve" not in bt_col_names:
    conn.exec_driver_sql(
        "ALTER TABLE backtestresult ADD COLUMN equity_curve TEXT"
    )
```
注意：必须在同一 `if "backtestresult" in tables:` 块内，复用已有的 `bt_col_names` 集合，避免重复调用 PRAGMA。

---

## Section 2: Service Layer + CLI

### `backtest_engine.py`：curve 填充

两个函数内部已有 `curve` 列表，直接塞入返回的 `BacktestMetrics`：

**`run_weighted_backtest`**：现有代码为 `equity = 1.0; curve = [equity]`，然后每个周期执行 `equity *= ...; curve.append(equity)`。因此 `len(curve) == periods + 1`，`curve[0] == 1.0` 成立。

**`run_dynamic_backtest`**：现有代码同样初始化 `equity = 1.0; curve = [equity]`，每个区块内逐日 append。由于动态回测跨多个区块，最后区块可能不满 `rebalance_days` 天，`len(curve)` 不保证严格等于 `len(all_returns) + 1`，但 `curve[0] == 1.0` 成立，`len(curve) > 1` 成立。

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
    """将权益曲线降采样到至多 width 个字符，映射到 8 级 Unicode 块字符。

    输出长度规则：
    - 若 len(curve) >= width：输出恰好 width 个字符
    - 若 len(curve) < width：输出 len(curve) 个字符（不补齐，调用方可按需 ljust）
    - 若 len(curve) < 2：返回 width 个 '─'
    """
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

新增函数供 `show` 命令使用。**注意**：`_to_view(row)` 在 `with` 块内调用（现有 `list_backtest_results` 在 `with` 外调用，SQLite 下均可正常工作，本函数遵循更安全的模式）：
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

`_sparkline(curve, width=40)` — show 命令固定使用 width=40。

日期范围行：不显示开始日期（`BacktestResult` 未存储），仅显示 `created_at` 作为结束日期，格式：
```
  权益曲线（{periods} 期）
  ▁▂▂▃▃▄▃▄▅▅▆▅▆▇▇▇▆▇██▇▇█████
  创建：2026-03-18
```

完整输出示例：
```
回测 #3 · Momentum · 动态 · 180 天

  总收益     最大回撤    Sharpe
  +34.2%    -8.1%       1.84

  权益曲线（180 期）
  ▁▂▂▃▃▄▃▄▅▅▆▅▆▇▇▇▆▇██▇▇█████
  创建：2026-03-18
```

旧记录（`equity_curve=NULL`）时输出：
```
  权益曲线
  [历史记录无曲线数据，重新运行回测可获得曲线]
```

### `backtest compare <id1> <id2> ...` 输出

`_sparkline(curve, width=28)` — compare 命令固定使用 width=28（适配多行前缀）。
`--output json` 支持：输出 list，每项为对应 `BacktestResultView.to_dict()`（含 `equity_curve`）。

```
策略对比

  ID  策略             类型   周期   总收益    最大回撤   Sharpe
   1  EqualWeight      静态   180   +12.3%    -5.2%     0.92
   2  Momentum         动态   180   +34.2%    -8.1%     1.84
   3  BollingerBand    动态   180   +28.7%    -6.9%     1.56

  权益曲线（各起点归一为 1.0）
  #1  EqualWeight     ▁▁▂▂▂▃▃▃▃▃▄▄▄▅▅▅▅▅▅▅▅
  #2  Momentum        ▁▂▂▃▃▄▃▄▅▅▆▅▆▇▇▇▆▇██
  #3  BollingerBand   ▁▂▂▂▃▃▃▄▄▄▅▅▅▆▆▆▇▇▇▇
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
| `test_sparkline_width` | 输入长度 ≥ 40 的曲线，`width=10` 时输出恰好 10 字符 |
| `test_backtest_show_cli` | 种入含非空 `equity_curve` 的回测记录；`backtest show <id>` exit_code=0，输出含策略名、总收益数字、至少一个 `_SPARK_CHARS` 中的字符 |
| `test_backtest_show_no_curve` | `equity_curve=NULL` 的旧记录，exit_code=0，输出含"无曲线数据"提示 |
| `test_backtest_show_missing_id` | 不存在 ID，exit_code=1，输出含错误提示 |
| `test_backtest_compare_cli` | `backtest compare <id1> <id2>` exit_code=0，输出含两行 sparkline |
| `test_backtest_compare_missing_id` | 含不存在 ID，exit_code=1，输出列出所有无效 ID |
| `test_backtest_show_json_output` | `backtest show <id> --output json`，exit_code=0，输出可解析为含 `strategy_name` / `equity_curve` 键的 dict |
| `test_backtest_compare_json_output` | `backtest compare <id1> <id2> --output json`，exit_code=0，输出可解析为含 2 个元素的 list，每项含 `strategy_name` 键 |

---

## Error Handling

错误退出统一使用 `raise typer.Exit(code=1)`（与现有 CLI 模式一致，确保 `typer.testing.CliRunner` 正确捕获）：

- `backtest show <id>`：ID 不存在 → `typer.echo("错误：回测记录 #N 不存在。"); raise typer.Exit(code=1)`
- `backtest compare`：**先做全量预检**，收集所有无效 ID，若有任何无效则输出错误信息后 `raise typer.Exit(code=1)`，不输出部分结果
- `equity_curve=NULL`：降级提示，不报错，不 Exit

## Constraints

- 不新增第三方依赖
- sparkline width：`backtest show` 固定 40，`backtest compare` 固定 28
- `--output json` 支持（与现有 `backtest run` 保持一致，直接输出 JSON，不加 envelope）：
  - `backtest show`：`json.dumps(result.to_dict(), ensure_ascii=False, indent=2)`
  - `backtest compare`：`json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2)`
