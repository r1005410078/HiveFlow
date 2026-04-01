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

## 9. Symbols 来源设计

### 并集策略

```
最终 symbols = 沪深300成分股 ∪ 中证500成分股 ∪ watchlist.toml 中的自选股
```

未来补全持仓管理后，持仓股由系统自动并入，无需手动维护到 watchlist。

### watchlist.toml 格式

位于 `~/.hiveflow/watchlist.toml`，用户手动维护关注股与持仓股：

```toml
[universe]
indices = ["CSI300", "CSI500"]   # 指数成分股，默认开启

[watchlist]
symbols = ["002415.SZ", "300750.SZ"]   # 关注股

[holdings]
symbols = ["600519.SH", "000858.SZ"]   # 持仓股（后续由持仓管理模块自动填充，不再手动维护）
```

若文件不存在，降级为仅使用 `indices` 默认值（CSI300 + CSI500）。

### SymbolsResolver

新增 `hiveflow/market_data/application/symbols_resolver.py`：

```
输入：watchlist_path: Path

流程：
  1. 读取 watchlist.toml（文件不存在则用默认 indices）
  2. akshare 拉取各指数最新成分股列表
  3. 与 watchlist + holdings 取并集，去重
  4. 返回 list[str]（标准化格式 XXXXXX.SH/SZ）
```

### 接入 daily_run_service

```python
resolver = SymbolsResolver(watchlist_path=Path.home() / ".hiveflow/watchlist.toml")
symbols = resolver.resolve()

repo = AkshareQuoteAdapter(is_fallback=True)
manifest_svc = ManifestService(NdjsonManifestRepository(root))
use_case = IngestUseCase(repo, manifest_svc)

result = use_case.run(symbols=symbols, as_of=as_of, root=root)
data["data_manifest_id"] = result.manifest_id
```

---

## 10. 接入 SyncUseCase

`SyncUseCase` 同样通过 `SymbolsResolver` 获取 symbols，不接受外部传入 symbols 列表（由系统统一管理来源）。

---

## 11. 测试策略

| 文件 | 类型 | 覆盖点 |
|------|------|--------|
| `tests/unit/market_data/test_ingest_use_case.py` | Unit | mock `QuoteRepository`，验证完整编排：落盘 + manifest 写入 + IngestResult |
| `tests/unit/market_data/test_akshare_adapter.py` | Unit | monkeypatch akshare，验证字段映射与 DataFetchError 抛出 |
| `tests/integration/test_l1_ingest_integration.py` | Integration | tmp_path + mock adapter，端到端验证 Parquet 文件与 manifest NDJSON 均写出 |

现有 `test_ingest_use_case.py`（只测 `persist_quotes`）改为测新的 `IngestUseCase`。

新增 `tests/unit/market_data/test_symbols_resolver.py`：mock akshare 成分股接口 + 各种 watchlist.toml 场景（文件存在/不存在/含 holdings）。

---

## 11. CLI 设计

### 两条命令，职责分离

| 命令 | 类型 | 触发方 | 说明 |
|------|------|--------|------|
| `hf data sync --days N` | 写操作 | 用户 / cron / AI Skill | 同步最近 N 天行情，**AI 可调用** |
| `hf data history [--days N \| --from F --to T]` | 读操作 | 用户 / AI Skill | 查询历史数据覆盖情况，**AI 可调用** |

`sync --days` 典型值：`30`（月度补数）、`90`（季度回补）、`360`（年度初始化）。

### Rust CLI 改动

**`cli/src/cmd/data.rs`** — 将现有 `Snapshot` 占位替换为 `Sync` + `History`：

```rust
pub enum DataSubcommand {
    Sync(SyncArgs),
    History(HistoryArgs),
}

pub struct SyncArgs {
    #[arg(long)]
    pub days: u32,
}

pub struct HistoryArgs {
    /// 查询最近 N 天（与 --from/--to 互斥）
    #[arg(long, conflicts_with_all = ["from", "to"])]
    pub days: Option<u32>,

    /// 起始日期（与 --days 互斥）
    #[arg(long, requires = "to")]
    pub from: Option<String>,

    /// 截止日期（与 --days 互斥）
    #[arg(long, requires = "from")]
    pub to: Option<String>,
}
```

**新增文件：**
- `cli/src/application/handlers/data_sync.rs` — 调用 `http_client::post_data_sync()`
- `cli/src/application/handlers/data_history.rs` — 调用 `http_client::get_data_history()`

**`cli/src/infrastructure/http_client.rs`** — 新增两个函数：
- `post_data_sync(server_url, days, timeout_ms) → Result<Value, AppError>`  
  调用 `POST /api/v1/data/sync`
