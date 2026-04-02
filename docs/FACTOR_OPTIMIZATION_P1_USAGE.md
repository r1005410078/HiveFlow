# Factor Optimization P1 使用说明

> 适用版本：2026-04-02 之后的 `master`。

## 1. 能力概览

P1 在统一接口 `POST /api/v1/factor-optimization/evaluate` 上新增两块输出：

- `data.correlation_analysis`：高相关冗余告警
- `data.report`：10维评估摘要 + G3 审批清单

同时保持安全边界：

- `advice_only = true`
- `decision_weight = 0`

这代表输出仅用于建议与审核，不会自动生效参数变更。

## 2. CLI 快速使用

### 2.1 默认阈值（0.7）

```bash
cd cli
cargo run -- factor optimize \
  --start-date 2026-01-01 \
  --end-date 2026-04-01 \
  --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60 \
  --output table
```

### 2.2 自定义阈值（例如 0.9）

```bash
cd cli
cargo run -- factor optimize \
  --start-date 2026-01-01 \
  --end-date 2026-04-01 \
  --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60 \
  --correlation-threshold 0.9 \
  --output json
```

## 3. 输出字段说明

### 3.1 `data.correlation_analysis`

- `threshold`: 告警阈值，默认 `0.7`
- `alerts[]`: 告警列表
- `alert_count`: 告警总数

`alerts[]` 单条结构：

- `factor_a`, `factor_b`: 因子对
- `correlation`: 相关系数（保留小数）
- `severity`: `high|medium`
- `suggestion`: 降权/替换建议

分级规则：

- `high`: `abs(correlation) >= 0.8`
- `medium`: `threshold <= abs(correlation) < 0.8`

### 3.2 `data.report`

- `matrix_10d`: 固定 10 维摘要
- `summary`: 推荐方案与关键结论
- `g3_checklist`: 人工审批清单（风控/合规/CRO）

当前 10 维包括：

1. IC
2. Sharpe
3. Max Drawdown
4. Correlation Redundancy
5. Coverage
6. Stability
7. Data Quality
8. Risk Contribution
9. Incremental Value
10. Operational Readiness

## 4. 阈值使用建议

- 日常筛查：`0.7`（敏感，告警更多）
- 严格筛查：`0.8`（平衡）
- 强过滤：`0.9`（只看极高相关）

建议在评审会议里同时给出两档结果（如 `0.7` + `0.9`），便于讨论冗余程度。

## 5. 常见问题

### Q1: 为什么推荐方案有时是 `return_first`，不是 `balanced`？

A: 推荐由当前评分逻辑与样本数据共同决定，不是固定写死。`balanced` 不保证永远第一。

### Q2: `matrix_10d` 里为什么有 `N/A`？

A: P1 首版对部分维度保留占位（例如窗口稳定性、增量回测细项），避免输出伪精度数据。

### Q3: 这会不会自动改线上权重？

A: 不会。当前输出是建议态，必须走 G3 审批链路。

## 6. 验收建议

- 运行 `--output table` 验证人读可读性
- 运行 `--output json` 验证字段完整性
- 至少对比两组阈值（如 `0.7` 与 `0.9`）确认告警数量变化符合预期
