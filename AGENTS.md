# AGENTS.md

本文件定义 HiveFlow 的强约束架构规范。所有 agent 在修改代码前必须先阅读并遵守。

## 1. 分层规则（强约束）

`quant/src` 采用三层结构：

- `domain/`: 领域模型与规则，禁止依赖 `application`、`interfaces`
- `application/`: 用例编排，可依赖 `domain`，禁止依赖 FastAPI/HTTP 框架
- `interfaces/`: 协议与适配层（HTTP/IO），可依赖 `application`、`domain`

依赖方向只允许：

`interfaces -> application -> domain`

## 2. HTTP 层规范（强约束）

`quant/src/interfaces/http` 中：

- 路由函数只做：
  - 请求 DTO 解析
  - 调用 application service
  - 返回响应 DTO
- 禁止在路由里写业务算法、风控规则、优化逻辑
- 依赖注入仅通过 `Depends` + provider（`dependencies.py`）完成
- `dependencies.py` 只做装配/提供者，不写业务流程

## 3. Rust CLI 分层规范（强约束）

`cli/src` 采用四层结构：

- `cmd/`: 命令定义与参数解析（clap），不写业务流程
- `application/`: 命令编排与流程控制，可调用 `domain` 与 `infrastructure`
- `domain/`: 命令语义模型，禁止依赖 `cmd`、`application`、`infrastructure`
- `infrastructure/`: HTTP、配置、外部 IO

依赖方向约束：

- 允许：`cmd -> application -> domain`
- 允许：`application -> infrastructure`
- 禁止：`cmd -> infrastructure`
- 禁止：`domain -> infrastructure|cmd|application`

## 4. 测试与门禁（强约束）

- 新增/修改架构边界时，必须更新 `quant/tests/architecture/` 测试
- 新增/修改 Rust 架构边界时，必须更新 `cli/tests/architecture_rules.rs`
- PR 必须通过：
  - `make architecture-check`
  - `make check`

## 5. 代码评审检查项（强约束）

- 是否违反分层依赖方向
- 是否在 `interfaces/http` 写了业务逻辑
- 是否引入了框架耦合到 `application/domain`
- 是否在 `cli/src/cmd` 直接调用 `infrastructure`
- 是否在 `cli/src/domain` 引入外部 IO/网络依赖
- 是否补充了对应契约或架构测试

## 6. 约定式提交规范（强约束）

提交信息必须使用约定式格式：

`<type>: <description>`

允许的 `type`：

- `feat`: 新功能
- `fix`: 缺陷修复
- `refactor`: 重构（不改变对外行为）
- `test`: 测试相关
- `docs`: 文档相关
- `chore`: 构建、脚本、依赖等杂项

额外要求：

- 描述必须明确“改了什么”，禁止使用模糊词（如“更新一下”“修复问题”）
- 一次提交尽量只包含一个逻辑主题，避免混合无关改动

## 7. 项目快速上下文（新窗口速览）

本节用于让 agent 在新窗口中 1-2 分钟完成上下文恢复。若与上文“强约束”冲突，以上文强约束为准。

### 7.1 仓库定位

- 项目名：HiveFlow
- 形态：`quant`（Python HTTP 服务端） + `cli`（Rust 客户端）
- 调用关系：`cli` 通过 HTTP 调用 `quant`，不走本地 Python CLI 主流程

### 7.2 关键目录

- `quant/src/`：服务端核心（`domain/application/interfaces`）
- `quant/tests/`：Python 单元/集成/契约/架构测试
- `cli/src/`：Rust CLI（`cmd/application/domain/infrastructure`）
- `cli/tests/`：CLI 集成与架构规则测试
- `docs/`：架构与输出合同文档（入口：`docs/DOCUMENTATION_INDEX.md`）
- `scripts/`：输出合同校验脚本

### 7.3 高频命令

- 全量校验：`make check`
- 架构门禁：`make architecture-check`
- 启动服务端：`make run-server`（开发热更新：`make run-server-dev`）
- 运行日频管线：`make run-pipeline AS_OF=YYYY-MM-DD`
- 运行版本对比回放：`cd cli && cargo run -- pipeline compare --start-date YYYY-MM-DD --end-date YYYY-MM-DD --top-n 5 --output table`
- 数据库启动：`make db-up`（查看日志：`make db-logs`）

### 7.4 本地联调最小路径

