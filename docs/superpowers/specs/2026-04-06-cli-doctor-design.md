# CLI `hf doctor` 设计说明

> 日期：2026-04-06（v2：方案 B 服务端聚合）  
> 范围：Rust CLI + Python `GET /v1/system/doctor`。

## 目标

为联调提供一键自检：

1. **本机**：`~/.hiveflow/config.toml` 是否存在且可解析。  
2. **HTTP 可达**：`GET {server_url}/openapi.json`（不依赖 DB）。  
3. **服务端聚合**（OpenAPI 成功后）：`GET /v1/system/doctor?sync_days=N` → DB 连通性、`sync_runs` 近窗摘要、`positions` 最新截面摘要。

## 行为

### 本机 + OpenAPI（与 v1 一致）

- 配置缺失/读失败/解析失败：不探测远端；`probe_skipped=true`；`quant=null`。  
- `errors`：仅配置类（`CONFIG_FILE_MISSING` / `CONFIG_READ_ERROR` / `CONFIG_PARSE_ERROR`）。  
- OpenAPI 失败：`warnings` 含 `CLI_DOCTOR_SERVER_UNREACHABLE`；`quant=null`。

### 服务端聚合

- 路由：`GET /v1/system/doctor`，`sync_days` 查询参数 **1–90**，默认 7。  
- 实现：`interfaces/http/routes_system.py` → `dependencies.get_system_doctor_envelope` → `application/system/doctor_service.run_system_doctor`。  
- 返回 **标准 CLI envelope**，`command` 为 `hf doctor`，`data` 为 **纯 quant 负载**（无本机字段）。  
- CLI 将响应的 `data` 对象写入最终输出的 **`data.quant`**。  
- 无 DB 配置或连接失败：`db.reachable=false`，`error` 为 `NO_DB_CONFIG` 或异常摘要；仍 **HTTP 200**。  
- `positions` 查询失败：`positions.error` 为字符串；CLI 可能追加 `CLI_DOCTOR_POSITIONS_QUERY_FAILED` warning。  
- 聚合 HTTP 失败或非 ok：CLI `data.quant=null`，`warnings` 含 `CLI_DOCTOR_AGGREGATE_FAILED` 等。

### 进程退出码

- `doctor` **始终**以 exit 0 结束；脚本以 envelope 的 `status` / `warnings` / `errors` 为准。

## `data` 字段（CLI 最终输出）

| 字段 | 说明 |
|------|------|
| `config_path` | 绝对路径 |
| `config_status` | `ok` \| `missing` \| `read_error` \| `parse_error` |
| `probe_skipped` | 配置无效时为 `true` |
| `server_url` / `timeout_ms` / `retry` | 来自配置；无效时为 `null` |
| `server_probe_url` | `…/openapi.json`；跳过探测时为 `null` |
| `server_reachable` | OpenAPI 返回 200 |
| `server_http_status` / `server_error` | OpenAPI 探测结果 |
| `cli_version` | `hf-cli` 版本 |
| `quant` | `null` 或服务端聚合对象（见下） |

### `data.quant`（非 null 时）

| 字段 | 说明 |
|------|------|
| `producer_version` | 如 `quant-system-doctor-v1` |
| `db` | `reachable`（bool）、`error`（string \| null） |
| `sync` | `window_days`、`runs_returned`、`by_status`、`latest`、`has_running` |
| `positions` | `snapshot_as_of`、`symbol_count`、`total_notional`、`has_positions`、`error`（string \| null） |

## 非目标

- 不做全表 bars 行数统计（避免重查询）。  
- 不替代 `hf monitor health-report`（不消费 `run_daily` 业务健康语义）。

## 相关文件

- `quant/src/application/system/doctor_service.py`  
- `quant/src/interfaces/http/routes_system.py`  
- `cli/src/application/handlers/doctor.rs`  
- `docs/CLI_OUTPUT_SCHEMA.json`（`command == "hf doctor"`）
