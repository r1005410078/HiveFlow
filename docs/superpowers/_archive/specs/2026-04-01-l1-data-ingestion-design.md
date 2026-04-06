# L1 数据接入设计

> 状态：待评审
> 日期：2026-04-01
> 适用对象：L1 数据层实现、G1 数据治理集成

---

## 1. 目标

本设计仅覆盖 **L1 ingestion 核心能力**：

范围边界说明：

- 本文档目标是完成 **L1** 设计与实现约束
- 对 **L0** 仅定义“最小调用契约”（CLI/AI 如何触发 L1）
- 不覆盖完整 L0 客户端架构与交互系统设计

- 从 akshare 拉取 A 股 K 线行情（多粒度）
- 落盘为 Parquet（按 `timeframe/as_of` 分区）
- 使用 `PostgreSQL + Timescale` 作为查询与增量索引层
- 写入 DataManifest（可追溯数据来源、版本、hash）
- 提供面向 CLI/AI 的数据同步与最近 N 天查询能力
- 通过 Port/Adapter 模式隔离数据源，后续可平滑接入腾讯数跟

粒度策略：

- 设计层面：统一支持多粒度（`timeframe` 为必选入参）
- MVP 强制支持：`1d`（日线）与 `1m`（1 分钟）
- 其他粒度（如 `5m/15m/60m`）后续按同一契约扩展

本设计 **不包含** AI 白名单策略本身；但接口参数与返回结构需满足 AI 可稳定调用。

---

## 2. 分层与目录（对齐当前三层架构）

```text
quant/src/
  domain/
    market_data/
      quote.py                    # Quote 领域对象
      quote_repository.py         # QuoteRepository port
  application/
    market_data/
      ingest_use_case.py          # IngestUseCase（编排）
      ingest_result.py            # IngestResult DTO
  interfaces/
    adapters/
      market_data/
        akshare_quote_adapter.py  # 实现 QuoteRepository
        parquet_quote_writer.py   # Parquet 落盘与 hash
        timescale_bar_store.py    # Timescale 写入/查询/增量 checkpoint
      governance/
        manifest_repo_ndjson.py   # 已有能力可复用
```

约束：

- `domain` 不依赖 `application/interfaces`
- `application` 可依赖 `domain`
- `interfaces/adapters` 实现外部 IO（akshare、文件系统、PostgreSQL/Timescale）

---

## 3. Port 定义

**`domain/market_data/quote_repository.py`**

```python
from abc import ABC, abstractmethod
import pandas as pd


class QuoteRepository(ABC):
    @abstractmethod
    def fetch(self, symbols: list[str], as_of: str, timeframe: str) -> pd.DataFrame:
        """
        拉取指定 symbols 在 as_of 的指定粒度行情。

        返回 DataFrame 必须至少包含：
        symbol, timeframe, bar_time, open, high, low, close, volume, amount, adj_factor
        """
```

---

## 4. Application 编排（IngestUseCase）

**`application/market_data/ingest_use_case.py`**

输入：`symbols: list[str]`, `as_of: str`, `timeframe: str`, `root: Path`

流程：

1. `repo.fetch(symbols, as_of, timeframe)`
   - 异常映射为 `DATA_FETCH_FAILED`
2. 校验 `timeframe`（当前允许：`1d`, `1m`）
   - 非法值抛 `ValueError`（阻断）
3. 校验最小列集
   - 缺列抛 `ValueError`（阻断）
4. `parquet_writer.write(df, root, as_of, timeframe)`
   - 输出 `parquet_path`
   - 输出 `data_hash`（SHA256）
5. `manifest_service.create_manifest(...)`
   - 写入 `manifest_id/run_id/as_of/timeframe/data_source/fallback_used/symbols_count/bar_count/data_hash`
6. 返回 `IngestResult(manifest_id, symbols_count, bar_count, parquet_path, data_hash)`

构造参数：

