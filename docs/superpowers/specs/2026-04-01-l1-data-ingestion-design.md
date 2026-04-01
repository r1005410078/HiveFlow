# L1 数据接入设计

> 状态：已确认
> 日期：2026-04-01
> 适用对象：L1 数据层实现、G1 数据治理集成

---

## 1. 目标

将 `hiveflow/market_data/` 从最小化骨架升级为可运行的 L1 数据层：

- 通过 akshare 拉取 A 股日频行情，落盘为 Parquet
- 每次数据拉取写入 G1 DataManifest（可追溯数据来源、版本、hash）
- 通过 Port/Adapter 模式隔离数据源，未来接入腾讯数跟只需新增 adapter

---

## 2. 目录结构

```
quant/src/hiveflow/market_data/
├── domain/
│   ├── quote.py                    # 已有：Quote dataclass
│   └── quote_repository.py         # 新增：QuoteRepository abstract port
├── application/
│   └── ingest_use_case.py          # 改造：IngestUseCase 编排完整 L1 流程
└── infrastructure/
    ├── __init__.py
    ├── akshare_quote_adapter.py    # 新增：akshare 实现 QuoteRepository port
    └── parquet_quote_writer.py     # 新增：Parquet 落盘（提炼自现有 persist_quotes）
```

`hiveflow/governance/application/manifest_service.py` 已有，直接复用。

---

## 3. Port 定义

**`domain/quote_repository.py`**

```python
from abc import ABC, abstractmethod
import pandas as pd

class QuoteRepository(ABC):
    @abstractmethod
    def fetch(self, symbols: list[str], as_of: str) -> pd.DataFrame:
        """
        拉取指定标的在 as_of 日期的日频行情。

        返回 DataFrame 必须包含最小列集：
          symbol, date, open, high, low, close, volume, amount, adj_factor
        """
```

未来接入腾讯数跟：新增 `TencentQuoteAdapter(QuoteRepository)`，其余层不变。

---

## 4. Application Use Case 编排

**`application/ingest_use_case.py`**，重构为 `IngestUseCase` 类：

```
输入：symbols: list[str], as_of: str, root: Path

编排流程：
  1. repo.fetch(symbols, as_of)
       → 失败时抛 DataFetchError（ErrorCode.DATA_FETCH_FAILED）
  2. 字段校验
       → 必须含最小列集，缺列抛 ValueError
  3. 计算 data_hash
       → SHA256(Parquet bytes)，支持 PIT 可追溯
  4. parquet_writer.write(df, root, as_of)
       → 落盘到 data/raw/as_of=YYYY-MM-DD/quotes.parquet
  5. manifest_service.create_manifest(
         as_of, data_source, fallback_used,
         symbols_count=len(df["symbol"].unique()),
         data_hash
     )
  6. 返回 IngestResult(manifest_id, symbols_count, parquet_path)
```

**`IngestUseCase` 构造参数：**
- `repo: QuoteRepository`
- `manifest_service: ManifestService`

---

## 5. Infrastructure

### AkshareQuoteAdapter

- 实现 `QuoteRepository.fetch()`
- 通过 `akshare` 拉取日频行情（`ak.stock_zh_a_hist`）
- 构造参数 `is_fallback: bool`，传入 manifest 的 `fallback_used` 字段
- 字段映射：akshare 原始列 → 最小列集（symbol/date/open/high/low/close/volume/amount/adj_factor）
- 第一版 adj_factor 固定为 1.0（前复权价格直接使用）

### ParquetQuoteWriter

- 封装落盘逻辑（从现有 `persist_quotes` 提炼）
- 路径规则：`{root}/data/raw/as_of={as_of}/quotes.parquet`
- 返回写出的 Path，同时返回 SHA256 hash（用于 manifest）

---

## 6. 字段 Schema

最小列集（第一版）：

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | str | 标的代码（如 000001.SZ） |
| date | str | 交易日（YYYY-MM-DD） |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价（前复权） |
| volume | float | 成交量 |
| amount | float | 成交额 |
| adj_factor | float | 复权因子（第一版固定 1.0） |

