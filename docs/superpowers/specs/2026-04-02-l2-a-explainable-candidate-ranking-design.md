# L2-A Explainable Candidate Ranking Design

## 1. Context

当前 `daily` 输出已包含：

- `factor_snapshot`（`l2-basic-v1`）
- `execution_plan.orders`（当前为空）

本次只实现 L2 的“可解释候选输出”，不进入下单与执行编排。

## 2. Goal

在 `factor_snapshot` 基础上新增 `l2_decision`，产出 `top_candidates=5` 与详版 `score_breakdown`，满足“业务可用优先”。

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

- `score_version`：评分公式版本，固定为 `l2-score-v1`
- `top_candidates`：按 `final_score` 降序取前 5
- `score_breakdown`：全样本解释明细，含分位、截断、异常标记

## 6. Scoring Design (v1)

### 6.1 Factors

使用现有三因子：

- `momentum_20`
- `inv_volatility_20`
- `turnover_rate`

### 6.2 Steps

1. 按 `symbol` 聚合 `factor_snapshot.rows`（长表转宽逻辑）
2. 对每个因子计算 `normalized_value`（min-max）
3. 计算 `percentile`（同批样本内分位）
4. 执行截断规则（防极值主导），记录 `clipped`
5. 缺失或异常值走默认回退，并写入 `anomaly_flags`
6. 按固定权重加总，得到 `final_score`
7. 排序后生成 `top_candidates`（前 5）

### 6.3 Weights (v1)

- `momentum_20`: `0.5`
- `inv_volatility_20`: `0.3`
- `turnover_rate`: `0.2`

## 7. Error Handling

- 某因子缺失：以默认值填补并写入 `anomaly_flags=["missing_factor:<name>"]`
- 全样本同值：`normalized_value=1.0`，并标记 `anomaly_flags=["flat_distribution:<name>"]`
- 样本为空：返回空 `top_candidates` 与空 `score_breakdown`，不抛异常

## 8. Testing Strategy

### 8.1 Unit

- 决策服务输出结构与排序正确
- 分位、截断、异常标记可预测
- 相同输入下结果一致（确定性）

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

