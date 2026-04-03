# L3 信号评估 Phase 2a 设计

> 日期：2026-04-03
> 状态：待确认
> 前置：L3 Phase 1（signal_matrix 已合入 master）
> 范围：IC 计算（per-factor + composite）+ 信号分布漂移检测，纯离线评估命令

---

## 1. 目标

为 L3 信号层增加质量评估能力——IC（Information Coefficient，预测力度量）和信号分布漂移检测。以独立评估命令形式提供，不修改 daily pipeline 主链路。

### Phase 2a 范围

- **IC 报告**：per-factor signal Rank IC + composite Rank IC（均值、标准差、信息比率、命中率、每日时序）
- **漂移诊断**：per-factor 原始值分布漂移 + coverage 漂移 + Kendall tau 排名周转率

### 明确不做

- 不引入信号持久化（无新 DB 表）
- 不修改 daily pipeline 的 `signal_matrix` 输出
- 不做 IC 衰减监控（留 Phase 2b+）
- 不做中性化/缺失值高级处理（留 Phase 2b）
- 不做与 L4 的衔接
- 不支持自定义 symbols（沿用 Phase 1 的 5 个硬编码标的，可配置 symbols 留后续）
- `signal_version` 保持 `l3-signal-v1.0`（不改信号算法本身）

---

## 2. 架构与文件布局

### 2.1 Python（quant/src/）

```
quant/src/
├── domain/models/
│   └── signal.py                        # 新增 ICResult, DriftResult 等 domain dataclass
├── application/signal/
│   ├── signal_engineering_service.py     # 不改（复用 compute_signal_matrix）
│   └── signal_evaluate_service.py **     # 核心：run_signal_evaluation()
├── interfaces/http/
│   ├── schemas.py                       # 新增 SignalEvaluate* Pydantic models
│   ├── routes_signal.py                 # 新增 POST /api/v1/signal/evaluate 路由
│   └── dependencies.py                  # 新增 get_signal_evaluate_service provider
```

### 2.2 Rust CLI（cli/src/）

```
cli/src/
├── cmd/
│   └── signal.rs                        # 新增 Evaluate 子命令（--start-date, --end-date, --forward-days, --output）
├── application/
│   ├── requests.rs                      # 新增 SignalEvaluateRequest + AppCommand::SignalEvaluate
│   ├── handlers/
│   │   ├── mod.rs                       # 注册 signal_evaluate module
│   │   └── signal_evaluate.rs **        # handle() → POST /api/v1/signal/evaluate
│   └── dispatch.rs                      # 新增 SignalEvaluate 分发
├── infrastructure/
│   ├── http_client.rs                   # 新增 post_signal_evaluate()
│   └── table_renderer.rs               # 新增 render_signal_evaluate_table()
```

### 2.3 依赖方向

```
signal_evaluate_service (application/signal)
  → compute_signal_matrix (application/signal)                    # 复用 Phase 1
  → compute_basic_factor_snapshot_from_bars (application/factor)  # 复用 L2
  → bar_store (通过函数参数注入，不直接依赖 infrastructure)
  → pandas Series.corr(method='spearman')                        # IC 计算，无新依赖

routes_signal (interfaces/http)
  → signal_evaluate_service (通过 dependencies.py 注入)
```

符合 `interfaces → application → domain` 方向约束。`signal_evaluate_service` 不直接依赖 infrastructure，bar_store 通过函数参数注入。Rust CLI 遵循 `cmd → application → infrastructure` 方向。

### 2.4 不改动的文件

- `application/signal/signal_engineering_service.py`：只复用，不修改
- `application/daily_run_service.py`：不改 daily pipeline
- `hiveflow/signal/application/normalize_use_case.py`：不改
- `application/factor/basic_factor_service.py`：只复用，不修改

---

## 3. 数据流

### 3.1 IC 计算流程

