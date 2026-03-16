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

# 运行 CLI（开发中）
uv run hiveflow --help
```

## Architecture

Clean Architecture 四层结构：

```
CLI (src/hiveflow/cli.py)           ← typer，所有命令入口
    ↓
Application (src/hiveflow/application/)  ← 用例逻辑，13个模块
    ↓
Domain (src/hiveflow/domain/)       ← 实体、仓储接口、聚合、值对象
    ↓
Infrastructure (src/hiveflow/infrastructure/)  ← SQLModel 仓储实现
Services (src/hiveflow/services/)   ← 引擎类（backtest/allocation/rebalance/risk）
```

**数据库**：SQLite，默认路径 `data/hiveflow.db`，由 `src/hiveflow/db.py` 管理，启动时自动建表。配置见 `src/hiveflow/config.py`（Pydantic Settings）。

**核心领域实体**（均为 SQLModel + `table=True`）：
- `Strategy` / `StrategySlot` — 策略与槽位（攻击/防守/长期）
- `Position` / `TargetAllocation` / `RiskSignal` — 持仓、目标配置、风险信号
- `BacktestResult` / `MarketBar` / `DecisionLog` — 回测、行情、决策日志

**CLI 输出**：支持 rich 表格、JSON（含 envelope 模式）、主题切换（hacker/minimal）。

**配置模板**：`config/target-templates.json` 驱动目标配置生成。

## Development Rules

- **TDD**：所有新能力先补测试，再实现。
- **文档维护**：
  - 产品决策变化 → 更新 `PROJECT_CONTEXT.md`
  - 实现进度变化 → 更新 `CURRENT_STATE.md`
  - 每次会话结束 → 向 `SESSION_LOG.md` 追加记录（日期 + 决策 + 结果）
- **不提交**本地数据文件（`data/`、本地 CSV 样例）。

## Git Commit Convention

提交信息统一用中文，格式：`类型: 简述`

推荐类型：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`

示例：`feat: 增加当前策略设置命令`
