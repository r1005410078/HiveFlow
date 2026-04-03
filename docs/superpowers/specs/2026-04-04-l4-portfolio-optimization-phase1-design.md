# L4 组合优化 Phase 1 设计

> 日期：2026-04-04
> 状态：待确认
> 前置：L3 Phase 2a（signal_evaluate 已合入 master）
> 范围：凸 QP 组合优化（alpha - risk - turnover cost）+ 独立评估命令 + daily pipeline 接入

---

## 1. 目标

为 HiveFlow 实现 L4 组合优化层，从 L3 信号（composite_score）生成目标权重 `target_weights`，打通 L0→L4 主链路。

### Phase 1 范围

- **目标函数**：`maximize αᵀw - λ_risk·wᵀΣw - λ_tc·Σ|wᵢ - w_prev_i|`
- **约束**：满仓（Σwᵢ=1）、单标的上限、行业暴露上限、非负（不做空）
- **风险模型**：历史样本协方差矩阵（60 日窗口，年化）
- **独立评估命令**：`hf portfolio optimize --as-of DATE`
- **Pipeline 接入**：独立命令验证后，接入 `run_daily()` 主链路

### 明确不做

- 不支持 `--prev-weights-file` CLI 参数（留 Phase 2）
- 不做中性化（留 L3 Phase 2b）
- 不做容量约束（成交量占比，留 Phase 2）
- 不做 L5 风险门控接入（L5 未开始）
- 不引入新 DB 表

---

## 2. 架构与文件布局

### 2.1 Python（`quant/src/`）

```
domain/models/
  portfolio.py                        # 新增：PortfolioOptimizationResult, OptimizationStatus domain dataclass

application/portfolio/
  __init__.py                         # 新增
  covariance_service.py               # 新增：历史收益率协方差矩阵 Σ
  optimizer_service.py                # 新增：cvxpy QP 问题构建 + 求解
  portfolio_optimize_service.py       # 新增：编排，处理 fallback，暴露 run_portfolio_optimize()

interfaces/http/
  schemas.py                          # 新增：PortfolioOptimize* Pydantic models
  routes_portfolio.py                 # 新增：POST /api/v1/portfolio/optimize
  dependencies.py                     # 新增：get_portfolio_optimize_service provider
```

### 2.2 Rust CLI（`cli/src/`）

```
cmd/portfolio.rs                      # 新增：portfolio optimize 子命令（--as-of, --output）
application/requests.rs               # 新增：PortfolioOptimizeRequest + AppCommand::PortfolioOptimize
application/handlers/
  mod.rs                              # 注册 portfolio_optimize module
  portfolio_optimize.rs               # 新增：handle() → POST /api/v1/portfolio/optimize
application/dispatch.rs               # 新增：PortfolioOptimize 分发
infrastructure/
  http_client.rs                      # 新增：post_portfolio_optimize()
  table_renderer.rs                   # 新增：render_portfolio_optimize_table()
```

### 2.3 依赖方向

```
portfolio_optimize_service (application/portfolio)
  → covariance_service (application/portfolio)   # 协方差计算
  → optimizer_service (application/portfolio)    # cvxpy 求解
  → bar_store (通过函数参数注入，不直接依赖 infrastructure)
  → signal_engineering_service (application/signal)  # 获取 composite_score（当 alpha 未传入时）

routes_portfolio (interfaces/http)
  → portfolio_optimize_service (通过 dependencies.py 注入)
```

符合 `interfaces → application → domain` 方向约束。Rust CLI 遵循 `cmd → application → infrastructure` 方向。

### 2.4 不改动的文件

- `application/signal/signal_engineering_service.py`：复用 `run_signal_snapshot()`
- `hiveflow/portfolio/application/allocate_use_case.py`：空壳保留，不改
- `hiveflow/portfolio/domain/target_weight.py`：保留，不改

---

## 3. 目标函数与约束

### 3.1 优化问题

```
变量：w ∈ ℝⁿ（n = 标的数）

maximize:   αᵀw  -  λ_risk · wᵀΣw  -  λ_tc · Σ tᵢ

subject to:
  Σwᵢ = 1                              # 满仓
  0 ≤ wᵢ ≤ w_max        ∀i            # 单标的上限，不做空
  Σ_{i∈industry_k} wᵢ ≤ ind_max  ∀k  # 行业暴露上限
  tᵢ ≥ wᵢ - w_prev_i               ∀i  # 换手辅助变量（线性化绝对值）
  tᵢ ≥ w_prev_i - wᵢ               ∀i
  tᵢ ≥ 0                             ∀i
```

`λ_tc · Σ tᵢ` 等价于 `λ_tc · Σ|wᵢ - w_prev_i|`，通过辅助变量 `t` 保持凸性。

### 3.2 参数默认值

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `lambda_risk` | `1.0` | 风险厌恶系数 |
| `lambda_tc` | `0.001` | 交易成本系数（等效万一双边） |
| `w_max` | `0.30` | 单标的权重上限 |
| `ind_max` | `0.40` | 单行业权重上限 |
| `lookback_days` | `60` | 协方差计算窗口（日历天） |

### 3.3 协方差计算

1. 从 `bar_store` 取 `[as_of - lookback_days, as_of]` 日频收盘价
2. 计算日收益率（`pct_change()`），去掉第一行 NaN
3. 若某标的有效数据不足 20 天，该标的协方差列/行替换为对角项（等方差近似，方差取所有标的均值）
4. 样本协方差矩阵乘以 252 年化

### 3.4 行业映射

Phase 1 使用静态映射表（与 `basic_factor_service.py` 现有行业划分一致），不引入新数据源。若标的不在映射表中，归入 `"other"` 行业。

