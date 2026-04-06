# L1 Foundation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 L1 数据层补强为 L2 可依赖的稳定底座，完成幂等同步、checkpoint 增量、run 查询语义收口，以及独立 bars 读取面。

**Architecture:** Python 侧继续遵守 `interfaces -> application -> domain` 三层结构：`TimescaleBarStore` 承担 persistence 细节，`SyncService/QueryService/BarsQueryService` 承担用例编排，HTTP 路由只做 DTO 解析与 service 调用。Rust CLI 继续保持 `cmd -> application -> infrastructure` 四层结构，把 `data query` 收口到 run 元数据，并新增独立 `data bars` 命令承载行情明细读取与 chart/tui 渲染。

**Tech Stack:** Python (`fastapi`, `pytest`, `uv`), PostgreSQL/Timescale, Rust (`clap`, `reqwest`, `serde_json`, `comfy-table`, `textplots`).

---

## 0. 文件与职责总览

### 0.1 Python 服务端

- Modify: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`
  备注：补齐 `request_id` 查询、checkpoint 读写、run 元数据查询、bars 查询。
- Modify: `quant/src/application/market_data/sync_service.py`
  备注：接入真实幂等命中和 checkpoint 增量窗口计算。
- Modify: `quant/src/application/market_data/query_service.py`
  备注：让现有 query service 明确只查询 `sync_runs` 元数据。
- Create: `quant/src/application/market_data/bars_query_service.py`
  备注：新增独立 bars 查询用例。
- Modify: `quant/src/domain/market_data/ports.py`
  备注：为 store 协议增加幂等、checkpoint、run 查询、bars 查询能力。
- Modify: `quant/src/interfaces/http/schemas_market_data.py`
  备注：新增 bars 查询参数 schema，补充 sync-runs 过滤字段 DTO。
- Modify: `quant/src/interfaces/http/routes_market_data.py`
  备注：让 `sync-runs` 回归 run 查询，并新增 `/bars` 路由。
- Modify: `quant/src/interfaces/http/dependencies.py`
  备注：装配 `BarsQueryService`，保留 provider-only 约束。

### 0.2 Python 测试

- Modify: `quant/tests/unit/market_data/test_sync_service_v2.py`
  备注：新增幂等命中与 checkpoint 增量测试。
- Modify: `quant/tests/unit/market_data/test_query_service_v2.py`
  备注：明确 `QueryService` 返回 run 元数据。
- Create: `quant/tests/unit/market_data/test_bars_query_service.py`
  备注：验证 bars 查询用例。
- Modify: `quant/tests/contract/test_http_market_data_query_endpoint.py`
  备注：收口到 `sync-runs` 元数据契约。
- Create: `quant/tests/contract/test_http_market_data_bars_endpoint.py`
  备注：验证 `/v1/market-data/bars` 契约。
- Create: `quant/tests/contract/test_http_market_data_sync_idempotency.py`
  备注：验证相同 `request_id` 幂等命中。

### 0.3 Rust CLI

- Modify: `cli/src/cmd/data.rs`
  备注：保留 `data query`，新增 `data bars`。
- Modify: `cli/src/application/dispatch.rs`
  备注：接入 bars handler。
- Modify: `cli/src/application/handlers/mod.rs`
  备注：导出 bars handler。
- Modify: `cli/src/application/handlers/data_query.rs`
  备注：收口到 run 元数据查询，只保留 `json/table`。
- Create: `cli/src/application/handlers/data_bars.rs`
  备注：新增 bars 查询与 `json/table/chart/tui` 路由。
- Modify: `cli/src/infrastructure/http_client.rs`
  备注：新增 `GET /v1/market-data/bars` 请求方法，收口 `sync-runs` 查询参数。
- Modify: `cli/src/infrastructure/table_renderer.rs`
  备注：把 run 表格和 bars 表格彻底分开，避免自动猜字段语义。

### 0.4 Rust 测试

- Modify: `cli/tests/http_data_query_json.rs`
  备注：改为 run 元数据形态。
- Modify: `cli/tests/http_data_query_table.rs`
  备注：改为 run 元数据表格断言。
- Create: `cli/tests/http_data_bars_json.rs`
  备注：验证 bars 查询 JSON。
- Create: `cli/tests/http_data_bars_table.rs`
  备注：验证 bars 查询 table。
- Create: `cli/tests/http_data_bars_chart.rs`
  备注：验证 bars chart 输出。

### 0.5 文档

- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
  备注：更新 `data query` 和 `data bars` 示例。

---

### Task 1: Store Contract First (Idempotency + Checkpoints + Query Split)

**Files:**
- Modify: `quant/src/domain/market_data/ports.py`
- Modify: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`
- Test: `quant/tests/unit/market_data/test_query_service_v2.py`
- Create: `quant/tests/unit/market_data/test_bars_query_service.py`

