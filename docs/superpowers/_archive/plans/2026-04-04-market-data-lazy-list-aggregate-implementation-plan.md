# Market Data Lazy List + Bars Aggregate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 `docs/superpowers/specs/2026-04-04-market-data-lazy-list-aggregate-design.md`：新增 `GET /v1/market-data/instruments`；将 `GET /v1/market-data/bars` 的 `timeframe` 改为 **输出桶宽**，服务端从存储最细粒度（默认 `1m`）读取后在 **domain/application** 聚合；支持游标分页、`session_date` 分时（`asc`）、§5.2 多周期与周/月/年；CLI/TUI 与契约测试同步。

**Architecture:** `interfaces/http` 只做参数解析与 DTO；**domain** 存放 SSE 日历、分桶边界、OHLC 合并、分时裁剪、5m/15m/… 会话内分桶、周/月/年「先日再合并」的纯函数（可单测）；**application** 编排「读原始 1m → 聚合 → 排序 → 游标切片」；**TimescaleBarStore** 新增 **按存储粒度** 读取方法，**保留**现有 `list_bars(timeframe=…)` 供 factor/pipeline 等内部直连库内 `1d`/`1m` 行，避免误伤研究链路。

**Tech Stack:** Python 3.12+、FastAPI、PostgreSQL/Timescale、`zoneinfo`/`datetime`（`Asia/Shanghai`）、可选依赖 **`exchange-calendars`**（推荐，SSE 交易日）或自维护节假日表（须在测试中固定行为）；Rust CLI `reqwest`、现有 `hf data` / `hf tui` 结构。

**Worktree（仓库强约束）：** 按 `AGENTS.md`，多文件跨层实现应在 **`.worktrees/`** 下独立分支进行；本计划默认执行环境为已创建的 worktree（或维护者书面豁免说明）。

---

## 文件结构（新增 / 修改一览）

| 路径 | 职责 |
|------|------|
| `quant/src/domain/market_data/sse_calendar.py`（新） | SSE 交易日判定、区间内枚举；无 IO |
| `quant/src/domain/market_data/bars_bucket.py`（新）或拆分为 `bars_ohlc.py` + `bars_timeframes.py` | §5.1 OHLC 合并；§5.2 分时裁剪、多周期分桶、ISO 周/月/年二次聚合；`volume`/`amount`：建议 **None 当 0 参与求和，全 None 则输出 None**（与 spec「implementation-plan 写死」一致） |
| `quant/src/domain/market_data/ports.py` | `BarStore` 增加 `list_storage_bars(...)`（或等价命名），**不按「输出 timeframe」筛库** |
| `quant/src/interfaces/adapters/market_data/timescale_bar_store.py` | 实现 `list_storage_bars`；**保留** `list_bars` 现有 SQL 语义 |
| `quant/src/application/market_data/bars_query_service.py` | 扩展为：解析窗口、禁止多标的+游标（首版）、调用 `list_storage_bars`、domain 聚合、`session_date` 分时分支 **`bar_time asc`**、默认 **`desc` + next_cursor** |
| `quant/src/application/market_data/instruments_list_service.py`（新） | `mode=universe|db` 列表 + `cursor_symbol` 分页 |
| `quant/src/interfaces/http/routes_market_data.py` | `GET /instruments`；`get_bars` 增加 `session_date`、`cursor_bar_time`、`cursor_symbol` 等 |
| `quant/src/interfaces/http/dependencies.py` | 装配新 service；`MarketDataBarsQueryService` / `MarketDataInstrumentsQueryService` 类型别名 |
| `quant/tests/unit/market_data/test_bars_bucket*.py`（新） | 分时裁剪、5m 首根锚点 `09:35+08`、月 K open=首交易日日 open、周 ISO 界 |
| `quant/tests/unit/market_data/test_bars_query_service.py` | 更新为 mock 新 store 方法 + 聚合行为 |
| `quant/tests/contract/test_http_market_data_bars_endpoint.py` | 新 query 形状、可选 `next_cursor_*` |
| `quant/tests/contract/test_http_market_data_instruments_endpoint.py`（新） | instruments 契约 |
| `quant/tests/architecture/` | 若有新 domain 包路径，更新允许规则 |
| `cli/src/infrastructure/http_client.rs` | `get_market_data_instruments`、`get_market_data_bars` 增加 query 参数 |
| `cli/src/application/requests.rs` / `handlers` | `data` 子命令与 TUI 请求体 |
| `cli/src/application/tui_app.rs` | 首屏 `instruments` + 选中后再 `bars` + 表格游标循环（与 spec §7 一致） |
| `cli/tests/` | mock server 覆盖 instruments + bars 游标 |
| `docs/ARCHITECTURE.md`、`AGENTS.md`、`CLAUDE.md`、`docs/CLI_OUTPUT_*` | 仅当 JSON 契约或对外行为变更时按需更新 |

