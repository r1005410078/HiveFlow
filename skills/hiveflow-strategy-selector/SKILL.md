---
name: hiveflow-strategy-selector
description: Use when a HiveFlow user wants to compare strategies, choose the most suitable strategy for the current market, or decide whether to switch strategy before rebalancing.
---

# HiveFlow Strategy Selector

用于策略筛选与切换决策。目标不是直接给出黑箱买卖指令，而是基于当前上下文和回测结果，回答“现阶段更适合哪种策略，是否值得切换”。

## When to Use

- 用户说“选策略”、“比较策略”、“现在更适合哪种策略”
- 用户想在多个量化策略之间做选择
- 用户想决定是否从当前方案切换到另一套策略
- 不适合：用户只想做每日体检，或已经明确知道要执行哪套策略

## Inputs

按以下顺序工作：

```bash
uv run hiveflow context daily --output json
uv run hiveflow quant list
```

然后对候选策略逐个运行：

```bash
uv run hiveflow quant run --strategy <StrategyName> --output json
uv run hiveflow backtest quant-run --strategy <StrategyName>
```

最后比较：

```bash
uv run hiveflow backtest compare <id1> <id2> ... --output json
```

## Selection Logic

按以下顺序做判断：

1. 市场状态是否支持该策略
- 趋势较强时，优先考虑趋势/动量类
- 震荡或均值回归特征明显时，优先考虑均值回归类
- 风险升高时，优先考虑更保守、波动更低的方案

2. 回测表现是否足够稳健
- 不只看总收益
- 优先看最大回撤、Sharpe、收益与回撤是否平衡
- 若高收益来自显著更差的回撤，谨慎对待

3. 当前组合是否值得切换
- 若新策略优势很小，不建议频繁切换
- 若当前市场状态与现有策略明显不匹配，可以建议切换

## Output Contract

建议输出：

```json
{
  "status": "success",
  "decision": {
    "selected_strategy": "",
    "switch_needed": "yes|no",
    "selection_reason": ""
  },
  "evidence": {
    "market_context": [],
    "candidate_comparison": []
  },
  "actions": [],
  "risks": [],
  "next_command": []
}
```

`candidate_comparison` 至少覆盖：
- `strategy`
- `total_return`
- `max_drawdown`
- `sharpe`
- `fit_for_current_market`

## Execution Handoff

如果结论是切换，并且用户同意继续，则按顺序调用：

```bash
uv run hiveflow targets set-from-backtest <backtest_id>
uv run hiveflow positions drift --output json
uv run hiveflow rebalance preview --output json
```

只有在用户明确确认执行时，才继续进入交易执行阶段。

## Response Style

- 先给出“选谁 / 不切换”的结论
- 再给最关键的比较证据
- 重点解释为什么当前市场更适合该策略
- 如果不建议切换，要明确说“不切换的原因”

## Example

```text
建议策略：MomentumStrategy
是否切换：yes

- 当前趋势信号强于均值回归信号，市场更偏趋势延续
- Momentum 的回测收益更高，且回撤没有明显恶化
- 与现有策略相比，切换收益风险比更优
```

## Common Mistakes

- 只看收益，不看回撤和 Sharpe
- 忽略当前市场状态，机械选历史最好策略
- 很小优势也频繁建议切换
- 未经用户确认就直接进入交易执行
