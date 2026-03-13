# PROJECT_CONTEXT

## 项目名

- 英文：HiveFlow
- 中文：策略流（沿用历史语境）

## 一句话定位

一个由多策略协作驱动的个人资产决策系统，用于把策略、持仓、风险、目标持仓和调仓建议放在同一个可追溯系统中。

## 核心目标

- 不是“问 AI 买什么”
- 而是建立“可信状态 + 可追溯决策 + 可执行动作”的闭环

## 核心对象

- 策略（Strategy）
- 策略席位（Slot）
- 当前策略（Current Strategy）
- 实际持仓（Positions）
- 目标持仓（Target Allocations）
- 风险信号（Risk Signals）
- 调仓建议（Rebalance Suggestions）
- 决策日志（Decision Logs）

## 建模原则（当前共识）

- 策略信息至少分三层：
  - 策略名称（name）
  - 策略类型（strategy_type，底层兼容 category）
  - 策略维度（dimension）
- “策略权重”和“当前策略”不是一回事：
  - 策略权重：组合结构
  - 当前策略：当前时点的执行主策略

## 开发原则

- CLI 优先，把业务闭环做实
- 先可追溯，再智能化
- 每个 chunk 都要有测试与文档回填

