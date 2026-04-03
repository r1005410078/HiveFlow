# L3 信号工程 Phase 1 设计

> 日期：2026-04-03
> 状态：待确认
> 范围：最小可用——去极值 + zscore 标准化 + 等权聚合，打通 L2→L3 端到端通路

---

## 1. 目标

将 L2 `factor_snapshot` 中的 raw factor values 转换为可比较、可聚合的标准化信号，以 `signal_matrix` 形式并行输出到 daily pipeline，为后续 L4 组合优化做准备。

### Phase 1 范围

- 去极值（winsorize，复用已有 `winsorize_then_zscore`）
- 标准化（zscore）
- 等权聚合（composite score = mean of all signal values per symbol）
- 诊断指标：`coverage_rate` + per-factor `transform_stats`（前后 mean/std/min/max）

### 明确不做

- 缺失处理的复杂策略（行业中位/分组回填）——Phase 1 直接 NaN drop
- 中性化（行业/市值回归取残差）——需行业分类数据，Phase 2
- IC 计算（需 T+1 收益，PIT 语义复杂）——Phase 2
- 漂移检测——Phase 2
- 不改动 `l2_decision` ranking 逻辑

---

## 2. 架构与文件布局

遵循现有分层模式，新增文件以 `**` 标注：

### 2.1 Python（quant/src/）

```
quant/src/
├── domain/models/
│   └── signal.py **                  # SignalRow, TransformStats dataclass
├── application/signal/
│   ├── __init__.py **
│   └── signal_engineering_service.py ** # compute_signal_matrix()
├── interfaces/http/
│   ├── schemas.py                    # 新增 Signal* Pydantic models，DailyRunData 加字段
│   ├── routes_signal.py **           # POST /api/v1/signal/snapshot 路由
│   └── dependencies.py              # 新增 get_signal_snapshot_service provider
└── hiveflow/
    └── signal/application/
        └── normalize_use_case.py     # 已有 winsorize_then_zscore（被 service 调用）
```

### 2.2 Rust CLI（cli/src/）

```
cli/src/
├── cmd/
│   ├── mod.rs                        # 新增 Signal 顶级命令注册
│   └── signal.rs **                  # hf signal snapshot --as-of --output
├── application/
│   ├── requests.rs                   # 新增 SignalSnapshotRequest, AppCommand::SignalSnapshot
│   ├── handlers/
│   │   ├── mod.rs                    # 新增 signal_snapshot module
│   │   └── signal_snapshot.rs **     # handle() → POST /api/v1/signal/snapshot
│   └── dispatch.rs                   # 新增 SignalSnapshot 分发
└── infrastructure/
    ├── http_client.rs                # 新增 post_signal_snapshot()
    └── table_renderer.rs             # 新增 render_signal_snapshot_table()
```

### 2.3 已有文件无需改动

- `hiveflow/contracts/l3_inputs.py`（L2→L3 契约）
- `hiveflow/signal/domain/signal_value.py`（保留，暂不扩展）

### 2.4 依赖方向

```
daily_run_service (application)
  → signal_engineering_service (application/signal)
    → normalize_use_case (hiveflow/signal/application)
    → domain/models/signal (domain)
  → l2_decision_service (application/decision)  # 不变

routes_signal (interfaces/http)
  → signal_engineering_service (application/signal)  # 通过 dependencies.py 注入
```

符合 `interfaces → application → domain` 方向约束。`hiveflow/signal/application` 被 `application/signal` 调用是跨 package 但同层（application → hiveflow subdomain application），不违反分层规则。Rust CLI 遵循 `cmd → application → infrastructure` 方向。

---

## 3. 数据流

```
factor_snapshot.rows
  │  (list[L2FactorSnapshotRow])
  ▼
┌─────────────────────────────────┐
│ signal_engineering_service      │
│                                 │
│ 1. pivot → wide DataFrame       │
│    (symbol × factor_name)       │
│                                 │
│ 2. per-factor:                  │
│    a. record pre_stats          │
│    b. winsorize_then_zscore()   │
│    c. record post_stats         │
│                                 │
│ 3. per-symbol:                  │
│    composite = mean(signals)    │
│    (skip NaN factors)           │
│                                 │
│ 4. assemble signal_matrix       │
└─────────────────────────────────┘
  │
  ▼
signal_matrix dict → 塞入 daily pipeline data
```

---

## 4. 输出 Schema

### 4.1 `signal_matrix` 顶层

```python
{
    "schema_version": "1.0",
    "generated_at": "<ISO-8601>",
    "producer_version": "quant-l3",
    "signal_version": "l3-signal-v1.0",
    "factor_names": ["momentum_20", "inv_volatility_20", ...],
    "coverage_rate": 0.95,          # 有效信号行 / (symbols × factors)
    "rows": [...],                  # list[SignalRow]
    "composite_scores": [...],      # list[CompositeScore]
    "transform_stats": [...],       # list[TransformStats]
}
```

