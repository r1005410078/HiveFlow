# HiveFlow 新手入门

这份文档给第一次接触 HiveFlow 的同学，目标是 10 分钟内跑通本地最小闭环。

## 1. 你会得到什么

- 启动本地 `PostgreSQL + TimescaleDB`
- 启动 quant HTTP 服务
- 用 Rust CLI 调用服务端命令
- 跑一遍项目校验

## 2. 前置依赖

- Python 3.11+
- `uv`
- Rust（含 `cargo`）
- Docker（含 `docker compose`）

## 3. 一次性初始化

```bash
make sync
make db-init-env
```

## 4. 启动数据库

```bash
make db-up
```

查看日志：

```bash
make db-logs
```

## 4.1 应用数据库迁移（首次或有新迁移时）

在**第一次**本地联调、或拉取代码后出现新的 `quant/db/migrations/*.sql` 时执行：

```bash
make db-migrate
```

未迁移时，行情同步等依赖表结构的接口可能报错或行为异常。

## 5. 启动 quant 服务端

```bash
make run-server
```

默认地址：`http://127.0.0.1:8000`

## 6. 配置 CLI

创建 `~/.hiveflow/config.toml`：

```toml
server_url = "http://127.0.0.1:8000"
timeout_ms = 10000
retry = 1
```

## 7. 运行一次命令

```bash
make run-pipeline AS_OF=2026-04-01
```

## 8. CLI 命令使用

CLI 二进制命令为 `hf`，在仓库内可用：

```bash
cd cli
cargo run -- --help
```

### 8.1 日频管线

```bash
cargo run -- pipeline daily --as-of 2026-04-01
```

### 8.2 数据同步（异步任务 + CLI 轮询）

服务端对 `POST /v1/market-data/sync` 采用**异步执行**：先返回 `run_id`，后台拉数写库。Rust CLI **默认会轮询** `GET /v1/market-data/sync-runs/{run_id}` 直到终态（`success` / `failed` / `cancelled` / `interrupted` 等），再打印最终 JSON。

```bash
cargo run -- data sync --days 5 --end-date 2026-04-01
```

带股票范围：

```bash
cargo run -- data sync \
  --days 5 \
  --end-date 2026-04-01 \
  --timeframe 1m \
  --symbols 600519.SH,000001.SZ
```

常用可选参数：

- `--no-wait`：只打印受理结果（含 `run_id`），不轮询；适合脚本里自行查状态。
- `--poll-interval-ms <毫秒>`：轮询间隔（默认约 1500）。
- **Ctrl+C**：结束本地轮询，**不取消**服务端任务；可按提示的 `run_id` 用 `data query` 查看进度。

临时覆盖超时（不改配置文件）：

```bash
cargo run -- data sync --days 90 --end-date 2026-04-01 --timeout-ms 120000
```

若同维度已有运行中任务，接口返回 **409**；CLI 会提示 `run_id`，可先取消再同步：

```bash
cargo run -- data sync-cancel --run-id <run_id>
```

若某次同步**部分标的失败**，可基于该次 `run_id` 只重试失败队列（默认同样轮询到终态）：

```bash
cargo run -- data sync-retry-failed --from-run-id <run_id>
```

只发起重试、不等待结束：

```bash
cargo run -- data sync-retry-failed --from-run-id <run_id> --no-wait
```

### 8.3 数据查询

JSON 输出（默认，适合 AI）：

```bash
cargo run -- data query --days 7 --output json
```

表格输出（适合人工查看）：

```bash
cargo run -- data query --days 7 --output table
```

按状态筛选（可选）：

```bash
cargo run -- data query --days 7 --status success --output table
```

说明：
- `data query` 对应 `GET /v1/market-data/sync-runs`，用于查看**近期**同步任务列表与元数据（含各次 `run_id`、状态）。
- `--output` 仅支持 `json|table`。
- 常用过滤参数：`--timeframe`、`--status`、`--request-id`、`--limit`。

查询时可临时覆盖超时：

```bash
cargo run -- data query --days 30 --output table --timeout-ms 120000
```

### 8.4 K 线查询（data bars）

JSON 输出：

```bash
cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output json
```

表格输出：

```bash
cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output table
```

图表输出（单标的）：

```bash
cargo run -- data bars --symbols 600519.SH --timeframe 1d --output chart
```

TUI 输出（全屏趋势图）：

```bash
cargo run -- data bars --symbols 600519.SH --timeframe 1d --output tui
```

提示：

- `data bars` 对应 `GET /v1/market-data/bars`。
- `chart` 模式要求 `--symbols` 只传一个股票。
- `tui` 模式支持键盘交互（`↑/↓`、`←/→`、`a/d`、`+/-`、`0`、`b`、`q/Esc/Enter`）。
- `--output` 支持 `json|table|chart|tui`（仅 `data bars`）。
- `--no-benchmark` 在 `chart/tui` 下关闭大盘对比线（默认基准 `000300.SH`）。
- `--verbose` 仅在 `--output table` 下追加诊断列。
- `--timeout-ms` 可覆盖 `~/.hiveflow/config.toml` 中的 `timeout_ms`
- `--timeframe` 默认是 `1m`（分钟级），可显式传 `1d` 切换日频
- `symbols` 参数使用逗号分隔（如 `600519.SH,000001.SZ`）

如果 TUI 看不到大盘线，通常是大盘数据尚未同步。可先执行：

```bash
cargo run -- data sync --days 5 --end-date 2026-04-01 --timeframe 1m --symbols 000300.SH
```

## 9. 项目校验

```bash
make check
```

## 10. 常用命令速查

```bash
make db-up
make db-down
make db-psql
make run-server
make run-server-dev
make rust-test
make test
```

## 11. 常见问题

- 数据库拉镜像失败：通常是网络问题，重试 `make db-up`。
- 表不存在 / 同步异常：确认已执行 `make db-migrate`（见 4.1）。
- CLI 报配置缺失：确认 `~/.hiveflow/config.toml` 已创建。
- 端口冲突：修改 `.env.db` 的 `HF_DB_PORT`，或释放占用端口。
- 同步提示「已有任务在跑」：使用 `data sync-cancel` 或等待该 `run_id` 结束后再发 `data sync`。

## 12. 场景化手册（推荐阅读）

更偏「按场景照做」的说明见 [docs/BEGINNER_QUICKSTART.md](docs/BEGINNER_QUICKSTART.md)。
