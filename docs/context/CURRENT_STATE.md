# CURRENT_STATE

## 当前时间点

- 日期：2026-03-13
- 当前分支：`main`

## 已完成阶段（按计划文档）

- Chunk 1 ~ Chunk 30 已落地
- 最近完成重点：
  - `market-data template / validate` 行情输入契约能力
  - `market-data import / list / summary` 行情落库与查询能力
  - `backtest run / list` 最小回测闭环（含结果落库）
  - `positions drift` 持仓偏离告警（含等级和动作）
  - `rebalance preview` 解释增强（风险水位 + explain 文本）
  - `targets template-rollback` 模板版本回滚
  - `current run` 一键执行当前策略
  - `doctor` / `init-demo` 新用户可快速跑通
  - JSON 标准化输出能力：`--envelope` + `--json-schema`

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
- `hiveflow doctor`
- `hiveflow init-demo`

## 当前状态说明

- 全量测试最近结果：`85 passed`
- 本地存在未跟踪数据文件：`data/`、`strategies.csv`（不应提交）

## 下一步建议

1. 继续 M4：风险分析从导入升级为计算（支持定时刷新）
2. 补齐资产配比建议闭环（allocation drift/suggest）
3. 自定义策略发布闭环（验证、版本、回滚）
