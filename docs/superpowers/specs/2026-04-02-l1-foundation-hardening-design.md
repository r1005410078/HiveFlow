# L1 Foundation Hardening Design

日期：2026-04-02

## 1. 目标

本设计用于将 HiveFlow 的 L1 数据层从“可用 MVP”补强到“可作为 L2 稳定底座”的状态，然后立即进入 L2 因子层建设。

本次只解决会直接影响 L2 稳定性的底座问题，不追求一次性补齐 L1 原始计划中的全部能力。

完成标准：

- `POST /v1/market-data/sync` 具备真实 `request_id` 幂等能力。
- 同步流程真正使用 `sync_checkpoints` 进行增量同步。
- `GET /v1/market-data/sync-runs` 只返回同步任务元数据。
- 新增独立 `GET /v1/market-data/bars` 作为 L2 的行情读取面。
- CLI 层不再混淆“同步运行记录查询”和“行情明细查询”。

## 2. 现状与问题

当前 L1 已具备以下 MVP 能力：

- HTTP 同步接口已可触发日线和分钟线同步。
- 具备 Tencent 优先、AkShare 兜底的数据源适配。
- Timescale `bars`、`sync_runs`、`sync_checkpoints` 迁移已存在。
- Rust CLI 已支持 `data sync` 与 `data query`。

当前阻碍 L2 稳定接入的问题：

1. `request_id` 只存表，没有真正的幂等命中逻辑。
2. `sync_checkpoints` 已建表，但同步流程没有真正使用。
3. `GET /v1/market-data/sync-runs` 按名称应返回运行记录，但当前实现实际返回的是 `bars` 视图。
4. CLI `data query` 的语义跟着接口漂移，容易让 L2 误把运维接口当成数据接口。

## 3. 设计原则

- 遵守仓库三层约束：`interfaces -> application -> domain`。
- L2 只能依赖“行情数据读取面”，不能依赖“同步运行记录面”。
- 运维/审计接口与数据读取接口必须分离。
- 只做最小必要改动，不在本轮扩展复杂清洗或审计归档。

## 4. 方案对比

### 方案 A：最小底座补强后进入 L2

做真实幂等、增量 checkpoint、查询语义收口、新增独立 bars 接口。

优点：

- 可以一次拉正 L1/L2 边界。
- 改动聚焦，投入可控。
- 最适合作为进入 L2 的稳定底座。

缺点：

- 需要调整 CLI 查询命令的职责边界。

### 方案 B：只修幂等和 checkpoint，保留现有 query 语义

优点：

- 变更最少，落地最快。

缺点：

- 接口语义继续模糊。
- L2 很可能依赖错误接口，后续返工风险高。

### 方案 C：补齐 L1 原计划后再进入 L2

优点：

- L1 更完整。

缺点：

- 延迟进入 L2。
- 当前许多能力不是 L2 的硬前置。

结论：选择方案 A。

## 5. 目标架构

### 5.1 HTTP 接口职责

- `POST /v1/market-data/sync`
  负责触发一次同步任务，并返回同步摘要。
- `GET /v1/market-data/sync-runs`
  只返回同步任务元数据，用于运维、审计、回放定位。
- `GET /v1/market-data/bars`
  返回行情 bars，用于 L2 或人工排查读取。

### 5.2 Application 层职责

- `SyncService`
  负责参数校验、幂等判断、增量窗口计算、调用 quote repo、写入 bar store、更新 checkpoint、返回 run 摘要。
- `QueryService`
  负责查询同步任务记录。
- 新增 `BarsQueryService` 或在 `application.market_data` 中新增独立 bars 查询服务
  负责按条件读取 bars。

### 5.3 Store 层职责

`TimescaleBarStore` 需要从“只支持 upsert 和假性 run 查询”扩展为：

- 根据 `request_id` 查询既有同步记录。
- 写入 `sync_runs`。
- 更新 `sync_checkpoints`。
- 查询 `sync_runs` 元数据。
- 查询 `bars` 明细。

## 6. 核心数据流

### 6.1 Sync 正常路径

1. HTTP 路由解析 `MarketDataSyncRequest`。
2. `SyncService` 校验 `days/end_date/timeframe/symbols/universe`。
3. 若请求包含 `request_id`，先查询 `sync_runs` 是否已有命中记录。
4. 若命中且状态为成功，直接返回已有 run 摘要，不重复抓取和写库。
5. 若未命中，则根据 `sync_checkpoints` 计算每个 `symbol + timeframe` 的最小拉取窗口。
6. 调用 quote repo 拉取缺失 bars。
7. 对返回结果执行最小规范化：
   - symbol 格式标准化
   - timeframe 校验
   - 时间戳统一
   - 数值字段转 float
8. upsert 到 `bars`。
9. 写入 `sync_runs`。
10. 更新 `sync_checkpoints`。
11. 返回同步摘要。

### 6.2 Sync 幂等路径

命中条件：

- 请求提供 `request_id`
- `sync_runs.request_id = request_id`
- 且该记录状态为 `success`

行为：

- 不再调用 quote repo
- 不再写 `bars`
- 不再更新 checkpoint
- 直接返回与该 run 对应的摘要

### 6.3 Query 路径