---

### Task 1: Domain — SSE 交易日历

**Files:**
- Create: `quant/src/domain/market_data/sse_calendar.py`
- Create: `quant/tests/unit/market_data/test_sse_calendar.py`
- Modify: `quant/src/domain/market_data/__init__.py`（如需导出）
- Modify: `quant/pyproject.toml`（若加入 `exchange-calendars`）

- [ ] **Step 1: 选定日历数据源并写失败用例**

在 `test_sse_calendar.py` 中固定若干日期（例如 2026-01-01 元旦休市、2026-01-05 假设为交易日——以你选定日历库实际结果为准，**断言与库一致**）：

```python
def test_sse_is_trading_day_known_holiday() -> None:
    from domain.market_data.sse_calendar import is_sse_trading_day
    assert is_sse_trading_day("2026-01-01") is False
```

运行：`cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/market_data/test_sse_calendar.py -v`  
预期：**FAIL**（模块不存在）。

- [ ] **Step 2: 实现 `is_sse_trading_day(date_str: str) -> bool` 与 `iter_sse_trading_days(start, end)`**

使用 `exchange_calendars.get_calendar("XSHG")`（或 spec 允许的等价物）；**禁止**在函数内访问 HTTP/DB。

- [ ] **Step 3: 测试通过**

运行同上 pytest，预期：**PASS**。

- [ ] **Step 4: Commit**

```bash
git add quant/src/domain/market_data/sse_calendar.py quant/tests/unit/market_data/test_sse_calendar.py quant/pyproject.toml
git commit -m "feat: 增加 SSE 交易日历纯函数与单测"
```

---

### Task 2: Domain — OHLC 与 §5.2 分桶（核心）

**Files:**
- Create: `quant/src/domain/market_data/bars_aggregate.py`（名称可调整，保持单一职责）
- Create: `quant/tests/unit/market_data/test_bars_aggregate.py`

- [ ] **Step 1: 测试 — 单桶 OHLC（§5.1）**

```python
def test_merge_ohlc_bucket_three_minutes() -> None:
    from domain.market_data.bars_aggregate import merge_ohlc_sequence
    rows = [
        {"open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100.0},
        {"open": 10.5, "high": 12.0, "low": 10.0, "close": 11.5, "volume": None},
        {"open": 11.5, "high": 11.8, "low": 11.2, "close": 11.6, "volume": 200.0},
    ]
    out = merge_ohlc_sequence(rows)
    assert out == {
        "open": 10.0,
        "high": 12.0,
        "low": 9.5,
        "close": 11.6,
        "volume": 300.0,
    }
```

运行 pytest，预期：**FAIL**。

- [ ] **Step 2: 实现 `merge_ohlc_sequence` + `aggregate_to_1d`（分钟→日，§5.1）**

输入为已按 `bar_time` 升序的 dict 列表（含 `bar_time` ISO 字符串）；按 SSE 交易日分桶；`bar_time` 输出 **`T15:00+08`**。

- [ ] **Step 3: 测试 — 分时裁剪（§5.2.2）**

构造某日 `1m` 行：`08:00`、`09:31`、`12:00`、`15:00` 等；`filter_intraday_session(rows, session_date)` 只保留 9:30–11:30、13:00–15:00（+08）内（集合竞价分钟若存在则保留，见 spec）。

- [ ] **Step 4: 测试 — 5m 锚点（§5.2.3）**

同一交易日：`09:30–09:35` 桶的锚点为 `09:35+08`；上午末桶覆盖至 `11:30`；下午自 `13:00` 起。

- [ ] **Step 5: 测试 — 月 K 先日再月（§5.2.5）**

同一公历月两个交易日两根「日 K」：`open` 取第一交易日日 K 的 open，`close` 取最后交易日；锚点为 **最后交易日 15:00+08**。

- [ ] **Step 6: 测试 — 周 K ISO（§5.2.4）**

两周边界跨 ISO 周时，周数与锚点符合 spec。

- [ ] **Step 7: 对外入口 `aggregate_storage_rows(output_timeframe, rows, *, session_date=None, sort_output_desc=True)`**

将 `1m` 存储行路由到：`1m` 透传/截整分、`5m`/`15m`/…、`1d`、`1w`、`1M`、`1y`；（`1Q` 可 **NotImplemented** 留 Task 4 返回 422）。

