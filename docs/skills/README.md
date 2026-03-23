# HiveFlow Skills Guide

这份文档用于说明 HiveFlow 当前推荐的 Skill 体系，以及它们与 `HiveFlow CLI`、外部 `Agent Runtime` 的关系。

## 项目内 / 项目外分工

1. `HiveFlow CLI`
负责确定性数据与工具输出，例如持仓、行情、信号、回测、调仓预览、交易执行。

2. `Skill`
负责把投资判断组织成稳定、可复用的工作流。

3. `Agent Runtime`
由 `Codex`、`Claude` 等平台提供，负责执行 Skill、调用 CLI、读取 JSON、与用户交互。

一句话理解：

`HiveFlow 提供上下文和动作接口，Skill 提供判断流程，Agent Runtime 负责执行流程。`

## 当前 Skill 列表

| Skill | 作用 | 适用阶段 |
|---|---|---|
| `hiveflow-daily-check` | 做每日组合检查，判断今天是否需要进一步动作 | 检查 |
| `hiveflow-strategy-selector` | 比较策略、决定是否切换策略 | 决策 |
| `hiveflow-rebalance-executor` | 基于目标仓位生成候选调仓动作，并等待确认 | 执行前 |
| `hiveflow-portfolio-advisor` | 作为总控 Skill，在多阶段任务中调度上述子 Skill | 跨阶段 |

## 路由顺序

默认按以下顺序推进：

1. `hiveflow-daily-check`
2. `hiveflow-strategy-selector`
3. `hiveflow-rebalance-executor`

如果用户的问题跨越多个阶段，优先使用 `hiveflow-portfolio-advisor` 作为入口。

## Skill 详情

### `hiveflow-daily-check`

目标：
- 回答“今天组合是否健康，是否值得继续动作”

典型输入：

```bash
uv run hiveflow sync
uv run hiveflow context decision --output json
uv run hiveflow positions list --output json
```

需要深度分析（多窗口/时效）时再补：

```bash
uv run hiveflow context daily --output json
```

典型输出：
- `stable`
- `watch`
- `action_needed`
- `context_insufficient`

适合的用户问题：
- “今天状态怎么样”
- “帮我看看组合”
- “今天需不需要动”

不适合：
- 直接做策略切换
- 直接生成交易订单

### `hiveflow-strategy-selector`

目标：
- 回答“当前市场更适合哪种策略，要不要切换”

典型输入：

```bash
uv run hiveflow context daily --output json
uv run hiveflow quant list
uv run hiveflow quant run --strategy <StrategyName> --output json
uv run hiveflow backtest quant-run --strategy <StrategyName>
uv run hiveflow backtest compare <id1> <id2> ... --output json
```

典型输出：
- `selected_strategy`
- `switch_needed`
- `candidate_comparison`

适合的用户问题：
- “现在哪种策略更合适”
- “要不要切换策略”
- “帮我比较下这些策略”

不适合：
- 直接进入交易执行

### `hiveflow-rebalance-executor`

目标：
- 回答“如果已经有目标仓位，接下来该怎么执行”

典型输入：

```bash
uv run hiveflow positions drift --output json
uv run hiveflow rebalance preview --output json
uv run hiveflow positions list --output json
```

必要时补充：

```bash
uv run hiveflow context daily --output json
```

典型输出：
- `execution_needed`
- `actions`
- `ready_for_confirmation`

适合的用户问题：
- “接下来怎么调仓”
- “生成执行计划”
- “帮我把目标仓位落到动作上”

不适合：
- 用户未确认就直接调用 `trade execute`

### `hiveflow-portfolio-advisor`

目标：
- 作为总控入口，解决跨阶段任务

适合的用户问题：
- “我该怎么动”
- “帮我完整分析并给出下一步”
- “调仓”

执行方式：
- 先判断任务阶段
- 再路由到合适的子 Skill
- 不把所有工作硬塞进一个长流程里

## 推荐命令面

Skill 体系当前主要围绕以下命令：

```bash
uv run hiveflow sync
uv run hiveflow positions list --output json
uv run hiveflow check --output json
uv run hiveflow signal snapshot --symbol <SYMBOL> --output json
uv run hiveflow context decision --output json
uv run hiveflow context daily --output json
uv run hiveflow quant list
uv run hiveflow quant run --strategy <StrategyName> --output json
uv run hiveflow backtest quant-run --strategy <StrategyName>
uv run hiveflow backtest compare <id1> <id2> ... --output json
uv run hiveflow targets set-from-backtest <backtest_id>
uv run hiveflow positions drift --output json
uv run hiveflow rebalance preview --output json
uv run hiveflow trade execute --orders '...'
uv run hiveflow perf compare <backtest_id> --output json
```

## Guardrails

这套 Skill 体系有几个硬边界：

1. HiveFlow 不做投资判断
2. Skill 负责决策流程，不负责伪造数据
3. Agent Runtime 可以分析和解释，但不应在用户未确认时直接交易
4. `trade execute` 只能在明确确认后调用
5. 数据不足时，优先返回“上下文不足”，而不是硬给结论

## 推荐阅读

- [CLI README](/Users/rongts/strat-flow/docs/cli/README.md)
- [PROJECT_CONTEXT.md](/Users/rongts/strat-flow/docs/context/PROJECT_CONTEXT.md)
- [hiveflow-daily-check](/Users/rongts/strat-flow/skills/hiveflow-daily-check/SKILL.md)
- [hiveflow-strategy-selector](/Users/rongts/strat-flow/skills/hiveflow-strategy-selector/SKILL.md)
- [hiveflow-rebalance-executor](/Users/rongts/strat-flow/skills/hiveflow-rebalance-executor/SKILL.md)
- [hiveflow-portfolio-advisor](/Users/rongts/strat-flow/skills/hiveflow-portfolio-advisor/SKILL.md)
