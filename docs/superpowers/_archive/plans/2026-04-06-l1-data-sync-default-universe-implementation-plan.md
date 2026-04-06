# L1 Data Sync — Default Universe & Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使任意 `quant/config/universes/{name}.txt`（含 `default`）可作为 bar sync 的 `--universe` 参数；新增 `GET /v1/market-data/coverage` 与 `hf data coverage`，用于对比 universe 与库内 1d K 线覆盖；Makefile 提供 `make sync-default` 便捷同步近窗日线。

**Architecture:** `SyncService._parse_universe_file` 统一走 `domain.universe.universe_loader.load_universe`，并在应用层做与旧路径一致的**代码规范化与去重**（`norm_exchange_symbol` + sorted set），缺失文件映射为 `ValueError` 以保持 `POST /v1/market-data/sync` 的 422 语义不变。覆盖率逻辑放在 `application/market_data/coverage_service.py`（纯函数 + `BarStore` 端口），HTTP 路由 thin wrapper；CLI 仿 `get_market_data_instruments` 的 GET + query 模式。

**Tech Stack:** Python 3 / FastAPI / domain `BarStore` 协议；Rust clap + reqwest（`http_client`）；TimescaleDB（`TimescaleBarStore.list_symbols_with_min_bars_in_window`）。

**设计评审摘要（相对 spec 的修正点，实现时必须遵守）：**

1. **`load_universe` 与旧 `list_symbols_from_universe_file` 的差异**：后者对每个代码调用 `norm_exchange_symbol` 并 `sorted(set(...))`；前者仅读行。若只 `return load_universe(universe)`，会改变既有 universe 的**顺序/去重/校验**行为。实现须在 `_parse_universe_file` 内对 `load_universe` 结果做与旧逻辑等价的规范化与去重；空结果抛 `ValueError`。
2. **缺失文件异常**：`load_universe` 抛 `FileNotFoundError`；`post_sync` 仅显式捕获 `ValueError` → 422。须在 `_parse_universe_file` 内将 `FileNotFoundError` **转换**为 `ValueError`（消息可与原 `unknown universe` 对齐），否则会变成 500。
3. **Contract 测试 patch 路径**：spec 中 `patch("...routes_market_data._get_coverage")` 不可行（`_get_coverage` 仅为函数内局部别名）。应在 `routes_market_data.py` **模块顶层**绑定可 patch 的名字（例如 `from application.market_data.coverage_service import get_coverage as run_coverage_query`），测试中 `patch("interfaces.http.routes_market_data.run_coverage_query", ...)`。
4. **覆盖率对比维度**：`covered`/`missing` 集合须基于**规范化后**的代码与 DB 返回集合对比，避免大小写或格式不一致导致误判。
5. **回归测试文件**：仓库中无 `test_sync_service.py`；请在 `quant/tests/unit/market_data/test_sync_service_v2.py`（或同目录既有 sync 单测文件）中追加用例。
6. **`list_symbols_with_min_bars_in_window` 上限**：`limit=10_000` 对当前 28 只足够；若未来超大 universe，需分页拉全量（本计划不实现，可在代码注释中注明）。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `quant/src/application/market_data/sync_service.py` | `_parse_universe_file` 改用语义化 loader + 规范化/去重 + 异常映射 |
| `quant/src/application/market_data/coverage_service.py` | `get_coverage(...)`：universe ∩ DB 符号差集 |
| `quant/src/interfaces/http/routes_market_data.py` | `GET /v1/market-data/coverage`；顶层 import 便于测试 patch |
| `quant/tests/unit/market_data/test_coverage_service.py` | coverage 纯函数单测 |
| `quant/tests/contract/test_http_coverage_endpoint.py` | 路由与 503/422 契约 |
| `quant/tests/unit/market_data/test_sync_service_v2.py` | `universe=default`（或 monkeypatch loader）回归 |
| `cli/src/application/requests.rs` | `DataCoverageRequest` + `AppCommand::DataCoverage` |
| `cli/src/cmd/data.rs` | `DataSubcommand::Coverage`、clap Args、`From` 实现 |
| `cli/src/cmd/mod.rs` | `Commands::Data` 分支映射 |
| `cli/src/application/dispatch.rs` | `data_coverage::handle` |
| `cli/src/application/handlers/mod.rs` | `pub mod data_coverage` |
| `cli/src/application/handlers/data_coverage.rs` | 编排 + table/json 输出 |
| `cli/src/infrastructure/http_client.rs` | `get_market_data_coverage(...)` |
| `Makefile` | `sync-default` target |

