# CLI：K 线 chart/tui 聚合 + data bars 支持 universe

> 日期：2026-04-04  
> 状态：**待维护者 / 用户确认**  
> **修订（2026-04-04）：** `hf data bars` 已**移除** `--output chart`（与 `tui` 重复且不利于自动化）；下文凡写 chart 处视为历史稿，实现时以 **json/table/tui** 为准。  
> 前置：L1 bars API（`GET /v1/market-data/bars`）已提供 `open/high/low/close/bar_time`；`hf data query` 已支持 `--universe` 与分批拉取合并；`hf data bars --output tui` 已具备左侧选股 + 右侧折线。

---

## 1. 目标

1. **K 线「聚合」**：在点数过多时，用 **OHLC 语义**压缩为更少根「合成 K 线」，再参与 **`--output tui`** 右侧走势图绘制（`chart` 子命令已移除）；避免仅按 close 均匀抽点带来的高低价信息丢失。
2. **`hf data bars` 支持 universe**：与 `data query` 一致，`--symbols` 与 `--universe` **并集去重**（至少其一），从仓库 `quant/config/universes/{name}.txt` 读标的；**大池分批请求**（与 `data query` 同批大小策略），合并 `items` 后走 **json/table/tui**。
3. **多标的与 tui**：`--output tui` 已支持左列表右图；universe 解析后多标的时**仅**走 `tui`（或 json/table），无需再区分「单标的 chart」。

非目标（本期不做）：

- 服务端新增「按 universe 查 bars」或「服务端聚合」接口（本期 **CLI 侧**合并与聚合即可）。
- 终端内绘制完整蜡烛实体图（ratatui/textplots 能力有限）；本期聚合后 **折线仍以合成 bar 的 `close`（或可配置 `hl2`）** 为主，OHLC 用于合成规则与后续扩展。

---

## 2. 聚合定义（按时间顺序的连续分桶）

对**单标的、已按 `bar_time` 升序**排列的原始 bar 序列：

- 参数 **`max_display_points`**（CLI 可选，建议默认 **2000**，与「可读性」平衡；可与终端宽度/默认窗口联动 cap，在实现计划中写死可调常量）。
- 若 `n = len(bars) <= max_display_points`：**不聚合**。
- 若 `n > max_display_points`：令 `bucket_count = max_display_points`，`bars_per_bucket = ceil(n / bucket_count)`（或等价：将 `n` 根连续 bar 划分为 `bucket_count` 段，每段至多相差 1 根——实现计划选一种并单测锁死）。
- 对每个桶内 bar（时间顺序）：
  - **`open`** = 桶内第一根 `open`
  - **`high`** = 桶内 `high` 的 **max**
  - **`low`** = 桶内 `low` 的 **min**
  - **`close`** = 桶内最后一根 `close`
  - **`bar_time`**（代表时刻）= 桶内**最后一根**的 `bar_time`（与 close 对齐；实现计划可注明）

绘制：

- **tui（ratatui）**：对每个标的的 `SymbolSeries.points` 在入图前套用同一聚合；**窗口/缩放**仍在合成序列上操作（本期接受：极大数据下放大看到的是桶内已压缩信息；要细粒度需缩小日期范围或增大 `max_display_points` 或后续做「按需加载」）。库内 `chart_renderer`（textplots）可保留供测试或非 bars 路径，**不作为** `hf data bars` 的 `--output`。

**json / table 输出**：默认 **仍为原始合并结果**（不强制聚合），避免破坏脚本；可选 **未来** 增加 `--aggregate-json`（本期可不实现，计划在「后续」列出）。

---

## 3. `hf data bars`：universe 与请求形状

- 新增 **`--universe <name>`**（可选），语义对齐 `data query`：`HIVEFLOW_ROOT` 或仓库根定位 + `load_universe_symbols`。
- **`--symbols` 与 `--universe` 至少其一**，并集去重；排序稳定（如字母序）。
- HTTP：沿用 `GET /v1/market-data/bars`，**每批最多 30 只**（与 `SYMBOL_BATCH` 一致），多次请求后合并 `items`，按 `bar_time`、再 `symbol` 排序（复用 `data_market_query` 已有排序逻辑或抽公共函数）。
- **`--limit`**：建议与 `data query` 对齐语义——**每批 per-request limit** 与可选 **合并后截断**（实现计划写明与现网 `data bars` 行为是否保持「仅传一个 limit 给单次请求」；多批时推荐每批使用相同 `limit`）。

---

## 4. `tui` 与标的数

| 标的数 | `--output tui` |
|--------|----------------|
| 0（非法） | 报错（须 `--symbols` 和/或 `--universe`） |
| ≥1 | 允许；左列表选股 + 右图（一项时列表仅一行） |

---

## 5. 测试与门禁

- **Rust 单元测试**：聚合函数（OHLC 边界：单根桶、两根桶、全等 high/low、bar_time 单调）。
- **集成测试**：`data bars` handler mock：universe+symbols 合并批次数；`--output chart` 返回 **`InvalidArgs`**（未支持该取值）。
- 全量 **`make check`**。

---

## 6. 风险与回滚

- 大 universe × 高 `limit` 会导致 **内存与耗时** 上升；依赖现有分批与文档说明；必要时在 help 中提示缩小 `--limit` 或日期区间。
- 聚合改变视觉形状；必须在 **tui 脚注或 stderr** 提示 `aggregated: N→M`（或类似文案）。

---

## 7. 配套计划

见：`docs/superpowers/plans/2026-04-04-cli-bars-chart-universe-aggregation-implementation-plan.md`。

---

## 8. 确认清单（请 reviewer 勾选）

- [ ] 聚合采用「连续分桶 OHLC」且默认 `max_display_points=2000` 可接受  
- [ ] 交互看图仅用 **`tui`**（`data bars` 已无 `chart` `--output`）可接受  
- [ ] json/table 保持原始数据、聚合仅用于 **tui** 可接受  

确认后进入实现阶段（建议 **`using-git-worktrees`** 独立分支，除非书面豁免）。
