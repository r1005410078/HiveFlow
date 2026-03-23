---
name: hiveflow-rebalance-executor
description: Use when a HiveFlow user has already chosen a strategy or target allocation and now wants to review rebalance actions, build candidate orders, and execute trades only after explicit confirmation.
---

# HiveFlow Rebalance Executor

用于调仓执行前的最后一公里。它的职责是把“目标仓位”转换为“可审查、可确认、可执行”的动作计划，而不是跳过用户确认直接交易。

## When to Use

- 用户已经选好策略或已经有目标持仓
- 用户问“接下来怎么调仓”、“帮我生成执行计划”
- 用户准备从分析进入执行
- 不适合：用户还没有完成每日检查或策略选择

## Preconditions

满足以下至少一项：

- 已有目标持仓记录
- 刚完成 `targets set-from-backtest <id>`
- 刚完成策略选择并准备落地

如果缺少目标持仓，不要强行继续执行。

## Inputs

按以下顺序获取：

```bash
uv run hiveflow positions drift --output json
uv run hiveflow rebalance preview --output json
uv run hiveflow positions list --output json
```

需要时补充：

```bash
uv run hiveflow context daily --output json
```

## Execution Rules

1. 先判断是否真的需要交易
- 如果 `drift` 很小，或 `rebalance preview` 没有建议，优先输出“不动作”
- 不要为了显得积极而制造交易

2. 再判断动作优先级
- 优先处理高优先级、大偏离、风险敞口过大的仓位
- 高风险资产只适合减仓或观望，不应鼓励加仓

3. 再生成候选执行计划
- 输出“买什么 / 卖什么 / 大概金额 / 原因”
- 如果系统没有直接给出金额，可以先输出基于偏离和优先级的人类可读计划
- 在没有足够证据时，不伪造精确数值

4. 强制用户确认
- 进入 `trade execute` 之前，必须明确要求用户确认
- 用户未确认时，停在执行计划层

## Output Contract

建议输出：

```json
{
  "status": "success",
  "decision": {
    "execution_needed": "yes|no",
    "execution_mode": "none|review_only|ready_for_confirmation"
  },
  "evidence": {
    "drift_summary": [],
    "rebalance_summary": []
  },
  "actions": [
    {
      "symbol": "",
      "action": "buy|sell|hold",
      "reason": "",
      "priority": ""
    }
  ],
  "risks": [],
  "next_command": []
}
```

## Confirmation Gate

只有在用户明确确认后，才继续调用：

```bash
uv run hiveflow trade execute --orders '[{"symbol":"ETH","action":"buy","usdt":500}]'
```

如果用户没有确认：
- 停止在执行计划
- 总结待执行动作
- 提醒用户确认后再执行

## Response Style

- 先说“是否值得执行”
- 再列出 2 到 5 条候选动作
- 每条动作都说明原因
- 明确区分“建议计划”和“已执行结果”
- 不要把执行计划伪装成已经成交

## Example

```text
建议状态：ready_for_confirmation

- 卖出 SOL：偏离目标过高，且优先级为 high
- 买入 ETH：当前低于目标权重，但需结合整体风险控制仓位
- BTC 暂不动作：当前偏离有限

如果你确认执行，我再进入 trade execute。
```

## Common Mistakes

- 用户未确认就直接调用交易命令
- 把 `rebalance preview` 直接当成已执行结果
- 没有目标持仓仍强行生成交易计划
- 忽略高风险资产的限制，机械建议加仓
