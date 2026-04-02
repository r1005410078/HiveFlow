# L2-A Explainable Candidate Ranking Design

## 1. Context

当前 `daily` 输出已包含：

- `factor_snapshot`（`l2-basic-v1`）
- `execution_plan.orders`（当前为空）

本次只实现 L2 的“可解释候选输出”，不进入下单与执行编排。

## 2. Goal

在 `factor_snapshot` 基础上新增 `l2_decision`，产出 `top_candidates=5` 与详版 `score_breakdown`，满足”业务可用优先”。

## 3. Scope

In Scope:

- 新增 L2 打分与解释服务（application 层）
- 在 daily 输出中新增 `data.l2_decision`
- 更新 HTTP response schema 与契约测试

Out of Scope:

- 生成真实交易订单（`execution_plan.orders` 继续保持空数组）
- 引入新的外部数据源或行业/基本面过滤
- L3 风控、成本、执行路由

## 4. Constraints

- 严格遵守分层：`interfaces -> application -> domain`
- `interfaces/http` 只做 DTO 与 service 调用，不写业务算法
- 输出必须确定性（同输入同输出），便于回放与回归测试

## 5. Output Contract

在 `data` 节点新增：

```json
{
  "l2_decision": {
    "schema_version": "1.0",
    "generated_at": "2026-04-02T14:30:00+08:00",
    "producer_version": "quant-l2",
    "score_version": "l2-score-v1",
    "universe_size": 2,
    "top_candidates": [
      {"symbol": "600519.SH", "score": 0.8123, "rank": 1}
    ],
    "score_breakdown": [
      {
        "symbol": "600519.SH",
        "final_score": 0.8123,
        "factors": [
          {
            "factor_name": "momentum_20",
            "raw_value": 0.024,
            "normalized_value": 0.86,
            "percentile": 0.95,
            "clipped": false,
            "anomaly_flags": [],
            "weight": 0.5,
            "contribution": 0.43
          }
        ]
      }
    ]
  }
}
```

字段说明：

- `schema_version`：`l2_decision` 契约版本，破坏性变更需升级主版本
- `generated_at`：本次 `l2_decision` 生成时间（ISO8601，带时区）
- `producer_version`：产出组件版本（用于回放定位）
- `score_version`：评分公式版本，固定为 `l2-score-v1`
- `universe_size`：当日参与打分的标的总数（含因子缺失但以 0.0 填补后仍参与打分的标的）
- `top_candidates`：按 `final_score` 降序取前 5（样本不足时返回实际数量）
- `score_breakdown`：全样本解释明细，含分位、截断、异常标记
- `contribution`：单因子对最终分数的贡献度，计算公式为 `weight * normalized_value`

## 6. Scoring Design (v1)

### 6.1 Factors

使用现有三因子：

- `momentum_20`：20 日动量，衡量近 20 个交易日价格趋势强弱（越高代表近期趋势越强）。
- `inv_volatility_20`：20 日波动率倒数，衡量价格稳定性（越高代表波动越小、稳定性越好）。
- `turnover_rate`：换手率，衡量交易活跃度与流动性水平（适中偏高通常更利于执行）。

### 6.2 Steps

1. 按 `symbol` 聚合 `factor_snapshot.rows`（长表转宽逻辑）
2. **缺失值处理**：因子缺失时用默认值 `0.0` 填补，记录 `anomaly_flags=["missing_factor:<name>"]`
3. **分位截断**：对每个因子计算 p1 和 p99，将原始值截断到 `[p1, p99]`，记录 `clipped` 标志
4. **min-max 标准化**：截断后的值 → `normalized_value = (x - min) / (max - min)`；若全样本同值（`max == min`），**跳过 min-max 标准化**，设 `normalized_value=1.0`、`percentile=1.0`，记录 `anomaly_flags=["flat_distribution:<name>"]`，并跳过步骤 5
5. **分位计算**（仅在非 flat_distribution 时执行）：基于截断后的值计算 `percentile`（同批样本内分位）
6. **因子贡献度**：计算 `contribution = weight * normalized_value`
7. **加权求和**：`final_score = sum(weight_i * normalized_value_i)`，四舍五入到 6 位小数
8. **排序与生成候选**：先按 `final_score desc`，再按 `symbol asc`，取前 5 生成 `top_candidates`

### 6.3 Weights (v1)

- `momentum_20`: `0.5`
- `inv_volatility_20`: `0.3`
- `turnover_rate`: `0.2`

**权重说明**：
- Phase 1 初始权重基于启发式设计；Phase 2 后续通过因子 IC/Sharpe 回测优化

### 6.4 Factor Extension (v1.1 / Phase 2)

在不破坏 `v1` 可回放性的前提下，Phase 2 将扩展以下三因子：

