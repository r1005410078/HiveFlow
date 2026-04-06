# MA5/MA10 金叉·死叉技术字段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SMA(5)/SMA(10) golden/death cross flags per symbol under `data.technical.ma5_ma10` for `pipeline/daily` and `signal/snapshot`, with Rust CLI json+table support; do **not** add to L2 factor rows or L3 zscore composite.

**Architecture:** Pure `application/technical/ma_cross_service.py` computes crosses from sorted 1d closes (PIT ≤ as_of). `run_daily` and `run_signal_snapshot` call it after bar rows are available and merge the result. HTTP schemas gain typed `technical`; **signal snapshot** response `data` becomes a **wrapper** `{ signal_matrix, technical }` (breaking for clients that assumed `data` was the matrix root — see Task 5).

**Tech Stack:** Python 3, FastAPI/Pydantic, pytest; Rust CLI (table_renderer, handlers).

**Prerequisite:** Spec approved — `docs/superpowers/specs/2026-04-05-ma-cross-technical-design.md`.

**Worktree:** Per AGENTS.md §8.5, implement in `.worktrees/` git worktree unless user waived in writing.

---

## File Map

> **Status (2026-04-05):** 契约与集成已补 `data.technical` 断言；`quant/tests/fixtures/cli_output/valid/*.json` 未改——`validate_cli_output` 仅校验 envelope，`data` 无 pipeline/signal 专用形状要求。

| File | Action | Responsibility |
|------|--------|----------------|
| `quant/src/application/technical/__init__.py` | Create | Package marker |
| `quant/src/application/technical/ma_cross_service.py` | Create | `compute_ma_cross_for_symbols(as_of, symbols, bar_rows)` → dict per spec |
| `quant/tests/unit/technical/test_ma_cross_service.py` | Create | Golden, death, none, insufficient bars, flat edge |
| `quant/src/application/daily_run_service.py` | Modify | After factor path, attach `technical` to `ok_output` data |
| `quant/src/application/signal/signal_engineering_service.py` | Modify | `run_signal_snapshot`: build `technical`, return `data` wrapper |
| `quant/src/interfaces/http/schemas.py` | Modify | Pydantic: `MaCrossBySymbol`, `MaCrossBlock`, `TechnicalIndicators`; extend `DailyRunData`; add `SignalSnapshotData`; change `SignalSnapshotResponse.data` type |
| `quant/src/interfaces/http/routes_signal.py` | Modify | Return type / validation uses new wrapper |
| `quant/src/interfaces/http/routes_daily_run.py` | Modify | OpenAPI example includes `technical` |
| `quant/tests/contract/test_http_daily_endpoint.py` | Modify | Assert `technical` key when applicable |
| `quant/tests/integration/test_daily_pipeline_mvp.py` | Modify | 无 bar 时 `technical is None`；有 `_BarStore` 时断言 `ma5_ma10` 结构 |
| `quant/tests/unit/signal/test_signal_engineering.py` | Modify | Snapshot tests expect wrapped `data.signal_matrix` |
| `cli/src/application/handlers/signal_snapshot.rs` | Unchanged | 仍透传 JSON；表格由 `table_renderer` 解析 `data.signal_matrix` / `technical` |
| `cli/src/application/handlers/pipeline_daily.rs` | Unchanged | 同上 |
| `cli/src/infrastructure/table_renderer.rs` | Modify | Helpers for `technical.ma5_ma10` |
| `cli/tests/http_pipeline_daily_table.rs` | Modify | 断言输出含「MA5/MA10」；mock 可无 `technical` 字段 |
| `docs/CLI_OUTPUT_EXAMPLES.md` | Modify | Examples for daily + signal snapshot |
| `quant/tests/fixtures/cli_output/valid/*.json` | Skip | 见上：envelope 校验不要求 daily/signal 的 `data` 形状 |

---

## Task 1: `ma_cross_service` + unit tests (TDD)

**Files:**
- Create: `quant/src/application/technical/__init__.py`
- Create: `quant/src/application/technical/ma_cross_service.py`
- Create: `quant/tests/unit/technical/test_ma_cross_service.py`