- [ ] **Step 1: Write the failing unit tests for the split query contracts**

```python
# quant/tests/unit/market_data/test_query_service_v2.py
from application.market_data.query_service import QueryService


class _FakeBarStore:
    def list_sync_runs(self, days, timeframe=None, status=None, request_id=None, limit=None):
        return [
            {
                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                "request_id": "req_001",
                "status": "success",
                "days": 5,
                "end_date": "2026-04-01",
                "timeframe": "1d",
                "effective_symbols_count": 2,
                "started_at": "2026-04-01T09:30:00+08:00",
                "finished_at": "2026-04-01T09:31:00+08:00",
                "error_code": None,
                "error_message": None,
            }
        ]


def test_query_service_returns_run_metadata_items() -> None:
    svc = QueryService(bar_store=_FakeBarStore())

    out = svc.query(days=5, timeframe="1d", status="success", request_id="req_001", limit=20)

    assert "items" in out
    assert out["items"][0]["request_id"] == "req_001"
    assert out["items"][0]["effective_symbols_count"] == 2
    assert "close" not in out["items"][0]
```

```python
# quant/tests/unit/market_data/test_bars_query_service.py
from application.market_data.bars_query_service import BarsQueryService


class _FakeBarStore:
    def list_bars(self, symbols=None, timeframe=None, start_date=None, end_date=None, limit=None):
        return [
            {
                "symbol": "600519.SH",
                "timeframe": "1d",
                "bar_time": "2026-04-01T15:00:00+08:00",
                "open": 1450.0,
                "high": 1468.0,
                "low": 1442.0,
                "close": 1459.44,
                "volume": 29125.0,
                "amount": 4256185472.0,
                "adj_factor": 1.0,
                "data_source": "tencent",
            }
        ]


def test_bars_query_service_returns_bar_items() -> None:
    svc = BarsQueryService(bar_store=_FakeBarStore())

    out = svc.query(
        symbols=["600519.SH"],
        timeframe="1d",
        start_date="2026-04-01",
        end_date="2026-04-01",
        limit=200,
    )

    assert "items" in out
    assert out["items"][0]["symbol"] == "600519.SH"
    assert out["items"][0]["close"] == 1459.44
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd quant && uv run pytest tests/unit/market_data/test_query_service_v2.py tests/unit/market_data/test_bars_query_service.py -q`
Expected: FAIL with missing `BarsQueryService` and/or `QueryService.query()` signature mismatch.

- [ ] **Step 3: Implement the protocol and query split**

```python
# quant/src/domain/market_data/ports.py
from __future__ import annotations

from typing import Protocol


class QuoteRepository(Protocol):
    def fetch(self, symbols: list[str], as_of: str, timeframe: str) -> list[dict]:
        ...


class BarStore(Protocol):
    def upsert_bars(self, rows: list[dict]) -> int:
        ...

    def get_sync_run_by_request_id(self, request_id: str) -> dict | None:
        ...

    def get_checkpoints(self, symbols: list[str], timeframe: str) -> dict[str, str]:
        ...

    def upsert_checkpoints(self, checkpoints: list[dict]) -> None:
        ...

    def insert_sync_run(self, payload: dict) -> None:
        ...

    def list_sync_runs(
        self,
        days: int,
        timeframe: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        ...

    def list_bars(
        self,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        ...
```

```python
# quant/src/application/market_data/query_service.py
from __future__ import annotations


class QueryService:
    def __init__(self, bar_store):
        self.bar_store = bar_store

    def query(
        self,
        days: int,
        timeframe: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        limit: int | None = None,
    ) -> dict:
        items = self.bar_store.list_sync_runs(
            days=days,
            timeframe=timeframe,
            status=status,
            request_id=request_id,
            limit=limit,
        )
        return {"items": items}
```

```python
# quant/src/application/market_data/bars_query_service.py
from __future__ import annotations


class BarsQueryService:
    def __init__(self, bar_store):
        self.bar_store = bar_store

    def query(
        self,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> dict:
        items = self.bar_store.list_bars(
            symbols=symbols,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return {"items": items}
```

- [ ] **Step 4: Expand the Timescale store for run metadata and bars queries**

