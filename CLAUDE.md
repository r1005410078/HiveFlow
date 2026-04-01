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
# ── 全量 CI 门禁（test + lint + architecture-check + validate-cli-output + rust-test）──
make check

# ── Python Quant Core（uv 管理，需在 quant/ 下执行）────────
make sync                                      # 等价于 cd quant && uv sync
make test                                      # 等价于 cd quant && uv run python -m pytest -q
make lint                                      # 等价于 cd quant && uv run ruff check .
make architecture-check                        # Python + Rust 架构边界测试

# 也可直接进 quant/ 单独跑：
cd quant && uv sync --extra dev               # 含测试依赖
cd quant && uv run python -m pytest tests/test_cli.py -q   # 单个文件
cd quant && uv run python -m pytest -k rebalance -q        # 按关键词过滤

# ── Rust CLI（cli/ 目录）─────────────────────────────────
make rust-test                                 # 运行 Rust 测试
cd cli && cargo build                          # dev 构建
cd cli && cargo build --release                # release 构建

# 直接运行（dev 构建后）
./cli/target/debug/hf --help
./cli/target/debug/hf signal snapshot --as-of 2026-01-01 --run-id run_001
./cli/target/debug/hf factor health --factor momentum

# ── CLI 输出校验（CI 必过项）────────────────────────────
make validate-cli-output                       # 批量校验所有 fixtures
make validate-cli-output-one FILE=path/to.json # 校验单个文件
./scripts/validate_cli_output.sh <file.json>   # 直接调脚本

# ── 数据库（TimescaleDB via Docker）─────────────────────
make db-init-env                               # 生成 .env.db（首次必须执行）
make db-up                                     # 启动 TimescaleDB
make db-down                                   # 停止
make db-psql                                   # 进入 psql
make db-reset-db-volume                        # 清除数据卷（破坏性）

# ── 服务端与端到端联调 ───────────────────────────────────
# 前置：make db-init-env && make db-up
# 首次本地联调需先准备 ~/.hiveflow/config.toml：
#   server_url = "http://127.0.0.1:8000"
#   timeout_ms = 10000
#   retry = 1
make run-server                                # 启动 Python HTTP 服务端
make run-server-dev                            # 带热重载启动（uvicorn --reload）
make run-pipeline AS_OF=2026-04-01            # 运行日频 pipeline（需服务端已启动）

# ── CLI data query 输出模式 ─────────────────────────────
# --output json|table|chart|tui（默认 json）
cargo run -- data query --days 7 --output table
cargo run -- data query --days 30 --symbols 600519.SH --output tui
# TUI 键位：↑↓/jk 切换标的，←→/hl 移动光标，a/d 平移，+/- 缩放，0 重置，q 退出
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

## 源码分层结构

### Python（`quant/src/`）

三层结构，依赖方向只允许 `interfaces → application → domain`：

- `domain/` — 领域模型与规则，禁止依赖 `application`、`interfaces` 或任何框架
- `application/` — 用例编排，可依赖 `domain`，禁止依赖 FastAPI/HTTP 框架
- `interfaces/` — 协议与适配层（HTTP/IO），路由函数只做 DTO 解析、调用 application service、返回响应 DTO
- `hiveflow/` — 公开 API 层（`contracts/` 跨层共享契约类型，`cli/entrypoint.py` 为 Python 侧 CLI 入口）

架构边界测试位于 `quant/tests/architecture/`，新增层或跨层依赖时必须同步更新。

### Python 测试分层（`quant/tests/`）

- `unit/` — 纯单元测试，无外部依赖
- `integration/` — 需要运行中的 HTTP 服务端（`make run-server`）
- `contract/` — 校验 CLI JSON 输出 schema 契约（`test_python_cli_contract.py`）
- `architecture/` — 层间依赖边界静态检查

运行单一套件：`cd quant && uv run pytest tests/unit -q`

### Rust CLI（`cli/src/`）

五层结构，依赖约束：`cmd → application → domain`，`application → infrastructure`，禁止 `cmd → infrastructure` 和 `domain → 任何外层`：

- `cmd/` — 命令定义与参数解析（clap），不写业务流程
- `application/` — 命令编排与流程控制
- `domain/` — 命令语义模型，禁止引入外部 IO/网络依赖
- `infrastructure/` — HTTP 客户端、配置读取、外部 IO
- `contracts/` — CLI 输出类型（`cli_output.rs`）与错误码（`error_codes.rs`），跨层共享

架构边界测试位于 `cli/tests/architecture_rules.rs`，新增模块时必须同步更新。

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