- [x] **Step 1:** Add failing tests: synthetic closes for金叉、死叉、无交叉、仅10根K（available=false）、并列相等边界。
- [x] **Step 2:** Run `cd quant && uv run pytest quant/tests/unit/technical/test_ma_cross_service.py -v` — expect FAIL.
- [x] **Step 3:** Implement `_sma_last_two(closes, n)` helper; main entry `build_ma_cross_payload(as_of, symbols, bar_rows: list[dict])` returning structure matching spec (`schema_version`, `definition`, `as_of`, `by_symbol`).
- [x] **Step 4:** Tests PASS.
- [x] **Step 5:** Commit `test: MA cross service unit tests` / `feat: ma cross technical payload`.

**Notes:** Reuse sorting key `bar_time` string like `basic_factor_service`. Bar rows are **flat** list with `symbol` — group by symbol before computing.

---

## Task 2: Wire `run_daily`

**Files:**
- Modify: `quant/src/application/daily_run_service.py`

- [x] **Step 1:** After `bar_store` path succeeds (same symbols, same window as factors), call `build_ma_cross_payload`; on failure log + set `technical` to `None` or omit + optional warning `MA_CROSS_UNAVAILABLE`.
- [x] **Step 2:** When no `bar_store`, omit `technical` or set `null` per spec.
- [x] **Step 3:** Run `uv run pytest quant/tests/integration/test_daily_pipeline_mvp.py -v` and unit tests.
- [x] **Step 4:** Commit.

---

## Task 3: Pydantic — `DailyRunData.technical`

**Files:**
- Modify: `quant/src/interfaces/http/schemas.py`
- Modify: `quant/tests/contract/test_http_daily_endpoint.py` (if needed)

- [x] **Step 1:** Define nested models for `technical.ma5_ma10` (strict typing for OpenAPI).
- [x] **Step 2:** Add `technical: TechnicalIndicators | None = None` to `DailyRunData`.
- [x] **Step 3:** Ensure `DailyRunResponse.model_validate` still passes on existing tests; update if response now always includes `technical` key.
- [x] **Step 4:** Commit.

---

## Task 4: `run_signal_snapshot` + **breaking** `data` wrapper

**Files:**
- Modify: `quant/src/application/signal/signal_engineering_service.py`
- Modify: `quant/src/interfaces/http/schemas.py`
- Modify: `quant/src/interfaces/http/routes_signal.py`
- Modify: `quant/tests/unit/signal/test_signal_engineering.py`

- [x] **Step 1:** Change return payload so `data` = `{ "signal_matrix": <existing matrix dict>, "technical": <ma cross dict or null> }`. Update `ok_output(..., data=...)`.
- [x] **Step 2:** Add `SignalSnapshotData` model with `signal_matrix: SignalMatrix`, `technical: TechnicalIndicators | None`.
- [x] **Step 3:** `SignalSnapshotResponse.data: SignalSnapshotData`.
- [x] **Step 4:** Fix all Python tests that expect `result["data"]["factor_names"]` → `result["data"]["signal_matrix"]["factor_names"]`.
- [x] **Step 5:** Run `uv run pytest quant/tests/unit/signal quant/tests/contract -q`.
- [x] **Step 6:** Document breaking change in spec footer or CHANGELOG one-liner; commit.

---

## Task 5: Rust CLI

**Files:**
- Modify: `cli/src/application/handlers/signal_snapshot.rs`
- Modify: `cli/src/application/handlers/pipeline_daily.rs`
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Modify: `cli/tests/http_pipeline_daily_table.rs` (and any signal snapshot tests)

- [x] **Step 1:** JSON path: deserialize `data.signal_matrix` for matrix display; read `data.technical.ma5_ma10` for optional appendix.
- [x] **Step 2:** Table: for daily, add section「MA5/MA10」listing symbols with GC/DC true or compact summary.
- [x] **Step 3:** `cargo test` in `cli/`.
- [x] **Step 4:** Commit.

---

## Task 6: Docs + fixtures + full gate

**Files:**
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Modify: `tests/fixtures/cli_output/valid/` as required by `scripts/validate_cli_output.sh`
- Modify: `quant/src/interfaces/http/routes_daily_run.py` OpenAPI example

- [x] **Step 1:** Update examples with `technical` and new signal snapshot shape.
- [x] **Step 2:** `make validate-cli-output`
- [x] **Step 3:** `make check`
- [x] **Step 4:** Final commit.

---

## Verification

```bash
make check
make validate-cli-output
```

---

## Risk note

**Signal snapshot JSON breaking:** Any external consumer parsing `data.rows` at top level must switch to `data.signal_matrix.rows`. CLI and contract tests in-repo must be updated in the same PR.