Schema 预留扩展：L2/L3 需要时可直接追加 `turnover_rate`、`total_mv`、`float_mv` 等列，不破坏现有消费方。

---

## 7. G1 DataManifest 集成

每次成功落盘后写入 DataManifest，字段：

- `manifest_id`：唯一 ID（`dm_{as_of}_{uuid6}`）
- `run_id`：本次运行 ID
- `as_of`：数据日期
- `data_source`：`"akshare"`（或 `"tencent"`）
- `fallback_used`：`bool`，akshare 第一版设为 `True`（待腾讯数跟接入后可改为 `False`）
- `symbols_count`：拉取标的数
- `data_hash`：SHA256 of Parquet bytes

---

## 8. 错误处理

| 场景 | 行为 |
|------|------|
| `repo.fetch()` 失败（网络/akshare 异常） | 抛 `DataFetchError`，由 `daily_run_service` 捕获，输出 `status: warning` |
| 字段缺失 | 抛 `ValueError`，阻断流程 |
| 落盘失败（磁盘/权限） | 让异常向上传播，由调用方处理 |

---

## 9. 接入 daily_run_service

`application/daily_run_service.run_daily()` 增加 L1 调用：

```python
repo = AkshareQuoteAdapter(is_fallback=True)
manifest_repo = NdjsonManifestRepository(root)
manifest_svc = ManifestService(manifest_repo)
use_case = IngestUseCase(repo, manifest_svc)

result = use_case.run(symbols=["000001.SZ", "600519.SH"], as_of=as_of, root=root)
data["data_manifest_id"] = result.manifest_id
```

`symbols` 第一版硬编码少量测试标的，待 L0 Universe 层接入后替换为动态列表。

---

## 10. 测试策略

| 文件 | 类型 | 覆盖点 |
|------|------|--------|
| `tests/unit/market_data/test_ingest_use_case.py` | Unit | mock `QuoteRepository`，验证完整编排：落盘 + manifest 写入 + IngestResult |
| `tests/unit/market_data/test_akshare_adapter.py` | Unit | monkeypatch akshare，验证字段映射与 DataFetchError 抛出 |
| `tests/integration/test_l1_ingest_integration.py` | Integration | tmp_path + mock adapter，端到端验证 Parquet 文件与 manifest NDJSON 均写出 |

现有 `test_ingest_use_case.py`（只测 `persist_quotes`）改为测新的 `IngestUseCase`。

---

## 11. CLI 设计

### 两条命令，职责分离

| 命令 | 类型 | 触发方 | 说明 |
|------|------|--------|------|
| `hf data sync --days N` | 写操作 | 用户 / cron | 同步最近 N 天行情，**不在 AI 白名单** |
| `hf data status --as-of YYYY-MM-DD` | 读操作 | 用户 / AI Skill | 查询指定日期的数据就绪状态，**AI 可调用** |

`--days` 典型值：`30`（月度补数）、`90`（季度回补）、`360`（年度初始化）。

### Rust CLI 改动

**`cli/src/cmd/data.rs`** — 将现有 `Snapshot` 占位替换为 `Sync` + `Status`：

```rust
pub enum DataSubcommand {
    Sync(SyncArgs),
    Status(StatusArgs),
}

pub struct SyncArgs {
    #[arg(long)]
    pub days: u32,              // 同步最近 N 天
}

pub struct StatusArgs {
    #[arg(long)]
    pub as_of: String,          // 查询指定日期的数据就绪状态
}
```

**新增文件：**
- `cli/src/application/handlers/data_sync.rs` — 调用 `http_client::post_data_sync()`
- `cli/src/application/handlers/data_status.rs` — 调用 `http_client::get_data_status()`

**`cli/src/infrastructure/http_client.rs`** — 新增两个函数：
- `post_data_sync(server_url, days, timeout_ms) → Result<Value, AppError>`  
  调用 `POST /api/v1/data/sync`
- `get_data_status(server_url, as_of, timeout_ms) → Result<Value, AppError>`  
  调用 `GET /api/v1/data/status?as_of=YYYY-MM-DD`

