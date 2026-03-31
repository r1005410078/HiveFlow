# HiveFlow

项目文档入口：

- [docs/DOCUMENTATION_INDEX.md](docs/DOCUMENTATION_INDEX.md)

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
make validate-cli-output
make rust-test
```

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
