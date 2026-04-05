# 设计：POST /v1/market-data/bars-bundle（多周期一次读库）

**日期**：2026-04-05  
**状态**：与实现对齐的追溯说明；契约以路由与单测为准。  
**关联**：`hf tui` 按需加载、[`BarsQueryService`](quant/src/application/market_data/bars_query_service.py)、现有 `GET /v1/market-data/bars`。

## 1. 目标

- 对同一批 `symbols`、同一日期窗，**单次**从存储读取细粒度（`1m`）行，再按请求的多个 `timeframes` 分别聚合，避免 N 次读库。
- 供 CLI `hf tui` 在**换标后一次拉齐**当前 UI 阶梯所需的全部周期。

## 2. 首期不包含

- 请求体中的 `session_date`（分时会话日）与 `cursor_*` 游标分页；与当前 TUI 未传 `session_date` 一致。
- 后续若扩展，须升 `schema_version` 并补契约测试。

## 3. HTTP 契约

### 3.1 `POST /v1/market-data/bars-bundle`

**请求 JSON**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `symbols` | `string[]` | 非空 | 例如 `[选中标的, 基准]` |
| `timeframes` | `string[]` | 非空 | 如 `1m`,`1d`,`1w`,`1M`,`1y` |
| `start_date` | `string?` | `YYYY-MM-DD` | 与 `GET /bars` 一致 |
| `end_date` | `string?` | `YYYY-MM-DD` | 与 `GET /bars` 一致 |
| `limit_per_timeframe` | `int` | 默认 5000，1–10000 | **每个** timeframe 分别截断 |

**响应 JSON**

| 字段 | 说明 |
|------|------|
| `schema_version` | 固定 `1.0.0`（破坏性变更时升主版本） |
| `generated_at` | ISO-8601 UTC |
| `producer_version` | 实现标识字符串 |
| `by_timeframe` | 映射 `timeframe -> { "items": BarRow[], "has_more": bool }` |

`items` 中每行字段与 `GET /v1/market-data/bars` 的 `items` 元素一致（含 `timeframe`）。

### 3.2 错误

与 `GET /bars` 类似：`422` + `detail.code`，例如 `TIMEFRAME_FINER_THAN_STORAGE`、`TIMEFRAME_NOT_IMPLEMENTED`。

## 4. 分层

- **路由**：仅解析 DTO、调用 application、返回 dict。
- **application**：`BarsQueryService.query_bundle` 内一次 `list_storage_bars`，按 symbol 分组排序后对每个 `timeframe` 调用 `aggregate_storage_rows`（与单周期查询同语义）。
