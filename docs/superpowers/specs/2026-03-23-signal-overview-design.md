# signal overview 设计文档

## 目标

新增 `hiveflow signal overview` 命令，一次性输出所有活跃持仓的信号分类摘要 + 组合级信号关键指标，提供"仪表盘式"总览视角，补充现有 `signal snapshot --symbol` 的单资产详情能力。

---

## 背景

现有命令需要逐资产查看：

```bash
hiveflow signal snapshot --symbol BTC
hiveflow signal snapshot --symbol ETH
hiveflow signal portfolio
```

`signal overview` 将这三类信息合并为一次输出，方便快速判断整体持仓信号健康度。

---

## 数据结构

### Application 层返回值

```python
{
    "as_of": "2026-03-23T08:00:00+00:00",
    "assets": [
        {
            "symbol": "BTC",
            "category_summary": {
                "trend":   {"state": "bullish", "triggered": 2, "total": 6},
                "risk":    {"state": "low",     "triggered": 0, "total": 4},
                "confirm": {"state": "neutral", "triggered": 0, "total": 4},
                "regime":  {"state": "bullish", "triggered": 1, "total": 3},
            },
            "triggered_total": 3,
            "signals_total": 17,
        },
        ...
    ],
    "portfolio": {
        "as_of": "...",
        "signals": [ ...7 条 PORTFOLIO 信号... ]
    }
}
```

**说明：**

- `assets` 列表按持仓 `market_value` 降序排列
- `category_summary` 只含 per-asset 分类（trend/risk/confirm/regime），不含 quality（quality 的 4 条信号全为 PORTFOLIO 级，归入 portfolio 侧）
- 每个分类的 `state` 为该分类信号的众数状态（most common state）；平局时按优先级取最严重的（risk: high > medium > low；trend/confirm/regime: bearish > bullish > neutral）
- `triggered_total` / `signals_total` 仅统计 per-asset 信号（17 条，不含 PORTFOLIO 的 7 条）
- `portfolio.signals` 直接复用 `build_portfolio_signals` 返回值

---

## 接口设计

### Application 层

**新增函数：** `build_signal_overview(settings=None) -> dict`

位置：`src/hiveflow/application/signals.py`，放在 `build_signal_category_multi` 之后。

```python
def build_signal_overview(settings: Settings | None = None) -> dict:
    """所有活跃持仓的信号分类摘要 + 组合级信号。

    返回结构见设计文档。无持仓时退化为 MarketBar 中全部非 USDT symbol。
    """
```

内部逻辑：
1. 调用 `_load_market_context` 获取 close_df 和 positions
2. 确定 active symbols（market_value > 0.01，按 market_value 降序）
3. 对每个 symbol 调用 `build_signal_snapshot(symbol, settings=s)`
4. 过滤 `s["symbol"] != "PORTFOLIO"` 得到 17 条 per-asset 信号
5. 按 category 分组，计算 dominant state 和 triggered 统计
6. 调用 `build_portfolio_signals(settings=s)` 获取组合信号
7. 返回汇总 dict，`as_of` 取第一个 asset 的快照 `as_of`

**Dominant state 算法：**

```python
_CATEGORY_STATE_PRIORITY: dict[str, list[str]] = {
    "trend":   ["bearish", "bullish", "neutral"],
    "confirm": ["bearish", "bullish", "neutral"],
    "regime":  ["bearish", "bullish", "neutral"],
    "risk":    ["high", "medium", "low"],
}

def _dominant_state(category: str, states: list[str]) -> str:
    from collections import Counter
    counts = Counter(states)
    top_count = counts.most_common(1)[0][1]
    top_states = {s for s, c in counts.items() if c == top_count}
    for priority_state in _CATEGORY_STATE_PRIORITY.get(category, []):
        if priority_state in top_states:
            return priority_state
    return states[0]
```

### CLI 层

**新增命令：** `signal overview`

位置：`src/hiveflow/cli.py`，放在 `signal_portfolio_command` 之后。

```python
@signal_app.command("overview")
def signal_overview_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出所有持仓资产的信号分类摘要与组合级信号。"""
```

**Pretty 输出格式：**

```
信号总览  2026-03-23

资产   趋势     风险      确认     状态     触发/总计
BTC    看多     低风险    中性     看多     3 / 17
ETH    中性     中风险    中性     中性     1 / 17
SOL    看空     高风险    中性     中性     5 / 17

组合  集中度:低  相关性:中  宽度:看多  置信度:0.81
```

- 资产表格：`Table`，列为 资产 / 趋势 / 风险 / 确认 / 状态（即 `regime` 分类的 dominant state） / 触发总计
- 状态列带颜色（复用已有 `_STATE_STYLE` 逻辑）
- 组合摘要：单行 `console.print`，展示 concentration_risk / correlation_spike / local_breadth_proxy / confidence_score 四个关键指标
- JSON 输出：`json.dumps(payload)`，完整结构体

**import 更新：**

在 `cli.py` 顶部 signals import 中追加 `build_signal_overview`。

---

## 测试

文件：`tests/test_signal_cli.py`，追加以下用例：

| 测试名 | 验证内容 |
|--------|---------|
| `test_signal_overview_json_returns_all_positions` | exit_code=0；`assets` 含 BTC/ETH/SOL；每个 asset 有 4 个 category_summary；`signals_total==17` |
| `test_signal_overview_json_includes_portfolio` | `portfolio.signals` 长度为 7，全部 symbol="PORTFOLIO" |
| `test_signal_overview_pretty_prints_table` | exit_code=0；输出含"信号总览"/"触发"/"组合" |
| `test_signal_overview_fails_without_market_data` | 空 DB 时 exit_code=1，JSON 含 `code`；`payload["details"]["strict_mode"] is True`；`context` 字段值接受底层抛出的 `"signal.snapshot"` passthrough |

---

## 边界行为

| 场景 | 行为 |
|------|------|
| 无持仓 | 使用 MarketBar 中全部非 USDT symbol（与其他 multi 命令一致） |
| MarketBar 为空 | 抛出 SignalPipelineError，CLI 返回结构化错误 exit_code=1 |
| 单一持仓 | assets 列表只有 1 行，组合信号正常输出 |

---

## 不在范围内

- 历史 overview 快照持久化（不落库）
- `--symbol` 过滤（overview 定位是全局视角）
- 信号详情展开（详情用 `signal snapshot --symbol`）
