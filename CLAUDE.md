# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 分支说明

`master` 是架构重构分支（当前）。完整历史实现（CLI、测试、domain/application/infrastructure/services 各层）在 `main` 分支，实现阶段开发指导请读 `main` 分支的 `CLAUDE.md`。

## 核心架构文档

开始工作前必须阅读：

1. `docs/ARCHITECTURE.md` — 量化系统目标架构（L0–L8 + G1–G3 横切层）、设计原则、层间契约、上线闸门与反馈闭环。
2. `docs/AI_SKILLS_INTEGRATION.md` — AI/CLI 解耦契约：AI 可调用什么、不可调用什么、Skill 设计规范、CLI 输出 schema、G3 审批流。
3. `docs/TECH_STACK_DECISION.md` — 技术选型决议：Python（Quant Core L0–L8）+ Rust（CLI 入口），两者通过 CLI/JSON 契约协作。

## 架构概览

### 系统分层

```
L0 标的池 → L1 数据 → L2 因子 → L3 信号工程
    → L4 组合优化 → L5 风险门控 → L5.5 预交易模拟
    → L6 执行 → L8 监控复盘

横切层：
  G1 数据治理（PIT、版本、血缘）
  G2 实验治理（假设、参数版本、结果追踪）
  G3 执行安全（审批流、应急停机、操作审计）
  L7 回测/验证（贯穿 L0–L6）
```

### 技术边界

- **Python**：L0–L8 与 G1–G3 的研究、回测、风控、治理、复盘逻辑。
- **Rust CLI**：命令入口、参数校验、命令路由、错误码规范、稳定 JSON 输出。
- AI/Skills 只通过 CLI 交互，不直连系统内部服务。

### 核心设计原则

- **先可复现，再追收益**：任何结果必须能用同版本代码 + 数据重算。
- **先安全，再自动化**：执行自动化以风险门控通过为前提。
- **先契约，再扩展**：先定义层间 I/O schema，再实现。
- **先验证，再上线**：无验证报告的策略/参数变更不得上实盘。

### AI 边界

- AI 以**独立进程**运行，只能通过 Skills 调用白名单 CLI 命令。
- AI 不得直接访问数据库、消息队列或交易网关，不得调用实盘下单或风控阈值变更。
- AI 可调用：`hf signal snapshot`、`hf factor health`、`hf factor correlation`、`hf backtest run`、`hf backtest summary`、`hf monitor snapshot`、`hf monitor risk-events`、`hf attribution summary`、`hf attribution diff-live-vs-backtest`、`hf universe snapshot`、`hf validate walk-forward`、`hf propose constraint-tuning`、`hf propose factor-retire`。
- `web_search` 固定为情报分支：`advice_only=true`、`decision_weight=0`，不入主决策公式。

## 常用命令

```bash
# ── Python Quant Core（uv 管理）──────────────────────────
uv sync
uv sync --extra dev      # 含测试依赖

uv run python -m pytest -q
uv run python -m pytest tests/test_cli.py -q   # 单个文件
uv run python -m pytest -k rebalance -q        # 按关键词过滤

uv run ruff check .

# ── Rust CLI（cli/ 目录）─────────────────────────────────
make build-cli                                 # dev 构建
make build-cli-release                         # release 构建
make test-cli                                  # 运行 Rust 测试

# 直接运行（dev 构建后）
./cli/target/debug/hf --help
./cli/target/debug/hf signal snapshot --as-of 2026-01-01 --run-id run_001
./cli/target/debug/hf factor health --factor momentum

# ── CLI 输出校验（CI 必过项）────────────────────────────
make validate-cli-output                       # 批量校验所有 fixtures
make validate-cli-output-one FILE=path/to.json # 校验单个文件
./scripts/validate_cli_output.sh <file.json>   # 直接调脚本
```

## CLI 输出契约

所有命令输出统一 JSON 包装，机器校验标准见 `docs/CLI_OUTPUT_SCHEMA.json`，样例见 `docs/CLI_OUTPUT_EXAMPLES.md`，Fixture 位于 `tests/fixtures/cli_output/{valid,invalid}/`。

```json
{
  "schema_version": "1.0.0",
  "command": "hf <subcommand>",
  "run_id": "<唯一 ID>",
  "status": "ok|warning|error",
  "generated_at": "<ISO-8601>",
  "source": "system|news_system|web_search",
  "advice_only": false,
  "decision_weight": 1,
  "data": {},
  "warnings": [],
  "errors": []
}
```

`source` 语义约束（由 schema 机器校验）：
- `system` / `news_system`：`advice_only=false`，`decision_weight=1`
- `web_search`：`advice_only=true`，`decision_weight=0`

变更输出字段必须按序：①更新 `CLI_OUTPUT_SCHEMA.json` → ②更新 `CLI_OUTPUT_EXAMPLES.md` → ③通过 `make validate-cli-output`。

## 开发规范

- **TDD**：先补测试，再实现。
- **层间契约优先**：新增层之前先定义 `schema_version`、`generated_at`、`producer_version` 字段。破坏性变更必须升主版本号，并保留至少一个兼容窗口。
- **禁止前视数据**：任何训练/回测样本只能使用 `effective_timestamp <= as_of` 的特征。
- **G3 闸门**：参数变更、阈值变更、实盘发布必须走审批流——AI 提出的变更不得自动生效。
- **审计可追溯**：每次 Skill 运行、每个 proposal、每个实盘操作，必须能追溯到数据版本 + 代码版本 + 操作人身份。
- **不提交**：本地数据文件（`data/`）、本地 CSV 样例、API Key。

## Git 提交规范

中文提交信息，格式：`type: 描述`
类型：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`