---

### Task 1: SyncService — `_parse_universe_file` 统一 loader

**Files:**

- Modify: `quant/src/application/market_data/sync_service.py`
- Test: `quant/tests/unit/market_data/test_sync_service_v2.py`

- [ ] **Step 1: 写失败单测（default universe 不再因白名单被拒）**

在 `test_sync_service_v2.py` 增加：对 `application.market_data.sync_service.load_universe` 做 `monkeypatch`（实现须在 `sync_service.py` **模块顶层** `from domain.universe.universe_loader import load_universe`，以便可替换）；使 `name == "default"` 时返回 `["600519.SH"]`；构造 `SyncService` + `_FakeBarStore`/`_FakeQuoteRepo`（与文件内既有模式一致）；调用 `sync(..., universe="default", ...)`；断言 `selection_mode == "universe"` 且 `effective_symbols_count == 1`。在实现前运行应失败（当前会因 `unknown universe` 或等价错误失败）。

```python
def test_sync_service_accepts_default_universe_via_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    def _load(name: str) -> list[str]:
        if name == "default":
            return ["600519.SH"]
        raise AssertionError(f"unexpected universe {name}")

    monkeypatch.setattr(
        "application.market_data.sync_service.load_universe",
        _load,
    )
    svc = SyncService(quote_repo=_FakeQuoteRepo(), bar_store=_FakeBarStore())
    out = svc.sync(days=1, end_date="2026-04-01", timeframe="1d", universe="default")
    assert out["selection_mode"] == "universe"
    assert out["effective_symbols_count"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/market_data/test_sync_service_v2.py::test_sync_service_accepts_default_universe_via_loader -v`

Expected: FAIL（与当前白名单/`list_symbols_from_universe_file` 行为一致的错误）

- [ ] **Step 3: 最小实现**

在 `sync_service.py` **文件顶部**增加 `from domain.universe.universe_loader import load_universe`（供测试 monkeypatch）。在 `_parse_universe_file` 中：

- `try: raw = load_universe(universe) except FileNotFoundError as exc: raise ValueError(f"unknown universe: {universe}") from exc`
- `normalized = sorted({self._norm_symbol(s) for s in raw if s and str(s).strip()})`（`_norm_symbol` 已调用 `norm_exchange_symbol`）
- `if not normalized: raise ValueError(f"universe {universe} has no symbols")`
- `return normalized`

移除对 `list_symbols_from_universe_file` 的调用；保留文件顶部 `_UNIVERSE_KEYS` 导入（`_write_universe_file` 仍需要）。

- [ ] **Step 4: 运行单测通过**

Run: `cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/market_data/test_sync_service_v2.py::test_sync_service_accepts_default_universe_via_loader -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/src/application/market_data/sync_service.py quant/tests/unit/market_data/test_sync_service_v2.py
git commit -m "fix: bar sync universe 解析改用 load_universe 并保留规范化语义"
```

---

### Task 2: CoverageService — `get_coverage`

**Files:**

- Create: `quant/src/application/market_data/coverage_service.py`
- Test: `quant/tests/unit/market_data/test_coverage_service.py`

- [ ] **Step 1: 写失败单测**

新建 `test_coverage_service.py`，包含 spec 中 `test_full_coverage` / `test_partial_coverage` / `test_empty_db` / `test_unknown_universe`；将 `monkeypatch` 目标设为 `application.market_data.coverage_service.load_universe`（实现文件内顶层 import 后）。`bar_store` 用 `MagicMock`，`list_symbols_with_min_bars_in_window.return_value = (symbols, False)`。

