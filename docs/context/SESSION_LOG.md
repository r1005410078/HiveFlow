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
- 实现：统一 CLI table 表头中文化，并将 `signal` 的 pretty 展示改为中文信号键/中文状态；JSON 契约保持英文键值（供 Agent 稳定消费）。
- 实现：新增信号与风格回测历史存档能力：`SignalSnapshot`、`StyleBacktestResult` 两张表；`signal snapshot` / `style backtest-rank` 成功后自动落库；新增 `signal history/show`、`style history/show` 命令支持历史回放。
- 测试：`tests/test_signal_cli.py` 扩展到 11 例并通过；回归通过 `tests/test_cli.py`、`tests/test_cli_check.py`、`tests/test_dynamic_backtest.py`、`tests/test_quant_cli.py`、`tests/test_positions_list_grid.py`、`tests/test_perf_cli.py`、`tests/test_blend_cli.py` 共 `106 passed`。
- 实现：新增 `repro_meta` 元数据工具，输出 `feature_set_version/style_preset_version/symbols_hash/params_hash/code_version`；并为 `style backtest-rank` 补齐报告契约字段 `objective/constraints/search_method/candidates_count/valid_candidates_count/best_candidate`。
- 行为：保持“pretty 中文、JSON 英文契约”不变，同时为 Agent 增强可复现上下文与报告可追溯字段。
- 实现：补齐历史回放契约一致性，`signal show` / `style show` 现在可返回与实时命令一致的可复现元数据与风格报告字段；对应 `SignalSnapshot` / `StyleBacktestResult` 持久化表新增字段并完成读写透传。
- 兼容：`db.py` 新增 SQLite 轻量迁移，旧库自动补齐新增列（无需手工迁移）。
- 测试：新增断言覆盖历史回放元数据与报告字段；定向用例 `2 passed`，`tests/test_signal_cli.py` `11 passed`，回归集合 `106 passed`。
- 文档：补完 `docs/cli/README.md` 场景二，明确每日健康检查推荐流程（`sync/check/drift/signal snapshot`）、`<=0.01 USDT` 极小持仓忽略规则、`signal/style` 历史回放命令及严格模式系统日志排障方式。
- 实现：新增 `hiveflow context daily` 命令，聚合输出 `check`、`drift`、`signal_latest`、`style_latest`，作为 Agent 的标准日常上下文输入（仅数据，不推荐）。
- 行为：严格模式下如果缺少 `signal`/`style` 历史记录会结构化失败并写系统日志，避免输出部分降级结果。
- 测试：新增 3 条 `context daily` 用例（命令可用、缺失历史失败、完整上下文成功）；`tests/test_signal_cli.py` `14 passed`，回归集合 `106 passed`。
- 实现：`context daily` 新增 `--envelope` 与 `--json-schema`，统一接入全局 JSON 契约（schema + envelope）。
- 测试：新增 schema/envelope 用例通过；`tests/test_signal_cli.py` 更新为 `16 passed`，回归集合保持 `106 passed`。
- 实现：`context daily` 增加新鲜度严格模式（`--strict-source latest|fresh` + `--max-age-hours`）；当最新 `signal/style` 快照超过阈值时返回 `E_PIPELINE_ABORTED_STRICT` 并写系统日志。
- 测试：新增 stale/fresh 两条用例；`tests/test_signal_cli.py` 更新为 `18 passed`，回归集合保持 `106 passed`。
- 实现：`context daily` 增加 `source_meta`，输出每个来源组件的 `record_id/as_of/age_hours` 与当前 `strict_source/max_age_hours`，增强 Agent 可追溯判断。
- 测试：为 `source_meta` 增加成功路径断言（普通 JSON、envelope、fresh 模式）并通过；回归集合保持 `106 passed`。
- 实现：按“系统出数据、Agent做分析”边界收口，`check`、`risk-analysis assets/portfolio`、`context daily` JSON 输出新增 `decision_boundary` 元信息（`system=data_only`、`agent=analysis_and_decision`）。
- 实现：CLI 与文档关键措辞统一为“风险数据输出”，避免“系统做风险分析/推荐”的歧义表达。
- 文档：新增边界词汇表 `docs/context/BOUNDARY_GLOSSARY.md`；新增改造执行计划 `docs/superpowers/plans/2026-03-20-risk-data-boundary-refactor.md`。
- 测试：新增 decision_boundary 断言并通过；`tests/test_cli_check.py + tests/test_risk_analysis_cli.py + tests/test_signal_cli.py` 共 `38 passed`，回归集合 `102 passed`。
- 实现：Signal Phase 2 起步，`context daily` 增加交易窗口分组输出 `windows.w24/w7/w30`，每窗口包含 `check/drift/signal/style/source_meta`；并在窗口内实时重跑 `style backtest-rank`。
- 测试：更新 `context daily` 成功路径断言（窗口结构 + 三窗口独立 run_id）并通过；`tests/test_signal_cli.py` `18 passed`，回归集合 `122 passed`。
- 实现：Signal Phase 2.1 增加窗口级严格策略 `--strict-window all|partial`，并新增 `summary` 字段（`latency_ms`、成功/失败窗口计数、`window_failures`）。
- 行为：`all` 模式保持严格失败；`partial` 模式允许部分窗口失败并返回可用窗口结果。
- 测试：新增 `strict-window` 两条用例（partial 成功 + all 失败）并通过；`tests/test_signal_cli.py` 更新为 `20 passed`。
- 实现：Signal Phase 2.2 增加 `window_diff`（`signal_diff/style_diff/risk_diff/consensus_score`），用于多窗口分歧检测与一致性量化。
- 测试：新增 `window_diff` 成功路径断言并通过；`tests/test_signal_cli.py` 保持 `20 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.3 增加 `context daily --windows`，支持按逗号传入自定义交易窗口（如 `12,24`），默认值仍为 `24,7,30`。
- 行为：`--windows` 仅接受正整数；重复窗口自动去重并按输入顺序保留；与 `--strict-window all|partial`、`window_diff` 逻辑兼容。
- 测试：新增 `test_context_daily_supports_custom_windows` 并通过；`tests/test_signal_cli.py` 更新为 `21 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.4 增加窗口请求审计字段，`context daily` 在 `summary` 回传 `windows_requested/window_count_requested`；`strict-window=all` 失败详情同步回传请求窗口范围。
- 测试：扩展 `test_context_daily_supports_custom_windows` 断言审计字段并通过；`tests/test_signal_cli.py` 保持 `21 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.5 将 `--windows` 解析校验前置到 `context daily` 命令入口，确保参数非法时优先返回参数错误，不被“缺少快照”分支遮蔽。
- 行为：`--windows` 非法值（空字符串、`0`、非数字、空片段）统一返回 exit code 2。
- 测试：新增 `test_context_daily_rejects_invalid_windows_option` 参数化用例（4 例）并通过；`tests/test_signal_cli.py` 更新为 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.6 增加窗口键审计字段，`context daily summary` 回传 `window_keys_success/window_keys_failed`，`strict-window=all` 失败详情新增 `window_keys_failed`。
- 测试：扩展 `strict-window partial/all` 与自定义窗口成功用例断言窗口键列表并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.7 增加 `window_status_map`，在 `context daily summary` 提供窗口状态直出映射（`wxx -> ok/failed`）；`strict-window=all` 失败详情同步输出该映射。
- 测试：扩展窗口成功/失败场景断言 `window_status_map` 并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.8 增加窗口执行总计数字段，`summary` 新增 `window_count_total_computed`；`strict-window=all` 失败详情新增 `window_count_success/window_count_failed/window_count_total_computed`。
- 测试：扩展窗口计数断言并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.9 抽取窗口审计聚合 helper（`_build_window_audit_summary`），复用到 `context daily summary` 与 `strict-window=all` 失败详情，减少重复统计逻辑。
- 测试：扩展窗口计数一致性断言（`window_count_total_computed == window_count_requested`）并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.10 补齐 `window_status_map` 的失败窗口状态，严格失败场景下该映射覆盖全部请求窗口。
- 测试：更新 `strict-window=all` 用例断言（包含失败窗口键）并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.11 新增 `is_window_audit_consistent` 字段（summary + strict fail details），用于直接表达窗口审计一致性。
- 测试：扩展窗口场景断言 `is_window_audit_consistent` 并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.12 新增 `window_audit` 子对象（summary + strict fail details），将窗口审计字段结构化输出，同时保留原平铺字段。
- 测试：扩展窗口场景断言 `window_audit` 并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 实现：Signal Phase 2.13 为 `window_audit` 增加 `window_audit_schema_version`（当前 `v1`），用于审计契约版本管理。
- 测试：扩展窗口场景断言 `window_audit_schema_version` 并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 文档：Signal Phase 2.14 新增 `docs/context/WINDOW_AUDIT_CONTRACT.md`，明确 `window_audit` 的字段语义、版本规则（`v1`）与成功/失败示例。
- 文档：`docs/cli/README.md` 与 `docs/context/SIGNAL_ACCEPTANCE_CHECKLIST.md` 已同步引用该契约，并更新信号模块测试基线为 `25/122`。
- 决策：选择“先立新里程碑再开发”，启动 M11 规划，不继续无规划增量开发。
- 文档：新增 `docs/superpowers/plans/2026-03-20-m11-signal-contractization-plan.md`，定义目标、边界、Phase A/B/C 与验收标准。
- 文档：`ROADMAP` 新增 M11（规划中）段落，`CURRENT_STATE` 的“下一步建议”已切换为 M11 执行顺序。
- 决策：M10 需求整体砍掉，不进入实现排期；`ROADMAP` 已同步标记为“已取消”。
- 文档：新增信号模块一页验收清单 `docs/context/SIGNAL_ACCEPTANCE_CHECKLIST.md`，用于版本验收与回归核对。
