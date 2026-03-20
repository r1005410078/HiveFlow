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
  - **M8：风险分析引擎** `risk-analysis assets`（资产年化波动率、日波动率、历史 MDD、相关性矩阵）+ `risk-analysis portfolio <id>`（组合年化波动率、胜率、Calmar ratio）；`backtest show` 追加风险指标节
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

## 下一步建议

1. M10：网格机器人管理（`grid create/list/stop`，OKX Grid Trading API）
2. 多交易所支持
