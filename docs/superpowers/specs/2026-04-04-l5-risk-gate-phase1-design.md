# L5 风险门控 Phase 1 设计

> 日期：2026-04-04
> 状态：待确认
> 前置：L4 Phase 1（portfolio_optimize 已合入 master）
> 范围：三态市场状态机 + 四项硬约束检查 + `POST /api/v1/risk/check` + `hf risk check` CLI + daily pipeline 集成

---

## 1. 目标

在 L4 组合优化输出进入执行层之前，加一道与收益无关的硬拦截层：

1. **市场状态机**：根据近期市场波动率自动切换 normal / warning / crisis 三态，不同态对应不同阈值。
2. **四项硬约束检查**：组合预期波动率、单标的集中度、行业集中度、单日换手率。
3. **独立接口**：`POST /api/v1/risk/check` + `hf risk check`，与 L3/L4 接口对称，可单独调用。
4. **pipeline 集成**：daily run 在 L4 之后自动执行 L5，结果写入 `data.risk_gate` 字段。

### 明确不做

- 不引入新 DB 表（状态机是推导值，不持久化）
- 不做 L5.5 预交易模拟（留后续）
- 不做因子暴露集中度检查（留后续）
- 不升 `optimize_version`（L4 版本不变）

---

## 2. 架构与文件布局

### 2.1 新增文件

```
quant/src/application/risk/__init__.py
quant/src/application/risk/risk_gate_service.py
    → 市场状态机（regime 检测）
    → 四项检查逻辑
    → run_risk_check() 公开接口（返回 CLI 包装输出）

quant/src/interfaces/http/routes_risk.py
    → POST /api/v1/risk/check

quant/tests/unit/risk/test_risk_gate_service.py
    → 12 个单元测试

cli/src/commands/risk.rs
    → hf risk check --as-of DATE [--output json|table]
```

### 2.2 修改文件

```
quant/src/interfaces/http/app.py
    → 注册 routes_risk router

quant/src/application/daily_run_service.py
    → L4 之后调用 run_risk_check()
    → data 新增 risk_gate 字段

cli/src/commands/mod.rs
    → 注册 risk 子命令
```

### 2.3 不改动的文件

- `application/portfolio/portfolio_optimize_service.py`：不改，L5 独立消费 L4 输出
- `application/portfolio/covariance_service.py`：不改，L5 复用其函数计算 σ_p
- `interfaces/http/schemas.py`：不改
- `application/signal/signal_engineering_service.py`：不改

### 2.4 依赖方向

```
risk_gate_service (application/risk)
  → covariance_service (application/portfolio)   # 已有，计算 σ_p
  → numpy / pandas                               # 已有
  （无新依赖）
```

---

## 3. 市场状态机

### 3.1 检测逻辑

每次调用 `run_risk_check()` 时实时计算，无缓存。

**步骤（按优先级依次尝试）：**

1. **优先使用 000300.SH**：bar_store 非 None 时，取近 30 根日线，有效收益率点 ≥ 20 → 计算年化波动率，`regime_vol_source = "benchmark"`
2. **降级使用等权组合**：bar_store 非 None 但 000300.SH 数据不足 20 个收益率点时，改用 5 只默认标的等权组合日收益率，`regime_vol_source = "equal_weight"`
3. **兜底默认 normal**：bar_store=None，或步骤 2 数据也不足 → `regime = "normal"`，`regime_vol = null`，`regime_vol_source = "none"`（保守降级，避免因数据缺失误触发 crisis 拦截）

**年化波动率计算：**

```python
returns = prices.pct_change().dropna().tail(20)
regime_vol = float(returns.std() * np.sqrt(252))
```

### 3.2 状态切换阈值

| 年化波动率 | 状态 |
|-----------|------|
| `< 0.25` | `normal` |
| `0.25 ≤ vol < 0.40` | `warning` |
| `≥ 0.40` | `crisis` |

状态只影响各项检查的阈值，不影响检查项目（四项检查在任何状态下都执行）。