```
输入: start_date, end_date, forward_days (默认 1), symbols (默认 5)

对每个 T ∈ [start_date, end_date - forward_days]:
  ┌─────────────────────────────────────────────────┐
  │ 1. bar_store.list_bars(symbols, T-180d ~ T)     │
  │    → 用于因子计算的 PIT 安全窗口                   │
  │                                                   │
  │ 2. compute_basic_factor_snapshot_from_bars(T)     │
  │    → L2 factor_snapshot（复用已有）                 │
  │                                                   │
  │ 3. compute_signal_matrix(factor_snapshot)          │
  │    → L3 signal_matrix（复用 Phase 1）              │
  │                                                   │
  │ 4. 取 close(T) 和 close(T+forward_days)           │
  │    → forward_return = close(T+fwd)/close(T) - 1   │
  │                                                   │
  │ 5. per-factor: Spearman(signal_values, fwd_ret)   │
  │    composite: Spearman(composite_scores, fwd_ret)  │
  └─────────────────────────────────────────────────┘

汇总:
  per-factor: daily_ic[], mean_ic, ic_std, ic_ir, hit_rate
  composite:  daily_ic[], mean_ic, ic_std, ic_ir, hit_rate
```

**关键约束**：IC 评估**必须有 DB 中的真实 bar 数据**。bar_store 不可用或 bar 数据不足时返回明确错误（不降级到 deterministic，因为确定性因子对所有日期返回相同值，IC 无意义）。

### 3.2 漂移检测流程

在上述循环中，同时收集每日的 `transform_stats`（pre_winsorize 原始统计量）和 `coverage_rate`：

```
对每个 factor:
  raw_means = [日期T的 pre_winsorize.mean for T in 范围]

  baseline = raw_means[:-drift_window]   # 前段做基线
  recent   = raw_means[-drift_window:]   # 后段做检测

  drift_z = (mean(recent) - mean(baseline)) / std(baseline)
  drift_flag = |drift_z| > 2.0

同时:
  coverage_rates = [日期T的 coverage_rate for T in 范围]
  coverage_drift = 同样的 z-score 检测

  rank_turnover = 相邻日 composite 排名的 Kendall tau 距离均值
```

### 3.3 为什么监控 pre_winsorize 而非 post_zscore

z-score 是截面标准化，每天的 post_zscore 均值/标准差都约为 0/1，无法反映时序变化。而 pre_winsorize 保留了原始分布信息，能捕捉数据源异常和市场结构性变化。

---

## 4. 输出 Schema

### 4.1 顶层包装

标准 CLI Output 信封：

```json
{
    "schema_version": "1.0.0",
    "command": "hf signal evaluate",
    "run_id": "...",
    "status": "ok",
    "generated_at": "...",
    "source": "system",
    "advice_only": false,
    "decision_weight": 1,
    "data": { /* SignalEvaluation */ },
    "warnings": [],
    "errors": []
}
```

### 4.2 `SignalEvaluation` data 结构

```json
{
    "eval_version": "l3-eval-v1.0",
    "start_date": "2026-03-01",
    "end_date": "2026-04-01",
    "forward_days": 1,
    "trading_days_evaluated": 20,
    "symbols": ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"],

    "ic_report": {
        "per_factor": [
            {
                "factor_name": "momentum_20",
                "mean_ic": 0.062,
                "ic_std": 0.15,
                "ic_ir": 0.41,
                "hit_rate": 0.65,
                "daily_ic": [
                    {"date": "2026-03-03", "ic": 0.12},
                    {"date": "2026-03-04", "ic": -0.05}
                ]
            }
        ],
        "composite": {
            "mean_ic": 0.085,
            "ic_std": 0.12,
            "ic_ir": 0.71,
            "hit_rate": 0.70,
            "daily_ic": [
                {"date": "2026-03-03", "ic": 0.15},
                {"date": "2026-03-04", "ic": 0.02}
            ]
        }
    },

    "drift_diagnostics": {
        "drift_window": 5,
        "baseline_days": 15,
        "factor_drift": [
            {
                "factor_name": "momentum_20",
                "baseline_mean": 0.042,
                "baseline_std": 0.008,
                "recent_mean": 0.039,
                "drift_z": -0.375,
                "drift_flag": false
            }
        ],
        "coverage_drift": {
            "baseline_mean": 1.0,
            "recent_mean": 1.0,
            "drift_z": 0.0,
            "drift_flag": false
        },
        "rank_turnover": {
            "mean_turnover": 0.20,
            "max_turnover": 0.40,
            "stable": true
        }
    }
}
```

