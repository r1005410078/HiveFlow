# L1 Data Sync — Default Universe Coverage Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `hf data sync --universe default` 正确同步 28 只标的至 TimescaleDB，并提供 `hf data coverage` 命令验证数据覆盖率。

**Architecture:** 统一 `SyncService._parse_universe_file()` 调用路径，改为使用 `domain.universe.universe_loader.load_universe()`（已有），消除 `universe_symbols.py::UNIVERSE_KEYS` 白名单对 bar sync 路径的限制。新增独立的 `CoverageService` 与对应 HTTP 端点，Rust CLI 新增 `hf data coverage` 子命令。

**Tech Stack:** Python (FastAPI, domain layer), Rust (clap), TimescaleDB (BarStore protocol `list_symbols_with_min_bars_in_window`)

---

## 文件结构

| 文件 | 操作 |
|------|------|
| `quant/src/application/market_data/sync_service.py` | 修改：`_parse_universe_file()` 改调 `load_universe()` |
| `quant/src/application/market_data/coverage_service.py` | 新增：`get_coverage()` 纯函数 |
| `quant/src/interfaces/http/routes_market_data.py` | 修改：新增 `GET /v1/market-data/coverage` 端点 |
| `quant/tests/unit/market_data/test_coverage_service.py` | 新增：unit tests |
| `quant/tests/contract/test_http_coverage_endpoint.py` | 新增：contract tests |
| `quant/tests/unit/market_data/test_sync_service.py` | 修改：加 `universe="default"` parametrize case |
| `cli/src/application/handlers/data_coverage.rs` | 新增：Rust handler |
| `cli/src/cmd/data.rs` | 修改：注册 `coverage` 子命令 |
| `Makefile` | 修改：新增 `sync-default` target |

---

## Section 1：SyncService 统一 loader

**变更：** `SyncService._parse_universe_file(universe)` 不再调用 `list_symbols_from_universe_file(universe)`（需要在 `UNIVERSE_KEYS` 白名单内），改为直接调用：

```python
from domain.universe.universe_loader import load_universe

def _parse_universe_file(self, universe: str) -> list[str]:
    return load_universe(universe)
```

`load_universe()` 的行为：
- 文件存在 → 返回 `list[str]`（已过滤注释与空行）
- 文件不存在 → 抛 `FileNotFoundError`（调用方在 `_resolve_effective_symbols` 中会向上冒泡为 `ValueError`，现有错误处理路径不变）

**不需要修改 `UNIVERSE_KEYS`**：`UNIVERSE_KEYS` 仅用于 `sync_universe_symbols()`（akshare 写回 `.txt` 文件），与 bar sync 路径无关，保持不变。

---

## Section 2：CoverageService

**文件：** `quant/src/application/market_data/coverage_service.py`

```python
from __future__ import annotations

from domain.universe.universe_loader import load_universe


def get_coverage(
    universe: str,
    bar_store,
    start_date: str,
    end_date: str,
    min_bars: int = 1,
) -> dict:
    """Compare universe symbols against DB bar coverage."""
    universe_symbols = load_universe(universe)  # raises FileNotFoundError if missing

    db_covered = set(
        bar_store.list_symbols_with_min_bars_in_window(
            storage_timeframe="1d",
            start_date=start_date,
            end_date=end_date,
            min_bars=min_bars,
            after_symbol=None,
            limit=10_000,
        )[0]
    )

    universe_set = set(universe_symbols)
    covered = sorted(universe_set & db_covered)
    missing = sorted(universe_set - db_covered)

    return {
        "universe": universe,
        "start_date": start_date,
        "end_date": end_date,
        "min_bars": min_bars,
        "universe_size": len(universe_symbols),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "coverage_rate": round(len(covered) / len(universe_symbols), 4) if universe_symbols else 0.0,
        "covered": covered,
        "missing": missing,
    }
```

注意：`list_symbols_with_min_bars_in_window` 的 `storage_timeframe` 固定传 `"1d"`（日线），因为 bar sync 的目标 timeframe 是 `1d`。

---

## Section 3：HTTP 端点

**新增到 `routes_market_data.py`：**

```python
@router.get(
    "/coverage",
    summary="查询 universe 标的的数据覆盖率",
    description="对比 universe .txt 中的标的与 DB 已有数据，返回 covered/missing 列表。",
)
def get_coverage(
    universe: str = Query(..., description="universe 名称，如 default"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    min_bars: int = Query(default=1, ge=1),
) -> dict:
    from application.market_data.coverage_service import get_coverage as _get_coverage
    from interfaces.adapters.market_data.db_connection import has_db_config, open_db_connection_from_env
    from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore

    if not has_db_config():
        raise HTTPException(
            status_code=503,
            detail={"code": "COVERAGE_DB_UNAVAILABLE", "message": "no database configured"},
        )
    try:
        bar_store = TimescaleBarStore(open_db_connection_from_env())
        return _get_coverage(
            universe=universe,
            bar_store=bar_store,
            start_date=start_date,
            end_date=end_date,
            min_bars=min_bars,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "COVERAGE_UNIVERSE_NOT_FOUND", "message": str(exc)},
        ) from exc
```

---

## Section 4：Rust CLI

**`cli/src/application/handlers/data_coverage.rs`：**