```python
# quant/src/interfaces/adapters/market_data/timescale_bar_store.py
def get_sync_run_by_request_id(self, request_id: str) -> dict | None:
    sql = """
    select run_id::text, request_id, status, days, end_date::text, timeframe,
           effective_symbols_count, started_at::text, finished_at::text,
           error_code, error_message
    from sync_runs
    where request_id = %s
    limit 1
    """
    cur = self._conn.cursor()
    try:
        cur.execute(sql, [request_id])
        row = cur.fetchone()
    finally:
        cur.close()
    if row is None:
        return None
    return {
        "run_id": row[0],
        "request_id": row[1],
        "status": row[2],
        "days": row[3],
        "end_date": row[4],
        "timeframe": row[5],
        "effective_symbols_count": row[6],
        "started_at": row[7],
        "finished_at": row[8],
        "error_code": row[9],
        "error_message": row[10],
    }

def get_checkpoints(self, symbols: list[str], timeframe: str) -> dict[str, str]:
    if not symbols:
        return {}
    sql = """
    select symbol, last_bar_time::text
    from sync_checkpoints
    where timeframe = %s and symbol = any(%s)
    """
    cur = self._conn.cursor()
    try:
        cur.execute(sql, [timeframe, symbols])
        rows = cur.fetchall()
    finally:
        cur.close()
    return {row[0]: row[1] for row in rows}

def upsert_checkpoints(self, checkpoints: list[dict]) -> None:
    if not checkpoints:
        return
    sql = """
    insert into sync_checkpoints (symbol, timeframe, last_bar_time, last_run_id)
    values (%(symbol)s, %(timeframe)s, %(last_bar_time)s, %(last_run_id)s)
    on conflict (symbol, timeframe)
    do update set
      last_bar_time = excluded.last_bar_time,
      last_run_id = excluded.last_run_id,
      updated_at = now()
    """
    cur = self._conn.cursor()
    try:
        for item in checkpoints:
            cur.execute(sql, item)
        self._conn.commit()
    finally:
        cur.close()
```

- [ ] **Step 5: Finish SQL-backed list methods**

```python
# quant/src/interfaces/adapters/market_data/timescale_bar_store.py
def list_sync_runs(self, days, timeframe=None, status=None, request_id=None, limit=None) -> list[dict]:
    sql = """
    select run_id::text, request_id, status, days, end_date::text, timeframe,
           effective_symbols_count, started_at::text, finished_at::text,
           error_code, error_message
    from sync_runs
    where started_at >= (current_date - (%s::int - 1))::timestamptz
    """
    params: list[object] = [days]
    if timeframe:
        sql += " and timeframe = %s"
        params.append(timeframe)
    if status:
        sql += " and status = %s"
        params.append(status)
    if request_id:
        sql += " and request_id = %s"
        params.append(request_id)
    sql += " order by started_at desc"
    sql += " limit %s"
    params.append(limit or 100)
    cur = self._conn.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()
    return [
        {
            "run_id": row[0],
            "request_id": row[1],
            "status": row[2],
            "days": row[3],
            "end_date": row[4],
            "timeframe": row[5],
            "effective_symbols_count": row[6],
            "started_at": row[7],
            "finished_at": row[8],
            "error_code": row[9],
            "error_message": row[10],
        }
        for row in rows
    ]

def list_bars(self, symbols=None, timeframe=None, start_date=None, end_date=None, limit=None) -> list[dict]:
    sql = """
    select symbol, timeframe, bar_time::text, open, high, low, close,
           volume, amount, adj_factor, data_source
    from bars
    where 1=1
    """
    params: list[object] = []
    if timeframe:
        sql += " and timeframe = %s"
        params.append(timeframe)
    if symbols:
        sql += " and symbol = any(%s)"
        params.append(symbols)
    if start_date:
        sql += " and bar_time >= %s::timestamptz"
        params.append(f"{start_date}T00:00:00+08:00")
    if end_date:
        sql += " and bar_time <= %s::timestamptz"
        params.append(f"{end_date}T23:59:59+08:00")
    sql += " order by bar_time desc, symbol asc limit %s"
    params.append(limit or 5000)
    cur = self._conn.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()
    return [
        {
            "symbol": row[0],
            "timeframe": row[1],
            "bar_time": row[2],
            "open": row[3],
            "high": row[4],
            "low": row[5],
            "close": row[6],
            "volume": row[7],
            "amount": row[8],
            "adj_factor": row[9],
            "data_source": row[10],
        }
        for row in rows
    ]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd quant && uv run pytest tests/unit/market_data/test_query_service_v2.py tests/unit/market_data/test_bars_query_service.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add quant/src/domain/market_data/ports.py quant/src/application/market_data/query_service.py quant/src/application/market_data/bars_query_service.py quant/src/interfaces/adapters/market_data/timescale_bar_store.py quant/tests/unit/market_data/test_query_service_v2.py quant/tests/unit/market_data/test_bars_query_service.py
git commit -m "feat: split market data run and bars query contracts"
```