### 4.3 设计说明

- `daily_ic` 时序在 JSON 模式下完整输出，table 模式下折叠为汇总行
- `drift_window` 默认为评估天数的 25%（最小 3 天），`baseline_days` 为剩余天数
- `rank_turnover` 基于 composite_scores 排名，计算相邻两天的 Kendall tau 距离（归一化逆序对数），比 Jaccard 更适合全排列比较
- 当评估天数不足以拆分 baseline/drift 时（< 5 天），`drift_diagnostics` 为 null，warnings 中加 `INSUFFICIENT_DAYS_FOR_DRIFT`

---

## 5. 核心算法细节

### 5.1 IC 计算

```python
def _compute_daily_ic(signal_matrix: dict, forward_returns: dict[str, float]) -> dict:
    """
    signal_matrix: compute_signal_matrix() 的输出
    forward_returns: {symbol: float} T+fwd 收益率
    返回: {"per_factor": {factor_name: ic}, "composite": ic}
    """
    result = {}
    for factor in signal_matrix["factor_names"]:
        signal_series = pd.Series({
            r["symbol"]: r["signal_value"]
            for r in signal_matrix["rows"]
            if r["factor_name"] == factor and not math.isnan(r["signal_value"])
        })
        common = signal_series.index.intersection(forward_returns.keys())
        if len(common) >= 3:
            ic = signal_series[common].corr(
                pd.Series(forward_returns)[common], method="spearman"
            )
        else:
            ic = float("nan")
        result[factor] = ic

    # composite IC
    composite_series = pd.Series({
        cs["symbol"]: cs["composite_score"]
        for cs in signal_matrix["composite_scores"]
        if not math.isnan(cs["composite_score"])
    })
    common = composite_series.index.intersection(forward_returns.keys())
    if len(common) >= 3:
        result["composite"] = composite_series[common].corr(
            pd.Series(forward_returns)[common], method="spearman"
        )
    else:
        result["composite"] = float("nan")

    return result
```

Spearman 最低样本数：3 对。当前 5 symbols 满足，某天 bar 缺失导致 < 3 对有效数据时该天 IC 为 NaN，不计入汇总统计。

### 5.2 前瞻收益率获取

```python
def _get_forward_returns(bar_store, symbols, as_of, forward_days) -> dict[str, float]:
    """获取每个 symbol 从 as_of 到 T+forward_days 的收益率"""
    # 查询 as_of 及之后 forward_days+5 个自然日的 bars（留缓冲应对非交易日）
    end = (date.fromisoformat(as_of) + timedelta(days=forward_days + 5)).isoformat()
    bars = bar_store.list_bars(symbols, "1d", as_of, end, limit=len(symbols) * 10)

    for symbol:
        # 按 bar_time 排序，找到 <= as_of 的最后一根 bar 的 close（基准价）
        # 从 > as_of 的 bar 中取第 forward_days 根的 close（前瞻价）
        # forward_return = close_fwd / close_base - 1
        # 若找不到基准或前瞻 bar，该 symbol 不参与当天 IC 计算
```

**PIT 安全**：信号计算用 <= T 的 bar，前瞻收益用 T ~ T+fwd 的 bar，时间窗口严格分离。

### 5.3 漂移检测

```python
def _compute_drift(daily_stats, drift_window):
    baseline = daily_stats[:-drift_window]
    recent = daily_stats[-drift_window:]

    # per-factor: 比较 pre_winsorize.mean 的 z-score
    for factor:
        baseline_means = [s[factor]["mean"] for s in baseline]
        recent_mean = mean([s[factor]["mean"] for s in recent])
        if std(baseline_means) == 0:
            drift_z = 0.0  # 基线期不变，无法判断漂移
        else:
            drift_z = (recent_mean - mean(baseline_means)) / std(baseline_means)
        drift_flag = abs(drift_z) > 2.0
```

### 5.4 Kendall tau 排名周转率

