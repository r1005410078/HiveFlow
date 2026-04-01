# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Session Startup

每次新会话必须按顺序读取以下文件，再开始开发：

1. `docs/context/PROJECT_CONTEXT.md` — 项目定位与原则
2. `docs/context/ROADMAP.md` — 里程碑与后续计划
3. `docs/context/CURRENT_STATE.md` — 当前实现进度
4. `docs/context/SESSION_LOG.md` — 最近会话结论（只看最新日期段）

## Commands

```bash
# 安装依赖
uv sync
uv sync --extra dev   # 含测试依赖

# 运行所有测试
uv run python -m pytest -q

# 运行单个测试文件
uv run python -m pytest tests/test_cli.py -q

# 按关键词过滤测试
uv run python -m pytest -k rebalance -q

# Lint
uv run ruff check .

# 运行 CLI
uv run hiveflow --help
```

## Architecture

Clean Architecture 四层结构：

```
CLI (src/hiveflow/cli.py)                ← typer，所有命令入口
    ↓
Application (src/hiveflow/application/)  ← 用例逻辑（~27 个模块）
    ├── policy/      ← 门控规则（rebalance_policy, strategy_switch_policy）
    ├── evaluation/  ← 策略健康度评估（strategy_evaluation）
    └── execution/   ← 执行计划生成（execution_planner）
    ↓
Domain (src/hiveflow/domain/)            ← 实体、仓储接口、聚合、值对象
    ↓
Infrastructure (src/hiveflow/infrastructure/)  ← SQLModel 仓储实现、OKX 接入
Services (src/hiveflow/services/)        ← 引擎类（backtest/allocation/rebalance/risk）
    └── strategies/  ← 8 种量化策略（EqualWeight/Momentum/MeanReversion/MovingAverageCross/
                        BollingerBand/RiskParity/MaxSharpe/MinVariance）
```

**数据库**：SQLite，默认路径 `data/hiveflow.db`，由 `src/hiveflow/db.py` 管理，启动时自动建表。配置见 `src/hiveflow/config.py`（Pydantic Settings）。支持 SQLite 轻量迁移（自动补列）。

**核心领域实体**（均为 SQLModel + `table=True`）：
- `Strategy` / `StrategySlot` — 策略与席位（攻击/防守/长期）
- `Position` / `TargetAllocation` / `RiskSignal` — 持仓、目标配置、风险信号
- `BacktestResult` / `MarketBar` / `DecisionLog` — 回测（含 `equity_curve` JSON）、行情、决策日志
- `StrategyRun` / `BlendConfig` — 量化策略运行记录、多策略混合配置
- `PortfolioSnapshot` — 实盘持仓快照（用于实盘 vs 回测对比）
- `SignalSnapshot` / `StyleBacktestResult` — 信号快照与风格回测结果（含可复现元数据）
- `SystemLog` — 全局错误协议日志（严格模式失败时落库）

**主要命令组**：
- `positions` / `risk` / `strategies` / `slots` / `current` / `targets` / `rebalance` / `logs`
- `backtest` — 含 `quant-run`（动态再平衡回测）、`show`（权益曲线 Sparkline + 风险指标）、`compare`
- `risk-analysis` — `assets`（波动率/MDD/相关性矩阵）、`portfolio`（Calmar ratio/胜率）
- `market-data` — 行情全链路（template/validate/import/list/summary）
- `trade execute` — OKX 现货市价单（含余额预检与确认流程）
- `quant` — `list/run/history` + `blend create/run/list/show`（多策略加权混合）
- `perf` — `snapshot/list/compare/setup-cron`（实盘绩效追踪与 cron 配置）
- `signal` — `snapshot/history/show`（信号快照落库与回放）
- `style` — `backtest-rank/history/show`（风格回测排名）
- `context` — `daily`（聚合全量上下文）、`decision`（轻量决策层上下文，Agent 快速消费入口）
- `policy` — `rebalance-check`、`strategy-switch-check`（规则门控）
- `evaluation` — `strategy-health`（策略健康度）
- `execution` — `plan`（执行计划生成）
- `skills list / install` — Skills 纳入版本控制，软链接安装到 `~/.agents/skills/`
- `summary` / `doctor` / `init-demo`

**CLI 输出**：支持 rich 表格、JSON（含 `--envelope` 模式与 `--json-schema`）、主题切换（hacker/minimal）。所有 JSON 输出含 `decision_boundary`（`system=data_only, agent=analysis_and_decision`）。

**配置模板**：`config/target-templates.json` 驱动目标配置生成（支持版本快照与回滚）。

**Skills**：`skills/` 目录纳入版本控制，包含 `hiveflow-daily-check`、`hiveflow-portfolio-advisor`、`hiveflow-strategy-selector`、`hiveflow-rebalance-executor`。

## Development Rules

- **TDD**：所有新能力先补测试，再实现。
- **系统边界**：HiveFlow 只做确定性工具与数据输出，投资判断放到 Skills；严格模式下缺失即失败，不输出降级结果作为决策上下文。
- **文档维护**：
  - 产品决策变化 → 更新 `PROJECT_CONTEXT.md`
  - 实现进度变化 → 更新 `CURRENT_STATE.md`
  - 每次会话结束 → 向 `SESSION_LOG.md` 追加记录（日期 + 决策 + 结果）
- **不提交**本地数据文件（`data/`、本地 CSV 样例）。

## Git Commit Convention

提交信息统一用中文，格式：`类型: 简述`

推荐类型：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`

示例：`feat: 增加当前策略设置命令`
