# AI Factor Optimization P2 Top5 Combination Design

## 1. Goal

在保持 `evaluate` 单接口统一输出的前提下，新增 Top5 组合推荐能力：

- 搜索范围：仅当前 6 个已上线因子
- 组合大小：2~4 因子可变
- 排序目标：收益/风险平衡（等权）
- 安全边界：`advice_only=true`、`decision_weight=0`，仅建议不自动生效

## 2. Scope

In Scope:

- 在 `POST /api/v1/factor-optimization/evaluate` 增加 `top_combinations` 输出
- 穷举 6 因子在 `k=2..4` 的全部组合并排序
- 输出组合级可解释字段（得分构成、惩罚来源、推荐理由）
- CLI `table/json` 展示增强

Out of Scope:

- 接入外部回测引擎/收益曲线级仿真
- 自动改写线上权重或策略参数
- 候选因子池扩展（仅限当前 6 因子）

## 3. Why Approach A

采用“穷举 + 轻量打分”而非贪心/随机：

- 6 因子在 `k=2..4` 组合总量可控（56 组）
- 结果可复现、可审计，适合 G3 审批链路
- 首版实现复杂度低，便于快速落地与回归验证

组合总量：

- C(6,2)=15
- C(6,3)=20
- C(6,4)=15
- Total=50

（若后续扩展到 7 因子则总量 91，仍可控）

## 4. API Contract Extension

## 4.1 Request

保持现有请求结构，新增可选组合参数：

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-04-01",
  "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate", "max_drawdown_60", "trend_stability_20", "relative_strength_vs_index"],
  "correlation_threshold": 0.7,
  "combination_size_min": 2,
  "combination_size_max": 4,
  "top_k_combinations": 5
}
```

默认值：

- `combination_size_min=2`
- `combination_size_max=4`
- `top_k_combinations=5`

## 4.2 Response

在 `data` 下新增：

```json
{
  "top_combinations": {
    "search_space": {
      "factor_pool_size": 6,
      "combination_size_min": 2,
      "combination_size_max": 4,
      "candidate_count": 50
    },
    "ranking_profile": "balanced_v1",
    "items": [
      {
        "rank": 1,
        "factors": ["momentum_20", "inv_volatility_20", "max_drawdown_60"],
        "weights": {
          "momentum_20": 0.33,
          "inv_volatility_20": 0.34,
          "max_drawdown_60": 0.33
        },
        "composite_score": 1.24,
        "return_score": 1.31,
        "risk_score": 1.22,
        "redundancy_penalty": 0.04,
        "alerts_inside": 1,
        "explanations": [
          "Sharpe 贡献较高",
          "组合内仅 1 组高相关因子"
        ]
      }
    ]
  }
}
```

## 5. Scoring Design (Balanced)

组合评分采用平衡模型：

`composite_score = 0.5 * return_score + 0.5 * risk_score - redundancy_penalty`

- `return_score`: 由组合内因子 `ic/sharpe` 聚合得到
- `risk_score`: 由 `max_drawdown` 与可用性稳定性近似得到
- `redundancy_penalty`: 对组合内高相关对进行惩罚

惩罚规则（首版）：

- 若 `abs(corr) >= correlation_threshold`，记为一组冗余
- `penalty += 0.02 + 0.03 * max(0, abs(corr)-threshold)`
- `abs(corr) >= 0.9` 额外加 `0.02`

## 6. Application Design

新增 `combination_service`：

1. 枚举 `k=2..4` 全组合
2. 对每组生成默认权重（等权）
3. 复用现有 `analysis + correlation` 指标进行评分
4. 计算组合内冗余惩罚
5. 按 `composite_score` 排序，取 Top K
6. 产生解释字段 `explanations`

编排位置：`run_factor_optimization(...)` 末段追加 `top_combinations`。

## 7. CLI Design

命令保持：

```bash
hf factor optimize --start-date ... --end-date ... --factors ... --output table
```

`table` 新增区块：

- `Top5 组合推荐`
- 列：`rank`, `factors`, `composite_score`, `return_score`, `risk_score`, `penalty`

`json` 保持透传完整结构。

## 8. Error Handling

- `combination_size_min < 2` 或 `combination_size_max > 4`：`400 INVALID_ARGUMENT`
- `combination_size_min > combination_size_max`：`400 INVALID_ARGUMENT`
- `top_k_combinations <= 0`：`400 INVALID_ARGUMENT`
- `factor_names` 不足最小组合大小：返回空 `items` + warning（不报错）

## 9. Testing Strategy

Quant Unit:

- 组合枚举数量正确（6 因子下 50 组）
- 评分与惩罚规则可复现
- TopK 截断正确且排序稳定

Quant Contract:

- `top_combinations.search_space` 字段完整
- `top_combinations.items[*]` 关键字段与类型正确

CLI:

- table 区块与关键列存在
- json 输出含 `top_combinations`

Gate:

- `make architecture-check`
- `make check`

## 10. Rollout

- Phase P2-A：先交付 `top_combinations` JSON 输出
- Phase P2-B：补 table 展示与说明文档
- 全程保持 advice-only 与 G3 审批边界