---

## 4. Fallback 策略

| 触发条件 | Fallback 行为 | optimization_status |
|----------|--------------|---------------------|
| cvxpy 求解成功（optimal / optimal_inaccurate） | 使用求解结果 | `optimal` / `optimal_inaccurate` |
| 求解失败 + prev_weights 全为零 | 等权分配（1/n） | `fallback_equal_weight` |
| 求解失败 + prev_weights 非零 | 维持上期权重（归一化） | `fallback_prev_weight` |
| 极端情况（上期权重也无效） | 等权分配 | `fallback_equal_weight` |

所有 fallback 路径：
- CLI 输出 `status: "warning"`（非 `"error"`，因组合有值）
- `fallback_reason` 字段记录求解器返回的失败原因
- 审计日志打印 WARNING 级别

---

## 5. HTTP 接口

### `POST /api/v1/portfolio/optimize`

**请求体**（全部字段可选，除 `as_of`）：

```json
{
  "as_of": "2026-04-01",
  "alpha": {"000001.SZ": 0.85, "600519.SH": 1.20, "300750.SZ": 0.60},
  "prev_weights": {"000001.SZ": 0.20, "600519.SH": 0.35},
  "lambda_risk": 1.0,
  "lambda_tc": 0.001,
  "w_max": 0.30,
  "ind_max": 0.40,
  "lookback_days": 60
}
```

- `alpha` 缺省时：自动调用 `run_signal_snapshot(as_of)` 取 composite_score
- `prev_weights` 缺省时：视为全零向量

**响应**（CLI_OUTPUT_SCHEMA 标准包装）：

```json
{
  "schema_version": "1.0.0",
  "command": "hf portfolio optimize",
  "run_id": "run_20260401_abc12345",
  "status": "ok",
  "generated_at": "2026-04-01T10:00:00Z",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "optimization_status": "optimal",
    "fallback_reason": null,
    "target_weights": [
      {"symbol": "600519.SH", "weight": 0.2987, "prev_weight": 0.0, "delta": 0.2987},
      {"symbol": "000001.SZ", "weight": 0.2341, "prev_weight": 0.0, "delta": 0.2341},
      {"symbol": "300750.SZ", "weight": 0.1823, "prev_weight": 0.0, "delta": 0.1823},
      {"symbol": "601318.SH", "weight": 0.1521, "prev_weight": 0.0, "delta": 0.1521},
      {"symbol": "000333.SZ", "weight": 0.1328, "prev_weight": 0.0, "delta": 0.1328}
    ],
    "optimization_report": {
      "objective_value": 0.4231,
      "risk_contribution": 0.0312,
      "turnover_cost": 0.0018,
      "solver": "CLARABEL",
      "solve_time_ms": 42
    }
  },
  "warnings": [],
  "errors": []
}
```

`optimization_status` 取值：`optimal` / `optimal_inaccurate` / `fallback_equal_weight` / `fallback_prev_weight`

---

## 6. CLI 命令

```bash
hf portfolio optimize --as-of 2026-04-01 [--output json|table]
```

**table 输出示例**：

```
组合优化结果（2026-04-01）  求解状态: optimal  求解器: CLARABEL  耗时: 42ms
标的         目标权重   上期权重   变动
600519.SH    29.87%     0.00%    +29.87%
000001.SZ    23.41%     0.00%    +23.41%
300750.SZ    18.23%     0.00%    +18.23%
601318.SH    15.21%     0.00%    +15.21%
000333.SZ    13.28%     0.00%    +13.28%
```

---

## 7. Daily Pipeline 接入

独立命令验证通过后，在 `run_daily()` 中 L3 信号快照步骤之后新增调用：

```python
portfolio_result = run_portfolio_optimize(
    as_of=as_of,
    alpha={r["symbol"]: r["composite_score"] for r in signal_matrix["composite_scores"]},
    bar_store=bar_store,
)
```

结果追加到 daily output 的 `data.portfolio` 字段，不修改现有字段。若 L4 调用失败（异常），pipeline 降级为 WARNING 并继续，不阻断主链路。

---

## 8. 测试策略

### 单元测试（`quant/tests/unit/`）

- `test_covariance_service.py`：mock bar_store；验证协方差矩阵维度；数据不足 20 天时降级为对角阵
- `test_optimizer_service.py`：给定固定 alpha + Σ；验证权重之和 = 1、单标的 ≤ w_max、行业约束生效；infeasible 输入时返回正确 fallback status
- `test_portfolio_optimize_service.py`：验证 fallback 路径（prev_weights 全零 → 等权）；ok_output 包装格式正确

### 契约测试（`quant/tests/contract/`）

新增 fixture `tests/fixtures/cli_output/valid/portfolio_optimize.json`，通过 `make validate-cli-output` 校验 schema。

### 架构测试（`quant/tests/architecture/`）

- `application/portfolio/` 不直接引入 FastAPI / HTTP 框架
- `domain/models/portfolio.py` 不依赖 `application` 或 `infrastructure`

### Rust 架构测试（`cli/tests/architecture_rules.rs`）

- `cmd/portfolio.rs` 不直接引用 `infrastructure`
- `domain/` 不引用 `infrastructure`

### 集成测试（`quant/tests/integration/`，需服务端 + DB）

- `test_portfolio_optimize_integration.py`：端到端验证 `POST /api/v1/portfolio/optimize` 返回合法权重（sum=1，各项在 [0, w_max]）

---

## 9. 依赖新增

- Python：`cvxpy`（加入 `quant/pyproject.toml`）
- Rust：无新依赖