**`cli/src/application/dispatch.rs`** — 将 `Commands::Data(_)` 的占位替换为实际分发。

### Python HTTP 端点与 Use Case 扩展

**新增 `quant/src/interfaces/http/routes_data.py`，注册两个路由：**
- `POST /api/v1/data/sync` — body: `{"days": 90}`，调用 `SyncUseCase`  
  返回：synced_dates 列表、manifest_ids、total_symbols_count
- `GET /api/v1/data/status?as_of=YYYY-MM-DD` — 查询 DataManifest by as_of  
  返回：manifest 字段或 `status: "not_found"`

**`app.py`** 注册新 router。

**`SyncUseCase`**（新增，在 `hiveflow/market_data/application/`）：
```
输入：days: int

流程：
  1. 计算日期列表：过去 N 个交易日（简单版：过去 N 个自然日，跳过周末）
  2. 对每个 date 调用 IngestUseCase.run(symbols, date, root)
  3. 汇总结果：成功落盘日期、跳过日期（已有 manifest）、失败日期
  4. 返回 SyncResult(synced_dates, skipped_dates, failed_dates, manifest_ids)
```

幂等性：若某日期已有 manifest，跳过重新拉取（`skipped_dates` 记录），避免重复覆盖。

### CLI 输出 schema

`hf data sync --days 30` 成功响应示例：
```json
{
  "schema_version": "1.0.0",
  "command": "hf data sync",
  "run_id": "run_20260401_abc123",
  "status": "ok",
  "generated_at": "2026-04-01T10:00:00Z",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "days_requested": 30,
    "synced_count": 22,
    "skipped_count": 0,
    "failed_count": 0,
    "synced_dates": ["2026-04-01", "..."],
    "manifest_ids": ["dm_20260401_xyz456", "..."]
  },
  "warnings": [],
  "errors": []
}
```

`hf data status --as-of YYYY-MM-DD` 响应中 `data` 为单日 manifest 字段（manifest_id、data_source、fallback_used、symbols_count、data_hash）。

### 测试扩展

| 文件 | 类型 | 覆盖点 |
|------|------|--------|
| `cli/tests/http_data_sync.rs` | Rust unit | mock server，验证 sync 请求/响应映射 |
| `cli/tests/http_data_status.rs` | Rust unit | mock server，验证 status 请求/响应映射 |
| `quant/tests/contract/test_data_sync_output.py` | Contract | 校验响应符合 CLI_OUTPUT_SCHEMA.json |
| `quant/tests/integration/test_http_data_endpoint.py` | Integration | FastAPI TestClient，验证两个端点 + 幂等性（重复 sync 同一日期） |

---

## 12. AI Skills 集成

### 设计原则

- `hf data sync`：**不在 AI 白名单**。数据写入是运营操作，必须由人或 cron 触发，AI 不得触发数据落盘。
- `hf data status`：**加入 AI 白名单**。只读查询，AI 用来验证数据就绪后再执行分析。

### 白名单更新

在 `docs/AI_SKILLS_INTEGRATION.md` 的可调用命令列表中新增：

```
hf data status --as-of <date>
```

### Skill 使用场景

AI Skill 在执行任何依赖行情数据的分析（`hf signal snapshot`、`hf factor health` 等）之前，先调用 `hf data status` 验证数据就绪：

```
步骤一：hf data status --as-of 2026-04-01
  → status=ok 且 data.manifest_id 存在 → 继续
  → status=not_found → Skill 输出 "数据未就绪，请先运行 hf data sync --days 30"，终止
```

AI 可将 `manifest_id` 作为下游命令的 `--data-manifest` 参数，确保数据版本对齐（G1 可追溯）。

---

## 13. 不在本次范围内

- 腾讯数跟 adapter 实现
- L0 Universe 动态过滤标的列表
- 交易日历（当前 sync 跳过周末，不做完整交易日历）
- L2 及以上层接入
- 实时/分钟频行情
- `hf data sync` 加入 AI 白名单（明确排除）
