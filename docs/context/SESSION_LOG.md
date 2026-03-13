# SESSION_LOG

## 2026-03-13

- 完成 Chunk 14：新增 `slots list / slots set-weight`，并联动 `summary` 席位统计。
- 完成 Chunk 15：新增 `current show / current set-strategy`，并联动 `summary.current_strategy`。
- 完成 Chunk 16：`targets generate` 与 `rebalance preview` 在未传策略时默认使用当前策略。
- 完成 Chunk 17：`targets list` 支持 `--strategy` 过滤；`targets import append` 改为同策略同标的覆盖写入，避免重复堆积。
- 完成 Chunk 18：策略模型落地 `strategy_type + dimension`，并补旧库轻量迁移（自动加 `strategy.dimension` 列）。
- 统一输出口径：涉及策略输出的命令逐步从“分类”统一为“类型”，并补充维度展示。
- 完成 Chunk 19：`targets generate` 支持“维度优先、类型回退”的模板选择，并输出模板来源。
- 完成 Chunk 20：目标模板支持外部配置文件 `config/target-templates.json`，可通过 `HIVEFLOW_TARGET_TEMPLATE_FILE` 切换。
- 完成 Chunk 21：新增 `targets template-show / template-set`，可在 CLI 里直接查看和更新模板。
- 提交约定确认：后续 git 提交信息使用中文。
- 完成 Chunk 25：新增 `positions drift`，支持按当前策略检测偏离等级和动作建议。
- 完成 Chunk 26：`rebalance preview` 增加 `risk_waterline + explanation` 输出，可直接供模型消费。
- 完成 Chunk 27：模板修改写入版本快照，新增 `targets template-rollback` 回滚能力。
- 完成 Chunk 28：新增 `hiveflow doctor` 与 `hiveflow init-demo`。
- 完成 Chunk 29：新增统一 JSON 输出预备层（`--envelope`）与 `--json-schema`。
- 完成 Chunk 30：文档收口并完成全量回归（`73 passed`）。
- 完成 M4 Chunk 0：新增 `market-data template / validate`，冻结行情输入契约并提供校验能力。
- 完成 M4 Chunk 1：新增 `backtest run / list`，实现最小回测引擎与结果落库。
- 增加行情落库能力：新增 `market-data import / list / summary`，支持行情数据沉淀与查询。
