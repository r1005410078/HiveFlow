# Factor Optimization P2 使用说明

> 适用版本：2026-04-02 之后的 `master`。

## 1. 能力概览

P2 在统一接口 `POST /api/v1/factor-optimization/evaluate` 上新增：

- `data.top_combinations`：TopK 因子组合推荐（首版默认 Top5）

组合搜索策略（方案 A）：

- 因子池：当前请求中的候选因子（建议使用已上线 6 因子）
- 组合大小：默认 `2~4`
- 排序目标：收益/风险平衡（`balanced_v1`）
- 冗余惩罚：对高相关因子对扣分

安全边界保持不变：

- `advice_only = true`
- `decision_weight = 0`

## 2. CLI 快速使用

```bash
cd cli
cargo run -- factor optimize \
  --start-date 2026-01-01 \
  --end-date 2026-04-01 \
  --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60,trend_stability_20,relative_strength_vs_index \
  --output table
```

`table` 会新增 `Top5 组合推荐` 区块：

- 组合空间摘要（池大小、组合范围、候选数、ranking_profile）
- TopK 明细（`rank/factors/composite_score/return_score/risk_score/penalty/alerts`）

## 3. HTTP 参数扩展

请求体新增可选字段：

- `combination_size_min`：最小组合大小，默认 `2`
- `combination_size_max`：最大组合大小，默认 `4`
- `top_k_combinations`：返回组合数，默认 `5`

示例：

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-04-01",
  "factor_names": [
    "momentum_20",
    "inv_volatility_20",
    "turnover_rate",
    "max_drawdown_60",
    "trend_stability_20",
    "relative_strength_vs_index"
  ],
  "correlation_threshold": 0.7,
  "combination_size_min": 2,
  "combination_size_max": 4,
  "top_k_combinations": 5
}
```

参数约束：

- `combination_size_min >= 2`
- `combination_size_max <= 4`
- `combination_size_min <= combination_size_max`
- `top_k_combinations > 0`

非法参数将返回 `400 INVALID_ARGUMENT`。

## 4. 输出字段说明

`data.top_combinations` 结构：

- `search_space`
- `ranking_profile`
- `items[]`

`search_space`：

- `factor_pool_size`：参与评分的因子数
- `combination_size_min` / `combination_size_max`
- `candidate_count`：穷举出的候选组合总数

`items[]` 单条：

- `rank`
- `factors`
- `weights`（首版等权）
- `composite_score`
- `return_score`
- `risk_score`
- `redundancy_penalty`
- `alerts_inside`
- `explanations`

`data.release_gate`（P3 补充）：

- `status`：发布门禁状态，枚举 `pass|watch|fail`
- `blocking_reasons`：阻断原因列表；非空时通常不可放行
- `watch_items`：关注项列表；用于人工复核与跟踪

## 5. 评分口径（首版）

组合评分采用平衡模型：

`composite_score = 0.5 * return_score + 0.5 * risk_score - redundancy_penalty`

其中：

- `return_score`：组合内因子的 `ic/sharpe` 聚合
- `risk_score`：组合内因子的回撤风险近似聚合
- `redundancy_penalty`：组合内高相关因子对惩罚

## 6. 常见问题

### Q1: 为什么 Top5 里会有 2 因子和 3 因子混在一起？

A: 默认按 `2~4` 统一搜索，再用同一评分函数排序，TopK 不按组合大小分组。

### Q2: `factors` 顺序有意义吗？

A: 组合本身是无序集，当前顺序仅用于稳定展示与可重复性比较。

### Q3: 会自动应用到线上评分权重吗？

A: 不会。仍是建议态输出，必须走 G3 审批流程。
