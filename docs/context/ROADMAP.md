# ROADMAP

## 为什么要这份文档

这是一份“一眼看懂下一步”的路线图，避免开发变成只看当前小需求。

## 当前位置

- 已完成：Chunk 1 ~ Chunk 30 + M4 Chunk 0/1
- 当前阶段：M4 进行中

## 三个里程碑

### M1：策略驱动决策闭环（已完成）

目标：
- 策略、当前策略、目标持仓、调仓建议、日志形成完整链路
- 模板可配置且可通过命令维护

代表能力：
- `current set-strategy`
- `targets generate`
- `rebalance preview`
- `targets template-show / template-set`

### M2：策略质量与风控闭环（已完成）

目标：
- 让“策略回测”和“风险门控”成为一等能力，不再只是展示字段

已交付：
1. `positions drift` 偏离检测（低/中/高等级与动作建议）
2. `rebalance preview` 解释增强（类型/维度/风险水位）
3. `targets template-rollback` 模板版本回滚

### M3：自定义策略与发布闭环（已完成）

已交付：
- `hiveflow doctor` 环境/配置诊断
- `hiveflow init-demo` 一键演示数据
- 统一 JSON envelope（`--envelope`）与 `--json-schema`
- 文档与测试收口（全量回归通过）

## M4：行情驱动分析闭环（进行中）

已交付：
- `market-data template / validate` 行情输入契约与校验
- `market-data import / list / summary` 行情落库与查询
- `backtest run / list` 最小回测引擎与结果落库

后续：
1. 风险分析引擎 v1（指标计算从”导入”升级为”计算”）
2. 资产配比建议闭环（allocation drift/suggest）
3. 自定义策略 DSL 与发布流程（导入/验证/生效）
4. AI/Skills 调用契约冻结（schema 版本治理）

## 决策规则（防止“抓芝麻”）

- 不新增“看起来很酷但不改变主线结果”的功能
- 所有需求都要回答：是否直接提升“回测质量、风险控制、自定义策略”其中之一
- 如果答案是否定，进入 backlog，不占当前 sprint