- `get_data_history(server_url, from, to, timeout_ms) → Result<Value, AppError>`  
  调用 `GET /api/v1/data/history?from=YYYY-MM-DD&to=YYYY-MM-DD`  
  （handler 负责将 `--days N` 转换为 `from = today - N, to = today`）

**`cli/src/application/dispatch.rs`** — 将 `Commands::Data(_)` 的占位替换为实际分发。

### Python HTTP 端点与 Use Case 扩展

**新增 `quant/src/interfaces/http/routes_data.py`，注册两个路由：**
- `POST /api/v1/data/sync` — body: `{"days": 90}`，调用 `SyncUseCase`
- `GET /api/v1/data/history?from=YYYY-MM-DD&to=YYYY-MM-DD` — 调用 `HistoryQueryUseCase`  
  返回：日期范围内每天的 manifest 摘要列表（含缺口标记）

**`app.py`** 注册新 router。

**`SyncUseCase`**（新增，在 `hiveflow/market_data/application/`）：
```
输入：days: int

流程：
  1. 计算日期列表：过去 N 个自然日，跳过周末
  2. 对每个 date 调用 IngestUseCase.run(symbols, date, root)
  3. 汇总：synced_dates、skipped_dates（已有 manifest）、failed_dates
  4. 返回 SyncResult(synced_dates, skipped_dates, failed_dates, manifest_ids)
```

幂等性：若某日期已有 manifest，跳过重新拉取（`skipped_dates` 记录）。

**`HistoryQueryUseCase`**（新增，在 `hiveflow/market_data/application/`）：
```
输入：from_date: str, to_date: str

流程：
  1. 枚举 [from, to] 日期范围内的自然日（跳过周末）
  2. 对每个 date 查询 manifest_repo.find_by_as_of(date)
  3. 返回 HistoryResult：
     - records: list of {date, manifest_id, data_source, symbols_count, has_data}
     - coverage_rate: 有数据日期 / 总交易日数
     - gaps: 缺数据的日期列表
```

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

`hf data history` 响应示例：
```json
{
  "data": {
    "from": "2026-03-01",
    "to": "2026-04-01",
    "coverage_rate": 0.95,
    "gaps": ["2026-03-15"],
    "records": [
      {"date": "2026-04-01", "has_data": true, "manifest_id": "dm_20260401_xyz", "data_source": "akshare", "symbols_count": 2},
      {"date": "2026-03-15", "has_data": false, "manifest_id": null, "data_source": null, "symbols_count": 0}
    ]
  }
}
```

### 测试扩展

| 文件 | 类型 | 覆盖点 |
|------|------|--------|
| `cli/tests/http_data_sync.rs` | Rust unit | mock server，验证 sync 请求/响应映射 |
| `cli/tests/http_data_history.rs` | Rust unit | mock server，验证 history `--days` 与 `--from/--to` 两种参数转换 |
| `quant/tests/contract/test_data_sync_output.py` | Contract | 校验响应符合 CLI_OUTPUT_SCHEMA.json |
| `quant/tests/integration/test_http_data_endpoint.py` | Integration | FastAPI TestClient，验证两个端点 + 幂等性（重复 sync 同一日期）+ history 缺口标记 |

---

## 12. AI Skills 集成

### 白名单更新

两条命令均加入 AI 白名单（在 `docs/AI_SKILLS_INTEGRATION.md` 可调用命令列表中新增）：

```
hf data sync --days <N>
hf data history --days <N>
hf data history --from <date> --to <date>
```

### Skill 使用场景

**场景一：数据补全**  
AI 发现分析所需日期无数据时，可主动调用 `hf data sync` 补数：

```
hf data history --days 7
  → 发现 gaps: ["2026-03-30", "2026-03-31"]
  → hf data sync --days 7   （触发补数）
  → hf data history --days 7 （验证缺口已填补）
```

**场景二：分析前数据就绪验证**  
执行 `hf signal snapshot` 等分析前，先确认数据覆盖率：

```
hf data history --from 2026-01-01 --to 2026-04-01
  → coverage_rate < 0.9 → Skill 告警"数据覆盖率不足，分析结果可能有偏"
  → coverage_rate >= 0.9 → 继续分析，将 manifest_ids 传入下游命令
```

AI 可将 `manifest_ids` 作为下游命令的 `--data-manifest` 参数，确保数据版本对齐（G1 可追溯）。

---

## 13. 不在本次范围内

- 腾讯数跟 adapter 实现
- L0 Universe 动态过滤标的列表
- 完整交易日历（当前跳过周末，不识别 A 股节假日）
- L2 及以上层接入
- 实时/分钟频行情
- 个人持仓管理模块（后续任务，完成后持仓股由系统自动并入 symbols，watchlist.toml 的 `[holdings]` 段将废弃）
- 关注股管理 UI / CLI（后续任务，当前通过手动编辑 watchlist.toml 维护）