---

## 4. 四项检查

### 4.1 P1 — 组合预期波动率

```python
# Σ 由 covariance_service.compute_covariance_matrix() 计算
# 若 bar_store=None，使用对角线 fallback（年化方差 0.04）
sigma_p = float(np.sqrt(w_vec @ Sigma @ w_vec) * np.sqrt(252))
```

拒单码：`PORTFOLIO_VOL_EXCEEDED`

### 4.2 P2 — 单标的集中度

```python
single_max = float(max(w_vec))
```

拒单码：`SINGLE_ASSET_CONCENTRATION`

### 4.3 P3 — 行业集中度

```python
# 行业映射与 L4 optimizer_service 一致
industry_sums = {ind: sum(w[s] for s in syms) for ind, syms in industry_groups.items()}
industry_max = float(max(industry_sums.values()))
```

拒单码：`INDUSTRY_CONCENTRATION`

### 4.4 P4 — 单日换手率

```python
# prev_weights 为空时，视为从零建仓：turnover = sum(w_new) = 1.0
turnover = float(sum(abs(w.get(s, 0.0) - prev_weights.get(s, 0.0)) for s in w))
```

拒单码：`TURNOVER_EXCEEDED`

### 4.5 分态阈值

| 检查项 | normal | warning | crisis |
|--------|--------|---------|--------|
| P1 组合年化波动率 | `≤ 0.30` | `≤ 0.22` | `≤ 0.15` |
| P2 单标的最大权重 | `≤ 0.35` | `≤ 0.28` | `≤ 0.20` |
| P3 行业最大权重 | `≤ 0.45` | `≤ 0.38` | `≤ 0.30` |
| P4 单日换手率 | `≤ 0.80` | `≤ 0.55` | `≤ 0.30` |

任意一项超阈值 → 整体 `block`。**所有检查在 block 后继续执行**，返回完整证据列表。

---

## 5. 接口设计

### 5.1 `run_risk_check()` 签名

```python
def run_risk_check(
    as_of: str,
    target_weights: dict[str, float],
    prev_weights: dict[str, float] | None = None,
    bar_store=None,
) -> dict:
    """
    返回 CLI 标准包装输出。
    risk_gate: "pass" | "block"
    status: "ok"（pass）| "warning"（block）
    """
```

### 5.2 输出结构

```json
{
  "schema_version": "1.0.0",
  "command": "hf risk check",
  "run_id": "run_20260404_xxxxxxxx",
  "status": "ok",
  "generated_at": "2026-04-04T10:00:00+08:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-04",
    "risk_gate": "pass",
    "regime": "normal",
    "regime_vol": 0.182,
    "regime_vol_source": "benchmark",
    "checks": [
      {"name": "portfolio_vol",    "value": 0.220, "threshold": 0.300, "passed": true},
      {"name": "single_asset_max", "value": 0.280, "threshold": 0.350, "passed": true},
      {"name": "industry_max",     "value": 0.350, "threshold": 0.450, "passed": true},
      {"name": "turnover",         "value": 0.450, "threshold": 0.800, "passed": true}
    ],
    "block_codes": []
  },
  "warnings": [],
  "errors": []
}
```

`risk_gate = "block"` 时：`status = "warning"`，`block_codes` 列出所有失败项拒单码（如 `["PORTFOLIO_VOL_EXCEEDED"]`）。

### 5.3 HTTP 接口

```
POST /api/v1/risk/check
Content-Type: application/json

{
  "as_of": "2026-04-04",
  "target_weights": {"000001.SZ": 0.25, "600519.SH": 0.30, ...},
  "prev_weights": {"000001.SZ": 0.20, ...}   // 可省略
}
```

`prev_weights` 省略时视为 `{}`（全量换手）。

### 5.4 CLI 命令

```
hf risk check --as-of DATE [--output json|table]
```

`--output table` 显示格式：

