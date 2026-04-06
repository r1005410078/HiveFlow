# L2 因子层补全设计文档

**日期**: 2026-04-03  
**范围**: L2 因子层（`quant/src/application/factor/`, `quant/src/hiveflow/factor/`）  
**方案**: A——就地扩展，不引入新依赖或新服务层

---

## 1. 背景

ARCHITECTURE.md 规定 L2 输出 `factor_matrix(as_of, symbol, factor_name, raw_value, factor_version)`，每因子独立版本，因子定义/方向/单位固定，覆盖率与稳定性可观测。当前实现存在 6 项缺口：

1. `relative_strength_vs_index` 使用个股 momentum 代理，非真实基准对比
2. 因子元数据缺 `direction`、`unit` 字段
3. 所有因子共享单一 `_FACTOR_VERSION`，非独立版本
4. 因子稳定性监控仅有 `coverage_rate`，缺 drift 检测
5. `FactorValue` domain model 字段与实际 rows schema 不一致
6. L2→L3 契约缺 `missing_strategy` 和 `source`（real vs fallback）标记

---

## 2. 设计决策

### IC 计算位置

**决策**: IC（信息系数）由 L8 计算后反馈至 L2，L2 不计算 IC。  
**理由**: IC 需要未来收益，L2 不持有该信息；L2 计算 IC 会破坏层间契约。  
L2 稳定性监控只覆盖"因子值自身是否稳定"：coverage_rate + drift。

### 历史基线来源

**决策**: `stability_metrics` 中的 drift 计算需要历史基线（historical mean/std per factor），由调用方可选传入 `historical_baselines` dict；无则跳过 drift 计算，`drift_flag=null`。

---

## 3. 数据结构变更

### 3.1 FACTOR_METADATA 注册表

替换 `_FACTOR_VERSION` 单值，新增 `FACTOR_METADATA` dict：

```python
FACTOR_METADATA: dict[str, dict] = {
    "momentum_20": {
        "version": "l2-momentum-v1.0",
        "direction": 1,        # +1 = 越大越好，-1 = 越小越好
        "unit": "return",      # 无量纲收益率
        "missing_strategy": "deterministic_fallback",
    },
    "inv_volatility_20": {
        "version": "l2-inv-vol-v1.0",
        "direction": 1,
        "unit": "1/return_std",
        "missing_strategy": "deterministic_fallback",
    },
    "turnover_rate": {
        "version": "l2-turnover-v1.0",
        "direction": 1,        # 相对换手率越高说明近期活跃，方向为正；L3 中性化时视策略可调
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "max_drawdown_60": {
        "version": "l2-mdd-v1.0",
        "direction": 1,        # 已编码为 1 - drawdown，越大越好
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "trend_stability_20": {
        "version": "l2-trend-stab-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "relative_strength_vs_index": {
        "version": "l2-rsi-v1.1",  # v1.1 引入真实基准支持
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "benchmark_proxy_fallback",
    },
}
```

### 3.2 factor rows schema（L2→L3 契约）

每条 row 新增字段：

```python
{
    "as_of": "2026-04-03",
    "symbol": "600519.SH",
    "factor_name": "momentum_20",
    "factor_version": "l2-momentum-v1.0",   # 独立版本
    "raw_value": 0.023,
    "direction": 1,
    "unit": "return",
    "missing_strategy": "deterministic_fallback",
    "source": "real",  # "real" | "deterministic_fallback" | "benchmark_proxy_fallback"
}
```

### 3.3 stability_metrics schema

顶层 snapshot 输出新增 `stability_metrics`（list，per-factor）：

```python
{
    "factor_name": "momentum_20",
    "factor_version": "l2-momentum-v1.0",
    "coverage_rate": 0.98,
    "real_count": 142,
    "fallback_count": 8,
    "mean_value": 0.023,
    "std_value": 0.011,
    "drift_flag": False,       # None if no historical_baselines provided
    "drift_z_score": 0.4,      # None if no historical_baselines provided
}
```

### 3.4 FactorValue domain model 对齐

```python
@dataclass(frozen=True)
class FactorValue:
    as_of: str
    symbol: str
    name: str
    value: float
    factor_version: str
    direction: int
    unit: str
    missing_strategy: str
    source: str  # "real" | "deterministic_fallback" | "benchmark_proxy_fallback"
```

---

## 4. relative_strength_vs_index 真实基准

### 接口变更

`compute_basic_factor_snapshot_from_bars` 新增可选参数：

```python
def compute_basic_factor_snapshot_from_bars(
    as_of: str,
    symbols: list[str],
    bar_rows: list[dict],
    benchmark_rows: list[dict] | None = None,  # 新增：基准指数 bars（如 000300.SH）
) -> dict:
```

### 计算逻辑