- `max_drawdown_60`：回撤控制因子，衡量过去 60 交易日下行风险（回撤越小越优）。
- `trend_stability_20`：趋势连续性因子，衡量近 20 交易日趋势的一致性，减少假突破影响。
- `relative_strength_vs_index`：相对基准强弱因子，衡量个股相对基准（如沪深 300）的超额表现。

建议升级版本号为 `l2-score-v1.1`，并采用如下初始权重（总和=1.0）：

- `momentum_20`: `0.25`
- `inv_volatility_20`: `0.15`
- `turnover_rate`: `0.10`
- `max_drawdown_60`: `0.20`
- `trend_stability_20`: `0.15`
- `relative_strength_vs_index`: `0.15`

说明：

- 保留趋势维度（`momentum_20`）为最大单因子，但降低其独占权重；
- 风险控制维度（`max_drawdown_60` + `inv_volatility_20`）合计 `0.35`；
- 趋势质量与相对强弱（`trend_stability_20` + `relative_strength_vs_index`）合计 `0.30`，提升“有效趋势”筛选能力；
- 流动性（`turnover_rate`）保持 `0.10`，用于执行可行性约束而非主导收益排序。

### 6.5 Deterministic Rules

- **截断与标准化流程**：
  1. 原始值 `raw_value` → 分位截断（p1~p99） → 截断后的值
  2. 截断后的值 → min-max 标准化 → `normalized_value` 
  3. `clipped = True` 当且仅当值在截断过程中被修改
  
- `normalized_value`（min-max）：`(x - min) / (max - min)`；若 `max == min`（flat_distribution），`normalized_value=1.0`，`percentile=1.0`，不执行 clipping。
- `percentile`：仅在非 flat_distribution 时计算；使用截断后的值，`rank(method="average") / N`（同值取平均名次），范围 `(0, 1]`。
- `contribution`：单因子贡献度 = `weight * normalized_value`。
- `final_score`：`sum(weight_i * normalized_value_i)`，等价于 `sum(contribution_i)`，结果四舍五入到 6 位小数。
- 一致性约束：`sum(score_breakdown.factors[].contribution)` 必须等于 `final_score`（6 位精度内）。
- 排序与并列：先按 `final_score desc`，再按 `symbol asc`，确保同输入稳定输出。
- `score_version`：由代码常量 `SCORE_VERSION = "l2-score-v1"` 控制，Phase 2 升级时同步更新常量与本文档版本号，`score_version` 变更时须同步升级 `schema_version`。

## 7. Error Handling

### 7.1 缺失与异常处理

- **某因子缺失**：以默认值 `0.0` 填补，并写入 `anomaly_flags=["missing_factor:<factor_name>"]`
- **全样本同值**（`max == min`）：`normalized_value=1.0`，`percentile=1.0`，并标记 `anomaly_flags=["flat_distribution:<factor_name>"]`，不执行 clipping
- **样本为空**：返回空 `top_candidates=[]` 与空 `score_breakdown=[]`，不抛异常，`universe_size=0`

### 7.2 anomaly_flags 枚举值

| 标记 | 触发条件 | 含义 |
|------|--------|------|
| `missing_factor:<name>` | 因子在 factor_snapshot 中不存在 | 使用默认值 0.0，该符号对应的因子无法计算 |
| `flat_distribution:<name>` | 样本中该因子全部相同（max==min） | 无法进行 min-max 标准化，`normalized_value` 统一设为 1.0 |

**说明**：
- `clipped` 字段已在 JSON 结构中明确标记，无需在 `anomaly_flags` 中重复
- 若某符号某因子既缺失又被截断，只记录 `missing_factor:<name>`（缺失优先级更高）

## 8. Testing Strategy

### 8.1 Unit

- 决策服务输出结构与排序正确（`final_score desc` → `symbol asc`）
- 分位、截断、异常标记可预测
- 相同输入下结果一致（确定性）
- 边界用例必须覆盖：
  - 所有因子全缺失（`anomaly_flags` 含 `missing_factor`，`normalized_value=0.0`）
  - 某因子在全样本中同值（`flat_distribution` 标记，`normalized_value=1.0`，`percentile=1.0`）
  - `top_candidates` 样本数 < 5 时返回实际数量，不补空
  - 样本为空时返回 `universe_size=0`、`top_candidates=[]`、`score_breakdown=[]`
  - `sum(factors[].contribution) == final_score`（6 位精度断言）

### 8.2 Integration

- `run_daily` 输出包含 `l2_decision`
- `top_candidates` 长度为 5（或样本不足时为样本数）

### 8.3 Contract

- `POST /api/v1/pipeline/daily` 响应通过 typed schema
- `l2_decision` 字段完整且类型正确

## 9. Rollout

Phase 1（本次）：

- 仅输出可解释候选，不生成订单

Phase 2（后续）：

- 在不破坏 `score_version` 可回溯前提下优化因子与过滤规则