- [ ] **Step 8: pytest 全通过 + commit**

```bash
cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/market_data/test_bars_aggregate.py -v
git add quant/src/domain/market_data/bars_aggregate.py quant/tests/unit/market_data/test_bars_aggregate.py
git commit -m "feat: 行情 K 线分桶与 OHLC 聚合 domain 规则"
```

---

### Task 3: BarStore — 按存储粒度读取

**Files:**
- Modify: `quant/src/domain/market_data/ports.py`
- Modify: `quant/src/interfaces/http/dependencies.py`（Fake/stub 如有）
- Modify: `quant/src/interfaces/adapters/market_data/timescale_bar_store.py`
- Modify: `quant/tests/unit/market_data/test_timescale_bar_store_v2.py`（或新增用例文件）

- [ ] **Step 1: 扩展 Protocol**

```python
def list_storage_bars(
    self,
    symbols: list[str] | None = None,
    storage_timeframe: str = "1m",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    order: str = "asc",  # "asc" | "desc"
) -> list[dict]:
    ...
```

- [ ] **Step 2: SQL 实现**

`where timeframe = %s` 使用 **`storage_timeframe`**；**不得**把「请求的输出 timeframe」传入此方法。

- [ ] **Step 3: 单测**（可用 mock connection 或现有测试夹具）验证 `order`、`storage_timeframe` 传入正确。

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: BarStore 支持按存储粒度 list_storage_bars"
```

---

### Task 4: Application — Bars 查询编排 + 422 规则

**Files:**
- Modify: `quant/src/application/market_data/bars_query_service.py`
- Modify: `quant/tests/unit/market_data/test_bars_query_service.py`

- [ ] **Step 1: 更新 fake store**

Fake 实现 `list_storage_bars`，返回可控 `1m` 序列。

- [ ] **Step 2: 测试 — `timeframe=1d` 走聚合**

`query(..., timeframe="1d")` 应调用 `list_storage_bars(storage_timeframe="1m", ...)` 一次（或文档化窗口扩大策略），再经 domain 得 `1d`。

- [ ] **Step 3: 测试 — `session_date` 分时 `asc`**

带 `session_date` 时结果按时间升序；且调用域内裁剪。

- [ ] **Step 4: 测试 — 多标的 + 游标禁止**

`symbols` 长度 > 1 且提供 `cursor_bar_time` → 抛 `ValueError` 或由路由转 **422** `code=BARS_CURSOR_MULTI_SYMBOL`（与实现一致即可，**整仓统一**）。

- [ ] **Step 5: 测试 — 过细 timeframe**

`timeframe="1s"` 且仅有 `1m` 存储 → **422**（在 service 层 `ValueError` + 路由捕获，或直接 HTTPException）。

- [ ] **Step 6: 实现 `BarsQueryService.query` 完整签名**

对齐路由：`symbols, timeframe, start_date, end_date, limit, session_date, cursor_bar_time, cursor_symbol`。

- [ ] **Step 7: Commit**

```bash
git commit -m "feat: BarsQueryService 业务层聚合与游标校验"
```

---

### Task 5: HTTP — `GET /bars` 参数与响应

**Files:**
- Modify: `quant/src/interfaces/http/routes_market_data.py`
- Modify: `quant/src/interfaces/http/dependencies.py`
- Modify: `quant/tests/contract/test_http_market_data_bars_endpoint.py`

- [ ] **Step 1: 契约测试扩展**

Stub 增加 `session_date`、`cursor_bar_time` 捕获；断言响应含 `next_cursor_bar_time`（有下一页时）或 `null`。

- [ ] **Step 2: 路由 Query 参数**

与 OpenAPI 描述同步（破坏性变更说明）。

- [ ] **Step 3: 错误码枚举**

文档化：`TIMEFRAME_FINER_THAN_STORAGE`、`BARS_CURSOR_MULTI_SYMBOL`、`SESSION_DATE_NOT_TRADING_DAY`（名称以代码为准）。

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: market-data bars HTTP 参数与游标响应"
```

---

### Task 6: Application + HTTP — `GET /instruments`

**Files:**
- Create: `quant/src/application/market_data/instruments_list_service.py`
- Modify: `quant/src/interfaces/http/routes_market_data.py`
- Create: `quant/tests/contract/test_http_market_data_instruments_endpoint.py`
- Modify: `quant/src/interfaces/http/dependencies.py`

- [ ] **Step 1: 契约测试**

