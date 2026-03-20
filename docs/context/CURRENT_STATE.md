# CURRENT_STATE

## 当前时间点

- 日期：2026-03-20
- 当前分支：`main`

## 已完成阶段（按计划文档）

- Chunk 1 ~ Chunk 30 已落地
- M5 全部六个能力已交付
- M6 量化策略管理系统已交付
- 最近完成重点：
  - `market-data template / validate / import / list / summary` 行情全链路
  - `backtest run / list` 含从 DB 读行情、`weights_snapshot` 落库
  - `targets set-from-backtest` 从回测配比直接写入目标
  - `trade execute` OKX 现货市价单执行（含余额预检、确认流程）
  - `positions list` 区分自由持仓与网格持仓（含 inst_type：SPOT/SWAP）
  - `skills list / install` Skills 纳入版本控制，软链接安装到 `~/.agents/skills/`
  - `hiveflow-daily-check` + `hiveflow-portfolio-advisor` Skills 已迁移到 `skills/`
  - `quant list / run / history` 内置 8 种量化策略，结果落库，支持 `--apply`
  - `backtest quant-run` 量化策略动态再平衡回测（每隔 N 天重新计算权重，backtest_type=dynamic）
  - **M7：`backtest show <id>` + `backtest compare <id1> <id2> ...`** 回测权益曲线可视化（Unicode Sparkline），equity_curve 字段落库，支持旧记录降级提示与 `--output json`
  - **M8：风险数据引擎** `risk-analysis assets`（资产年化波动率、日波动率、历史 MDD、相关性矩阵）+ `risk-analysis portfolio <id>`（组合年化波动率、胜率、Calmar ratio）；`backtest show` 追加风险指标节
  - **M9：多策略混合 + 实盘绩效追踪** `quant blend create/run/list/show`（BlendConfig 实体 + 自动/手动权重优化，--apply 写入 TargetAllocation）+ `perf snapshot/list/compare/setup-cron`（PortfolioSnapshot 落库、权益曲线 Sparkline 对比、cron 配置）

## 当前可用命令（核心）

- `hiveflow positions ...`
- `hiveflow risk ...`
- `hiveflow strategies ...`
- `hiveflow slots ...`
- `hiveflow current ...`
- `hiveflow targets ...`
- `hiveflow rebalance preview ...`
- `hiveflow logs ...`
- `hiveflow backtest ...`（含 `quant-run` 动态回测、`show` 权益曲线 + 风险指标、`compare` 多回测对比）
- `hiveflow risk-analysis assets [--symbols] [--output]`
- `hiveflow risk-analysis portfolio <id> [--output]`
- `hiveflow market-data ...`
- `hiveflow trade execute`
- `hiveflow quant list / run / history`
- `hiveflow quant blend create / run / list / show`
- `hiveflow perf snapshot / list / compare / setup-cron`
- `hiveflow skills list / install`
- `hiveflow summary`
- `hiveflow doctor`
- `hiveflow init-demo`

## 当前状态说明