- `repo: QuoteRepository`
- `parquet_writer: ParquetQuoteWriter`
- `manifest_service: ManifestService`

---

## 5. Adapter 设计

### 5.1 AkshareQuoteAdapter

职责：实现 `QuoteRepository.fetch()`。

要点：

- 根据 `timeframe` 调用 akshare 对应接口（`1d`、`1m`）
- 字段映射到最小列集（symbol/timeframe/bar_time/open/high/low/close/volume/amount/adj_factor）
- 第一版 `adj_factor=1.0`
- 支持 `data_source="akshare"` 与 `fallback_used` 标识

### 5.2 ParquetQuoteWriter

职责：落盘 + hash。

路径规则：

- `{root}/data/raw/timeframe={timeframe}/as_of={as_of}/quotes.parquet`

返回：

- `parquet_path: Path`
- `data_hash: str`（SHA256 of parquet bytes）

### 5.3 TimescaleBarStore（PostgreSQL + Timescale）

职责：作为“查询与增量索引层”。

要点：

- 写入标准化 K 线到 Timescale hypertable（按 `bar_time` 分片）
- 提供 `hf data query` 所需检索能力（按 `days/timeframe/symbol/status`）
- 维护增量同步 checkpoint（每个 `symbol + timeframe` 的最近 `bar_time`）
- 与 Parquet 层职责分离：Parquet 偏归档与回放，Timescale 偏在线查询与增量计算

---

## 6. 字段 Schema（最小列集）

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | str | 标的代码（如 `000001.SZ`） |
| timeframe | str | 粒度（`1d` / `1m`） |
| bar_time | str | K 线时间（ISO8601，东八区） |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价（前复权） |
| volume | float | 成交量 |
| amount | float | 成交额 |
| adj_factor | float | 复权因子（第一版固定 `1.0`） |

说明：

- 当 `timeframe=1d`：`bar_time` 统一归一到当日收盘时刻
- 当 `timeframe=1m`：`bar_time` 为分钟 K 线时间戳

---

## 7. DataManifest 集成

成功落盘后必须写入 manifest，字段对齐当前治理模型：

- `manifest_id`
- `run_id`
- `as_of`
- `timeframe`
- `data_source`
- `fallback_used`
- `symbols_count`
- `bar_count`
- `data_hash`
- `created_at`

当前代码中的领域模型见：
[manifest.py](/Users/rongts/HiveFlow/quant/src/hiveflow/governance/domain/manifest.py)

---

## 8. 错误处理策略

| 场景 | 处理 |
|------|------|
| 数据源异常（网络/akshare） | 抛 `DATA_FETCH_FAILED` |
| 返回空数据 | 抛业务异常并阻断 |
| 字段缺失 | `ValueError` 阻断 |
| 落盘失败（权限/磁盘） | 异常上抛 |
| manifest 写入失败 | 异常上抛 |

---

## 9. 测试策略

| 文件 | 类型 | 覆盖点 |
|------|------|--------|
| `quant/tests/unit/market_data/test_ingest_use_case.py` | Unit | mock repo/writer/manifest，验证 `1d/1m` 编排与错误映射 |
| `quant/tests/unit/market_data/test_akshare_adapter.py` | Unit | mock akshare，验证 `timeframe` 路由、字段映射与异常处理 |
| `quant/tests/unit/market_data/test_parquet_quote_writer.py` | Unit | 验证 `timeframe/as_of` 路径规则与 hash 生成 |
| `quant/tests/integration/test_l1_ingest_integration.py` | Integration | tmp_path 端到端验证 `1d/1m` parquet + manifest 写出 |

---

## 10. 非目标（本次不做）

- 完整 L0 客户端架构设计（命令体系、会话态、插件机制等）
- AI 白名单与 Skill 流程改造
- 复杂调度编排（cron/任务队列/分布式 worker）
- 全量历史覆盖率与数据质量大盘
- 完整交易日历（当前不处理节假日）
- 腾讯数跟 adapter 实现
- ClickHouse 引入（当前明确不采用）
- `5m/15m/60m` 等更多粒度（按相同契约后续扩展）

