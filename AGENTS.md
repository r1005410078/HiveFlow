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