```python
def _rank_turnover(rankings_prev: list[str], rankings_curr: list[str]) -> float:
    """归一化 Kendall tau 距离：逆序对数 / C(n,2)"""
    n = len(rankings_prev)
    index_map = {s: i for i, s in enumerate(rankings_curr)}
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = rankings_prev[i], rankings_prev[j]
            if index_map[a] > index_map[b]:
                discordant += 1
    return discordant / (n * (n - 1) / 2)
```

---

## 6. HTTP 端点

### 6.1 `POST /api/v1/signal/evaluate`

**路由文件**：`quant/src/interfaces/http/routes_signal.py`（追加）

```python
@router.post("/evaluate")
def post_signal_evaluate(
    req: SignalEvaluateRequest,
    service: SignalEvaluateService = Depends(get_signal_evaluate_service),
) -> SignalEvaluateResponse:
    return SignalEvaluateResponse.model_validate(
        service(req.start_date, req.end_date, req.forward_days)
    )
```

**请求 Schema**：

```python
class SignalEvaluateRequest(BaseModel):
    start_date: str = Field(description="评估起始日期，YYYY-MM-DD")
    end_date: str = Field(description="评估结束日期，YYYY-MM-DD")
    forward_days: int = Field(default=1, ge=1, le=10, description="前瞻天数（默认 1）")
```

**响应**：标准 CLI Output 包装，`data` 即 `SignalEvaluation`（schema 见 §4）。

### 6.2 依赖注入（dependencies.py）

```python
SignalEvaluateService = Callable[[str, str, int], dict]

def get_signal_evaluate_service() -> SignalEvaluateService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    if bar_store is None:
        raise HTTPException(status_code=503, detail="Signal evaluation requires database with real bar data")
    return lambda start, end, fwd: run_signal_evaluation(
        start_date=start, end_date=end, forward_days=fwd, bar_store=bar_store,
    )
```

**与 Phase 1 snapshot 端点的区别**：snapshot 可降级到 deterministic，evaluate 必须有 DB。

---

## 7. Rust CLI 命令

### 7.1 命令格式

```bash
hf signal evaluate --start-date 2026-03-01 --end-date 2026-04-01 [--forward-days 1] [--output json|table]
```

### 7.2 文件与模式

遵循 `hf signal snapshot` 的模式：

| 层 | 文件 | 职责 |
|---|---|---|
| cmd | `cli/src/cmd/signal.rs` | 新增 `Evaluate(EvaluateArgs)` 到 `SignalSubcommand` |
| request | `cli/src/application/requests.rs` | `SignalEvaluateRequest` struct + `AppCommand::SignalEvaluate` |
| handler | `cli/src/application/handlers/signal_evaluate.rs` | `handle()` → POST → json/table |
| dispatch | `cli/src/application/dispatch.rs` | `SignalEvaluate(req) => signal_evaluate::handle(req)` |
| http | `cli/src/infrastructure/http_client.rs` | `post_signal_evaluate(server_url, start, end, fwd, timeout)` |
| render | `cli/src/infrastructure/table_renderer.rs` | `render_signal_evaluate_table(json)` |

### 7.3 table 输出格式

```
┌ L3 信号评估 (2026-03-01 → 2026-04-01, T+1) ─────────────────┐
│ 评估天数: 20  标的数: 5                                        │
├───────────────────────────────────────────────────────────────┤
│ IC 报告                                                       │
├──────────────────────┬────────┬────────┬────────┬────────────┤
│ 因子                 │ 均值IC │ IC_IR  │ 命中率 │ 评级        │
├──────────────────────┼────────┼────────┼────────┼────────────┤
│ momentum_20          │  0.062 │  0.41  │ 65.0%  │ 中等        │
│ inv_volatility_20    │  0.035 │  0.23  │ 55.0%  │ 偏弱        │
│ ...                  │  ...   │  ...   │  ...   │ ...         │
├──────────────────────┼────────┼────────┼────────┼────────────┤
│ ★ 综合信号           │  0.085 │  0.71  │ 70.0%  │ 良好        │
├──────────────────────┴────────┴────────┴────────┴────────────┤
│ 漂移诊断                                                      │
├──────────────────────┬────────┬───────────────────────────────┤
│ 因子                 │ 漂移Z  │ 状态                           │
├──────────────────────┼────────┼───────────────────────────────┤
│ momentum_20          │ -0.38  │ ✓ 正常                        │
│ turnover_rate        │  2.31  │ ⚠ 漂移                        │
├──────────────────────┼────────┼───────────────────────────────┤
│ 覆盖率               │  0.00  │ ✓ 正常                        │
│ 排名周转率           │  0.20  │ ✓ 稳定                        │
└──────────────────────┴────────┴───────────────────────────────┘
```