### Task 2: Sync Idempotency and Checkpoint-Driven Incremental Sync

**Files:**
- Modify: `quant/src/application/market_data/sync_service.py`
- Modify: `quant/tests/unit/market_data/test_sync_service_v2.py`
- Create: `quant/tests/contract/test_http_market_data_sync_idempotency.py`

- [ ] **Step 1: Write the failing tests for idempotency and incremental checkpoints**

```python
# quant/tests/unit/market_data/test_sync_service_v2.py
def test_sync_service_returns_existing_run_for_same_request_id() -> None:
    class _IdempotentStore(_FakeBarStore):
        def get_sync_run_by_request_id(self, request_id):
            assert request_id == "req_001"
            return {
                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                "request_id": "req_001",
                "status": "success",
                "days": 5,
                "end_date": "2026-04-01",
                "timeframe": "1d",
                "effective_symbols_count": 1,
                "started_at": "2026-04-01T09:30:00+08:00",
                "finished_at": "2026-04-01T09:31:00+08:00",
                "error_code": None,
                "error_message": None,
                "selection_mode": "symbols",
                "symbols_hash": "abc123",
                "written_rows": 5,
                "manifest_ids": ["mf_existing_001"],
                "generated_at": "2026-04-01T01:31:00+00:00",
            }

    repo = _FakeQuoteRepo()
    svc = SyncService(quote_repo=repo, bar_store=_IdempotentStore())

    out = svc.sync(
        days=5,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
        request_id="req_001",
    )

    assert out["request_id"] == "req_001"
    assert out["written_rows"] == 5
    assert repo.calls == []
```

```python
# quant/tests/unit/market_data/test_sync_service_v2.py
def test_sync_service_uses_checkpoint_to_reduce_fetch_window() -> None:
    class _CheckpointStore(_FakeBarStore):
        def get_sync_run_by_request_id(self, request_id):
            return None

        def get_checkpoints(self, symbols, timeframe):
            assert symbols == ["600519.SH"]
            assert timeframe == "1d"
            return {"600519.SH": "2026-03-31T15:00:00+08:00"}

        def upsert_checkpoints(self, checkpoints):
            self.checkpoints = checkpoints

    repo = _FakeQuoteRepo()
    store = _CheckpointStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    out = svc.sync(days=5, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])

    assert out["written_rows"] == 1
    assert len(repo.calls) == 1
    assert repo.calls[0]["as_of"] == "2026-04-01"
    assert store.checkpoints[0]["symbol"] == "600519.SH"
```

```python
# quant/tests/contract/test_http_market_data_sync_idempotency.py
from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_market_data_sync_service


def test_post_market_data_sync_returns_existing_run_for_same_request_id() -> None:
    app = create_app()

    def _stub_sync(*, days, end_date, timeframe, symbols, universe, request_id):
        del days, end_date, timeframe, symbols, universe
        assert request_id == "req_001"
        return {
            "status": "success",
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "request_id": "req_001",
            "timeframe": "1d",
            "days": 5,
            "end_date": "2026-04-01",
            "effective_symbols_count": 1,
            "selection_mode": "symbols",
            "symbols_hash": "abc123",
            "written_rows": 5,
            "manifest_ids": ["mf_existing_001"],
            "generated_at": "2026-04-01T01:31:00+00:00",
        }

    app.dependency_overrides[get_market_data_sync_service] = lambda: _stub_sync
    client = TestClient(app)

    resp = client.post(
        "/v1/market-data/sync",
        json={"days": 5, "end_date": "2026-04-01", "timeframe": "1d", "request_id": "req_001"},
    )

    assert resp.status_code == 200
    assert resp.json()["request_id"] == "req_001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd quant && uv run pytest tests/unit/market_data/test_sync_service_v2.py tests/contract/test_http_market_data_sync_idempotency.py -q`
Expected: FAIL because `SyncService` does not yet short-circuit on `request_id` or use checkpoints.

