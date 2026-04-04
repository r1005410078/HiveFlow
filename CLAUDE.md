# CLAUDE.md

本文件为 Claude Code（claude.ai/code）专属指引，仅包含 Claude Code CLI 特有内容。

架构规范、分层约束、开发规范、项目上下文、Superpowers 工作流，统一见 **[AGENTS.md](./AGENTS.md)**。

---

## 分支说明

`master` 是架构重构分支（当前）。完整历史实现（CLI、测试、domain/application/infrastructure/services 各层）在 `main` 分支，实现阶段开发指导请读 `main` 分支的 `CLAUDE.md`。

## 核心架构文档

开始工作前必须阅读：

1. `docs/ARCHITECTURE.md` — 量化系统目标架构（L0–L8 + G1–G3 横切层）、设计原则、层间契约、上线闸门与反馈闭环。
2. `docs/AI_SKILLS_INTEGRATION.md` — AI/CLI 解耦契约：AI 可调用什么、不可调用什么、Skill 设计规范、CLI 输出 schema、G3 审批流。
3. `docs/TECH_STACK_DECISION.md` — 技术选型决议：Python（Quant Core L0–L8）+ Rust（CLI 入口），两者通过 CLI/JSON 契约协作。

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
./cli/target/debug/hf pipeline daily --as-of 2026-01-01

# L3 信号快照（需服务端；完整说明见 `hf signal snapshot --help`）
./cli/target/debug/hf signal snapshot --as-of 2026-04-01
./cli/target/debug/hf signal snapshot --as-of 2026-04-01 --output table
cargo run -p hf-cli -- signal snapshot --as-of 2026-04-01 --output json

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
make restart-run-server                        # 结束 HF_PORT（默认 8000）监听进程后启动 run-server
make run-server-dev                            # 带热重载启动（uvicorn --reload）
make run-pipeline AS_OF=2026-04-01            # 运行日频 pipeline（需服务端已启动）

# ── CLI task / data query / data bars ───────────────────
# task list：--output json|table，同步任务元数据；别名 task sync-runs
cargo run -- task list --days 7 --output table
# task progress：运行中进度；别名 task status；--watch 轮询至终态
cargo run -- task progress
cargo run -- task progress --run-id <run_id> --watch
# data query：近窗 K 线，--output json|tui|table（默认 tui 分页）
cargo run -- data query --days 7 --symbols 600519.SH --output tui
# data bars：--output json|table|chart|tui（显式区间）
cargo run -- data bars --symbols 600519.SH --timeframe 1d --start-date 2026-03-01 --end-date 2026-04-01 --output tui
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