---

## 11. CLI 闭环命令（数据同步导向）

目标：本机安装 `cli` 后，通过 HTTP 调用远端 `quant` 服务，完成一次“行情数据同步”闭环。

### 11.1 命令清单（同步 + 查询）

1. `hf data sync`
   - 作用：同步最近 N 天行情到本地数据层（核心闭环命令）
2. `hf data query`
   - 作用：查询最近 N 天同步结果（面向运维与 AI 编排）

### 11.2 参数约定

- `hf data sync` 参数：
  - `--days`：同步最近 N 天（`N>=1`）
  - `--end-date`：结束日期，格式 `YYYY-MM-DD`，默认今天
  - `--timeframe`：`1d` 或 `1m`，默认 `1m`
  - `--symbols`：逗号分隔股票列表（可选）
  - `--universe`：股票池标识（可选，如 `csi300`, `zz500`, `all_a`）
- `hf data query` 参数：
  - `--days`：查询最近 N 天执行结果
  - `--timeframe`：可选过滤
  - `--symbols`：可选过滤
  - `--status`：可选过滤（`success` / `failed`）
  - `--output`：输出模式（`table` / `json` / `chart` / `tui`）
  - `--no-benchmark`：关闭大盘对比线（`chart/tui` 生效）
  - `--verbose`：表格模式追加展示诊断列（仅 `--output table` 生效）
当前实现未启用 `--interactive/--non-interactive` 参数。CLI 采用显式参数驱动：

1. 参数优先级：命令行显式参数 > 配置默认值。
2. `hf data query` 默认输出为 `json`（未显式传 `--output` 时）。
3. 人工查看建议显式使用 `--output table` 或 `--output tui`。

`hf data query --output chart` 约束：

1. 仅面向人工阅读，不作为 AI 消费格式。
2. 终端不支持图形字符时，自动降级为 `table` 并提示 warning。
3. 当前实现要求 `--symbols` 仅传 1 个标的（单标的图）。
4. 图表不替代明细（需要明细请使用 `table/json`）。

`hf data query --output tui` 约束：

1. 面向人工交互查看，不作为 AI 消费格式。
2. 未传 `--symbols` 时，展示查询结果中的股票列表并可交互切换。
3. 传 `--symbols` 时，可作为默认选中标的或范围过滤。
4. 默认带大盘对比（`000300.SH`）；可用 `--no-benchmark` 或交互键 `b` 关闭。

### 11.3 HTTP 映射

- `hf data sync` -> `POST /v1/market-data/sync`
- `hf data query` -> `GET /v1/market-data/sync-runs`

`POST /v1/market-data/sync` 请求体最小字段：

- `days`
- `end_date`
- `timeframe`
- `symbols`（可空）
- `universe`（可空）

`GET /v1/market-data/sync-runs` 查询参数：

- `days`
- `timeframe`（可空）
- `symbols`（可空）
- `status`（可空）

### 11.4 同步股票范围（必须明确）

优先级规则（从高到低）：

1. 显式 `--symbols`
2. `--universe` 指定股票池
3. 服务端默认股票范围（配置项）

服务端默认股票范围定义：

- 必须包含：`watchlist_symbols`（关注股）+ `position_symbols`（持仓股）
- 可选叠加：`default_universe`（如 `csi300`）
- 去重后形成最终默认集合（并集）

约束：

- `symbols` 与 `universe` 同时传入时，以 `symbols` 为准并记录告警日志
- 服务端返回中必须包含 `effective_symbols_count`
- manifest 中必须记录 `universe` 或 `symbols_hash`（用于追溯）
- `watchlist_symbols` 与 `position_symbols` 为独立配置项；基础文件契约见第 12 节

