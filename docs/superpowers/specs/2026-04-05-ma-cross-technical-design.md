# MA5/MA10 金叉·死叉技术字段设计（daily + signal snapshot + CLI）

> 状态：设计稿（待维护者/用户确认后进入 `writing-plans` 与实现）  
> 日期：2026-04-05  
> 范围：**A** `pipeline/daily` 的 `data`；**B** `signal/snapshot` 的 `data`；**C** Rust CLI 展示（json/table）。

---

## 1. 目标与非目标

### 1.1 目标

- 在 **同一套定义** 下，为指定 `as_of`、固定标的集合输出 **MA5/MA10（SMA，收盘）** 的 **金叉 / 死叉** 布尔标志（可按标的列表）。
- **三处消费**一致：`run_daily`、`run_signal_snapshot`、CLI（`hf pipeline daily` 与 `hf signal snapshot`）。
- **不进入** L2 因子加权、**不进入** L3 `signal_matrix` 的 zscore 合成（避免离散事件污染 `composite_score`）。

### 1.2 非目标

- 不作为 **L2 `factor_snapshot` 新行**（第一期）；不新增 `l2-score` 权重版本。
- 不实现 EMA、不实现多组周期可配 API（周期变更走 G3 / 未来 spec）。
- 不保证与任意第三方看盘软件像素级一致（以本 spec 数学定义为准）。

---

## 2. 数学定义（须与实现逐字一致）

- **价格序列**：按 `bar_time` 升序排列的日线 **收盘价** `close`。
- **SMA(n)**：包含 `as_of` 当日在内的最近 `n` 个收盘价的算术平均；若不足 `n` 根有效收盘，该日 SMA 视为 **不可用**。
- **比较日**：`t` = `as_of` 当日；`t-1` = 上一交易日（序列中倒数第二根）。
- **金叉（golden cross）**：  
  `SMA5[t-1] ≤ SMA10[t-1]` **且** `SMA5[t] > SMA10[t]`，且四个 SMA 值均可用。  
  （边界：`≤` / `>` 按此固定；相等视为未在 t 日形成严格上穿时可用 `≤` 与 `>` 的组合排除「已在上方」的重复信号，与常见实现一致。）
- **死叉（death cross）**：  
  `SMA5[t-1] ≥ SMA10[t-1]` **且** `SMA5[t] < SMA10[t]`，且四个 SMA 值均可用。

**最小历史**：至少需要 **11 根** 连续（按交易日序）收盘，才能同时算 `t` 与 `t-1` 的 SMA10（各需 10 根窗口，且错位一天）。实现前须用单元测试锁死边界。

---

## 3. 方案对比与推荐

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A** | 在 `daily_run_service` / `signal` 内各抄一段均线逻辑 | 改文件少 | 分叉、易漂移，**否决** |
| **B** | `application/` 新增 **`ma_cross_service`**（或 `technical/ma_cross.py`），两入口调用 | 单测集中、定义唯一 | 多一个小模块 |
| **C** | 做成第七个 L2 因子 | 快照统一 | 离散进 L3 伤 composite，**第一期否决** |

**推荐：方案 B** — 单一 application 纯函数（或小型 service），由 `run_daily` 与 `run_signal_snapshot` 在已有 `bar_store` / bars 路径上调用。

---

## 4. 架构与数据流

```
bar_store / bar_rows (≤ as_of, 1d, 升序 close)
        → application.ma_cross.compute_ma_cross_snapshot(as_of, symbols, bar_rows_by_symbol)
        → { schema_version, by_symbol: { symbol: { golden_cross, death_cross, sma5, sma10, available } } }
        → merge 进 CLI envelope data:
              daily:    data.technical.ma5_ma10
              signal:   data.technical.ma5_ma10   // 与 daily 同形，便于 CLI/审计
```

- **interfaces/http**：仅扩展响应 DTO / 文档示例；路由调用 application，**不写均线算法**。
- **无 DB schema 变更**（仍读现有 bars）。

---

## 5. JSON 合同（`data` 内嵌）

建议结构（字段名可微调，实现与 schema 示例须一致）：

```json
"technical": {
  "ma5_ma10": {
    "schema_version": "1.0.0",
    "definition": "sma_close_5_10",
    "as_of": "2026-04-01",
    "by_symbol": {
      "600519.SH": {
        "golden_cross": false,
        "death_cross": false,
        "sma5": 171.2,
        "sma10": 170.8,
        "available": true
      }
    }
  }
}
```

- **`available: false`** 时：`golden_cross` / `death_cross` 固定 `false`，`sma5`/`sma10` 可为 `null` 或省略（实现选一种并在示例中固定）。
- **deterministic / 无 bar_store**：与因子降级策略对齐——可整段 `technical.ma5_ma10` 为 `null` 或 `available: false` 占位，并可选 `warning` 码（如 `MA_CROSS_NO_BARS`），**不抛 500**。

---

## 6. 接入点

| 入口 | 变更 |
|------|------|
| `run_daily` | 在组装 `ok_output` `data` 前，若有 `bar_store` 且拉 bar 成功，计算并挂载 `technical`；失败则降级。 |
| `run_signal_snapshot` | 同上，保证与 daily **同源函数**。 |
| `POST /api/v1/pipeline/daily` | Pydantic 响应模型扩展 `DailyRunData`（或等价）含可选 `technical`。 |
| `POST /api/v1/signal/snapshot` | 同上。 |
| **Rust CLI** | `pipeline daily` / `signal snapshot` 的 json 透传；`table` 模式增加简短列或附录块（避免 table 过宽：可「仅显示发生金叉/死叉的标的」或单独小节）。 |

---

## 7. CLI 输出与校验

- 顶层 envelope 仍遵守 `CLI_OUTPUT_SCHEMA.json`（`data` 为 object 已允许）。
- 更新 **`docs/CLI_OUTPUT_EXAMPLES.md`** 与 **fixtures**（若有按 `data` 键全量匹配的校验脚本，须同步）。
- **`make validate-cli-output`** 必过。

---

## 8. 测试

- **单元**：构造 11+ 根 K 线，覆盖：金叉日、死叉日、无交叉、数据不足、`flat` 边界。
- **集成/契约**：HTTP daily / signal snapshot 响应含 `technical.ma5_ma10`（有 DB 与无 DB 降级各一）。
- **架构**：不新增 `interfaces → domain` 违规；application 不依赖 FastAPI。

---

## 9. 版本与治理

- `technical.ma5_ma10.schema_version`：子结构独立 semver；破坏性变更升主版本。
- 周期 5/10 或 SMA→EMA 变更：**G3 / 新 spec**，不在本稿内静默修改。

---

## 10. 自检（spec 质量）

- [x] 无「TBD」占位。  
- [x] 与「不进 L3 composite」一致。  
- [x] 与 ABC 范围一致。  

---

## 11. 待你确认后下一步

1. 你（或维护者）**书面确认**本 spec 无歧义。  
2. 调用 **writing-plans**，产出 `docs/superpowers/plans/2026-04-05-ma-cross-technical-implementation-plan.md`。  
3. 按 AGENTS.md **worktree** 实施（除非书面豁免）。  
4. 实现后 **`make check`**。