- `sync-runs` 读取 `sync_runs` 表，返回任务元数据。
- `bars` 读取 `bars` 表，返回行情记录。

## 7. 接口设计

### 7.1 `POST /v1/market-data/sync`

请求字段保持现有最小集合：

- `days`
- `end_date`
- `timeframe`
- `symbols`
- `universe`
- `request_id`

成功响应最小字段：

- `status`
- `run_id`
- `timeframe`
- `days`
- `end_date`
- `effective_symbols_count`
- `selection_mode`
- `symbols_hash`
- `written_rows`
- `manifest_ids`
- `generated_at`

补充约束：

- 若命中 `request_id` 幂等，可返回同样的摘要结构。
- `written_rows` 在幂等命中时应为既有 run 的值，不重新计算。

### 7.2 `GET /v1/market-data/sync-runs`

用途：同步任务记录查询，不返回 bars。

建议查询参数：

- `days`
- `timeframe`
- `status`
- `request_id`
- `limit`

响应项字段：

- `run_id`
- `request_id`
- `status`
- `days`
- `end_date`
- `timeframe`
- `effective_symbols_count`
- `started_at`
- `finished_at`
- `error_code`
- `error_message`

说明：

- 不在此接口返回 `open/high/low/close/volume/amount`。
- 若未来需要 `manifest_id`，可扩展为单字段或数组，但不影响本轮边界。

### 7.3 `GET /v1/market-data/bars`

用途：L2 和人工排查读取行情 bars。

建议查询参数：

- `symbols`
- `timeframe`
- `start_date`
- `end_date`
- `limit`

响应项字段：

- `symbol`
- `timeframe`
- `bar_time`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `adj_factor`
- `data_source`

## 8. CLI 设计

### 8.1 保持现有命令

- `hf data sync`
  继续映射到 `POST /v1/market-data/sync`

### 8.2 调整现有查询命令

- `hf data query`
  语义收口为查询 `sync-runs`

输出模式保持：

- `json`
- `table`

不再要求当前 `data query` 支持基于 bars 的 chart/tui 输出。

### 8.3 新增行情查询命令

建议新增：

- `hf data bars`

该命令映射到 `GET /v1/market-data/bars`，后续可承载：

- `json`
- `table`
- `chart`
- `tui`

这样可把“运行记录查看”和“行情数据查看”彻底分开。

## 9. 对 L2 的承诺

L2 可以基于以下稳定承诺开发：

- L1 同步接口具备幂等，不会因重复调度造成重复写入副作用。
- L1 同步具备 checkpoint 增量能力，不要求 L2 每次全量刷新。
- L2 只需要依赖 bars 读取面，不需要理解 sync-run 运维细节。
- sync-run 接口仅作为运维与审计视图，不作为 L2 的数据输入。

## 10. 测试策略

### 10.1 Python 单元测试

- `SyncService` 幂等命中时不会调用数据源或写库。
- `SyncService` 使用 checkpoint 缩小拉取窗口。
- `QueryService` 返回 run 元数据。
- `BarsQueryService` 返回 bars 明细。

### 10.2 Python 契约测试

- `POST /v1/market-data/sync` 幂等命中场景。
- `GET /v1/market-data/sync-runs` 返回字段不含 bar OHLCV。
- `GET /v1/market-data/bars` 返回 bar 明细。

### 10.3 Python 集成测试

- 初始化 migration 后，sync -> sync-runs -> bars 能闭环。
- 第二次相同 `request_id` 的 sync 不产生重复副作用。
- checkpoint 生效后只拉增量窗口。

### 10.4 Rust CLI 测试

- `data query` 查询 `sync-runs`。
- `data bars` 查询 bars。
- table/json 渲染与接口字段一致。

## 11. 非目标

以下内容不属于本轮：

- 完整 Parquet 审计归档
- 更复杂的数据清洗规则
- 更丰富的 universe 管理
- L2 因子计算逻辑本身

## 12. 实施顺序

1. 先收口 store 能力：幂等查询、checkpoint 读写、run 查询、bars 查询。
2. 再调整 application service：sync/query/bars-query。
3. 再补 HTTP schema 与 routes。
4. 最后调整 CLI，拆分 `data query` 与 `data bars`。

## 13. 风险与缓解

风险 1：CLI 现有 chart/tui 依赖 bars 形态，若直接切 `data query` 会破坏现有行为。

缓解：

- 把 chart/tui 迁移到新命令 `data bars`。
- `data query` 只保留 run 记录查看职责。

风险 2：checkpoint 设计若过早复杂化，会拖慢推进。

缓解：

- 本轮只按 `symbol + timeframe -> last_bar_time` 最小模型实现。

风险 3：幂等命中返回结构若与首次同步不一致，会增加上游处理分支。

缓解：

- 约束幂等命中返回与首次成功返回同构。

## 14. 结论

本设计选择方案 A：以最小变更把 L1 收口为 L2 的稳定底座。

核心动作只有四个：

- 做真实 `request_id` 幂等
- 接入 `sync_checkpoints` 增量同步
- 让 `sync-runs` 回归 run 元数据语义
- 新增独立 `bars` 读取接口与 CLI 命令

完成这些后，即可进入 L2，而无需等待 L1 全量计划全部实现。
