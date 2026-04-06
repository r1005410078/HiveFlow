# AGENTS.md

本文件是 HiveFlow 所有 agent 的权威规范与上下文。修改代码前必须先阅读并遵守。

**Superpowers**：本仓库使用 Superpowers 技能辅助开发，详见 §8。

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
- **人工确认**：AI 提出的参数/阈值变更不得自动生效，须人工确认。
- **审计可追溯**：操作须能追溯到数据版本 + 代码版本。
- **不提交**：本地数据文件（`data/`）、本地 CSV 样例、API Key。

## 5. 代码评审检查项（强约束）

- 是否违反分层依赖方向
- 是否在 `interfaces/http` 写了业务逻辑
- 是否引入了框架耦合到 `application/domain`
- 是否在 `cli/src/cmd` 直接调用 `infrastructure`
- 是否在 `cli/src/domain` 引入外部 IO/网络依赖
- 是否补充了对应契约或架构测试
- 影响契约/API 的新功能是否有设计 spec（见 §8.2）

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
make db-clear-l1                               # 清空 L1 行情相关表（破坏性，仅联调重跑同步）

# CLI 命令示例
cd cli && cargo run -- pipeline compare --start-date YYYY-MM-DD --end-date YYYY-MM-DD --top-n 5 --output table
cd cli && cargo run -- factor replay --start-date YYYY-MM-DD --end-date YYYY-MM-DD --factors momentum_20,inv_volatility_20 --output json
cd cli && cargo run -- monitor health-report --as-of YYYY-MM-DD --output table
```

### 7.5 本地联调最小路径

1. `make db-init-env`（如需要） + `make db-up`
2. `make run-server`
3. 准备 `~/.hiveflow/config.toml`：`server_url = "http://127.0.0.1:8000"` / `timeout_ms = 10000` / `retry = 1`
4. `make run-pipeline AS_OF=2026-04-01`  
5. 首次联调 DB 相关能力时执行 `make db-migrate`（应用 `quant/db/migrations/*.sql`）

### 7.6 主要 HTTP 接口

- `POST /api/v1/pipeline/daily`：日频管线触发
- `POST /api/v1/pipeline/compare`：版本对比回放（`l2-score-v1` vs `l2-score-v1.1`）
- `POST /api/v1/factor-optimization/evaluate`：因子评估与权重建议（advice-only）
- `POST /v1/market-data/sync`：行情同步（异步 202 + 轮询，或无 DB 同步 200）
- `GET /v1/market-data/sync-runs/{run_id}`：单任务详情（含 progress/phase）
- `POST /v1/market-data/sync-runs/{run_id}/cancel`：协作式取消
- `POST /v1/market-data/sync-runs/{run_id}/retry-failed`：仅补拉失败标的
- `POST /v1/market-data/universes/sync`：标的池同步（异步 202）
- `POST /v1/market-data/universes/symbol-names/sync`：仅合并 `symbol_names.json`（默认 csi300+zz500+all_a；CLI：`hf data symbol-names-sync`）
- `GET /v1/market-data/sync-runs`：同步任务列表（CLI：`hf task list`，别名 `hf task sync-runs`）
- `GET /v1/market-data/sync-runs/{run_id}`：单任务详情含进度（CLI：`hf task progress`，别名 `hf task status`）
- `GET /v1/market-data/bars`：行情 K 线查询
- `POST /v1/market-data/bars-bundle`：同一批标的、同一日期窗单次读库 1m，再按多个 `timeframes` 分别聚合；响应 `schema_version` + `by_timeframe`（`hf tui` 按需多周期）
- `POST /api/v1/signal/snapshot`：L3 信号快照
- `POST /api/v1/signal/evaluate`：L3 信号质量评估（IC + 漂移检测，需 DB）
- `POST /api/v1/portfolio/optimize`：L4 组合优化（均值-方差 QP，含换手成本惩罚）
- `POST /api/v1/risk/check`：L5 风险门控（CLI：`hf risk check`）
- `POST /api/v1/pretrade/check`：L5.5 预交易冲击与可成交性估算（CLI：`hf pretrade check`，两跳经 L4 取权重）
- `POST /api/v1/execution/plan`：L6 执行计划（订单生成，CLI：`hf execution plan`，三跳经 L4→L5.5）
- `POST /api/v1/experiment/config/snapshot`：G2 参数快照写入（CLI：`hf config snapshot`）
- `GET /api/v1/experiment/configs`：G2 快照列表（CLI：`hf config list`）
- `GET /api/v1/experiment/configs/{config_id}`：G2 快照明细（CLI：`hf config get`）
- `POST /v1/walk-forward/run`：L7 walk-forward 回测（CLI：`hf walk-forward run`）
- `GET /v1/monitor/health-report`：L8 因子/信号/风控健康报告（CLI：`hf monitor health-report`）
- `GET /v1/system/doctor`：系统只读自检聚合（DB / sync_runs / positions，CLI：`hf doctor` 在 OpenAPI 探测成功后拉取并写入 `data.quant`）

### 7.7 当前健康状态

- `make check`：通过（Python tests 与 CLI fixtures、Rust tests 以本机最新 `make check` 输出为准）
- 已知非阻塞警告：CLI 存在少量 `dead_code` 警告（`retry` 字段、部分合同类型未使用），不影响门禁。

### 7.8 各层完成度（2026-04-06）

> **维护说明**：每次完成一个层/阶段，更新此表的状态与说明。个人/单机自用场景下，**不设**下文「非目标」清单中的默认路线图；主干以缺陷修复与契约/小改进为主。

#### 个人/单机自用：已从路线图移除的事项（非目标，不限期）

以下能力**不作为**本仓库默认可交付待办；历史 spec/plan 中若曾出现 Phase 2/审批/血缘等表述，以本节为准**冻结**范围。若将来改为主干或机构向目标，须**另开** spec/plan 再纳入。

- **L6**：OKX/券商 **API 自动下单**（系统内真实执行通道）。
- **L8**：健康报告之外的 **增强监控**（如响应里预留的 `trend` 等字段的填充与产品化）。
- **G1**：**版本血缘**等产品级数据治理补全（现有 PIT 与 `run_id`/快照可复跑即够用）。
- **G2**：**配置驱动**（从 DB 读 active 配置替代硬编码常量）；Phase 1 快照审计保留。
- **G3**：**审批流**等产品化执行安全（`advice_only`/`decision_weight` 框架保留；个人依赖人工确认与自行风控）。
- **L7**：在已有 compare / factor replay / walk-forward **接入**之上，继续 **平台化加深**（不作为默认里程碑）。

| 层 | 名称 | 状态 | 说明 |
|---|---|---|---|
| L0 | 标的池 | ✅ Phase 2 完成 | Phase 1: A 股 universe，静态快照；Phase 2: 精选 28 只（new_energy/robotics/semiconductor/pcb/power/power_grid 6 行业）+ industry_map.json 集中管理 + 非交易日守卫（daily pipeline 跳过非交易日） |
| L1 | 数据层 | ✅ Phase 2 完成 | Phase 1: TimescaleDB + bars 同步，180 天窗口；Phase 2: 异步作业（202+轮询）、协作式取消（cancel）、标的失败队列+自动重试+审计表、retry-failed 补拉、进度追踪（current_symbol/done/pending）、孤儿 run 收口 |
| L2 | 因子层 | ✅ Phase 2 完成 | 6 因子，per-factor 独立版本（FactorMeta TypedDict）、rows 含 direction/unit/missing_strategy/source、真实基准计算（000300.SH）、per-factor stability_metrics（coverage_rate/drift 检测）、FactorValue domain model 对齐、Pydantic schema 同步（FactorStabilityMetric） |
| L3 | 信号工程 | ✅ Phase 2b 完成 | Phase 1: winsorize+zscore+等权 composite、signal_matrix、snapshot CLI；Phase 2a: Rank IC（per-factor+composite）、信号分布漂移检测、`POST /api/v1/signal/evaluate` + `hf signal evaluate`；Phase 2b: 横截面中位数缺失值填补 + 行业哑变量 OLS 中性化框架（守卫：单行业单标的时透传） |
| L4 | 组合优化 | ✅ Phase 1 完成 | 均值-方差 QP（cvxpy CLARABEL）+ 换手成本惩罚 + 单标的/行业约束；`POST /api/v1/portfolio/optimize` + `hf portfolio optimize`；daily pipeline 接入（data.portfolio 字段） |
| L5 | 风险门控 | ✅ Phase 1 完成 | 三态市场状态机（normal/warning/crisis，基于 000300.SH 年化波动率，降级等权组合，兜底 normal）+ 四项硬约束检查（portfolio_vol/single_asset_max/industry_max/turnover，全态执行）；`POST /api/v1/risk/check` + `hf risk check`（两跳：先调 L4 取权重，再调 L5）；daily pipeline 接入（data.risk_gate 字段，L5 block 不阻断 pipeline） |
| L5.5 | 预交易模拟 | ✅ Phase 1 完成 | 平方根冲击模型（η=0.1）+ 参与度≤10% ADV 可成交性；`POST /api/v1/pretrade/check` + `hf pretrade check`（两跳 L4→L5.5，名义 1e6 CNY）；`run_daily` 写入 `data.pretrade`；bar 不可用降级 ADV/σ + `PRETRADE_USING_FALLBACK_ADV` |
| L6 | 执行 | ✅ Phase 1 完成 | 平方根冲击 + 持仓表（positions）+ limit 日单生成（quantity/limit_price/action/open_close）；`POST /api/v1/execution/plan` + `hf execution plan`（三跳 L4→L5.5→L6，名义 1e6 CNY）；`run_daily` 替换 `execution_plan.orders=[]`；bar 不可用降级 null 价格 + `EXECUTION_USING_NO_PRICE`；DB migration `0005_positions.sql` |
| L7 | 回测/验证 | ✅ 已接入 | `pipeline compare`、`factor replay`；`POST /v1/walk-forward/run` + `hf walk-forward run`。不设「验证平台化」默认待办（见上非目标） |
| L8 | 监控复盘 | ✅ Phase 1 完成 | `GET /v1/monitor/health-report` + `hf monitor health-report`：基于 `run_daily` 聚合 green/yellow/red（个人场景范围至此） |
| G1 | 数据治理 | ✅ 个人范围够用 | PIT 约束已实现；`run_id` 与快照支持复现审计。不设「版本血缘产品线」默认待办（见上非目标） |
| G2 | 实验治理 | ✅ Phase 1 完成 | `experiment_configs` 表 + `run_daily` 开头快照 + `POST/GET /api/v1/experiment/config*` + `hf config snapshot|list|get`（纯审计） |
| G3 | 执行安全 | ✅ 框架完成 | `advice_only`/`decision_weight` 契约字段已建；个人场景以人工确认为准，不设审批流实现任务（见上非目标） |

**当前工作位置**：主干维护（缺陷修复、契约一致、小改进）；**无**默认「下一阶段」路线图。机构/自动化执行等需求须单独立项与 spec。

### 7.9 已交付能力摘要

- **L1/L2 主链路**：factor_snapshot（6 因子，per-factor 版本/方向/单位/来源标记）+ l2_decision（score_version、top_candidates、score_breakdown、factor_availability）+ stability_metrics（coverage_rate、drift_flag、drift_z_score）
- **数据韧性**：优先真实 bars + 真实基准（000300.SH），异常降级 deterministic 快照，低可用率告警 `FACTOR_AVAILABILITY_LOW`；source 字段区分 real/deterministic_fallback/benchmark_proxy_fallback
- **Compare 回放**：`POST /api/v1/pipeline/compare` + `hf pipeline compare`，逐日 daily_items + summary
- **Factor 优化建议**：`POST /api/v1/factor-optimization/evaluate` + `hf factor optimize`，含 correlation_analysis、report、g3_checklist，固定 advice_only
- **Factor 回放**：`hf factor replay`，summary + daily_items，区分 fetch_status/release_gate_status
- **CLI 可读性**：`--output table` 中文标题，top 候选最多 5 条
- **L3 信号**：`signal_matrix`（coverage_rate、transform_stats）；`hf signal snapshot --as-of ... [--output json|table]`；信号评估 `hf signal evaluate --start-date ... --end-date ... [--forward-days N] [--output json|table]`（Rank IC + drift diagnostics）；详见 `--help` 与 `docs/CLI_OUTPUT_EXAMPLES.md`
- **L4 组合优化**：`POST /api/v1/portfolio/optimize` + `hf portfolio optimize --as-of DATE [--output json|table]`；均值-方差 QP（cvxpy CLARABEL）；目标函数含 alpha、风险惩罚（协方差矩阵）、换手成本惩罚；单标的上限 30%、行业上限 40%；首次运行等权 fallback；daily pipeline 自动调用（data.portfolio 字段）
- **L5.5 预交易**：`POST /api/v1/pretrade/check` + `hf pretrade check --as-of DATE [--output json|table]`（默认 table）；`run_daily` 的 `data.pretrade`；详见 `docs/CLI_OUTPUT_EXAMPLES.md` 与 `docs/superpowers/specs/2026-04-06-l5.5-pretrade-simulation-design.md`
- **L6 执行计划**：`POST /api/v1/execution/plan` + `hf execution plan --as-of DATE [--output json|table]`（默认 table，三跳 L4→L5.5→L6）；`run_daily` 替换 `data.execution_plan`；positions 表持仓快照；action=open_long/add_long/reduce_long/close_long；limit 日单，slippage_bp=5，A 股 100 股/手取整；详见 `docs/superpowers/specs/2026-04-06-l6-execution-plan-design.md`
- **G2 参数快照（Phase 1）**：`experiment_configs` 表（`make db-migrate`）；`run_daily` 开头 `snapshot_current(note="daily_run")`；`POST /api/v1/experiment/config/snapshot` + `GET /api/v1/experiment/configs` + `GET /api/v1/experiment/configs/{config_id}`；`hf config snapshot|list|get`；无 DB 时 `EXPERIMENT_CONFIG_NO_DB` warning；详见 `docs/superpowers/specs/2026-04-06-g2-experiment-governance-phase1-design.md`
- **L8 健康报告**：`GET /v1/monitor/health-report?as_of=DATE` + `hf monitor health-report --as-of DATE [--output json|table]`；消费 `run_daily` 的 L2~L5 输出聚合 factor/signal/risk 健康度与总评；详见 `docs/CLI_OUTPUT_EXAMPLES.md` 与 `docs/superpowers/specs/2026-04-06-l8-monitor-health-report-design.md`
- **L1 异步同步**：`hf data sync` 提交→202→**默认** stderr 提示 + stdout JSON（含 run_id）；**`hf task progress`**（别名 `hf task status`）查看运行中进度，**`--watch`** 轮询至终态（与 **`--wait`** 同类）；任务列表 **`hf task list`**（别名 `hf task sync-runs`）；取消/重试 **`hf task cancel` / `hf task retry-failed`**（与 `hf data sync-cancel`、`hf data sync-retry-failed` 等价）；近窗 K 线 **`hf data query`** → `GET /v1/market-data/bars`（默认 TUI 分页）；失败队列自动重试（MAX_SYMBOL_ATTEMPTS=3）+ 审计表 `sync_run_symbol_failures`；startup 孤儿 run 收口为 `interrupted`；Provider 无行返回且无异常时 run 可为 **`success` + `error_code: NO_DATA_RETURNED`**；`sync_runs.effective_symbols_count` finalize 写库 + 读取 **enrich** 与 `progress` 一致；本地仅清 L1 表 **`make db-clear-l1`**（破坏性）

## 8. Superpowers 开发流程

本仓库使用 Superpowers 技能辅助 AI agent 开发。以下是开发流程说明。

### 8.1 流程总览

| 技能名 | 触发时机 | 说明 |
|---|---|---|
| `brainstorming` | 新功能、方案未定、需要探索设计空间 | 探索用户意图、需求与设计方案，**必须在写代码之前** |
| `writing-plans` | 有 spec/需求，需要拆解为多步骤实现 | 生成分步实现计划，含关键文件、依赖关系、检查点 |
| `executing-plans` | 已有书面计划，开始实现 | 按计划分步执行，含 review checkpoint |
| `systematic-debugging` | 遇到 bug、测试失败、行为异常 | 先定位根因再修复，**禁止跳过诊断直接改代码** |
| `test-driven-development` | 实现功能或修复 bug | 先写测试再写实现 |
| `verification-before-completion` | 即将宣称完成/修好/通过 | 必须运行验证命令并确认输出，**证据先于断言** |
| `subagent-driven-development` | 计划中有 2+ 独立任务可并行 | 派发子 agent 并行执行无依赖任务 |
| `dispatching-parallel-agents` | 同上，侧重并行调度 | 当多个任务无共享状态或顺序依赖时使用 |
| `using-git-worktrees` | 跨多文件/多层较大改动需隔离 | 在 `.worktrees/` 建隔离工作区，避免污染当前分支 |
| `finishing-a-development-branch` | 实现完成、测试通过、准备合并 | 引导选择 merge/PR/cleanup 路径 |
| `requesting-code-review` | 完成任务或重大功能、合并前 | 验证工作是否满足需求 |
| `receiving-code-review` | 收到 code review 反馈 | 技术验证反馈，非盲从实现 |
| `writing-skills` | 创建/编辑 Superpowers 技能 | 确保技能格式正确、可部署 |
| `simplify` | 代码变更后 | 审查变更代码的复用、质量、效率 |

### 8.2 标准工作流

典型的功能开发全流程：

```
用户需求
  │
  ▼
brainstorming          ← 探索需求、确认方案
  │
  ▼
writing-plans          ← 拆解为分步计划
  │
  ▼
[设计 spec]            ← 影响契约/API 时写 spec（见 §8.4）
  │
  ▼
executing-plans        ← 按计划分步实现
  │  ├─ test-driven-development  ← 每步先测试后实现
  │  └─ subagent-driven-development  ← 独立任务并行
  │
  ▼
verification-before-completion  ← make check 必须通过
  │
  ▼
finishing-a-development-branch  ← merge / PR / cleanup
```

简单修复（单文件 bug fix、typo）可跳过 brainstorming/writing-plans，但 `verification-before-completion` 不可跳过。

### 8.3 场景速查

| 场景 | 流程 |
|---|---|
| 新功能 / 方案未定 | `brainstorming` → `writing-plans` → `executing-plans` → `verification` |
| 缺陷 / 测试失败 | `systematic-debugging` → 定位根因 → `test-driven-development` → `verification` |
| 多步骤实现（已有计划） | `executing-plans` → `verification` |
| 宣称完成前 | `verification-before-completion`（`make check` 门禁必须通过） |
| 大型跨层改动 | `using-git-worktrees` → 隔离工作区中执行上述流程 |
| 完成后合并 | `finishing-a-development-branch` |

### 8.4 设计文档

影响契约/存储/对外 API 的**新功能**，建议先写设计 spec 到 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`，经确认后再编码。

### 8.5 Git worktree

跨多文件/多层的较大改动，建议在 `.worktrees/` 下建立隔离工作区。单文件修复或用户明确要求在当前 workspace 操作时不需要。

### 8.6 关键纪律

- **技能检查先于一切行动**：收到任务后先判断是否有适用技能，哪怕只有 1% 可能也应调用检查
- **brainstorming 先于实现**：任何创造性工作（新功能、新组件、行为修改）必须先 brainstorm
- **debugging 先于修复**：遇到 bug 必须先诊断，禁止"先改改看"
- **证据先于断言**：宣称"已修复/已通过"前必须有命令输出证据
- **刚性技能不可变通**：TDD、debugging、verification 是刚性流程，不因"简单"而跳过
- **柔性技能可适配**：brainstorming、writing-plans 等可根据任务复杂度调整深度
