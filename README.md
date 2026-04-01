# HiveFlow

项目文档入口：

- [docs/DOCUMENTATION_INDEX.md](docs/DOCUMENTATION_INDEX.md)
- [GETTING_STARTED.md](GETTING_STARTED.md)

## 目录结构

- `quant/src/`：Python 服务端（量化策略核心）
- `quant/tests/`：Python 测试与 fixtures
- `quant/pyproject.toml` 与 `quant/uv.lock`：Python 项目配置与锁文件
- `cli/`：Rust CLI 客户端
- `docs/`：架构与设计文档
- `scripts/`：校验脚本

## 开发验证

推荐统一使用 `Makefile`：

```bash
make check
```

或分步执行：

```bash
make test
make lint
make architecture-check
make validate-cli-output
make rust-test
```

## Agent 规范

- 所有 Agent 修改代码前必须先阅读 [AGENTS.md](AGENTS.md)
- 架构边界由 `make architecture-check` 与 CI 强制校验

运行日频命令：

```bash
make run-pipeline AS_OF=2026-04-01
```

## 运行前提

当前运行模式为：

- `quant/`：Python HTTP 服务端
- `cli/`：Rust CLI 客户端

首次本地联调前需要先准备 CLI 配置文件 `~/.hiveflow/config.toml`：

```toml
server_url = "http://127.0.0.1:8000"
timeout_ms = 10000
retry = 1
```

推荐启动顺序：

```bash
cd quant && uv run python bin/server.py
make run-pipeline AS_OF=2026-04-01
```

## 本地数据库（PostgreSQL + Timescale）

已提供 Docker Compose 基建文件，可一键启动本地 TimescaleDB。

```bash
make db-init-env
make db-up
```

常用命令：

```bash
make db-logs
make db-psql
make db-down
```

说明：

- 首次启动会自动执行 `quant/db/migrations/0001_l1_timescale.sql`
- 数据持久化在 Docker volume `timescale_data`
- 重置数据库（会清空数据）：`make db-reset-db-volume`