### 11.5 AI 可调用契约

- 参数稳定：优先使用 `days/end_date/timeframe/symbols/universe`
- AI 调用 `hf data query` 必须使用 `--output json`
- 响应稳定：字段固定，不因调用方变化
- 幂等支持：`sync` 请求支持 `request_id`（重复提交返回同一任务结果）
- 错误机器可读：`error.code` 枚举化（如 `INVALID_ARGUMENT`, `DATA_FETCH_FAILED`）

### 11.6 输出与退出码

- 成功：退出码 `0`
- 失败：输出标准错误 JSON，退出码非 `0`
- `sync` 成功响应至少包含：
  - `status`
  - `run_id`
  - `timeframe`
  - `days`
  - `effective_symbols_count`
  - `manifest_ids`
- `query --output json` 成功响应至少包含：
  - `items[]`（行情查询形态下每项包含 `bar_time/symbol/timeframe/open/high/low/close/volume`）
- `query --output table`（行情查询形态）默认列：
  - `bar_time | symbol | timeframe | close`
- `query --output table --verbose`：
  - 在明细行后追加诊断行（`open/high/low/volume/data_source`）
- `query --output chart` 默认图表：
  - 单标的价格趋势（textplots）
  - 显示 `Change` 摘要与 `Compact Trend`
- `query --output chart` 降级规则：
  - 若终端不支持图形字符，降级到 `table` 并输出 warning 文本
- `query --output tui` 交互键：
  - `↑/↓` 切换股票
  - `←/→` 移动光标
  - `a/d` 平移、`+/-` 缩放、`0` 重置
  - `b` 开关大盘对比
  - `q/Esc/Enter` 退出

### 11.7 验证用例（闭环）

1. 启动 quant HTTP 服务。
2. 执行：
   - `hf data sync --days 5 --timeframe 1d --universe csi300`
   - `hf data query --days 5 --timeframe 1d --output table`
   - `hf data query --days 5 --timeframe 1d --output table --verbose`
   - `hf data query --days 5 --timeframe 1d --output chart`
   - `hf data query --days 5 --timeframe 1d --output json`
   - `hf data query --days 5 --timeframe 1d --output tui`
3. 断言：
   - 相关命令 CLI 返回 `0`
   - 服务端落盘存在最近 5 天分区
   - manifest 写入成功并包含 `timeframe/bar_count`
   - `query table` 输出 `bar_time/symbol/timeframe/close` 核心列
   - `query table --verbose` 输出诊断扩展信息
   - `query chart` 输出单标的趋势图；不支持图形字符时自动降级到 `table`
   - `query tui` 可交互切换股票与开关大盘对比（`b`）
   - `query json` 输出可被机器解析并可查询到对应 `run_id`

---

## 12. 关注股与持仓股配置文件定义（MVP）

目的：为默认同步范围提供稳定、可审计的输入来源。

### 12.1 文件位置

- `quant/config/watchlist.yml`（关注股）
- `quant/config/positions.yml`（持仓股）

### 12.2 `watchlist.yml` 结构

```yaml
version: 1
updated_at: "2026-04-01T09:30:00+08:00"
symbols:
  - "600519.SH"
  - "000001.SZ"
```

字段约束：

- `version`：必填，当前固定 `1`
- `updated_at`：必填，ISO8601
- `symbols`：必填，股票代码数组，允许空数组

### 12.3 `positions.yml` 结构

```yaml
version: 1
updated_at: "2026-04-01T09:30:00+08:00"
positions:
  - symbol: "600036.SH"
    qty: 1000
  - symbol: "510300.SH"
    qty: 2000
```

字段约束：

- `version`：必填，当前固定 `1`
- `updated_at`：必填，ISO8601
- `positions`：必填，持仓列表，允许空数组
- `positions[].symbol`：必填，股票代码
- `positions[].qty`：必填，`>0` 数值

### 12.4 代码格式规范