- [ ] **Step 3: Implement the idempotent sync flow**

```python
# quant/src/application/market_data/sync_service.py
def _existing_run_summary(self, request_id: str | None) -> dict | None:
    if not request_id:
        return None
    getter = getattr(self.bar_store, "get_sync_run_by_request_id", None)
    if not callable(getter):
        return None
    existing = getter(request_id)
    if existing and existing.get("status") == "success":
        return existing
    return None

def sync(self, days, end_date, timeframe, symbols=None, universe=None, request_id=None) -> dict:
    validate_timeframe(timeframe)
    existing = self._existing_run_summary(request_id)
    if existing is not None:
        return existing
    effective_symbols, selection_mode = self._resolve_effective_symbols(symbols, universe)
    # remaining logic continues...
```

- [ ] **Step 4: Implement checkpoint-aware fetch window and checkpoint update**

```python
# quant/src/application/market_data/sync_service.py
def _dates_after_checkpoint(self, as_of_dates: list[str], checkpoint_value: str | None) -> list[str]:
    if not checkpoint_value:
        return as_of_dates
    checkpoint_day = checkpoint_value[:10]
    return [day for day in as_of_dates if day > checkpoint_day]

def sync(self, days, end_date, timeframe, symbols=None, universe=None, request_id=None) -> dict:
    ...
    checkpoint_getter = getattr(self.bar_store, "get_checkpoints", None)
    checkpoints = checkpoint_getter(effective_symbols, timeframe) if callable(checkpoint_getter) else {}
    latest_by_symbol: dict[str, str] = {}
    for symbol in effective_symbols:
        symbol_dates = self._dates_after_checkpoint(as_of_dates, checkpoints.get(symbol))
        for as_of in symbol_dates:
            rows = self.quote_repo.fetch(symbols=[symbol], as_of=as_of, timeframe=timeframe)
            if not rows:
                continue
            total_written_rows += self.bar_store.upsert_bars(rows)
            has_any_rows = True
            latest_by_symbol[symbol] = max(row["bar_time"] for row in rows)
    ...
    checkpoint_upserter = getattr(self.bar_store, "upsert_checkpoints", None)
    if callable(checkpoint_upserter):
        checkpoint_upserter(
            [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "last_bar_time": last_bar_time,
                    "last_run_id": run_id,
                }
                for symbol, last_bar_time in latest_by_symbol.items()
            ]
        )
```

- [ ] **Step 5: Ensure inserted run payload contains idempotent replay fields**

```python
# quant/src/application/market_data/sync_service.py
sync_run_payload = {
    "run_id": run_id,
    "request_id": request_id,
    "status": "success",
    "days": days,
    "end_date": end_date,
    "timeframe": timeframe,
    "symbols_hash": self._symbols_hash(effective_symbols),
    "effective_symbols_count": len(effective_symbols),
    "error_code": None,
    "error_message": None,
    "selection_mode": selection_mode,
    "written_rows": total_written_rows,
    "manifest_ids": [manifest_id],
    "generated_at": now,
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd quant && uv run pytest tests/unit/market_data/test_sync_service_v2.py tests/contract/test_http_market_data_sync_idempotency.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add quant/src/application/market_data/sync_service.py quant/tests/unit/market_data/test_sync_service_v2.py quant/tests/contract/test_http_market_data_sync_idempotency.py
git commit -m "feat: add idempotent and checkpoint-driven market data sync"
```

### Task 3: HTTP Contract Split for `/sync-runs` and `/bars`

**Files:**
- Modify: `quant/src/interfaces/http/schemas_market_data.py`
- Modify: `quant/src/interfaces/http/routes_market_data.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/tests/contract/test_http_market_data_query_endpoint.py`
- Create: `quant/tests/contract/test_http_market_data_bars_endpoint.py`

- [ ] **Step 1: Write the failing HTTP contract tests**

```python
# quant/tests/contract/test_http_market_data_query_endpoint.py
from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_get_market_data_sync_runs_returns_run_metadata() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/v1/market-data/sync-runs", params={"days": 5, "timeframe": "1d"})

    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload
    if payload["items"]:
        first = payload["items"][0]
        assert "run_id" in first
        assert "status" in first
        assert "effective_symbols_count" in first
        assert "close" not in first
```

