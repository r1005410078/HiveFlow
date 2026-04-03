# AGENTS.md

本文件是 HiveFlow 所有 agent 的权威规范与上下文。修改代码前必须先阅读并遵守。

Claude Code 用户另见 [CLAUDE.md](./CLAUDE.md)（仅含 Claude Code CLI 专属命令）。

---

## 1. 分层规则（强约束）

### Python（`quant/src/`）

三层结构，依赖方向只允许 `interfaces → application → domain`：

- `domain/`: 领域模型与规则，禁止依赖 `application`、`interfaces` 或任何框架
- `application/`: 用例编排，可依赖 `domain`，禁止依赖 FastAPI/HTTP 框架
- `interfaces/`: 协议与适配层（HTTP/IO），路由函数只做 DTO 解析、调用 application service、返回响应 DTO
- `hiveflow/`: 公开 API 层（`contracts/` 跨层共享契约类型，`cli/entrypoint.py` 为 Python 侧 CLI 入口）

架构边界测试位于 `quant/tests/architecture/`，新增层或跨层依赖时必须同步更新。

测试分层（`quant/tests/`）：
- `unit/` — 纯单元测试，无外部依赖
- `integration/` — 需要运行中的 HTTP 服务端（`make run-server`）
- `contract/` — 校验 CLI JSON 输出 schema 契约
- `architecture/` — 层间依赖边界静态检查

### Rust CLI（`cli/src/`）

五层结构：

- `cmd/`: 命令定义与参数解析（clap），不写业务流程
- `application/`: 命令编排与流程控制，可调用 `domain` 与 `infrastructure`
- `domain/`: 命令语义模型，禁止依赖 `cmd`、`application`、`infrastructure`
- `infrastructure/`: HTTP、配置、外部 IO
- `contracts/`: CLI 输出类型（`cli_output.rs`）与错误码（`error_codes.rs`），跨层共享

依赖方向约束：
- 允许：`cmd -> application -> domain`
- 允许：`application -> infrastructure`
- 禁止：`cmd -> infrastructure`
- 禁止：`domain -> infrastructure|cmd|application`

架构边界测试位于 `cli/tests/architecture_rules.rs`，新增模块时必须同步更新。

## 2. HTTP 层规范（强约束）

`quant/src/interfaces/http` 中：

- 路由函数只做：请求 DTO 解析 → 调用 application service → 返回响应 DTO
- 禁止在路由里写业务算法、风控规则、优化逻辑
- 依赖注入仅通过 `Depends` + provider（`dependencies.py`）完成
- `dependencies.py` 只做装配/提供者，不写业务流程

## 3. 测试与门禁（强约束）

- 新增/修改架构边界时，必须更新 `quant/tests/architecture/` 测试
- 新增/修改 Rust 架构边界时，必须更新 `cli/tests/architecture_rules.rs`
- PR 必须通过：
  - `make architecture-check`
  - `make check`

## 4. 开发规范（强约束）

- **TDD**：先补测试，再实现。
- **层间契约优先**：新增层之前先定义 `schema_version`、`generated_at`、`producer_version` 字段。破坏性变更必须升主版本号，并保留至少一个兼容窗口。
- **禁止前视数据**：任何训练/回测样本只能使用 `effective_timestamp <= as_of` 的特征。
- **G3 闸门**：参数变更、阈值变更、实盘发布必须走审批流——AI 提出的变更不得自动生效。
- **审计可追溯**：每次 Skill 运行、每个 proposal、每个实盘操作，必须能追溯到数据版本 + 代码版本 + 操作人身份。
- **不提交**：本地数据文件（`data/`）、本地 CSV 样例、API Key。

## 5. 代码评审检查项（强约束）

- 是否违反分层依赖方向
- 是否在 `interfaces/http` 写了业务逻辑
- 是否引入了框架耦合到 `application/domain`
- 是否在 `cli/src/cmd` 直接调用 `infrastructure`
- 是否在 `cli/src/domain` 引入外部 IO/网络依赖
- 是否补充了对应契约或架构测试

## 6. 约定式提交规范（强约束）

提交信息格式：`<type>: <description>`（中文描述）

允许的 `type`：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`

- 描述必须明确"改了什么"，禁止使用模糊词（如"更新一下""修复问题"）
- 一次提交尽量只包含一个逻辑主题，避免混合无关改动

## 7. 项目快速上下文（新窗口速览）

若与上文"强约束"冲突，以上文强约束为准。

### 7.1 仓库定位

- 项目名：HiveFlow — 量化策略研究与执行系统
- 形态：`quant`（Python HTTP 服务端） + `cli`（Rust 客户端）
- 调用关系：`cli` 通过 HTTP 调用 `quant`，不走本地 Python CLI 主流程
- 技术边界：Python 负责 L0–L8 研究/回测/风控逻辑；Rust CLI 负责命令入口、参数校验、稳定 JSON 输出

### 7.2 系统分层

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

AI 边界：AI 以独立进程运行，只能通过 Skills 调用白名单 CLI 命令，不得直接访问数据库、消息队列或交易网关。

### 7.3 关键目录

- `quant/src/`：服务端核心（`domain/application/interfaces`）
- `quant/tests/`：Python 单元/集成/契约/架构测试
- `cli/src/`：Rust CLI（`cmd/application/domain/infrastructure/contracts`）
- `cli/tests/`：CLI 集成与架构规则测试
- `docs/`：架构与输出合同文档（入口：`docs/DOCUMENTATION_INDEX.md`）
- `scripts/`：输出合同校验脚本

### 7.4 高频命令

```bash
make check                                     # 全量 CI 门禁
make architecture-check                        # 架构门禁
make run-server                                # 启动服务端（开发热更新：make run-server-dev）
make run-pipeline AS_OF=YYYY-MM-DD            # 运行日频管线