实现中应对 `load_universe` 返回的每条做 `norm_exchange_symbol`（与 sync 一致），再构造 `universe_set`；`db_covered` 来自 store 的 tuple 第一个元素，转为 `set` 后与 `universe_set` 求交/差。

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/market_data/test_coverage_service.py -v`

Expected: 收集错误或 import 失败

- [ ] **Step 3: 实现 `get_coverage`**

按 spec 第二节结构实现，补充：

- `from application.market_data.universe_symbols import norm_exchange_symbol`
- 构建 `universe_symbols`：`sorted({norm_exchange_symbol(line) for line in load_universe(universe) if line and str(line).strip()})`；若为空抛 `ValueError` 或与 sync 一致的文案（单测若期望 `FileNotFoundError` 仅针对 `load_universe` 直接抛出，则空文件可不单独测）
- `bar_store.list_symbols_with_min_bars_in_window` 参数名与 `domain/market_data/ports.py` 一致：`storage_timeframe="1d"`, `start_date`, `end_date`, `min_bars`, `after_symbol=None`, `limit=10_000`

- [ ] **Step 4: 单测通过**

Run: `cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/unit/market_data/test_coverage_service.py -v`

- [ ] **Step 5: 提交**

```bash
git add quant/src/application/market_data/coverage_service.py quant/tests/unit/market_data/test_coverage_service.py
git commit -m "feat: 新增 market data coverage 应用服务与单测"
```

---

### Task 3: HTTP `GET /v1/market-data/coverage`

**Files:**

- Modify: `quant/src/interfaces/http/routes_market_data.py`
- Create: `quant/tests/contract/test_http_coverage_endpoint.py`

- [ ] **Step 1: 写契约测试（先失败）**

`test_http_coverage_endpoint.py`：

- `TestClient(app)`
- 在模块顶部无需 patch import；测试内 `patch("interfaces.http.routes_market_data.run_coverage_query")`（名称与实现一致即可）
- `test_coverage_ok`：`has_db_config=True`，mock `open_db_connection_from_env`、`TimescaleBarStore`（若路由仍实例化 store），`run_coverage_query.return_value = {...}`；`GET /v1/market-data/coverage?universe=default&start_date=2025-04-06&end_date=2026-04-06` → 200，`coverage_rate == 1.0`
- `test_coverage_db_unavailable`：`has_db_config=False` → 503，`detail["code"] == "COVERAGE_DB_UNAVAILABLE"`
- `test_coverage_universe_missing`：`run_coverage_query` 侧不调用；让真实 `get_coverage` 触发 `FileNotFoundError` 较难时，可改为 patch `run_coverage_query` 抛 `FileNotFoundError` 并在路由中转换为 422，或 patch `load_universe`；推荐路由内 `except FileNotFoundError` → 422 `COVERAGE_UNIVERSE_NOT_FOUND` 并加对应断言测试

- [ ] **Step 2: 运行失败**

Run: `cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/contract/test_http_coverage_endpoint.py -v`

- [ ] **Step 3: 实现路由**

在 `routes_market_data.py` 顶层增加：

```python
from application.market_data.coverage_service import get_coverage as run_coverage_query
```

处理函数内：`if not has_db_config():` → 503；否则 `TimescaleBarStore(open_db_connection_from_env())`，调用 `run_coverage_query(universe=..., bar_store=..., start_date=..., end_date=..., min_bars=...)`；`except FileNotFoundError` → 422。避免在路由内写业务比较逻辑（保持 thin）。

- [ ] **Step 4: 契约测试通过**

Run: `cd /Users/rongts/HiveFlow/quant && uv run python -m pytest tests/contract/test_http_coverage_endpoint.py -v`

- [ ] **Step 5: 提交**

```bash
git add quant/src/interfaces/http/routes_market_data.py quant/tests/contract/test_http_coverage_endpoint.py
git commit -m "feat: 新增 GET /v1/market-data/coverage 端点与契约测试"
```

---

### Task 4: Rust CLI — `hf data coverage`

**Files:**

- Modify: `cli/src/infrastructure/http_client.rs`
- Create: `cli/src/application/handlers/data_coverage.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/application/dispatch.rs`
- Modify: `cli/src/cmd/data.rs`
- Modify: `cli/src/cmd/mod.rs`

- [ ] **Step 1: 新增 `get_market_data_coverage`（可先写最小实现再 `cargo test` 相关模块）**

在 `http_client.rs` 参照 `get_market_data_instruments`：`GET {server}/v1/market-data/coverage`，query：`universe`, `start_date`, `end_date`, `min_bars`（若 `Some`）；非 2xx → `AppError::Upstream`。

- [ ] **Step 2: `DataCoverageRequest` 与 clap**

`requests.rs` 增加 `DataCoverageRequest { universe, start_date, end_date, min_bars: Option<i32>, output: String, timeout_ms: Option<u64> }`；`AppCommand::DataCoverage(DataCoverageRequest)`。

`data.rs`：`Coverage(DataCoverageArgs)`，`#[arg(long, default_value = "json")] output: String`，必填 `universe` / `start_date` / `end_date`，可选 `min_bars`（默认服务端 1）、`timeout_ms`。