评级规则（仅 table 展示用）：IC_IR >= 0.5 → 良好，0.2~0.5 → 中等，< 0.2 → 偏弱

---

## 8. Pydantic Schema 变更（interfaces/http/schemas.py）

### 8.1 新增 request

```python
class SignalEvaluateRequest(BaseModel):
    start_date: str = Field(description="评估起始日期，YYYY-MM-DD")
    end_date: str = Field(description="评估结束日期，YYYY-MM-DD")
    forward_days: int = Field(default=1, ge=1, le=10, description="前瞻天数")
```

### 8.2 新增 response models

```python
class DailyIC(BaseModel):
    date: str
    ic: float

class FactorICReport(BaseModel):
    factor_name: str
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: list[DailyIC]

class CompositeICReport(BaseModel):
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: list[DailyIC]

class ICReport(BaseModel):
    per_factor: list[FactorICReport]
    composite: CompositeICReport

class FactorDrift(BaseModel):
    factor_name: str
    baseline_mean: float
    baseline_std: float
    recent_mean: float
    drift_z: float
    drift_flag: bool

class CoverageDrift(BaseModel):
    baseline_mean: float
    recent_mean: float
    drift_z: float
    drift_flag: bool

class RankTurnover(BaseModel):
    mean_turnover: float
    max_turnover: float
    stable: bool

class DriftDiagnostics(BaseModel):
    drift_window: int
    baseline_days: int
    factor_drift: list[FactorDrift]
    coverage_drift: CoverageDrift
    rank_turnover: RankTurnover

class SignalEvaluation(BaseModel):
    eval_version: str
    start_date: str
    end_date: str
    forward_days: int
    trading_days_evaluated: int
    symbols: list[str]
    ic_report: ICReport
    drift_diagnostics: DriftDiagnostics | None

class SignalEvaluateResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: SignalEvaluation
    warnings: list[dict]
    errors: list[dict]
```

---

## 9. Domain Models 新增（domain/models/signal.py）

在已有 `SignalRow`、`TransformStats` 等 dataclass 之后追加：

```python
@dataclass(frozen=True)
class DailyICEntry:
    date: str
    ic: float

@dataclass(frozen=True)
class FactorICResult:
    factor_name: str
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: tuple[DailyICEntry, ...]

@dataclass(frozen=True)
class FactorDriftResult:
    factor_name: str
    baseline_mean: float
    baseline_std: float
    recent_mean: float
    drift_z: float
    drift_flag: bool

@dataclass(frozen=True)
class RankTurnoverResult:
    mean_turnover: float
    max_turnover: float
    stable: bool
```

---

## 10. 边界处理

| 场景 | 处理 |
|------|------|
| bar_store 不可用 | HTTP 503 错误；CLI 输出 error `BAR_STORE_REQUIRED` |
| 某天 bar 数据不足算因子（< 61 bars） | 跳过该天，warnings 中记录 `SKIPPED_DATE_INSUFFICIENT_BARS` |
| 某天 forward return 不可用（末尾几天） | 由 end_date - forward_days 截断，不出现此情况 |
| 评估天数 < 5 | IC 照常计算，drift_diagnostics 为 null + warning `INSUFFICIENT_DAYS_FOR_DRIFT` |
| 某天某 factor 全 NaN | 该天该 factor IC 为 NaN，不计入 mean_ic |
| Spearman 输入 < 3 对 | IC 为 NaN |
| baseline_std = 0（基线期因子完全不变） | drift_z = 0.0，drift_flag = false |
| forward_days > 评估区间天数 | 返回 error `INVALID_DATE_RANGE` |
| start_date >= end_date | 返回 error `INVALID_DATE_RANGE` |