```
Regime: normal (vol=18.2%)
┌──────────────────┬────────┬───────────┬────────┐
│ Check            │ Value  │ Threshold │ Passed │
├──────────────────┼────────┼───────────┼────────┤
│ portfolio_vol    │ 22.0%  │ 30.0%     │ ✓      │
│ single_asset_max │ 28.0%  │ 35.0%     │ ✓      │
│ industry_max     │ 35.0%  │ 45.0%     │ ✓      │
│ turnover         │ 45.0%  │ 80.0%     │ ✓      │
└──────────────────┴────────┴───────────┴────────┘
Risk Gate: PASS
```

---

## 6. Daily Pipeline 集成

`daily_run_service.py` 在 L4 之后插入 L5：

```python
risk_gate_result = None
if portfolio is not None:
    try:
        risk_gate_result = run_risk_check(
            as_of=as_of,
            target_weights={r["symbol"]: r["weight"] for r in portfolio["target_weights"]},
            prev_weights={},   # Phase 1 暂不传历史权重
            bar_store=bar_store,
        )
    except Exception:
        _logger.warning("daily run: risk gate failed", exc_info=True)
        warnings.append({
            "code": "RISK_GATE_FAILED",
            "message": "L5 risk gate computation failed; risk_gate set to null",
        })
```

`data` 输出新增字段：

```python
data = {
    ...
    "portfolio": portfolio,           # L4 输出不变（供审计）
    "risk_gate": risk_gate_result.get("data") if risk_gate_result else None,
}
```

L5 block **不阻断** daily pipeline（pipeline 韧性优先）；block 信息通过 `data.risk_gate.risk_gate = "block"` 和 `warnings` 传递给调用方。

---

## 7. 测试策略

全部为单元测试，位于 `quant/tests/unit/risk/test_risk_gate_service.py`。

| 测试名 | 验证内容 |
|--------|----------|
| `test_regime_normal_when_low_vol` | 低波动率 bar 数据 → `regime = "normal"` |
| `test_regime_warning_when_mid_vol` | 中等波动率 → `regime = "warning"` |
| `test_regime_crisis_when_high_vol` | 高波动率 → `regime = "crisis"` |
| `test_regime_fallback_to_equal_weight` | 000300.SH 数据不足时，降级使用等权组合，`regime_vol_source = "equal_weight"` |
| `test_regime_defaults_normal_when_no_data` | bar_store=None → `regime = "normal"`，不抛异常 |
| `test_p1_portfolio_vol_block` | σ_p 超阈值 → block + `PORTFOLIO_VOL_EXCEEDED` |
| `test_p2_single_asset_block` | max weight 超阈值 → block + `SINGLE_ASSET_CONCENTRATION` |
| `test_p3_industry_block` | 行业权重超阈值 → block + `INDUSTRY_CONCENTRATION` |
| `test_p4_turnover_block` | 换手超阈值 → block + `TURNOVER_EXCEEDED` |
| `test_all_checks_run_even_when_blocked` | 多项超阈值时，`block_codes` 含所有失败项 |
| `test_pass_returns_ok_status` | 所有检查通过 → `risk_gate = "pass"`，`status = "ok"` |
| `test_crisis_tightens_thresholds` | 同一权重在 normal 下 pass，在 crisis 下 block |

---

## 8. 与上下游的接口契约

### 输入

`run_risk_check(as_of, target_weights, prev_weights, bar_store)`

- `target_weights`：L4 `target_weights` 列表转 `{symbol: weight}` dict
- `prev_weights`：上期权重 dict，Phase 1 daily pipeline 传 `{}`
- `bar_store`：可为 None（触发兜底降级）

### 输出（新增字段）

`data.risk_gate` 出现在：
- `POST /api/v1/risk/check` 响应的 `data` 根节点（完整输出）
- `hf pipeline daily` 响应的 `data.risk_gate` 子字段（仅 `data` 部分）

`risk_gate` 字段结构不变，向后兼容：新增 `regime_vol_source` 字段（`"benchmark" | "equal_weight" | "none"`）标识数据来源。