```python
# quant/tests/contract/test_http_market_data_bars_endpoint.py
from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_get_market_data_bars_returns_ohlcv_items() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get(
        "/v1/market-data/bars",
        params={"symbols": ["600519.SH"], "timeframe": "1d", "start_date": "2026-04-01", "end_date": "2026-04-01"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload
    if payload["items"]:
        first = payload["items"][0]
        assert first["symbol"] == "600519.SH"
        assert "close" in first
        assert "bar_time" in first
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd quant && uv run pytest tests/contract/test_http_market_data_query_endpoint.py tests/contract/test_http_market_data_bars_endpoint.py -q`
Expected: FAIL because `/bars` route and provider do not exist yet.

- [ ] **Step 3: Add schema models and provider wiring**

```python
# quant/src/interfaces/http/schemas_market_data.py
from pydantic import BaseModel, Field


class MarketDataSyncRequest(BaseModel):
    days: int = Field(ge=1)
    end_date: str
    timeframe: str
    symbols: list[str] | None = None
    universe: str | None = None
    request_id: str | None = None


class MarketDataBarsQuery(BaseModel):
    symbols: list[str] | None = None
    timeframe: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(default=5000, ge=1, le=10000)
```

```python
# quant/src/interfaces/http/dependencies.py
from application.market_data.bars_query_service import BarsQueryService

MarketDataBarsService = Callable[..., dict]

def get_market_data_bars_service() -> MarketDataBarsService:
    service = BarsQueryService(bar_store=_build_bar_store())
    return service.query
```

- [ ] **Step 4: Implement the route split**

```python
# quant/src/interfaces/http/routes_market_data.py
from fastapi import APIRouter, Depends, Query

from interfaces.http.dependencies import (
    MarketDataBarsService,
    MarketDataQueryService,
    MarketDataSyncService,
    get_market_data_bars_service,
    get_market_data_query_service,
    get_market_data_sync_service,
)
...

@router.get("/sync-runs")
def get_sync_runs(
    days: int = Query(ge=1),
    timeframe: str | None = None,
    status: str | None = None,
    request_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    service: MarketDataQueryService = Depends(get_market_data_query_service),
) -> dict:
    return service(days=days, timeframe=timeframe, status=status, request_id=request_id, limit=limit)


@router.get("/bars")
def get_bars(
    symbols: list[str] | None = Query(default=None),
    timeframe: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = Query(default=5000, ge=1, le=10000),
    service: MarketDataBarsService = Depends(get_market_data_bars_service),
) -> dict:
    return service(
        symbols=symbols,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd quant && uv run pytest tests/contract/test_http_market_data_query_endpoint.py tests/contract/test_http_market_data_bars_endpoint.py tests/contract/test_http_market_data_sync_endpoint.py tests/contract/test_http_market_data_sync_error_mapping.py tests/contract/test_http_market_data_sync_idempotency.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add quant/src/interfaces/http/schemas_market_data.py quant/src/interfaces/http/routes_market_data.py quant/src/interfaces/http/dependencies.py quant/tests/contract/test_http_market_data_query_endpoint.py quant/tests/contract/test_http_market_data_bars_endpoint.py quant/tests/contract/test_http_market_data_sync_endpoint.py quant/tests/contract/test_http_market_data_sync_error_mapping.py quant/tests/contract/test_http_market_data_sync_idempotency.py
git commit -m "feat: separate market data run and bars http endpoints"
```

### Task 4: CLI Split Between Run Query and Bars Query

**Files:**
- Modify: `cli/src/cmd/data.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/application/handlers/data_query.rs`
- Create: `cli/src/application/handlers/data_bars.rs`
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Modify: `cli/tests/http_data_query_json.rs`
- Modify: `cli/tests/http_data_query_table.rs`
- Create: `cli/tests/http_data_bars_json.rs`
- Create: `cli/tests/http_data_bars_table.rs`
- Create: `cli/tests/http_data_bars_chart.rs`

- [ ] **Step 1: Write the failing CLI tests for the command split**

```rust
// cli/tests/http_data_query_json.rs
use hf_cli::infrastructure::http_client::get_data_sync_runs;
use mockito::Server;

#[test]
fn data_query_json_calls_sync_runs_endpoint_and_returns_run_metadata() {
    let mut server = Server::new();
    let _mock = server
        .mock("GET", "/v1/market-data/sync-runs")
        .match_query(mockito::Matcher::AllOf(vec![
            mockito::Matcher::UrlEncoded("days".into(), "5".into()),
            mockito::Matcher::UrlEncoded("timeframe".into(), "1d".into()),
        ]))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"run_id":"550e8400-e29b-41d4-a716-446655440000","request_id":"req_001","status":"success","days":5,"end_date":"2026-04-01","timeframe":"1d","effective_symbols_count":2,"started_at":"2026-04-01T09:30:00+08:00","finished_at":"2026-04-01T09:31:00+08:00","error_code":null,"error_message":null}]}"#,
        )
        .create();

    let out = get_data_sync_runs(&server.url(), 5, Some("1d"), Some("success"), None, 1000)
        .expect("query should succeed");

    assert_eq!(out["items"][0]["request_id"], "req_001");
    assert!(out["items"][0].get("close").is_none());
}
```

