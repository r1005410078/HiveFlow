# CURRENT_STATE

## 当前时间点

- 日期：2026-03-13
- 当前分支：`main`

## 已完成阶段（按计划文档）

- Chunk 1 ~ Chunk 30 已落地
- 最近完成重点：
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

- 全量测试最近结果：`73 passed`
- 本地存在未跟踪数据文件：`data/`、`strategies.csv`（不应提交）

## 下一步建议

1. 启动 M4：策略回测 v1（指标、窗口、费用、结果存档）
2. 风险分析从导入升级为计算（支持定时刷新）
3. 自定义策略发布闭环（验证、版本、回滚）