### 4.2 `SignalRow`

每条 = 一个 (symbol, factor) 对的标准化信号。

```python
{
    "symbol": "600519.SH",
    "factor_name": "momentum_20",
    "raw_value": 0.0532,            # 来自 L2
    "signal_value": 1.23,           # winsorize + zscore 后
    "direction": 1,                 # 继承自 L2
}
```

### 4.3 `CompositeScore`

每个 symbol 的聚合分（等权 mean）。

```python
{
    "symbol": "600519.SH",
    "composite_score": 0.87,        # mean(signal_values)
    "factor_count": 6,              # 参与聚合的因子数（非 NaN）
}
```

### 4.4 `TransformStats`

每个 factor 的变换前后统计，用于 sanity check。

```python
{
    "factor_name": "momentum_20",
    "pre_winsorize": {
        "count": 5,
        "mean": 0.042,
        "std": 0.031,
        "min": -0.012,
        "max": 0.098,
    },
    "post_zscore": {
        "count": 5,
        "mean": 0.0,               # zscore 后 mean ≈ 0
        "std": 1.0,                 # zscore 后 std ≈ 1
        "min": -1.52,
        "max": 1.81,
    },
}
```

---

## 5. 核心实现细节

### 5.1 `signal_engineering_service.compute_signal_matrix`

```python
def compute_signal_matrix(factor_snapshot: dict) -> dict:
    """
    输入: L2 factor_snapshot (含 rows, factor_names, coverage_rate)
    输出: signal_matrix dict (schema 见 §4)
    """
```

**算法步骤：**

1. **Pivot**：将 `factor_snapshot["rows"]` 透视为 `DataFrame[symbol × factor_name]`，取 `raw_value`。
2. **Direction 对齐**：从 rows 中提取每个 factor 的 `direction`（+1 或 -1）。若 direction = -1，翻转该列（乘以 -1），使所有因子统一为「越大越好」。
3. **Per-factor 变换**：
   - 记录 `pre_stats`（count/mean/std/min/max）
   - 调用 `winsorize_then_zscore(series, lower=0.05, upper=0.95)`
   - 记录 `post_stats`
4. **Composite**：对每个 symbol，取所有非 NaN signal_values 的 mean 作为 composite_score。
5. **Coverage**：`coverage_rate = 非 NaN 信号总数 / (symbols × factors)`。
6. **组装**输出 dict。

### 5.2 边界处理

| 场景 | 处理 |
|------|------|
| factor 列全为 NaN | 跳过该 factor，transform_stats 记录 count=0 |
| factor 列仅 1 个值 | winsorize 无效果，zscore std=0 → 产出 NaN，记录 post_stats |
| symbol 所有 factor 均 NaN | composite_score = NaN，factor_count = 0 |
| factor_snapshot.rows 为空 | 返回空 signal_matrix（rows=[], composite_scores=[], coverage=0） |
| direction 字段缺失 | 默认 +1 |

### 5.3 direction 对齐说明

L2 的 6 个因子中：
- `inv_volatility_20`（direction=+1）：波动率倒数，越大越好 ✓
- `turnover_rate`（direction=-1）：换手率，越小越好 → 翻转为 -turnover_rate 再标准化
- 其余 4 个 direction=+1

翻转在 winsorize 之前执行，确保去极值的分位数语义正确。

---

## 6. 集成：daily_run_service 改动

在 `run_daily()` 中，`compute_l2_decision` 之后新增一步：

```python
# 现有
l2_decision = compute_l2_decision_from_snapshot(...)

# 新增
signal_matrix = compute_signal_matrix(factor_snapshot)

return ok_output(
    ...,
    data={
        "as_of": as_of,
        "data_manifest_id": ...,
        "factor_snapshot": factor_snapshot,
        "execution_plan": {"orders": []},
        "l2_decision": l2_decision,
        "signal_matrix": signal_matrix,       # 新增
    },
    ...
)
```

**韧性**：`compute_signal_matrix` 调用用 try/except 包裹，失败时 `signal_matrix` 设为 `None`，记录 warning，不阻断 daily pipeline。

---

## 7. 独立 HTTP 端点

### 7.1 `POST /api/v1/signal/snapshot`

**路由文件**：`quant/src/interfaces/http/routes_signal.py`

```python
router = APIRouter(prefix="/api/v1/signal", tags=["signal"])

@router.post("/snapshot")
def post_signal_snapshot(req: SignalSnapshotRequest, service=Depends(get_signal_snapshot_service)):
    return SignalSnapshotResponse.model_validate(service(req.as_of))
```

**请求 Schema**：

```python
class SignalSnapshotRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")
```