```rust
use crate::application::requests::DataCoverageRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_data_coverage;
use serde_json::Value;

pub fn handle(args: DataCoverageRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);

    let result = get_data_coverage(
        &cfg.server_url,
        &args.universe,
        &args.start_date,
        &args.end_date,
        args.min_bars,
        timeout_ms,
    )?;

    match args.output.as_deref() {
        Some("table") => print_table(&result),
        _ => println!("{}", serde_json::to_string_pretty(&result).unwrap_or_default()),
    }
    Ok(())
}

fn print_table(v: &Value) {
    let rate = v["coverage_rate"].as_f64().unwrap_or(0.0) * 100.0;
    println!(
        "Universe: {}  |  {}/{} covered ({:.1}%)",
        v["universe"].as_str().unwrap_or(""),
        v["covered_count"].as_u64().unwrap_or(0),
        v["universe_size"].as_u64().unwrap_or(0),
        rate,
    );
    println!("{:<16} {}", "SYMBOL", "STATUS");
    println!("{}", "-".repeat(28));
    if let Some(arr) = v["covered"].as_array() {
        for sym in arr {
            if let Some(s) = sym.as_str() {
                println!("{:<16} covered", s);
            }
        }
    }
    if let Some(arr) = v["missing"].as_array() {
        for sym in arr {
            if let Some(s) = sym.as_str() {
                println!("{:<16} MISSING", s);
            }
        }
    }
}
```

**`DataCoverageRequest` struct（在 `requests.rs`）：**
```rust
pub struct DataCoverageRequest {
    pub universe: String,
    pub start_date: String,
    pub end_date: String,
    pub min_bars: Option<i32>,
    pub output: Option<String>,
    pub timeout_ms: Option<u64>,
}
```

**`http_client.rs` 新增：**
```rust
pub fn get_data_coverage(
    server_url: &str,
    universe: &str,
    start_date: &str,
    end_date: &str,
    min_bars: Option<i32>,
    timeout_ms: u64,
) -> Result<serde_json::Value, AppError> { ... }
```

---

## Section 5：Makefile

```makefile
TODAY := $(shell date +%Y-%m-%d)
SYNC_DAYS ?= 252

sync-default: ## 同步 default universe 近 $(SYNC_DAYS) 天日线数据（需服务端运行）
	./cli/target/debug/hf data sync \
	    --universe default \
	    --days $(SYNC_DAYS) \
	    --end-date $(TODAY) \
	    --timeframe 1d \
	    --wait
```

用法：`make sync-default`（252 天）或 `make sync-default SYNC_DAYS=90`（90 天）

---

## Section 6：测试

### Unit — `test_coverage_service.py`

```python
from unittest.mock import MagicMock
from application.market_data.coverage_service import get_coverage

def _make_bar_store(symbols):
    store = MagicMock()
    store.list_symbols_with_min_bars_in_window.return_value = (symbols, False)
    return store

def test_full_coverage(monkeypatch):
    symbols = ["000625.SZ", "300750.SZ"]
    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        lambda name: symbols,
    )
    result = get_coverage("default", _make_bar_store(symbols), "2025-01-01", "2026-01-01")
    assert result["coverage_rate"] == 1.0
    assert result["missing"] == []

def test_partial_coverage(monkeypatch):
    all_syms = ["000625.SZ", "300750.SZ", "688716.SH"]
    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        lambda name: all_syms,
    )
    result = get_coverage("default", _make_bar_store(["000625.SZ"]), "2025-01-01", "2026-01-01")
    assert result["missing_count"] == 2
    assert "300750.SZ" in result["missing"]
    assert "688716.SH" in result["missing"]

def test_empty_db(monkeypatch):
    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        lambda name: ["000625.SZ"],
    )
    result = get_coverage("default", _make_bar_store([]), "2025-01-01", "2026-01-01")
    assert result["coverage_rate"] == 0.0
    assert result["covered"] == []

def test_unknown_universe(monkeypatch):
    import pytest
    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        lambda name: (_ for _ in ()).throw(FileNotFoundError("not found")),
    )
    with pytest.raises(FileNotFoundError):
        get_coverage("nonexistent", _make_bar_store([]), "2025-01-01", "2026-01-01")
```

### Contract — `test_http_coverage_endpoint.py`

```python
from unittest.mock import patch
from fastapi.testclient import TestClient
from interfaces.http.app import app

client = TestClient(app)

def test_coverage_ok():
    with patch("interfaces.http.routes_market_data.has_db_config", return_value=True), \
         patch("interfaces.http.routes_market_data.open_db_connection_from_env"), \
         patch("interfaces.http.routes_market_data.TimescaleBarStore"), \
         patch("interfaces.http.routes_market_data._get_coverage") as mock_svc:
        mock_svc.return_value = {
            "universe": "default", "start_date": "2025-04-06", "end_date": "2026-04-06",
            "min_bars": 1, "universe_size": 28, "covered_count": 28, "missing_count": 0,
            "coverage_rate": 1.0, "covered": [], "missing": [],
        }
        resp = client.get("/v1/market-data/coverage?universe=default&start_date=2025-04-06&end_date=2026-04-06")
    assert resp.status_code == 200
    assert resp.json()["coverage_rate"] == 1.0

def test_coverage_db_unavailable():
    with patch("interfaces.http.routes_market_data.has_db_config", return_value=False):
        resp = client.get("/v1/market-data/coverage?universe=default&start_date=2025-04-06&end_date=2026-04-06")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "COVERAGE_DB_UNAVAILABLE"
```

### 回归 — `test_sync_service.py` 补充

```python
@pytest.mark.parametrize("universe", ["csi300", "default"])
def test_sync_recognizes_universe(universe, monkeypatch):
    monkeypatch.setattr(
        "application.market_data.sync_service.load_universe",
        lambda name: ["000625.SZ"],
    )
    # 验证 _resolve_effective_symbols 不再抛 ValueError
    svc = SyncService(quote_repo=..., bar_store=...)
    symbols, mode = svc._resolve_effective_symbols(symbols=None, universe=universe)
    assert symbols == ["000625.SZ"]
    assert mode == "universe"
```
