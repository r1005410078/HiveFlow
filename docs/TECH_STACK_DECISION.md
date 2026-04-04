# HiveFlow 技术选型决议（System Python + CLI Rust）

> 文档目标：明确当前技术选型、边界、复评条件与退出机制。适用对象：架构设计、平台工程、AI/Agent 开发。
> 状态：Accepted
> 生效日期：2026-03-31

## 1. 结论（Decision）

1. 系统端（Quant Core）采用 **Python**。
2. CLI 客户端采用 **Rust**。
3. 两者通过稳定的 **HTTP/JSON** 契约协作，已纳入统一 envelope 管理的 CLI 输出遵循 `CLI_OUTPUT_SCHEMA.json`（命令覆盖范围以当前实现与文档说明为准）。

## 2. 适用范围（Scope）

- Python 负责：L0~L8 与 G1~G3 相关的研究、回测、风控、治理、复盘逻辑。
- Rust 负责：CLI 命令入口、参数校验、命令路由、HTTP 客户端调用、错误码规范、稳定 JSON 输出。
- AI/Skills 只通过 CLI 交互，不直接连接系统内部核心服务。

## 3. 选择理由（Rationale）

### 3.1 System 选 Python

- 量化研发效率高：数据处理、回测、建模生态成熟。
- AI 协同友好：研究迭代、实验治理、诊断分析工具链完整。
- 与当前团队知识结构和目标（先验证再上线）匹配。

### 3.2 CLI 选 Rust

- 强类型 + 编译期约束：更适合做严谨的命令接口层。
- 二进制分发友好：部署、版本管理和回滚成本低。
- 错误处理与并发能力强：适合做稳定的命令编排与运行时保护。

### 3.3 Python 生态具体选型意向

**数据处理**

| 库 | 用途 | 选型理由 |
|----|------|----------|
| `pandas` | L1 数据清洗、宽表/长表操作、时间序列对齐 | 生态最成熟，与多数数据源 SDK 原生兼容 |
| `polars` | 大规模因子矩阵批量计算（L2/L3） | 惰性执行 + 列式内存，单机性能优于 pandas 5–10x；与 pandas 并存，不强制全量迁移 |
| `numpy` | 数值计算底层 | 不可替代的基础层 |
| `scipy` | 统计检验（IC 显著性、分布拟合）、简单优化 | 标准库，无额外维护成本 |

**组合优化**

| 库 | 用途 | 选型理由 |
|----|------|----------|
| `cvxpy` | L4 组合优化主求解器 | 声明式建模，支持凸/混整问题，求解器后端可替换（OSQP / ECOS / Clarabel）|
| `OSQP`（via cvxpy） | 默认 QP 求解器后端 | 开源、无 license 风险、冷启动快 |

回测/验证框架选自研（不引入 backtrader/zipline/qlib 等），原因：
- 第三方框架 PIT 纪律难以保证；
- 自研便于与 G1 数据治理层（`data_manifest`）直接集成；
- 避免框架版本升级破坏可复现性。

**代码质量与测试**

| 工具 | 用途 |
|------|------|
| `pytest` | 单元 + 集成测试 |
| `ruff` | Lint + 格式化（替代 flake8/black/isort） |
| `uv` | 依赖管理与虚拟环境（替代 pip/poetry） |

**依赖固定原则**：`uv.lock` 提交到仓库，保证跨机器、跨时间可复现。

### 3.4 Rust 生态具体选型意向

| Crate | 用途 | 选型理由 |
|-------|------|----------|
| `clap`（derive 模式） | CLI 参数解析 | 编译期生成 `--help`，参数类型安全 |
| `serde` + `serde_json` | JSON 序列化/反序列化 | 与 `CLI_OUTPUT_SCHEMA.json` 契约对齐，编译期 schema 绑定 |
| `anyhow` | 应用层错误传播 | 减少样板，便于快速原型 |
| `thiserror` | 域错误类型定义 | 为错误码枚举（`DATA_NOT_READY` 等）提供结构化错误 |
| `tokio`（按需引入） | 异步运行时（仅并发子命令调度时） | 当前阶段优先同步实现，异步为可选扩展 |