`cmd/mod.rs` 的 `Data` 分支：`DataSubcommand::Coverage(a) => AppCommand::DataCoverage(a.into())`。

- [ ] **Step 3: `data_coverage::handle`**

与 spec 第四节一致：`load_default_config`，`get_market_data_coverage`，`output == "table"` 时打印摘要表，否则 `serde_json::to_string_pretty` 打印 stdout。错误路径沿用 `AppError`（上游 422/503 打印 body 由既有 `AppError` 显示逻辑处理，勿重复造轮子）。

- [ ] **Step 4: `dispatch` 与 `mod.rs`**

注册 `data_coverage::handle`。

- [ ] **Step 5: 编译与 Rust 测试**

Run: `cd /Users/rongts/HiveFlow && make rust-test`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add cli/src/infrastructure/http_client.rs cli/src/application/handlers/data_coverage.rs cli/src/application/handlers/mod.rs cli/src/application/requests.rs cli/src/application/dispatch.rs cli/src/cmd/data.rs cli/src/cmd/mod.rs
git commit -m "feat: CLI 新增 hf data coverage 子命令"
```

---

### Task 5: Makefile — `sync-default`

**Files:**

- Modify: `Makefile`

- [ ] **Step 1: 增加 target**

按 spec 第五节写入 `TODAY`、`SYNC_DAYS`、`sync-default`，依赖注释说明需已 `cargo build` 且 `hf` 在 `./cli/target/debug/hf`。

- [ ] **Step 2: 提交**

```bash
git add Makefile
git commit -m "chore: Makefile 增加 sync-default 便捷目标"
```

---

### Task 6: 全量验证

- [ ] **Step 1: 架构门禁**

Run: `cd /Users/rongts/HiveFlow && make architecture-check`

- [ ] **Step 2: 全量 check**

Run: `cd /Users/rongts/HiveFlow && make check`

Expected: 全部通过

- [ ] **Step 3: 若有 CLI 合同校验要求**

本功能服务端返回的为**业务 JSON**，与 `hf data sync` 类似直接打印上游 body；若项目要求所有子命令必须包一层 `CLI_OUTPUT_SCHEMA` 信封，则须另开任务改 schema（**本计划假设与 `data sync` 一致：原始 JSON**）。若 `make check` 未要求则可不改动。

---

## Self-Review（计划自检）

| Spec 章节 | 对应 Task |
|-----------|-----------|
| Section 1 SyncService loader | Task 1 + 评审修正（规范化、FileNotFoundError→ValueError） |
| Section 2 CoverageService | Task 2 + 评审修正（norm_exchange_symbol） |
| Section 3 HTTP | Task 3 + 评审修正（可 patch 的顶层符号） |
| Section 4 Rust CLI | Task 4 |
| Section 5 Makefile | Task 5 |
| Section 6 测试 | Task 1–3 |

**Placeholder 扫描：** 无 TBD。**类型/命名：** `run_coverage_query` 为计划中统一可 patch 名称，实现时与测试保持一致即可。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-06-l1-data-sync-default-universe-implementation-plan.md`.

**1. Subagent-Driven（推荐）** — 每任务独立子代理，任务间人工复核，迭代快。

**2. Inline Execution** — 本会话用 executing-plans 批量执行并设检查点。

请选择其一；若使用 Subagent-Driven，须遵循 `superpowers:subagent-driven-development`；若 Inline，须遵循 `superpowers:executing-plans`。
