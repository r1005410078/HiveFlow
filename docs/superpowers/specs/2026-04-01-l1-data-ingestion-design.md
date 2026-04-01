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

## 11. 不在本次范围内

- 腾讯数跟 adapter 实现
- L0 Universe 动态过滤标的列表
- L2 及以上层接入
- 实时/分钟频行情