1. `make db-init-env`（如需要） + `make db-up`
2. 启动 quant：`make run-server`
3. 准备 CLI 配置：`~/.hiveflow/config.toml`
4. 运行：`make run-pipeline AS_OF=2026-04-01`

CLI 最小配置示例：

```toml
server_url = "http://127.0.0.1:8000"
timeout_ms = 10000
retry = 1
```

### 7.5 主要 HTTP 接口（当前）

- `POST /api/v1/pipeline/daily`：日频管线触发
- `POST /api/v1/pipeline/compare`：版本对比回放（`l2-score-v1` vs `l2-score-v1.1`）
- `POST /api/v1/factor-optimization/evaluate`：因子评估与权重建议（advice-only，不自动生效）
- `POST /v1/market-data/sync`：行情同步
- `GET /v1/market-data/sync-runs`：行情查询（供 CLI `data query`）
- `GET /v1/market-data/bars`：行情 K 线查询（供 CLI `data bars`）

### 7.6 当前健康状态（最近一次本地检查）

- `make architecture-check`：通过
- `make check`：通过
  - Python tests：`87 passed`
  - Python architecture tests：`5 passed`
  - CLI output fixtures：`pass=8 fail=0`
  - Rust tests：通过

### 7.7 已知注意点（非阻塞）

- CLI 存在少量 `dead_code` 警告（如 `retry` 字段、部分合同类型/解析函数未使用），当前不影响门禁通过。

### 7.8 近期已交付（避免上下文丢失）

- L1/L2 日频主链路：
  - `factor_snapshot` 已升级为 6 因子：`momentum_20`、`inv_volatility_20`、`turnover_rate`、`max_drawdown_60`、`trend_stability_20`、`relative_strength_vs_index`
  - `l2_decision` 已包含：`score_version`、`top_candidates`、`score_breakdown`、`factor_availability`
  - `execution_plan.orders` 当前仍为空数组（Phase 1 仅做可解释候选输出）
- 数据韧性：
  - 因子计算优先使用真实 bars（近 180 天窗口），异常时降级 deterministic 快照
  - 增加低可用率告警：`FACTOR_AVAILABILITY_LOW`
- CLI 可读性：
  - `pipeline daily --output table` 标题和主要列使用中文
  - Top 候选展示逻辑为“最多 5 条”，实际条数由有效 universe 决定
- Compare 回放能力（本轮新增）：
  - `quant`：新增 `POST /api/v1/pipeline/compare`
  - `cli`：新增 `hf pipeline compare --start-date --end-date --top-n --output json|table`
  - compare 输出含逐日 `daily_items` 与汇总 `summary`，并统计 `top1_symbol_change_days`
- Factor 优化建议能力（本轮新增）：
  - `quant`：新增 `POST /api/v1/factor-optimization/evaluate`
  - `cli`：新增 `hf factor optimize --start-date --end-date --factors --output json|table`
  - 输出固定 `advice_only=true`、`decision_weight=0`，并携带 `analysis/recommendations/audit`
- Factor 优化 P1（统一扩展）：
  - `evaluate` 新增 `correlation_analysis`（threshold、alerts、alert_count）
  - `evaluate` 新增 `report`（matrix_10d、summary、g3_checklist）
  - CLI 支持 `--correlation-threshold`，table 输出增加“相关性告警”“10维评估摘要”

## 8. Superpowers 工作流（强约束）

本仓库默认启用 `using-superpowers`。收到任何需求后，先做技能判定，再执行代码动作。

### 8.1 执行顺序

1. 判定任务类型（功能 / 缺陷 / 仅执行已有计划）
2. 先调用流程技能（process skill），后调用实现技能（implementation skill）
3. 在回复中明确说明“当前使用的 skill 与目的”
4. 按 skill 清单逐项执行，不跳步骤

### 8.2 任务到技能映射

- 新功能、需求不完整、方案未定：
  - 先用 `brainstorming`
  - 产出设计后，用 `writing-plans`
  - 再进入实现
- 缺陷、性能异常、测试失败：
  - 先用 `systematic-debugging`
  - 找到根因后再改代码
- 已有明确实现计划，直接落地：
  - 用 `executing-plans`
- 准备提交前：
  - 用 `verification-before-completion` 做结果核验
  - 需要时用 `requesting-code-review` 做收口检查

### 8.3 禁止事项

- 未完成技能判定就直接改代码
- 在 `systematic-debugging` 前先尝试“拍脑袋修复”
- 跳过验证就声称“已完成/已修复”
