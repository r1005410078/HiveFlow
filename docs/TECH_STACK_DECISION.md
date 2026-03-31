# HiveFlow 技术选型决议（System Python + CLI Rust）

> 文档目标：明确当前技术选型、边界、复评条件与退出机制。适用对象：架构设计、平台工程、AI/Agent 开发。
> 状态：Accepted
> 生效日期：2026-03-31

## 1. 结论（Decision）

1. 系统端（Quant Core）采用 **Python**。
2. CLI 客户端采用 **Rust**。
3. 两者通过稳定的 CLI/JSON 契约协作，统一输出遵循 `CLI_OUTPUT_SCHEMA.json`。

## 2. 适用范围（Scope）

- Python 负责：L0~L8 与 G1~G3 相关的研究、回测、风控、治理、复盘逻辑。
- Rust 负责：CLI 命令入口、参数校验、命令路由、错误码规范、稳定 JSON 输出。
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

## 4. 设计边界（Architecture Boundary）

- Rust CLI 不承载策略逻辑，不重复实现 Quant Core 核心计算。
- Python 系统不暴露“随意调用”的非审计入口，CLI 是统一入口。
- 输出契约稳定优先：先保证 schema 与错误码向后兼容，再扩展功能。

## 5. 工程约束（Implementation Constraints）

- 所有 CLI 子命令必须声明：输入参数、错误码、输出 schema 版本。
- 变更输出字段时：
  1. 先更新 `CLI_OUTPUT_SCHEMA.json`
  2. 更新 `CLI_OUTPUT_EXAMPLES.md`
  3. 通过 `make validate-cli-output`
- AI 相关约束保持不变：
  - `web_search` -> `advice_only=true`, `decision_weight=0`
  - 涉及实盘状态变更必须走 G3 审批

## 6. 复评机制（Review Triggers）

出现以下任一条件，必须触发技术选型复评：

1. 关键路径性能连续 3 个版本不达标，且定位为 Python 运行时瓶颈。
2. CLI 稳定性指标持续不达标（例如解析失败率、崩溃率异常）。
3. 团队维护成本显著上升（双语言协作效率明显下降）。
4. 新监管/审计要求导致当前技术路径无法满足合规要求。

## 7. 退出条件（Exit Criteria）

若未来要调整选型（例如系统端迁移或 CLI 改语言），必须同时满足：

1. 有量化收益或稳定性证据，不以“偏好”驱动。
2. 有兼容迁移方案（含回滚路径）。
3. 有审计连续性方案（历史 `run_id/data_manifest` 可追溯）。
4. 完成至少一轮灰度验证并通过上线闸门。

## 8. 当前执行建议（Now）

1. 保持 Quant Core 在 Python 快速迭代。
2. Rust CLI 优先实现：
- 白名单命令路由
- 输入参数强校验
- 统一错误码
- `CLI_OUTPUT_SCHEMA.json` 输出契约
3. 将 `make validate-cli-output` 纳入 CI 必过项。

## 9. 一句话原则

**Python 负责策略与研究速度，Rust 负责接口与执行边界稳定性。**
