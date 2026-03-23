---
name: hiveflow-portfolio-advisor
description: Use when a HiveFlow user wants an end-to-end portfolio decision workflow that may include daily review, strategy comparison, rebalance planning, and trade execution after confirmation.
---

# HiveFlow Portfolio Advisor

总控 Skill。它不负责把所有判断硬编码在一个长流程里，而是根据任务阶段，调度三个子 Skill：

- `hiveflow-daily-check`
- `hiveflow-strategy-selector`
- `hiveflow-rebalance-executor`

目标是让 Agent 按“先检查、再选策略、最后执行”的顺序推进，而不是一上来就直接生成订单。

## When to Use

- 用户说“调仓”、“rebalance”、“分析配比”、“我该怎么动”
- 用户需要一个从检查到执行的完整工作流
- 用户的问题可能跨越多个阶段，而不是只停留在单一步骤

## Routing Rules

先判断用户处于哪个阶段，再调用对应 Skill。

### 1. 仅做日常检查

如果用户只是问：
- “今天状态怎么样”
- “帮我看下组合”
- “现在需不需要动”

优先使用：
- `hiveflow-daily-check`

### 2. 需要比较策略或决定是否切换

如果用户在问：
- “现在哪种策略更合适”
- “要不要从当前策略切换”
- “帮我比较几种策略”

优先使用：
- `hiveflow-strategy-selector`

### 3. 已经准备落地调仓

如果用户已经：
- 选好了策略
- 已写入目标持仓
- 想从建议进入执行

优先使用：
- `hiveflow-rebalance-executor`

## Standard Workflow

默认按以下顺序推进：

1. 先拉取 `context decision` 做轻量判定（规则门控 + 健康度 + 执行状态）
2. 再做 `hiveflow-daily-check`
3. 如果需要更进一步，再做 `hiveflow-strategy-selector`
4. 只有在策略或目标仓位已经明确后，才进入 `hiveflow-rebalance-executor`

不要跳过前面的判断步骤，直接把用户推到交易执行。

## Core Commands

这个总控 Skill 主要围绕以下命令组织：

```bash
uv run hiveflow sync
uv run hiveflow context decision --output json
uv run hiveflow context daily --output json
uv run hiveflow quant list
uv run hiveflow backtest quant-run --strategy <StrategyName>
uv run hiveflow backtest compare <id1> <id2> ... --output json
uv run hiveflow targets set-from-backtest <backtest_id>
uv run hiveflow positions drift --output json
uv run hiveflow rebalance preview --output json
uv run hiveflow trade execute --orders '...'
```

## Guardrails

- 不直接跳到 `trade execute`
- 不在数据不足时硬做结论
- 不因为用户说“调仓”就默认应该马上动仓
- 始终把“分析结论”和“已执行结果”区分开

## Output Style

- 先说明当前处于哪个阶段
- 再给出下一步最合适的 Skill 或命令
- 需要升级到执行时，明确提示用户确认