```rust
// cli/tests/http_data_bars_json.rs
use hf_cli::infrastructure::http_client::get_market_data_bars;
use mockito::Server;

#[test]
fn data_bars_json_calls_bars_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("GET", "/v1/market-data/bars")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"symbol":"600519.SH","timeframe":"1d","bar_time":"2026-04-01T15:00:00+08:00","open":1450.0,"high":1468.0,"low":1442.0,"close":1459.44,"volume":29125.0,"amount":4256185472.0,"adj_factor":1.0,"data_source":"tencent"}]}"#,
        )
        .create();

    let out = get_market_data_bars(
        &server.url(),
        Some(&["600519.SH".to_string()]),
        Some("1d"),
        Some("2026-04-01"),
        Some("2026-04-01"),
        Some(200),
        1000,
    )
    .expect("bars query should succeed");

    assert_eq!(out["items"][0]["symbol"], "600519.SH");
    assert_eq!(out["items"][0]["close"], 1459.44);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cli && cargo test --test http_data_query_json --test http_data_bars_json --quiet`
Expected: FAIL because function signatures and `get_market_data_bars` do not exist yet.

- [ ] **Step 3: Extend clap commands and dispatch**

```rust
// cli/src/cmd/data.rs
#[derive(Debug, Subcommand)]
pub enum DataSubcommand {
    Sync(DataSyncArgs),
    Query(DataQueryArgs),
    Bars(DataBarsArgs),
}

#[derive(Debug, Args)]
pub struct DataBarsArgs {
    #[arg(long)]
    pub symbols: Option<String>,
    #[arg(long, default_value = "1m")]
    pub timeframe: String,
    #[arg(long)]
    pub start_date: Option<String>,
    #[arg(long)]
    pub end_date: Option<String>,
    #[arg(long, default_value = "json")]
    pub output: String,
    #[arg(long, default_value_t = false)]
    pub verbose: bool,
    #[arg(long, default_value_t = false)]
    pub no_benchmark: bool,
    #[arg(long)]
    pub limit: Option<i32>,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}
```

```rust
// cli/src/application/dispatch.rs
use crate::application::handlers::{data_bars, data_query, data_sync, pipeline_daily};
...
        Commands::Data(args) => match args.command {
            DataSubcommand::Sync(sync_args) => data_sync::handle(sync_args),
            DataSubcommand::Query(query_args) => data_query::handle(query_args),
            DataSubcommand::Bars(bars_args) => data_bars::handle(bars_args),
        },
```

- [ ] **Step 4: Add HTTP client method and split handlers**

```rust
// cli/src/infrastructure/http_client.rs
pub fn get_market_data_bars(
    server_url: &str,
    symbols: Option<&[String]>,
    timeframe: Option<&str>,
    start_date: Option<&str>,
    end_date: Option<&str>,
    limit: Option<i32>,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!("{}/v1/market-data/bars", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let mut request = client.get(url);
    if let Some(tf) = timeframe {
        request = request.query(&[("timeframe", tf)]);
    }
    if let Some(start) = start_date {
        request = request.query(&[("start_date", start)]);
    }
    if let Some(end) = end_date {
        request = request.query(&[("end_date", end)]);
    }
    if let Some(lim) = limit {
        request = request.query(&[("limit", lim.to_string())]);
    }
    if let Some(list) = symbols {
        for s in list {
            request = request.query(&[("symbols", s)]);
        }
    }
    let response = request.send().map_err(AppError::HttpClient)?;
    let status_code = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status_code.is_success() {
        let body = serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status_code.as_u16(), body));
    }
    serde_json::from_str(&body_text).map_err(AppError::InvalidJson)
}
```

```rust
// cli/src/application/handlers/data_query.rs
match args.output.as_str() {
    "json" => print!("{out}"),
    "table" => {
        let table = render_sync_runs_table(&out, args.verbose);
        print!("{table}");
    }
    other => {
        return Err(AppError::InvalidArgs(format!(
            "unsupported --output value for data query: {other} (expected: json|table)"
        )));
    }
}
```