**响应**：标准 CLI Output 包装，`data` 即 `signal_matrix`（schema 见 §4）。

```json
{
  "schema_version": "1.0.0",
  "command": "hf signal snapshot",
  "run_id": "...",
  "status": "ok",
  "generated_at": "...",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": { /* signal_matrix */ },
  "warnings": [],
  "errors": []
}
```

**依赖注入**（`dependencies.py`）：

```python
SignalSnapshotService = Callable[[str], dict]

def get_signal_snapshot_service() -> SignalSnapshotService:
    bar_store = ...  # 复用 daily pipeline 的 bar_store 构造逻辑
    return lambda as_of: run_signal_snapshot(as_of=as_of, bar_store=bar_store)
```

`run_signal_snapshot` 是一个轻量编排函数（放在 `application/signal/signal_engineering_service.py`），内部调用 L2 factor 计算 + L3 signal 计算，不走完整 daily pipeline。

### 7.2 路由注册

在 FastAPI app 初始化处（与 `routes_daily_run.router` 同级）注册 `routes_signal.router`。

---

## 8. Rust CLI 命令

### 8.1 命令格式

```bash
hf signal snapshot --as-of 2026-04-01 --output json|table
```

### 8.2 文件与模式

遵循 `hf pipeline daily` 的模式：

| 层 | 文件 | 职责 |
|---|---|---|
| cmd | `cli/src/cmd/signal.rs` | `SignalArgs` / `SignalSubcommand::Snapshot` / `SnapshotArgs`（clap） |
| cmd | `cli/src/cmd/mod.rs` | 注册 `Signal(signal::SignalArgs)` 到 `Commands` enum |
| request | `cli/src/application/requests.rs` | `SignalSnapshotRequest` struct + `AppCommand::SignalSnapshot` |
| handler | `cli/src/application/handlers/signal_snapshot.rs` | `handle()` → 调用 `http_client::post_signal_snapshot` → json/table 输出 |
| dispatch | `cli/src/application/dispatch.rs` | `SignalSnapshot(req) => signal_snapshot::handle(req)` |
| http | `cli/src/infrastructure/http_client.rs` | `post_signal_snapshot(server_url, as_of, timeout_ms)` |
| render | `cli/src/infrastructure/table_renderer.rs` | `render_signal_snapshot_table(json)` |

### 8.3 table 输出格式

```
┌ L3 信号快照 (2026-04-01) ─────────────────────────────────┐
│ 信号版本: l3-signal-v1.0  覆盖率: 95.0%                   │
├──────────┬──────────────┬──────────┬──────────┬───────────┤
│ 标的     │ 因子         │ 原始值   │ 信号值   │ 方向      │
├──────────┼──────────────┼──────────┼──────────┼───────────┤
│ 600519.SH│ momentum_20  │  0.0532  │  1.2300  │ +1        │
│ ...      │ ...          │  ...     │  ...     │ ...       │
├──────────┴──────────────┴──────────┴──────────┴───────────┤
│ 综合分排名                                                 │
├──────────┬──────────────┬─────────────────────────────────┤
│ 标的     │ 综合分       │ 参与因子数                       │
├──────────┼──────────────┼─────────────────────────────────┤
│ 600519.SH│  0.8700      │ 6                               │
└──────────┴──────────────┴─────────────────────────────────┘
```

---

## 9. Pydantic Schema 变更（interfaces/http/schemas.py）

### 9.1 新增 request

```python
class SignalSnapshotRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")
```

### 9.2 新增 response models

```python
class SignalRow(BaseModel):
    symbol: str
    factor_name: str
    raw_value: float
    signal_value: float
    direction: int

class SignalCompositeScore(BaseModel):
    symbol: str
    composite_score: float
    factor_count: int

class SignalTransformStatsDetail(BaseModel):
    count: int
    mean: float
    std: float
    min: float
    max: float

class SignalTransformStats(BaseModel):
    factor_name: str
    pre_winsorize: SignalTransformStatsDetail
    post_zscore: SignalTransformStatsDetail

class SignalMatrix(BaseModel):
    schema_version: str
    generated_at: str
    producer_version: str
    signal_version: str
    factor_names: list[str]
    coverage_rate: float
    rows: list[SignalRow]
    composite_scores: list[SignalCompositeScore]
    transform_stats: list[SignalTransformStats]
```

`DailyRunData` 新增 optional 字段：

```python
class DailyRunData(BaseModel):
    as_of: str
    data_manifest_id: str
    factor_snapshot: FactorSnapshot
    execution_plan: ExecutionPlan
    l2_decision: L2Decision
    signal_matrix: SignalMatrix | None = None   # 新增
```

### 9.3 新增 response 包装

```python
class SignalSnapshotResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: SignalMatrix
    warnings: list[dict]
    errors: list[dict]
```