`mode=universe&universe=csi300&limit=10` → `items` + `has_more` + `next_cursor_symbol`（字段名与 spec §6.1 定稿一致）。

- [ ] **Step 2: `mode=db`**

默认 7 自然日回窗、`min_bars`、`storage_timeframe` 过滤逻辑按 spec。

- [ ] **Step 3: universe 解析**

复用现有服务端 universe 文件解析逻辑（与 sync/CLI 一致的路径）。

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: GET /v1/market-data/instruments 列表与分页"
```

---

### Task 7: 架构测试与内部 Stub 对齐

**Files:**
- Modify: `quant/tests/architecture/` 下相关用例
- Modify: `quant/src/interfaces/http/dependencies.py` 内 `_FakeBarStore` / 测试 double（若有）

- [ ] **Step 1:** `make architecture-check` 失败则按报错补依赖边。

- [ ] **Step 2:** `cd quant && uv run python -m pytest tests/unit/market_data tests/contract/test_http_market_data_bars_endpoint.py tests/contract/test_http_market_data_instruments_endpoint.py -q`

- [ ] **Step 3: Commit**（若仅有测试小改可并入前序 commit，避免空 commit）

---

### Task 8: Rust CLI / TUI

**Files:**
- Modify: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/application/services/market_data.rs`（或等价）
- Modify: `cli/src/application/handlers/data_bars.rs`、`data_market_query.rs`（若存在）
- Modify: `cli/src/application/tui_app.rs`
- Modify: `cli/tests/architecture_rules.rs`（若新增模块路径）
- Add: `cli/tests/http_market_data_instruments.rs`（mock）

- [ ] **Step 1: `get_market_data_instruments`**

Query：`mode`, `universe`, `start_date`, `end_date`, `min_bars`, `storage_timeframe`, `limit`, `cursor_symbol`。

- [ ] **Step 2: `get_market_data_bars` 扩展**

`session_date`, `cursor_bar_time`, `cursor_symbol`。

- [ ] **Step 3: TUI 流程**

启动 → `instruments` 拉首屏 → 用户选择 symbol → `bars` 带游标循环直至 `has_more=false`（表格模式）；线图仍可用单页 `limit` + 客户端 `aggregate_ohlc_time_order`（`cli/src/domain/bars_aggregate.rs`）——与 spec §7 不冲突。

- [ ] **Step 4: `hf data bars` / `hf data query`**

帮助文案与默认参数反映新语义（输出 timeframe ≠ 存储粒度）。

- [ ] **Step 5: `cd cli && cargo test`**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: CLI/TUI 对接 instruments 与 bars 游标"
```

---

### Task 9: 全量验证与文档

**Files:**
- Modify: `docs/ARCHITECTURE.md`、`AGENTS.md`（§7.6 接口列表）、`docs/CLI_OUTPUT_EXAMPLES.md` / `CLI_OUTPUT_SCHEMA.json`（**仅当** CLI JSON 字段变化）

- [ ] **Step 1:** `make check`

- [ ] **Step 2:** 更新对外文档中「`timeframe` = 库内粒度」的旧表述。

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: 行情 bars timeframe 语义与 instruments 接口说明"
```

---

## Plan 自检（对照 spec）

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §5.1 OHLC / `1d` / 时区 | Task 2 |
| §5.2 分时、5–60m、周/月/年、可选季 | Task 2、4、5 |
| §6.1 instruments | Task 6 |
| §6.2 bars 破坏性语义、session_date、游标、排序例外 | Task 3–5 |
| §7 TUI/CLI | Task 8 |
| §8 测试门禁 | 各 Task 内嵌 + Task 9 `make check` |
| §9 迁移文档 | Task 9 |
| 多标的+游标禁止 | Task 4 |

**占位扫描：** 本计划未使用「TBD / 稍后 / 类似 Task N」作为省略实现理由；日历库选定后测试数据需与库一致，避免硬编码错误假日。

**类型一致性：** HTTP、`BarsQueryService.query`、`BarStore.list_storage_bars` 使用相同的 `session_date`、`cursor_bar_time` 命名。

---

## 执行交接

**Plan 已保存至** `docs/superpowers/plans/2026-04-04-market-data-lazy-list-aggregate-implementation-plan.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每任务派生子代理，任务间人工复核；技能：`superpowers:subagent-driven-development`。
2. **本会话内顺序执行** — 技能：`superpowers:executing-plans`，按 Task 检查点推进。

你更倾向哪一种？若继续在本会话实现，请先按 `AGENTS.md` 在 **`.worktrees/`** 建 worktree（除非已书面豁免），再从 **Task 1** 开始。
