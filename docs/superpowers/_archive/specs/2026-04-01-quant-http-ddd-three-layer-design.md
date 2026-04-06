# Quant HTTP 化与三层 DDD 重构设计

> 状态：待评审
> 日期：2026-04-01
> 适用对象：架构重构、服务化改造、CLI 联调

---

## 1. 目标

将当前本机子进程调用模式（Rust CLI -> `uv run python -m ...`）重构为服务化模式：

- `quant` 作为可部署服务端，通过 HTTP 对外提供量化编排能力。
- `cli` 作为本机客户端，通过 HTTP 调用远端 `quant` 服务。
- Python 端采用三层 DDD 目录：`domain`、`application`、`interfaces`（位于 `quant/src` 直接子目录）。
- 部署启动入口放在 `quant/bin`。

---

## 2. 目录设计（定稿）

```text
quant/
  bin/
    server.py
  src/
    domain/
    application/
    interfaces/
      http/
        app.py
        routes_daily_run.py
        schemas.py
        mapper.py
  tests/
```

说明：

- `bin/server.py`：仅负责启动服务进程，不承载业务逻辑。
- `src/domain`：纯领域规则与模型，不依赖 HTTP。
- `src/application`：用例编排层，组织跨领域流程。
- `src/interfaces/http`：HTTP 入站接口层，完成协议转换与路由。

---

## 3. 分层边界

1. `domain` 不依赖 `application/interfaces`。
2. `application` 可依赖 `domain`。
3. `interfaces` 可依赖 `application/domain`。
4. 所有 HTTP 框架细节只能出现在 `interfaces/http`。
5. `bin` 只能装配和启动，禁止业务判断。

---

## 4. HTTP API 设计（MVP）

### 4.1 接口

- Method: `POST`
- Path: `/api/v1/pipeline/daily`

### 4.2 请求

```json
{
  "as_of": "2026-04-01"
}
```

### 4.3 响应

沿用现有 CLI 契约结构（`schema_version`、`run_id`、`status`、`data`、`warnings`、`errors` 等），确保 Rust CLI 与既有 fixture 校验逻辑可继续复用。

---

## 5. Rust CLI 客户端改造

### 5.1 调用方式

从子进程调用改为 HTTP 调用：

- 旧：`python -m hiveflow.cli.entrypoint ...`
- 新：向 `quant` 服务发起 `POST /api/v1/pipeline/daily`

### 5.2 配置文件

- 路径：`~/.hiveflow/config.toml`
- 字段：

```toml
server_url = "http://127.0.0.1:8000"
timeout_ms = 10000
retry = 1
```

### 5.3 优先级

`CLI 参数 > 环境变量 > 配置文件 > 默认值`

---

## 6. 启动与运行

### 6.1 服务端

- 启动入口：`python quant/bin/server.py`
- `server.py` 内部调用 `interfaces.http.app` 的 app factory。

### 6.2 客户端

- 本机安装 `cli`，直接执行命令（如 `hf pipeline daily --as-of 2026-04-01`）。
- 默认读取 `~/.hiveflow/config.toml`，无需每次手工传 `--server-url`。

---

## 7. 测试策略

1. Python HTTP 契约测试：验证 `POST /api/v1/pipeline/daily` 响应结构与语义。
2. Rust 配置测试：验证配置文件读取与优先级。
3. Rust HTTP 集成测试：验证请求发送、超时、重试与错误映射。
4. 端到端测试：`cli -> http -> quant` 全链路。

---

## 8. 迁移约束

1. 先新增 HTTP 路由与服务端启动入口，再替换 Rust 调用链。
2. 迁移期允许保留旧 Python CLI 入口用于回归验证，最终移除。
3. 任何阶段都要保证 `make check` 可执行并可解释失败。

---

## 9. 风险与决策

### 风险

- Python 包命名空间由 `hiveflow.*` 向 `src/domain|application|interfaces` 迁移时，import 变动较大。
- 既有测试与文档路径需同步调整。

### 决策

- 按用户确认，不以“最小改动”为目标，优先 DDD 语义清晰和服务化边界清晰。
- 目录采用 `quant/src` 直接三包结构，不再保留 `quant/src/hiveflow`。

