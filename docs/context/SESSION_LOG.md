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
- 完成 Chunk 30：文档收口并完成全量回归（`73 passed`，后续持续增加至 87 passed）。
- 完成 M4 Chunk 0：新增 `market-data template / validate`，冻结行情输入契约并提供校验能力。
- 完成 M4 Chunk 1：新增 `backtest run / list`，实现最小回测引擎与结果落库。
- 增加行情落库能力：新增 `market-data import / list / summary`，支持行情数据沉淀与查询。
- 协作规范补充：在 `AGENTS.md` 增加约定式提交说明与推荐类型列表，统一中文提交格式。

## 2026-03-17

- 完成 M5 收尾：网格持仓区分合约类型（inst_type: SPOT/SWAP），改用 orders-algo-pending 接口拉取运行中机器人。
- 完成 Skills 版本控制化：新增 `skills/` 目录纳入项目仓库，迁移 `hiveflow-daily-check` 和 `hiveflow-portfolio-advisor` 的 SKILL.md。
- 新增 `hiveflow skills list / install` 命令，通过软链接将项目 skills/ 安装到 `~/.agents/skills/`，支持 --force 覆盖。
- 设计决策：`~/.agents/skills/` 作为统一安装目录，其他平台（Cursor 等）各自软链接到该目录。
- 全量测试：154 passed。

## 2026-03-18

- 完成 M6：新增 `hiveflow quant` 命令组，内置 8 种量化策略（EqualWeight / Momentum / MeanReversion / MovingAverageCross / BollingerBand / RiskParity / MaxSharpe / MinVariance），策略结果落库 StrategyRun，支持 `--apply` 写入 TargetAllocation + DecisionLog。
- RiskParity / MaxSharpe / MinVariance 依赖 PyPortfolioOpt（可选），不安装时自动降级为等权重并打印提示。
- 更新 `hiveflow-portfolio-advisor` Skill，新增 Step 2 量化策略工作流与 JSON 输出示例。
- 全量测试：193 passed。
- 完成动态回测：新增 `backtest quant-run --strategy <StrategyName>`，支持每隔 N 天重新计算量化策略权重并回测，结果落库 BacktestResult（backtest_type=dynamic）；backtest list 新增 ID 和类型列。
- 全量测试：204 passed。
- 完成 M7：回测权益曲线可视化。`BacktestMetrics.curve` 字段，`BacktestResult.equity_curve` 落库（JSON），`BacktestResultView.equity_curve` 视图。新增 `backtest show <id>`（权益曲线 Sparkline + 指标摘要）与 `backtest compare <id1> <id2>...`（多回测并排对比），均支持 `--output json`。Unicode Sparkline 用 8 级块字符（`▁▂▃▄▅▆▇█`），show 宽 40、compare 宽 28，上取整采样避免截断长曲线。旧记录 NULL curve 降级提示。
- 全量测试：221 passed。
- 完成 M8：风险分析引擎。新增 `services/risk_engine.py`（compute_volatility / compute_correlation / compute_drawdown / compute_portfolio_risk，纯计算无 DB 依赖，手工实现 Pearson 相关系数），`application/risk_analysis.py`（analyze_asset_risk / analyze_portfolio_risk）。新增 `hiveflow risk-analysis assets`（资产年化波动率、日波动率、历史 MDD、相关性矩阵，支持 --symbols / --output json）与 `risk-analysis portfolio <id>`（组合年化波动率、胜率、Calmar ratio，equity_curve=NULL 时降级提示，exit_code=0）。`backtest show` 追加风险指标节（仅在 equity_curve 存在时显示）。无新增第三方依赖，年化因子 365（加密市场）。
- 全量测试：247 passed。

## 2026-03-18

- 决策：M9 选择「多策略混合 + 实盘绩效追踪」，两个功能串联形成 blend→execute→track→compare 链路
- 设计：BlendConfig + PortfolioSnapshot 两个新实体，blend.py + perf.py 两个新 application 模块
- 实现：7 个子任务全部交付，含 TDD + 两阶段评审（spec + code quality）
- 结果：280 tests passed，quant blend 和 perf 命令组已上线

## 2026-03-19

- 修复：`positions drift` 与 `check` 统一忽略 `market_value <= 0.01 USDT` 的极小持仓，避免噪声仓位干扰分析。
- 验证：新增回归测试并通过，`tests/test_health_check.py`、`tests/test_cli.py`、`tests/test_cli_check.py` 均已绿色。

## 2026-03-20

- 决策：`Signal System` Phase 1 采用严格模式，缺失即失败，不返回部分结果；系统坚持“只输出数据、不做推荐”边界。
- 决策：冻结全局统一错误码（10 个）与错误对象结构（`code/message/context/as_of/details/trace_id/hint`）。
- 决策：冻结两层信号分层（关键层 12、增强层 12）与关键层参数寻优框架（`Calmar` 最大化，`MDD >= -20%`，Grid Search，每信号候选上限 500）。
- 决策：冻结 `market_regime_label v1` 判定公式，并将风格回测与现有 `backtest quant-run` 的关系、排序规则、报告字段契约写入设计文档。
- 结果：形成可执行设计稿 `docs/superpowers/specs/2026-03-20-signal-system-heavy-expansion-design.md`，待进入实现计划阶段。
- 实现：落地 Phase 1 Step 1（`signal trend/risk/confirm/regime/quality/snapshot` + `style backtest-rank` 命令骨架），引入全局错误协议 `error_protocol` 与系统日志表 `systemlog`。
- 行为：严格模式下命令返回结构化错误对象（含 `trace_id` 与 `details/hint`），并写入系统日志，CLI 退出码为 1。
- 测试：新增 `tests/test_signal_cli.py`（4 例）并通过；回归通过 `tests/test_cli.py`（66 例）与 `tests/test_cli_check.py`（4 例）。
- 实现：完成 Phase 1 Step 2，`signal snapshot` / `signal trend|risk|confirm|regime|quality` 从“骨架失败”升级为“真实计算输出”，支持 24 信号统一字段协议、`category_metrics` 与 `conflict_matrix`。
- 实现：新增 `style_backtest.py`，`style backtest-rank` 已复用 `backtest quant-run` 对 4 个风格批量回测并输出 `rank_table`、`sort_key`、`tie_breaker`（不含任何推荐字段）。
- 行为：数据不足或缺失时仍按严格模式失败并写系统日志；数据充足时命令返回结构化成功结果（`--output json` 可直接供 Agent 消费）。
- 测试：扩展 `tests/test_signal_cli.py` 到 7 例（成功 + 失败路径），并通过；回归通过 `tests/test_cli.py`、`tests/test_cli_check.py`、`tests/test_dynamic_backtest.py`、`tests/test_quant_cli.py` 共 `86 passed`。
