# CLI：K 线聚合 + data bars universe — 实现计划

> **Design spec:** [`docs/superpowers/specs/2026-04-04-cli-bars-chart-universe-aggregation-design.md`](../specs/2026-04-04-cli-bars-chart-universe-aggregation-design.md)  
> **Verification:** `cd cli && cargo test`；`make check`

---

## Task 1：公共符号解析与 bars 分批合并

**目标：** `data bars` 与 `data query` 共享「symbols ∪ universe → 有序标的列表」与「分批 `get_market_data_bars` + merge + sort」逻辑，避免复制漂移。

**建议路径：**

- 新建 `cli/src/application/bars_fetch.rs`（或 `application/symbols_bars.rs`）：  
  `fn resolve_bar_symbols(symbols_csv: Option<&str>, universe: Option<&str>) -> Result<Vec<String>, AppError>`  
  `fn fetch_bars_merged(cfg, symbols, timeframe, start, end, limit_per_batch, timeout) -> Result<Value, AppError>`
- `data_market_query.rs` / `data_bars.rs` 改为调用上述函数（`data query` 继续自带日期窗口解析）。

**测试：** 单元测试 `resolve_bar_symbols`（仅 symbols / 仅 universe / 并集）；mock HTTP 批次数 = `ceil(n/30)`。

---

## Task 2：`DataBarsRequest` / `data.rs` CLI

- `DataBarsArgs` / `DataBarsRequest` 增加 `universe: Option<String>`。
- `#[arg(long)]` 中文 help 与 `after_long_help` 示例增加 `--universe csi300`；说明多标的时 **`--output tui`** 左列表右图。
- 架构：`cli/tests/architecture_rules.rs` 若新增 `application` 模块被 cmd 引用规则变化则更新（通常不必）。

---

## Task 3：OHLC 聚合（domain 或 infrastructure）

- 新建 `cli/src/domain/bars_aggregate.rs`（推荐放 **domain**，无 IO）或 `infrastructure/bars_aggregate.rs`：  
  - 输入：`Vec<(bar_time, open, high, low, close)>` 已排序  
  - 输出：合成序列（同上结构）  
  - 算法按 spec §2，`max_display_points` 为参数
- 从 `serde_json::Value` 的 `items` 解析 bar（缺字段时保守跳过或按 0 处理——计划写死一种并测）
- **单元测试**：n≤max 不变；n=1000,max=10 桶数与 OHLC 可手工验算 case

---

## Task 4：`chart_renderer`（可选 / 测试保留）

- `hf data bars` 已不再使用 textplots **chart** 路径；本任务可 **跳过**，或仅保留库内单测与 `downsample_for_chart` 供非 CLI 调用方使用。

---

## Task 5：tui_renderer

- `build_symbol_series`（或等价）在构造 `SymbolSeries.points` 前对每个 symbol 应用聚合（`max_display_points` 计划写死常量 + 可选 CLI flag）。
- 确认左列表 + 右图仍工作；hint 行可加 `(aggregated)` 标记。

---

## Task 6：`data_bars` handler

- 使用 Task 1 的 fetch。
- **tui/json/table**：多标的允许（`tui` 左列表右图）。
- 将 `max_display_points` 从 args 传入（新增 `--max-display-points`，默认 2000；`0` = 不聚合——若实现复杂可首期不做 `0`，计划标注）

---

## Task 7：契约与文档（若对外 JSON 不变则最小）

- CLI 包装 JSON 若未变，可只更新 `GETTING_STARTED` / `CLI_OUTPUT_EXAMPLES` 中 **data bars** 说明一句（可选）。
- **不修改** `schema_version` 除非 `data` 信封字段变化。

---

## Task 8：门禁

- `make architecture-check`
- `make check`

---

## 提交建议

- `feat(cli): data bars 支持 universe 与 K 线 OHLC 聚合展示`（中文描述可再拆成 `feat` + `test` 若团队希望）
