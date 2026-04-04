# L3 信号工程 Phase 2b 设计

> 日期：2026-04-04
> 状态：待确认
> 前置：L3 Phase 2a（signal_evaluate 已合入 master）
> 范围：缺失值横截面中位数填补 + 行业哑变量 OLS 中性化框架

---

## 1. 目标

提升 L3 信号的鲁棒性：

1. **缺失值处理**：对因子缺失值用横截面中位数填补，提高 coverage_rate，避免因单标的数据缺失导致 composite_score 退化。
2. **行业中性化框架**：对填补后的因子做行业哑变量 OLS 回归取残差，消除行业共同暴露，使 composite_score 更能反映个股 alpha。

### Phase 2b 范围

- `compute_signal_matrix()` 内插入两个新步骤（填补 + 中性化）
- `transform_stats` 新增 `fill_count` 字段（向后兼容）
- 行业映射表定义在 `signal_engineering_service.py` 顶部常量
- 单元测试覆盖填补、中性化、端到端行为

### 明确不做

- 不改 HTTP 接口（`/api/v1/signal/snapshot` 响应结构不变）
- 不改 Rust CLI（`hf signal snapshot` 命令不变）
- 不升 `signal_version`（保持 `l3-signal-v1.0`）
- 不扩展标的池（保持 5 只硬编码标的）
- 不引入新 DB 表
- 不做市值（Size）中性化
- 不做 IC 衰减监控（留后续）

---

## 2. 架构与文件布局

### 2.1 改动文件

```
修改：quant/src/application/signal/signal_engineering_service.py
  → 新增顶部常量 _INDUSTRY_MAP
  → 新增私有函数 _fill_missing_cross_sectional()
  → 新增私有函数 _neutralize_industry()
  → compute_signal_matrix() 内插入填补 + 中性化步骤
  → transform_stats 条目新增 fill_count 字段

新增：quant/tests/unit/signal/test_signal_engineering_service.py
  → 6 个单元测试（见第 5 节）
```

### 2.2 不改动的文件

- `interfaces/http/routes_signal.py`：不改，HTTP 接口透传
- `interfaces/http/schemas.py`：不改，响应结构不变
- `application/signal/signal_evaluate_service.py`：不改
- `application/portfolio/optimizer_service.py`：不改（行业映射独立维护，不跨层共享）
- Rust CLI 全部文件：不改

### 2.3 依赖方向

```
signal_engineering_service (application/signal)
  → basic_factor_service (application/factor)   # 已有
  → numpy / pandas                               # 已有
  （无新依赖）
```

---

## 3. 新流水线

`compute_signal_matrix()` 内部处理顺序：

```
1. 方向对齐（已有）：direction=-1 的因子乘以 -1
          ↓
2. [NEW] 横截面中位数填补：NaN → 该因子所有标的中位数
          ↓
3. [NEW] 行业哑变量 OLS 中性化（含守卫条件）
          ↓
4. Winsorize → zscore（已有，对中性化后的残差执行）
          ↓
5. 等权聚合 composite_score（已有）
```

---

## 4. 详细算法

### 4.1 缺失值填补

```python
def _fill_missing_cross_sectional(
    wide: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """对每个因子列，用该列横截面中位数填补 NaN。
    返回 (填补后 DataFrame, {factor_name: fill_count})。
    """
    filled = wide.copy()
    fill_counts: dict[str, int] = {}
    for col in filled.columns:
        n_missing = int(filled[col].isna().sum())
        if n_missing > 0:
            median = filled[col].median()  # skipna=True
            filled[col] = filled[col].fillna(median)
        fill_counts[col] = n_missing
    return filled, fill_counts
```

**边界情况**：
- 某因子全列为 NaN：`median()` 返回 NaN，`fillna(NaN)` 不填补，后续 zscore 仍会退化为 NaN，聚合时 drop（与原行为一致）
- 只有 1 个有效值：中位数 = 该值，其余标的填为同一数值（合理降级）

### 4.2 行业中性化

```python
_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}

def _neutralize_industry(
    wide: pd.DataFrame,
    industry_map: dict[str, str],
) -> pd.DataFrame:
    """对每个因子列做行业哑变量 OLS 回归，返回残差矩阵。
    若标的不在 industry_map 中，归入 'other'。
    当每个行业只有 1 只标的时（OLS 完全拟合，残差全为 0），
    直接返回原值（透传），避免 composite_score 退化为 NaN。
    """
    from collections import Counter
    symbols = wide.index.tolist()
    industries = [industry_map.get(s, "other") for s in symbols]
    industry_counts = Counter(industries)

    # 守卫：所有行业均只有 1 只标的，中性化无意义
    if max(industry_counts.values()) < 2:
        return wide.copy()

    X = pd.get_dummies(industries, dtype=float).values  # shape (n, k)
    residuals = wide.copy()
    for col in wide.columns:
        y = wide[col].values.reshape(-1, 1)
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        residuals[col] = (y - X @ beta).flatten()
    return residuals
```

**5 只标的时的行为**：每行业 1 只，守卫条件触发，直接透传原值，composite_score 不变，pipeline 正常运行。

**将来扩标的时的行为**：某行业出现 ≥2 只标的，守卫条件不触发，OLS 激活，自动消除行业共同暴露，无需改代码。

### 4.3 transform_stats 新增字段

```python
transform_stats.append({
    "factor_name": fn,
    "fill_count": fill_counts.get(fn, 0),   # ← 新增，向后兼容
    "pre_winsorize": pre_stats,
    "post_zscore": post_stats,
})
```

---

## 5. 测试策略

全部为单元测试，位于 `quant/tests/unit/signal/test_signal_engineering_service.py`。

| 测试名 | 验证内容 |
|--------|----------|
| `test_fill_missing_uses_cross_sectional_median` | NaN 被填补为其余标的该因子的中位数 |
| `test_fill_missing_all_nan_column_stays_nan` | 全列 NaN 时不抛异常，填补后仍为 NaN |
| `test_neutralize_skips_when_one_symbol_per_industry` | 每行业 1 只标的时返回原值不变 |
| `test_neutralize_removes_industry_mean_with_multi_symbol` | 同行业 2 只标的，中性化后行业内均值为 0 |
| `test_compute_signal_matrix_fill_count_in_transform_stats` | `transform_stats` 中每条目含 `fill_count` 字段 |
| `test_compute_signal_matrix_end_to_end_no_nan_composite` | 含 NaN 的 factor_snapshot，填补后 composite_score 无 NaN |

---

## 6. 与上下游的接口契约

### 输入（不变）

`compute_signal_matrix(factor_snapshot: dict)` 接受与 Phase 1 完全相同的 `factor_snapshot` 结构。

### 输出（向后兼容变更）

`signal_matrix` 中 `transform_stats` 每条目新增 `fill_count: int`（整数，≥0）。
其余所有字段（`composite_scores`、`rows`、`coverage_rate` 等）结构不变。

数值变化：当标的存在因子缺失时，`coverage_rate` 可能升高，`composite_score` 可能由 NaN 变为有效值——这是预期的质量提升。
