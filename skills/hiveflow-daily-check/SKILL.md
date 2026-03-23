---
name: hiveflow-daily-check
description: Use when a HiveFlow user wants a daily portfolio review, health check, or quick risk status update before deciding whether further analysis or rebalancing is needed.
---

# HiveFlow Daily Check

用于每日例行检查。目标不是直接下单，而是回答三件事：今天是否安全、哪些仓位需要关注、是否值得进入下一步调仓分析。

## When to Use

- 用户说“daily check”、“今日检查”、“check my portfolio”、“今天要不要动”
- 用户想先看整体状态，再决定是否继续调仓
- 用户需要一个简短、结构化、可解释的结论
- 不适合：用户已经明确要做策略切换、深度回测比较或直接执行调仓

## Inputs

优先按下面顺序取数：

```bash
uv run hiveflow sync
uv run hiveflow context decision --output json
uv run hiveflow positions list --output json
```

若需要多窗口分歧、来源新鲜度、信号全量细节，再补充：

```bash
uv run hiveflow context daily --output json
```

如果 `context decision` 或 `context daily` 失败，明确说明失败原因，不要自行补脑，也不要输出看起来完整但其实缺数据的结论。

## Decision Rules

按以下顺序判断：

1. 看上下文可用性
- `context decision` 若严格失败，先报告“上下文不足”
- 需要深度证据时，再看 `context daily` 的来源时效与窗口执行结果
- 数据不完整时，结论只能是“需要补数据”或“只做有限观察”

2. 看风险与异常
- 优先关注 `check`
- 再看 `signal` 中的风险、趋势恶化、质量异常
- 再看 `positions drift`

3. 看是否需要进入调仓分析
- 若风险正常、信号稳定、偏离不大：维持观察
- 若风险抬升但还不明确：建议关注，不直接调仓
- 若高风险或偏离明显：进入 `rebalance preview`

## Escalation

在以下情况下，继续调用：

```bash
uv run hiveflow rebalance preview --output json
```

- `positions drift` 中存在明显偏离
- 风险高且持仓集中
- 用户明确追问“那我该怎么动”
- 需要把“观察”升级为“候选动作”

如果只是普通波动，不要过度升级。

## Output Contract

输出尽量简短，优先结构化表达，建议包含：

```json
{
  "status": "success",
  "decision": {
    "verdict": "stable|watch|action_needed|context_insufficient",
    "recommended_next_step": "hold|review_rebalance|reduce_risk|sync_first"
  },
  "evidence": {
    "risk_summary": [],
    "signal_summary": [],
    "drift_summary": []
  },
  "actions": [],
  "risks": [],
  "next_command": []
}
```

同时给用户一段 3 到 6 行的人类可读摘要。

## Response Style

- 先给一句结论
- 再列 2 到 4 个最重要证据
- 没有异常时，不要制造紧张感
- 有异常时，指出资产、原因、下一步
- 不要假装 AI 已经做了交易决定

## Example

```text
今日结论：watch

- ETH 风险抬升，近端信号转弱
- 当前总仓位结构可控，但 ETH 偏离目标较明显
- 建议下一步查看 rebalance preview，不急于直接执行
```

## Common Mistakes

- 把 daily check 变成完整调仓报告
- 只看一个信号就下结论
- 在上下文不足时硬给明确建议
- 跳过 `context decision` / `context daily`，只凭零散命令拼凑判断