---

## 10. Domain Models（domain/models/signal.py）

```python
@dataclass(frozen=True)
class SignalRow:
    symbol: str
    factor_name: str
    raw_value: float
    signal_value: float
    direction: int

@dataclass(frozen=True)
class TransformStatsDetail:
    count: int
    mean: float
    std: float
    min_val: float
    max_val: float

@dataclass(frozen=True)
class TransformStats:
    factor_name: str
    pre_winsorize: TransformStatsDetail
    post_zscore: TransformStatsDetail

@dataclass(frozen=True)
class CompositeScore:
    symbol: str
    composite_score: float
    factor_count: int
```

---

## 11. 测试策略

### 11.1 单元测试（`quant/tests/unit/signal/`）

| 测试 | 验证点 |
|------|--------|
| `test_signal_engineering_basic` | 5 symbols × 6 factors → signal_matrix 结构完整，rows 数量正确 |
| `test_zscore_properties` | post_zscore mean ≈ 0，std ≈ 1（>2 个不同值时） |
| `test_direction_flip` | turnover_rate (direction=-1) 翻转后信号方向正确 |
| `test_composite_equal_weight` | composite_score = mean(signal_values)，精度 6 位 |
| `test_empty_snapshot` | 空 rows → 空 signal_matrix，coverage=0 |
| `test_single_value_factor` | 仅 1 个值时 zscore → NaN，不报错 |
| `test_coverage_rate` | NaN 存在时 coverage < 1.0 |

### 11.2 集成测试

- `test_daily_pipeline_includes_signal_matrix`：调用 `run_daily()`，验证返回 `data.signal_matrix` 非 None 且 schema 符合预期
- `test_daily_pipeline_signal_matrix_failure_resilient`：mock `compute_signal_matrix` 抛异常，验证 daily 仍返回 ok + warning

### 11.3 架构测试

- 确认 `application/signal/` 不依赖 `interfaces`
- 确认 `domain/models/signal` 不依赖 `application`

---

## 12. 须改文件清单

### Python（quant/）

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `quant/src/domain/models/signal.py` | 新增 | Domain dataclasses |
| `quant/src/application/signal/__init__.py` | 新增 | Package init |
| `quant/src/application/signal/signal_engineering_service.py` | 新增 | 核心服务（compute_signal_matrix + run_signal_snapshot） |
| `quant/src/application/daily_run_service.py` | 修改 | 调用 signal service，塞入 data |
| `quant/src/interfaces/http/schemas.py` | 修改 | 新增 Signal* Pydantic models，DailyRunData 加字段 |
| `quant/src/interfaces/http/routes_signal.py` | 新增 | POST /api/v1/signal/snapshot 路由 |
| `quant/src/interfaces/http/dependencies.py` | 修改 | 新增 get_signal_snapshot_service provider |
| `quant/src/interfaces/http/app.py`（或注册处） | 修改 | 注册 routes_signal.router |
| `quant/tests/unit/signal/test_signal_engineering.py` | 新增 | 单元测试 |
| `quant/tests/unit/signal/test_normalize_use_case.py` | 保留 | 已有测试不动 |
| `quant/tests/architecture/test_layer_deps.py` | 修改 | 新增 L3 层依赖检查 |

### Rust CLI（cli/）

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `cli/src/cmd/signal.rs` | 新增 | SignalArgs / SnapshotArgs（clap 参数定义） |
| `cli/src/cmd/mod.rs` | 修改 | 注册 Signal 命令到 Commands enum |
| `cli/src/application/requests.rs` | 修改 | 新增 SignalSnapshotRequest + AppCommand variant |
| `cli/src/application/handlers/signal_snapshot.rs` | 新增 | handle() handler |
| `cli/src/application/handlers/mod.rs` | 修改 | 注册 signal_snapshot module |
| `cli/src/application/dispatch.rs` | 修改 | 新增 SignalSnapshot 分发 |
| `cli/src/infrastructure/http_client.rs` | 修改 | 新增 post_signal_snapshot() |
| `cli/src/infrastructure/table_renderer.rs` | 修改 | 新增 render_signal_snapshot_table() |

### 文档

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `docs/CLI_OUTPUT_EXAMPLES.md` | 修改 | daily pipeline 示例增加 signal_matrix；新增 signal snapshot 示例 |

### 无需改动

- `hiveflow/contracts/l3_inputs.py`：已有契约无需变更
- `hiveflow/signal/application/normalize_use_case.py`：已有实现直接复用

---

## 13. 验证命令

```bash
make check                    # 全量 CI 门禁
make architecture-check       # 架构边界
cd quant && uv run python -m pytest tests/unit/signal/ -q   # L3 单元测试
cd cli && cargo build         # Rust 编译
cd cli && cargo test          # Rust 测试
```