**版本固定原则**：`Cargo.lock` 提交到仓库；发布版本用 `cargo build --release`，dev 版本用 `cargo build`。

## 4. 数据持久化选型（Data Persistence）

### 4.1 选型决策

| 数据类型 | 存储方案 | 理由 |
|----------|----------|------|
| 行情原始归档 | Parquet（按日期分区） | 列式存储，压缩比高，适合归档回放 |
| 行情查询与增量索引 | PostgreSQL + Timescale | 支持时序查询、增量 checkpoint、在线检索 |
| `data_manifest` / `run_id` 索引 | NDJSON 文件（append-only） | 简单、可 git 跟踪、无 schema 迁移问题 |
| `decision_log` | NDJSON 文件（append-only + 哈希链） | 见 `AI_SKILLS_INTEGRATION.md` 完整性要求 |
| CLI 输出 / 告警事件 (`alert`) | JSON 文件（按 `run_id` 命名） | 与 `CLI_OUTPUT_SCHEMA.json` 契约对齐，机器可校验 |
| 参数/配置版本 | YAML / TOML（纳入 git 版本管理） | 与代码版本一一对应，满足"先验证再上线"原则 |

**当前确认引入数据库服务**（PostgreSQL + Timescale）：
- Parquet 负责归档，Timescale 负责在线查询与增量同步索引；
- 满足 `hf data sync/query` 最近 N 天与条件过滤检索需求；
- 为后续增量同步与高级查询提供稳定基础。

### 4.2 目录结构约定（参考）

```
data/
  raw/                  # L1 原始行情（Parquet，按日期分区，不提交 git）
  factors/              # L2 因子矩阵（Parquet）
  signals/              # L3 信号矩阵（Parquet）
  manifests/            # G1 data_manifest（NDJSON）
  alerts/               # L8 告警事件（JSON，按 run_id 命名）
  decision_log.ndjson   # G3 决策历史（append-only）
db/
  migrations/           # PostgreSQL/Timescale 迁移脚本
```

---

## 5. Python–Rust 通信方案（HTTP）

### 5.1 选定方案：Rust CLI 通过 HTTP 调用 Python 服务端

```
[AI / Skill]
    │ 调用白名单 CLI
    ▼
[Rust hf CLI 进程]
    │ HTTP/JSON
    ▼
[Python quant 服务端]
    │ 应用服务编排 / 数据同步 / 查询
    ▼
[HTTP JSON 响应]
    │
    ▼
[Rust hf CLI 收集并转发]
    │
    ▼
[JSON → AI / Skill]
```

**Rust CLI 行为**：
1. 解析命令行参数（clap）。
2. 通过 HTTP 客户端请求 quant 服务端（`POST /v1/market-data/sync`、`GET /v1/market-data/sync-runs` 等）。
3. 按输出模式渲染响应；行情明细 **`hf data bars`** 为 `json|table|tui`（看图用 `tui`），`tui` 默认可叠加大盘基准（`000300.SH`），可用 `--no-benchmark` 关闭。
4. 解析响应并校验 CLI 输出契约（`CLI_OUTPUT_SCHEMA.json`）。
5. 异常时将 HTTP/业务错误映射为标准错误码并包装输出。

**备选方案（未采纳）及排除原因**：

| 方案 | 排除原因 |
|------|----------|
| CLI 子进程调用 Python | 与服务端部署形态不一致，不利于远端部署与扩展 |
| gRPC | 当前阶段引入成本高，HTTP/JSON 已满足需求 |
| PyO3（Rust 直接调用 Python C API） | 编译耦合度高，Python 版本升级影响 Rust 侧 |
| 共享内存 / 消息队列 | 运维复杂，与"单机研究"阶段不符 |
| Python 直接作为 CLI（不引入 Rust） | 分发便利性低，参数校验不够严谨 |

