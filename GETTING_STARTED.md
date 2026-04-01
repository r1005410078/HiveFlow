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

### 8.2 数据同步

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

临时覆盖超时（不改配置文件）：

```bash
cargo run -- data sync --days 90 --end-date 2026-04-01 --timeout-ms 120000
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

图表输出：

```bash
cargo run -- data query --days 30 --symbols 600519.SH --output chart
```

说明：
- 图表输出包含两部分：`Compact Trend`（高可读单行趋势）和 `Close Price`（textplots 折线图）。

TUI 输出（全屏趋势图，更清晰）：

```bash
cargo run -- data query --days 30 --output tui
```

说明：
- TUI 键位：
  - `↑ / ↓`（或 `j / k`）切换左侧股票
  - `← / →`（或 `h / l`）移动图表光标，查看每个时点价格
  - `a / d` 平移可视窗口
  - `+ / -` 缩放窗口
  - `0` 重置视图
  - `q / Esc / Enter` 退出
  - 可选传 `--symbols` 来限制股票范围，或指定默认选中股票（取第一个）

查询时同样可临时覆盖超时：

```bash
cargo run -- data query --days 30 --output table --timeout-ms 120000
```

提示：

- `--output` 支持 `json|table|chart|tui`
- `--no-benchmark` 在 `chart/tui` 下关闭大盘对比线
- `--verbose` 仅在 `--output table` 下追加诊断列
- `--timeout-ms` 可覆盖 `~/.hiveflow/config.toml` 中的 `timeout_ms`
- `--timeframe` 默认是 `1m`（分钟级），可显式传 `1d` 切换日频
- `symbols` 参数使用逗号分隔（如 `600519.SH,000001.SZ`）

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
- CLI 报配置缺失：确认 `~/.hiveflow/config.toml` 已创建。
- 端口冲突：修改 `.env.db` 的 `HF_DB_PORT`，或释放占用端口。
