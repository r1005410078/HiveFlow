# CURRENT_STATE

## 当前时间点

- 日期：2026-03-13
- 当前分支：`main`

## 已完成阶段（按计划文档）

- Chunk 1 ~ Chunk 18 已落地
- 最近完成重点：
  - `current show / set-strategy` 闭环
  - `targets/rebalance` 默认跟随当前策略
  - `targets` 去重写入与按策略过滤
  - 策略模型支持 `strategy_type + dimension`

## 当前可用命令（核心）

- `hiveflow positions ...`
- `hiveflow risk ...`
- `hiveflow strategies ...`
- `hiveflow slots ...`
- `hiveflow current ...`
- `hiveflow targets ...`
- `hiveflow rebalance preview ...`
- `hiveflow logs ...`
- `hiveflow summary`

## 当前状态说明

- 全量测试最近结果：`62 passed`
- 本地存在未跟踪数据文件：`data/`、`strategies.csv`（不应提交）

## 下一步建议

1. 提交当前未提交改动（若会话里已有代码变更）
2. 进入下一个 chunk：围绕“策略维度驱动的目标持仓模板”做可配置化（替代硬编码）
3. 再往后：把 `rebalance` 的解释文案与策略维度联动（可解释性增强）