```
benchmark_return_20 = (benchmark_close[-1] / benchmark_close[-21]) - 1
relative_strength_vs_index = (1 + momentum_20) / (1 + benchmark_return_20) - 1
source = "real"
```

若 `benchmark_rows` 为 None 或数据不足 21 条（注意：基准只需 21 条，与单标的 61 条要求不同）：

```
relative_strength_vs_index = 1.0 + momentum_20  # 当前代理逻辑不变
source = "benchmark_proxy_fallback"
```

**混合情况（重要）**: 当单标的使用真实 bars（`source="real"`），但 `benchmark_rows` 不足时，该标的的 `relative_strength_vs_index` 行单独标记 `source="benchmark_proxy_fallback"`，同一标的的其他 5 个因子行仍为 `source="real"`。`source` 字段是 per-row 粒度，不是 per-symbol 粒度。

### 调用方责任

HTTP 路由层（pipeline daily）负责从 DB 查询 000300.SH 的 bars 并传入。基准 symbol 在路由层硬编码为 `"000300.SH"`，后续可配置化。

---

## 5. 稳定性监控计算

在 `compute_basic_factor_snapshot_from_bars` 末尾，基于已计算的 rows 聚合 per-factor 统计：

```python
def _compute_stability_metrics(
    rows: list[dict],
    factor_names: list[str],
    historical_baselines: dict[str, dict] | None,
) -> list[dict]:
    # 按 factor_name 聚合 values
    # 计算 mean, std, real_count, fallback_count, coverage_rate
    # 若 historical_baselines 存在：
    #   drift_z_score = (mean - baseline_mean) / max(baseline_std, 1e-6)
    #   drift_flag = abs(drift_z_score) > 2.0
    # 否则 drift_flag = None, drift_z_score = None
```

`historical_baselines` 格式：`{"momentum_20": {"mean": 0.020, "std": 0.009}, ...}`

---

## 6. 影响范围

| 文件 | 变更类型 |
|------|---------|
| `quant/src/application/factor/basic_factor_service.py` | 主要修改：metadata 注册表、benchmark 参数、stability metrics、source 标记；**`compute_basic_factor_snapshot`（deterministic 路径）同样需要更新**以输出 direction/unit/missing_strategy/source 字段 |
| `quant/src/hiveflow/factor/domain/factor_value.py` | 补齐字段 |
| `quant/src/interfaces/http/routes_*.py` / pipeline 路由 | 查询 benchmark bars 并传入；`DailyRunResponse` Pydantic schema 中 `factor_snapshot.stability_metrics` 字段声明 |
| `quant/tests/unit/factor/test_basic_factor_service.py` | 新增测试用例；**更新已有 `test_compute_basic_factor_snapshot_shape` 断言**（`factor_version` 由共享字符串改为 per-factor 版本） |

### stability_metrics 在 snapshot 中的位置

`stability_metrics` 作为 `factor_snapshot` 顶层字典的新 key，与 `rows`、`coverage_rate`、`factor_names`、`factor_version` 并列：

```python
{
    "factor_version": "l2-basic-v1.1",   # 保留，作为 snapshot 级别的 producer 标识
    "factor_names": [...],
    "coverage_rate": 0.97,               # 保留，作为全局快速指标
    "rows": [...],
    "stability_metrics": [...]           # 新增，per-factor 详细稳定性
}
```

---

## 7. 不做的事

- 不引入 DB 存储 `FACTOR_METADATA`（静态注册表已满足需求）
- 不在 L2 计算 IC（由 L8 反馈）
- 不拆分每因子独立文件（6 个因子耦合度高，拆分无收益）
- 不新建 HTTP 端点（现有 pipeline 接口扩展参数即可）

---

## 8. 测试策略

1. **unit（bars 路径）**: `test_basic_factor_service.py` 覆盖：
   - 有 benchmark_rows（≥21 条）：`relative_strength_vs_index` 行 `source="real"`，值为真实相对强度
   - 无 benchmark_rows：`relative_strength_vs_index` 行 `source="benchmark_proxy_fallback"`，同标的其他因子 `source="real"`
   - 有 historical_baselines：drift_flag 正确（超 2σ 置 True）
   - 无 historical_baselines：drift_flag=None, drift_z_score=None
   - rows schema 含所有新字段（direction、unit、missing_strategy、source）
   - `historical_baselines` 含未知 factor key 时发出 warning 日志（不报错）
2. **unit（deterministic 路径）**: `compute_basic_factor_snapshot` 输出的 rows 同样含 direction/unit/missing_strategy/source；**更新 `test_compute_basic_factor_snapshot_shape` 中 `factor_version` 断言**（不再是 `"l2-basic-v1.1"` 而是 per-factor 版本）
3. **domain**: `FactorValue` 字段可构造、frozen 不可变
4. **contract**: fixture 更新以含新字段（现有 validate-cli-output 覆盖）