---

## 11. 测试策略

### 11.1 单元测试（`quant/tests/unit/signal/`）

| 测试 | 验证点 |
|------|--------|
| `test_ic_basic_structure` | 构造 bar 数据 → ic_report 结构完整，per_factor 和 composite 均有值 |
| `test_ic_perfect_positive` | 构造 signal 与 return 完全正相关 → IC ≈ 1.0 |
| `test_ic_perfect_negative` | 完全负相关 → IC ≈ -1.0 |
| `test_ic_random` | 随机数据 → IC 绝对值接近 0 |
| `test_ic_ir_calculation` | IC_IR = mean_ic / ic_std |
| `test_hit_rate` | hit_rate = count(IC > 0) / total |
| `test_drift_flag_triggered` | 构造最近数据偏移 → drift_flag = true |
| `test_drift_no_flag` | 稳定数据 → drift_flag = false |
| `test_coverage_drift` | 构造 coverage 下降 → coverage drift flag |
| `test_rank_turnover_identical` | 排名不变 → turnover = 0 |
| `test_rank_turnover_reversed` | 排名完全反转 → turnover = 1.0 |
| `test_insufficient_days_drift_null` | < 5 天 → drift_diagnostics = null + warning |
| `test_forward_return_pit_safety` | 验证信号用 <= T 数据，收益用 T+fwd 数据 |

### 11.2 集成测试

- `test_signal_evaluate_with_mock_bar_store`：模拟 bar_store 返回多天 bar 数据，验证完整评估流程
- `test_signal_evaluate_no_bar_store_error`：无 bar_store → error 响应

### 11.3 架构测试

- 确认 `application/signal/signal_evaluate_service.py` 不依赖 `interfaces`
- 确认新增 domain models 不依赖 `application`

---

## 12. 须改文件清单

### Python（quant/）

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `quant/src/domain/models/signal.py` | 修改 | 新增 IC/Drift domain dataclasses |
| `quant/src/application/signal/signal_evaluate_service.py` | 新增 | 核心服务（run_signal_evaluation） |
| `quant/src/interfaces/http/schemas.py` | 修改 | 新增 SignalEvaluate* Pydantic models |
| `quant/src/interfaces/http/routes_signal.py` | 修改 | 新增 POST /api/v1/signal/evaluate 路由 |
| `quant/src/interfaces/http/dependencies.py` | 修改 | 新增 get_signal_evaluate_service provider |
| `quant/tests/unit/signal/test_signal_evaluate.py` | 新增 | IC + 漂移单元测试 |
| `quant/tests/architecture/test_layering_rules.py` | 修改 | 新增 evaluate service 架构检查 |

### Rust CLI（cli/）

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `cli/src/cmd/signal.rs` | 修改 | 新增 Evaluate 子命令 |
| `cli/src/application/requests.rs` | 修改 | 新增 SignalEvaluateRequest + AppCommand variant |
| `cli/src/application/handlers/signal_evaluate.rs` | 新增 | handle() handler |
| `cli/src/application/handlers/mod.rs` | 修改 | 注册 signal_evaluate module |
| `cli/src/application/dispatch.rs` | 修改 | 新增 SignalEvaluate 分发 |
| `cli/src/infrastructure/http_client.rs` | 修改 | 新增 post_signal_evaluate() |
| `cli/src/infrastructure/table_renderer.rs` | 修改 | 新增 render_signal_evaluate_table() |

### 文档

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `docs/CLI_OUTPUT_EXAMPLES.md` | 修改 | 新增 signal evaluate 示例 |

---

## 13. 验证命令

```bash
make check                    # 全量 CI 门禁
make architecture-check       # 架构边界
cd quant && uv run python -m pytest tests/unit/signal/ -q   # L3 全部单元测试
cd cli && cargo build         # Rust 编译
cd cli && cargo test          # Rust 测试
```
