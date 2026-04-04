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

### 4.2 仅清空 L1 行情数据（联调重跑，破坏性）

需要**保留库与迁移**、只删掉 bars / sync 相关表做同步回归时：

```bash
make db-clear-l1
```

会 `TRUNCATE` L1 相关表（含外键顺序，见 `scripts/db_clear_l1_stock_data.sql`）。**不**替代 `make db-reset-db-volume`（整卷清空）。清表后请**重启** `make run-server`，确保加载的是当前代码。

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

### 8.2 数据同步（异步任务；默认只返回 run_id）

服务端对 `POST /v1/market-data/sync` 采用**异步执行**：先返回 `run_id`，后台拉数写库。Rust CLI **默认不轮询**：stderr 提示「任务已提交」并给出 `run_id`，stdout 打印受理 JSON（便于脚本解析）。需要在本终端**等到终态**时加 **`--wait`**，此时会轮询 `GET /v1/market-data/sync-runs/{run_id}` 直至 `success` / `failed` / `cancelled` / `interrupted` 等，再打印最终 JSON。

```bash
cargo run -- data sync --days 5 --end-date 2026-04-01
```

在本终端等待同步跑完：

```bash
cargo run -- data sync --days 5 --end-date 2026-04-01 --wait
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

- `--wait`：轮询直至终态；不加则提交后立即返回（含 `run_id`）。
- `--poll-interval-ms <毫秒>`：与 `--wait` 合用时的轮询间隔（默认约 1500）。
- **Ctrl+C**（仅在 `--wait` 时）：结束本地轮询，**不取消**服务端任务；可按提示的 `run_id` 用 **`hf task progress --run-id <run_id>`** 查看进度（或 **`hf task progress --watch`** 继续跟到终态）。

临时覆盖超时（不改配置文件）：

```bash
cargo run -- data sync --days 90 --end-date 2026-04-01 --timeout-ms 120000
```

若同维度已有运行中任务，接口返回 **409**；CLI 会提示 `run_id`，可先取消再同步：

```bash
cargo run -- data sync-cancel --run-id <run_id>
```

若某次同步**部分标的失败**，可基于该次 `run_id` 只重试失败队列（默认只提交并返回新 `run_id`；加 `--wait` 则轮询到终态）：

```bash
cargo run -- data sync-retry-failed --from-run-id <run_id>
```

在本终端等待重试任务结束：

```bash
cargo run -- data sync-retry-failed --from-run-id <run_id> --wait
```

### 8.3 同步任务列表（`hf task list`）

JSON 输出（默认，适合 AI）：

```bash
cargo run -- task list --days 7 --output json
```

表格输出（适合人工查看）：

```bash
cargo run -- task list --days 7 --output table
```

按状态筛选（可选）：

```bash
cargo run -- task list --days 7 --status success --output table
```

说明：
- `task list` 对应 `GET /v1/market-data/sync-runs`，查看**近期行情同步任务**（`run_id`、状态等），**不是** K 线。
- 别名：`hf task sync-runs`（与 `list` 等价）。

**运行中进度**（`hf task progress`，别名 `hf task status`）：默认识别近期唯一 `running` 任务并拉详情；或 **`--run-id`** 指定；**`--watch`** 在本终端轮询直至终态（与 `data sync --wait` 同类体验）。**`--output json|table`**（默认 `table`）。

```bash
cargo run -- task progress
cargo run -- task progress --run-id <run_id> --output json
cargo run -- task progress --run-id <run_id> --watch
```

### 8.3.1 按窗口查 K 线（`hf data query`）

便捷入口：在**近 N 天**窗口内查 bars（`GET /v1/market-data/bars`），支持 `--symbols` 与 `--universe`（并集）。默认 **`--output tui`** 为分页表格；脚本用 `--output json`。

```bash
cargo run -- data query --days 7 --symbols 600519.SH --output tui
cargo run -- data query --days 14 --universe self_select --timeframe 1d --output json
```

显式 `start_date`/`end_date`、交互走势图（`--output tui`）等仍用 **8.4 `data bars`**。
- `data query`：`--output json|tui|table`；`task list`：`--output json|table`，过滤参数含 `--timeframe`、`--status`、`--request-id`、`--limit`；`task progress`：`--output json|table`，另支持 `--watch`、`--poll-interval-ms`。

查询任务列表时可临时覆盖超时：

```bash
cargo run -- task list --days 30 --output table --timeout-ms 120000
```

### 8.4 K 线查询（data bars）

**中文简称**：`hf data universe-sync --universe csi300`（需 quant 服务与 akshare）会更新 `quant/config/universes/{universe}.txt`，并把代码→简称合并进 `quant/config/universes/symbol_names.json`。此后各 HTTP JSON 响应里带 `symbol`（形如 `600519.SH`）的对象会多一个 **`symbol_name_zh`** 字段（无映射时为空字符串）；`data bars` / `data query` 的 **table** 在响应含该字段时会多一列「名称」。

JSON 输出：

```bash
cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output json
```

表格输出：

```bash
cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output table
```

TUI 输出（全屏趋势图，左侧选股）：

```bash
cargo run -- data bars --symbols 600519.SH --timeframe 1d --output tui
```

提示：

- `data bars` 对应 `GET /v1/market-data/bars`。
- `tui` 模式支持键盘交互（`↑/↓`、`←/→`、`a/d`、`+/-`、`0`、`b`、`q/Esc/Enter`）；自动化/脚本请用 **`--output json`**。
- `--output` 支持 `json|table|tui`（仅 `data bars`）。
- `--no-benchmark` 在 `tui` 下关闭大盘对比线（默认基准 `000300.SH`）。
- `--verbose` 仅在 `--output table` 下追加诊断列。
- `--timeout-ms` 可覆盖 `~/.hiveflow/config.toml` 中的 `timeout_ms`
- `--timeframe` 默认是 `1m`（分钟级），可显式传 `1d` 切换日频；参数名是 **`--timeframe`**（勿拼成 `tmeframe`）。
- **分钟线数据源**（如当前 Tencent 适配）往往只返回**最近一段**可解析窗口；若 **`--end-date` 落在该窗口之外**，可能出现**无 K 线**或同步摘要带 **`NO_DATA_RETURNED`**。日频或近端 `end-date` 更易对齐。
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
- 同步提示「已有任务在跑」：使用 **`hf task cancel --run-id ...`**（或 `data sync-cancel`）或等待该 `run_id` 结束后再发 `data sync`。
- 同步终态为 **success** 但带 **`NO_DATA_RETURNED`**：Provider 未返回可写入行（常见于分钟线窗口与 **`--end-date`** 不匹配）；可改用更近的结束日、换 **日频**，或确认标的在该源上可查。
- 改了 Python 同步逻辑但行为仍像旧版：**重启** `quant` 进程后再测。
- `task list` 里 **`effective_symbols_count`** 与详情里 **`progress.total_symbols`** 应一致；若曾见历史数据不一致，升级后读取路径会 **enrich**；仍异常时核对是否连错环境或旧 run。

## 12. 场景化手册（推荐阅读）

更偏「按场景照做」的说明见 [docs/BEGINNER_QUICKSTART.md](docs/BEGINNER_QUICKSTART.md)。