# CLI 命令示例
cd cli && cargo run -- pipeline compare --start-date YYYY-MM-DD --end-date YYYY-MM-DD --top-n 5 --output table
cd cli && cargo run -- factor replay --start-date YYYY-MM-DD --end-date YYYY-MM-DD --factors momentum_20,inv_volatility_20 --output json
```

### 7.5 本地联调最小路径

1. `make db-init-env`（如需要） + `make db-up`
2. `make run-server`
3. 准备 `~/.hiveflow/config.toml`：`server_url = "http://127.0.0.1:8000"` / `timeout_ms = 10000` / `retry = 1`
4. `make run-pipeline AS_OF=2026-04-01`

### 7.6 主要 HTTP 接口

- `POST /api/v1/pipeline/daily`：日频管线触发
- `POST /api/v1/pipeline/compare`：版本对比回放（`l2-score-v1` vs `l2-score-v1.1`）
- `POST /api/v1/factor-optimization/evaluate`：因子评估与权重建议（advice-only）
- `POST /v1/market-data/sync`：行情同步
- `POST /v1/market-data/universes/sync`：标的池同步（写入 `quant/config/universes/*.txt`）
- `GET /v1/market-data/sync-runs`：行情查询
- `GET /v1/market-data/bars`：行情 K 线查询

### 7.7 当前健康状态

- `make check`：通过（Python tests: 105 passed，architecture: 5 passed，CLI fixtures: pass=11 fail=0，Rust tests: 通过）
- 已知非阻塞警告：CLI 存在少量 `dead_code` 警告（`retry` 字段、部分合同类型未使用），不影响门禁。

### 7.8 各层完成度（2026-04-03）

> **维护说明**：每次完成一个层/阶段，更新此表的状态与说明，并更新"当前工作位置"。

| 层 | 名称 | 状态 | 说明 |
|---|---|---|---|
| L0 | 标的池 | ✅ Phase 1 完成 | A 股 universe，静态快照 |
| L1 | 数据层 | ✅ Phase 1 完成 | TimescaleDB + bars 同步，180 天窗口 |
| L2 | 因子层 | ✅ Phase 2 完成 | 6 因子，per-factor 独立版本（FactorMeta TypedDict）、rows 含 direction/unit/missing_strategy/source、真实基准计算（000300.SH）、per-factor stability_metrics（coverage_rate/drift 检测）、FactorValue domain model 对齐、Pydantic schema 同步（FactorStabilityMetric） |
| L3 | 信号工程 | 🔲 未开始 | **下一步** |
| L4 | 组合优化 | 🔲 未开始 | — |
| L5 | 风险门控 | 🔲 未开始 | — |
| L5.5 | 预交易模拟 | 🔲 未开始 | — |
| L6 | 执行 | 🔲 未开始 | Phase 1 orders 固定为空数组 |
| L7 | 回测/验证 | 🚧 部分完成 | compare 回放、factor replay 已完成；walk-forward 未开始 |
| L8 | 监控复盘 | 🔲 未开始 | — |
| G1 | 数据治理 | 🚧 部分完成 | PIT 约束已实现，版本血缘未完整 |
| G2 | 实验治理 | 🔲 未开始 | — |
| G3 | 执行安全 | 🚧 部分完成 | advice_only/decision_weight 框架已建，审批流未实现 |

**当前工作位置**：L2 完成 → 准备进入 L3 信号工程。

### 7.9 已交付能力摘要

- **L1/L2 主链路**：factor_snapshot（6 因子，per-factor 版本/方向/单位/来源标记）+ l2_decision（score_version、top_candidates、score_breakdown、factor_availability）+ stability_metrics（coverage_rate、drift_flag、drift_z_score）
- **数据韧性**：优先真实 bars + 真实基准（000300.SH），异常降级 deterministic 快照，低可用率告警 `FACTOR_AVAILABILITY_LOW`；source 字段区分 real/deterministic_fallback/benchmark_proxy_fallback
- **Compare 回放**：`POST /api/v1/pipeline/compare` + `hf pipeline compare`，逐日 daily_items + summary
- **Factor 优化建议**：`POST /api/v1/factor-optimization/evaluate` + `hf factor optimize`，含 correlation_analysis、report、g3_checklist，固定 advice_only
- **Factor 回放**：`hf factor replay`，summary + daily_items，区分 fetch_status/release_gate_status
- **CLI 可读性**：`--output table` 中文标题，top 候选最多 5 条

## 8. Superpowers 工作流（强约束）

本仓库默认启用 `using-superpowers`。收到任何需求后，先做技能判定，再执行代码动作。

### 8.1 执行顺序

1. 判定任务类型（功能 / 缺陷 / 仅执行已有计划）
2. 先调用流程技能（process skill），后调用实现技能（implementation skill）
3. 在回复中明确说明"当前使用的 skill 与目的"
4. 按 skill 清单逐项执行，不跳步骤

### 8.2 任务到技能映射

- 新功能、需求不完整、方案未定：先 `brainstorming` → 产出设计后 `writing-plans` → 再实现
- 缺陷、性能异常、测试失败：先 `systematic-debugging` → 找到根因再改代码
- 已有明确实现计划，直接落地：`executing-plans`
- 准备提交前：`verification-before-completion` 核验，需要时 `requesting-code-review` 收口

### 8.3 禁止事项

- 未完成技能判定就直接改代码
- 在 `systematic-debugging` 前先尝试"拍脑袋修复"
- 跳过验证就声称"已完成/已修复"