- 统一使用交易所后缀格式：`{6位代码}.{SH|SZ|BJ}`
- 读取时去重并升序排序
- 不合法代码直接报错 `INVALID_SYMBOL_FORMAT`

### 12.5 默认集合生成规则

1. 从 `watchlist.yml` 读取 `watchlist_symbols`
2. 从 `positions.yml` 读取 `position_symbols = [p.symbol for p in positions]`
3. 与 `default_universe`（若配置）做并集
4. 去重 + 升序，得到 `default_effective_symbols`

### 12.6 异常处理

- 文件不存在：按空集合处理，并输出 warning
- YAML 解析失败：阻断并返回 `INVALID_CONFIG_FILE`
- 字段缺失或类型错误：阻断并返回 `INVALID_CONFIG_SCHEMA`

---

## 13. Timescale 最小表结构（MVP）

目标：支持增量同步、最近 N 天查询、按条件过滤查询。

### 13.1 `bars`（行情主表，hypertable）

建议字段：

- `symbol` `text` not null：股票代码（如 `600519.SH`）
- `timeframe` `text` not null：K 线粒度（`1d` / `1m`）
- `bar_time` `timestamptz` not null：K 线时间点（带时区）
- `open` `double precision` not null：开盘价
- `high` `double precision` not null：最高价
- `low` `double precision` not null：最低价
- `close` `double precision` not null：收盘价
- `volume` `double precision` not null：成交量
- `amount` `double precision` not null：成交额
- `adj_factor` `double precision` not null default `1.0`：复权因子
- `data_source` `text` not null：数据来源（如 `akshare`）
- `ingested_at` `timestamptz` not null default `now()`：入库时间（系统写入时间）

约束与索引：

- 主键/唯一键：`(symbol, timeframe, bar_time)`
- 索引：`(timeframe, bar_time desc)`、`(symbol, bar_time desc)`
- Timescale hypertable 时间列：`bar_time`

### 13.2 `sync_runs`（同步任务记录）

建议字段：

- `run_id` `uuid` primary key：同步任务唯一 ID
- `request_id` `text` null：幂等请求 ID（可选）
- `status` `text` not null (`running/success/failed`)：任务状态
- `days` `int` not null：本次同步天数窗口
- `end_date` `date` not null：同步窗口结束日期
- `timeframe` `text` not null：同步粒度
- `symbols_hash` `text` not null：本次有效股票集合哈希
- `effective_symbols_count` `int` not null：本次实际同步股票数量
- `started_at` `timestamptz` not null default `now()`：任务开始时间
- `finished_at` `timestamptz` null：任务结束时间
- `error_code` `text` null：失败错误码
- `error_message` `text` null：失败错误详情

约束与索引：

- 唯一键：`(request_id)`（仅当 `request_id` 非空）
- 索引：`(started_at desc)`、`(status, started_at desc)`、`(timeframe, started_at desc)`

### 13.3 `sync_checkpoints`（增量游标）

建议字段：

- `symbol` `text` not null：股票代码
- `timeframe` `text` not null：粒度
- `last_bar_time` `timestamptz` not null：最近已同步到的 bar 时间
- `updated_at` `timestamptz` not null default `now()`：checkpoint 更新时间
- `last_run_id` `uuid` not null：最近一次更新该 checkpoint 的任务 ID

约束与索引：

- 主键：`(symbol, timeframe)`
- 索引：`(timeframe, last_bar_time desc)`

### 13.4 幂等与增量规则

1. `sync` 请求若传入 `request_id`，先查 `sync_runs.request_id`，命中则直接返回已有结果。
2. 增量拉取起点为 `sync_checkpoints.last_bar_time`（按 `symbol + timeframe`）。
3. 写入 `bars` 使用 upsert，冲突键为 `(symbol, timeframe, bar_time)`。
4. run 成功后批量更新 `sync_checkpoints` 与 `sync_runs.status=success`。