### 5.2 Python 服务入口约定

Python quant core 暴露 HTTP 入口（示例）：

```http
POST /v1/market-data/sync
GET  /v1/market-data/sync-runs
```

响应统一为 JSON；错误返回标准错误码与 message。

---

## 6. 设计边界（Architecture Boundary）

- Rust CLI 不承载策略逻辑，不重复实现 Quant Core 核心计算。
- Python 系统以 HTTP 服务对外，所有调用需经过契约化接口与审计。
- 输出契约稳定优先：先保证 schema 与错误码向后兼容，再扩展功能。

## 7. 工程约束（Implementation Constraints）

- 所有 CLI 子命令必须声明：输入参数、错误码、输出 schema 版本。
- 变更输出字段时：
  1. 先更新 `CLI_OUTPUT_SCHEMA.json`
  2. 更新 `CLI_OUTPUT_EXAMPLES.md`
  3. 通过 `make validate-cli-output`
- AI 相关约束保持不变：
  - `web_search` -> `advice_only=true`, `decision_weight=0`
  - 涉及实盘状态变更必须走 G3 审批
- 依赖锁定：`uv.lock` 与 `Cargo.lock` 均提交到仓库。
- Python 与 Rust 各自独立测试（`pytest` / `cargo test`），CI 两套均必须通过。

## 8. 性能预算（Performance Budget）

以下为复评触发基准，**非上线门槛**（上线门槛见 `ARCHITECTURE.md` 第 6 节）：

| 指标 | 当前参考预算 | 触发复评条件 |
|------|-------------|-------------|
| 单次 CLI 调用延迟（P95） | ≤ 2s（含 HTTP 往返） | 连续 3 个版本 P95 > 5s |
| 因子矩阵批量计算（全量 universe，单日） | ≤ 30s（单机） | 持续超 60s 且定位为运行时瓶颈 |
| CLI JSON schema 校验失败率 | 0% | 任意版本出现 > 0% |
| 回测重放时间（1 年，日频） | ≤ 5min | 超 15min 且有优化空间 |

## 9. 复评机制（Review Triggers）

出现以下任一条件，必须触发技术选型复评：

1. 关键路径性能连续 3 个版本不达标，且定位为 Python 运行时瓶颈（参考第 8 节）。
2. CLI 稳定性指标持续不达标（例如解析失败率、崩溃率异常）。
3. 团队维护成本显著上升（双语言协作效率明显下降）。
4. 新监管/审计要求导致当前技术路径无法满足合规要求。

## 10. 退出条件（Exit Criteria）

若未来要调整选型（例如系统端迁移或 CLI 改语言），必须同时满足：

1. 有量化收益或稳定性证据，不以”偏好”驱动。
2. 有兼容迁移方案（含回滚路径）。
3. 有审计连续性方案（历史 `run_id/data_manifest` 可追溯）。
4. 完成至少一轮灰度验证并通过上线闸门。

## 11. 当前执行建议（Now）

1. 保持 Quant Core 在 Python 快速迭代；优先用 pandas，性能瓶颈处按需引入 polars。
2. Rust CLI 优先实现：
   - 白名单命令路由（clap derive）
   - 输入参数强校验
   - 统一错误码（thiserror 枚举）
   - `CLI_OUTPUT_SCHEMA.json` 输出契约（serde_json）
   - 调用 quant HTTP 服务并透传标准 JSON
3. 将 `make validate-cli-output` 纳入 CI 必过项。
4. 持久化采用 “Parquet 归档 + PostgreSQL/Timescale 查询索引” 双层策略。

## 12. 一句话原则

**Python 负责策略与研究速度，Rust 负责接口与执行边界稳定性。**