```rust
// cli/src/application/handlers/data_bars.rs
use crate::cmd::data::DataBarsArgs;
use crate::error::AppError;
use crate::infrastructure::chart_renderer::render_sync_runs_chart;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_market_data_bars;
use crate::infrastructure::table_renderer::render_market_data_table;
use crate::infrastructure::tui_renderer::render_sync_runs_tui;

pub fn handle(args: DataBarsArgs) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let symbols = args.symbols.as_ref().map(|raw| {
        raw.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect::<Vec<_>>()
    });
    let out = get_market_data_bars(
        &cfg.server_url,
        symbols.as_deref(),
        Some(args.timeframe.as_str()),
        args.start_date.as_deref(),
        args.end_date.as_deref(),
        args.limit,
        timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => print!("{}", render_market_data_table(&out, args.verbose)),
        "chart" => print!("{}", render_sync_runs_chart(&out, symbols.as_ref().and_then(|v| v.first()).map(|s| s.as_str()).unwrap_or("UNKNOWN"), if args.no_benchmark { None } else { Some("000300.SH") }).map_err(AppError::InvalidArgs)?),
        "tui" => render_sync_runs_tui(&out, symbols.as_ref().and_then(|v| v.first()).map(|s| s.as_str()), if args.no_benchmark { None } else { Some("000300.SH") }).map_err(AppError::InvalidArgs)?,
        other => return Err(AppError::InvalidArgs(format!("unsupported --output value for data bars: {other} (expected: json|table|chart|tui)"))),
    }
    Ok(())
}
```

- [ ] **Step 5: Make the table renderer explicit instead of auto-detecting item shape**

```rust
// cli/src/infrastructure/table_renderer.rs
pub fn render_market_data_table(payload: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("bar_time"),
            Cell::new("symbol"),
            Cell::new("timeframe"),
            Cell::new("close"),
        ]);
    ...
    format!("Market Data\n{}\n", table)
}

pub fn render_sync_runs_table(payload: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("end_date"),
            Cell::new("status"),
            Cell::new("timeframe"),
            Cell::new("symbols_count"),
            Cell::new("run_id"),
            Cell::new("request_id"),
        ]);
    ...
    format!("Sync Runs\n{}\n", table)
}
```

- [ ] **Step 6: Run CLI tests to verify they pass**

Run: `cd cli && cargo test --test http_data_query_json --test http_data_query_table --test http_data_bars_json --test http_data_bars_table --test http_data_bars_chart --quiet`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add cli/src/cmd/data.rs cli/src/application/dispatch.rs cli/src/application/handlers/mod.rs cli/src/application/handlers/data_query.rs cli/src/application/handlers/data_bars.rs cli/src/infrastructure/http_client.rs cli/src/infrastructure/table_renderer.rs cli/tests/http_data_query_json.rs cli/tests/http_data_query_table.rs cli/tests/http_data_bars_json.rs cli/tests/http_data_bars_table.rs cli/tests/http_data_bars_chart.rs
git commit -m "feat: split cli market data run and bars queries"
```

### Task 5: Final Verification and Docs Refresh

**Files:**
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`

- [ ] **Step 1: Update CLI examples to match the new command split**

```md
## hf data query --output table

用于查看同步任务运行记录。

## hf data bars --output chart

用于查看行情 bars 明细与趋势图。
```

- [ ] **Step 2: Run Python market-data test slice**

Run: `cd quant && uv run pytest tests/unit/market_data tests/contract/test_http_market_data_sync_endpoint.py tests/contract/test_http_market_data_sync_error_mapping.py tests/contract/test_http_market_data_sync_idempotency.py tests/contract/test_http_market_data_query_endpoint.py tests/contract/test_http_market_data_bars_endpoint.py tests/integration/test_l1_timescale_migration.py -q`
Expected: PASS

- [ ] **Step 3: Run CLI market-data test slice**

Run: `cd cli && cargo test --test http_data_sync --test http_data_query_json --test http_data_query_table --test http_data_bars_json --test http_data_bars_table --test http_data_bars_chart --quiet`
Expected: PASS

- [ ] **Step 4: Run architecture gate**

Run: `make architecture-check`
Expected: PASS

- [ ] **Step 5: Run full project gate**

Run: `make check`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/CLI_OUTPUT_EXAMPLES.md
git commit -m "docs: refresh cli examples for split market data queries"
```