- 全量测试最近结果：`280 passed`
- `skills/` 目录已纳入版本控制，`~/.agents/skills/hiveflow-*` 为软链接
- 本地存在未跟踪数据文件：`data/`、`strategies.csv`、`prices.csv`（不应提交）
- 本次增量：`positions drift` 与 `check` 已忽略 `market_value <= 0.01 USDT` 的极小持仓，避免噪声仓位干扰结果
- 本次验证：`uv run pytest tests/test_health_check.py tests/test_cli.py -q`（`72 passed`）、`uv run pytest tests/test_cli_check.py -q`（`4 passed`）
- 方案冻结：完成 `Signal System` 重型扩展 Phase 1 设计定稿（严格模式、全局错误码、两层信号分层、关键层参数寻优网格、风格回测排名契约），详见 `docs/superpowers/specs/2026-03-20-signal-system-heavy-expansion-design.md`
- 当前阶段：Phase 1 实现中（已完成 Step 1 + Step 2）
- 本次实现进展（Phase 1 / Step 1）：已落地 `signal` 与 `style` 命令骨架、全局错误协议、系统日志表与日志写入；严格模式失败返回结构化错误并落库。新增测试 `tests/test_signal_cli.py`，并通过 `uv run pytest tests/test_signal_cli.py -q`、`uv run pytest tests/test_cli.py -q`、`uv run pytest tests/test_cli_check.py -q`
- 本次实现进展（Phase 1 / Step 2）：`signal snapshot` 与 `signal trend/risk/confirm/regime/quality` 已支持真实信号计算并输出统一 JSON（24 信号 + `category_metrics` + `conflict_matrix`）；`style backtest-rank` 已联动 `backtest quant-run` 批量执行 4 风格回测并输出 `rank_table`（仅指标排名，不含推荐字段）
- 本次验证：`uv run pytest tests/test_signal_cli.py -q`（`7 passed`）、`uv run pytest tests/test_cli.py tests/test_cli_check.py tests/test_dynamic_backtest.py tests/test_quant_cli.py -q`（`86 passed`）
- 本次实现进展（Phase 1 / Step 3）：新增 `SignalSnapshot` 与 `StyleBacktestResult` 持久化，`signal snapshot` / `style backtest-rank` 执行成功后自动落库；新增 `signal history/show` 与 `style history/show` 历史回放命令（支持 `--output json`）
- 本次验证：`uv run pytest tests/test_signal_cli.py -q`（`11 passed`）、`uv run pytest tests/test_cli.py tests/test_cli_check.py tests/test_dynamic_backtest.py tests/test_quant_cli.py tests/test_positions_list_grid.py tests/test_perf_cli.py tests/test_blend_cli.py -q`（`106 passed`）
- 本次实现进展（Phase 1 / Step 4）：补齐可复现元数据字段；`signal snapshot` 输出新增 `feature_set_version/style_preset_version/symbols_hash/params_hash/code_version`，`style backtest-rank` 输出新增 `run_id/objective/constraints/search_method/candidates_count/valid_candidates_count/best_candidate` 等报告字段
- 本次验证：`uv run pytest tests/test_signal_cli.py -q`（`11 passed`）、`uv run pytest tests/test_cli.py tests/test_cli_check.py tests/test_dynamic_backtest.py tests/test_quant_cli.py tests/test_positions_list_grid.py tests/test_perf_cli.py tests/test_blend_cli.py -q`（`106 passed`）
- 本次实现进展（Phase 1 / Step 4.1）：`signal show` / `style show` 历史回放补齐元数据与报告字段，保证“实时输出”和“历史回放”契约一致；并新增 SQLite 轻量迁移自动补列（兼容旧库）。
- 本次验证：`uv run pytest tests/test_signal_cli.py::test_signal_snapshot_history_and_show_json tests/test_signal_cli.py::test_style_backtest_rank_history_and_show_json -q`（`2 passed`），`uv run pytest tests/test_signal_cli.py -q`（`11 passed`），回归 `106 passed`。
- 文档收口：`docs/cli/README.md` 场景二已更新为当前真实流程（`sync/check/drift/signal snapshot`、`<=0.01 USDT` 极小持仓忽略、`signal/style` history/show、严格模式系统日志查询）。
- 本次实现进展（Phase 1 / Step 5）：新增 `context daily` 聚合命令（`hiveflow context daily`），一次性输出 `check + drift + signal_latest + style_latest` 的结构化上下文，保持“系统只输出数据，不做推荐”。
- 行为：严格模式下若缺少 `signal` 或 `style` 历史记录即失败并返回结构化错误对象（含 `trace_id`），同时写入系统日志。
- 本次验证：新增用例覆盖命令可用性、缺失历史失败、完整上下文成功；`uv run pytest tests/test_signal_cli.py -q`（`14 passed`），回归集合 `106 passed`。
- 本次实现进展（Phase 1 / Step 5.1）：`context daily` 补齐统一 JSON 契约能力，支持 `--envelope` 与 `--json-schema`，与现有主命令输出协议保持一致。
- 本次验证：新增 `context daily` schema/envelope 测试并通过；`uv run pytest tests/test_signal_cli.py -q`（`16 passed`），回归集合 `106 passed`。
- 本次实现进展（Phase 1 / Step 5.2）：`context daily` 新增来源严格模式参数 `--strict-source latest|fresh` 与 `--max-age-hours`；`fresh` 模式会校验最新 signal/style 快照时效，超阈值即严格失败并返回结构化错误。
- 本次验证：新增 stale/fresh 用例并通过；`uv run pytest tests/test_signal_cli.py -q`（`18 passed`），回归集合 `106 passed`。
- 本次实现进展（Phase 1 / Step 5.3）：`context daily` 新增 `source_meta` 输出，明确给出 `signal_latest/style_latest` 的 `record_id`、`as_of`、`age_hours` 以及当前 `strict_source/max_age_hours`。
- 本次验证：`source_meta` 相关断言已覆盖（普通 JSON + envelope + fresh 模式），`tests/test_signal_cli.py` 保持 `18 passed`，回归集合 `106 passed`。
- 本次实现进展（边界收口）：`check`、`risk-analysis assets`、`risk-analysis portfolio`、`context daily` 的 JSON 输出新增 `decision_boundary`（`system=data_only`，`agent=analysis_and_decision`），明确系统只输出数据、Agent负责分析决策。
- 本次实现进展（文案统一）：CLI 与文档关键文案统一为“风险数据输出”，避免“系统做风险分析/推荐”的歧义。
- 本次验证：`uv run pytest tests/test_cli_check.py tests/test_risk_analysis_cli.py tests/test_signal_cli.py -q`（`38 passed`），`uv run pytest tests/test_cli.py tests/test_dynamic_backtest.py tests/test_quant_cli.py tests/test_positions_list_grid.py tests/test_perf_cli.py tests/test_blend_cli.py -q`（`102 passed`）。
- 本次实现进展（Signal Phase 2 起步）：`context daily` 新增按交易窗口分组输出 `windows.w24/w7/w30`，每个窗口包含 `check/drift/signal/style/source_meta`；`style` 在各窗口下实时重跑并返回独立 `run_id`。
- 本次验证：`uv run pytest tests/test_signal_cli.py -q`（`18 passed`），`uv run pytest tests/test_cli_check.py tests/test_risk_analysis_cli.py tests/test_cli.py tests/test_dynamic_backtest.py tests/test_quant_cli.py tests/test_positions_list_grid.py tests/test_perf_cli.py tests/test_blend_cli.py -q`（`122 passed`）。
- 本次实现进展（Signal Phase 2.1）：`context daily` 新增 `--strict-window all|partial`。`all` 模式下任一窗口失败即严格失败；`partial` 模式下返回成功并在 `summary.window_failures` 标注失败窗口。新增 `summary`（`latency_ms/window_count_success/window_count_failed/window_failures`）。
- 本次验证：新增窗口失败策略测试通过，`uv run pytest tests/test_signal_cli.py -q`（`20 passed`），回归集合保持 `122 passed`。
- 本次实现进展（Signal Phase 2.2）：`context daily` 新增 `window_diff` 聚合层，输出 `signal_diff/style_diff/risk_diff` 与 `consensus_score`，用于表达多窗口一致性与冲突强度。
- 本次验证：`window_diff` 结构断言已覆盖并通过；`tests/test_signal_cli.py` 保持 `20 passed`，回归集合 `122 passed`。
- 本次实现进展（Signal Phase 2.3）：`context daily` 新增 `--windows` 参数，支持自定义窗口分组（如 `12,24`），并复用既有 `strict-window` 与 `window_diff` 逻辑。
- 本次验证：新增自定义窗口用例通过；`uv run pytest tests/test_signal_cli.py -q`（`21 passed`），回归集合保持 `122 passed`。
- 本次实现进展（Signal Phase 2.4）：`context daily.summary` 新增 `windows_requested/window_count_requested`，失败详情也回传请求窗口范围，增强窗口执行审计可追溯性。
- 本次验证：定向与整组信号用例通过；回归集合保持 `122 passed`。
- 本次实现进展（Signal Phase 2.5）：`--windows` 参数校验前置到 `context daily` 入口，非法窗口配置（如 `0`、非数字、空片段）会优先返回参数错误（exit code 2）。
- 本次验证：新增参数非法值参数化测试（4 例）并通过；`tests/test_signal_cli.py` 更新为 `25 passed`，回归集合保持 `122 passed`。
- 本次实现进展（Signal Phase 2.6）：`context daily.summary` 新增 `window_keys_success/window_keys_failed`，严格失败详情新增 `window_keys_failed`，降低 Agent 侧窗口结果解析成本。
- 本次验证：新增窗口键列表断言并通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 本次实现进展（Signal Phase 2.7）：新增 `summary.window_status_map`（窗口键到状态的直接映射），并在 `strict-window=all` 失败详情同步输出 `window_status_map`。
- 本次验证：扩展窗口场景断言后通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。
- 本次实现进展（Signal Phase 2.8）：新增 `window_count_total_computed`，并在严格失败详情补齐 `window_count_success/window_count_failed/window_count_total_computed`，支持请求数与执行数对账。
- 本次验证：扩展窗口计数断言后通过；`tests/test_signal_cli.py` 保持 `25 passed`，回归集合保持 `122 passed`。

## 下一步建议

1. 信号模块进入“维护模式”：仅做缺陷修复与契约稳定性增强
2. 如需新能力，先形成新里程碑需求文档，再进入实现
