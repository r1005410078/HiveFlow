# AI Factor Optimization P1 Unified Evaluate Design

## 1. Goal

在不新增接口的前提下，扩展现有 `POST /api/v1/factor-optimization/evaluate`，交付 P1 两项能力：

- 自动化相关性检测（高相关冗余告警）
- 多维度对比报告（10 维评估矩阵 + 审批清单）

并继续保持 `advice_only=true`、`decision_weight=0` 的 G3 安全边界。

## 2. Scope

In Scope:

- 扩展 `evaluate` 响应结构，新增 `correlation_analysis` 与 `report`
- 新增相关性告警规则（默认阈值 `0.7`）
- 新增 10 维报告结构与 CLI table 展示
- 增加 unit/contract/cli 测试覆盖

Out of Scope:

- 新增独立 API endpoint
- 自动改写 `SCORE_PROFILES` 或任何参数自动生效
- P2 的组合穷举/Top5 搜索

## 3. Architecture

遵循既有分层约束：

- `interfaces/http`: 仅 DTO + provider + route 编排
- `application`: 实现相关性告警与报告组装
- `domain`: 仅定义结构模型，禁止引入 IO

依赖方向保持：`interfaces -> application -> domain`

CLI 侧保持：`cmd -> application -> infrastructure`

## 4. API Contract Extension

## 4.1 Request

保持现有请求结构不变，仅可选新增阈值字段：

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-04-01",
  "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate"],
  "constraints": {"max_weight:max_drawdown_60": 0.3},
  "correlation_threshold": 0.7
}
```

`correlation_threshold` 省略时默认 `0.7`。

## 4.2 Response (新增字段)

在 `data` 下扩展：

```json
{
  "data": {
    "analysis": {
      "factor_health": [],
      "correlation_matrix": {}
    },
    "correlation_analysis": {
      "threshold": 0.7,
      "alerts": [
        {
          "factor_a": "momentum_20",
          "factor_b": "max_drawdown_60",
          "correlation": 0.73,
          "severity": "high",
          "suggestion": "降低弱势因子权重或替换"
        }
      ],
      "alert_count": 1
    },
    "report": {
      "matrix_10d": [
        {
          "dimension": "IC",
          "momentum_20": "0.12 ✅",
          "inv_volatility_20": "0.09 ✅"
        }
      ],
      "summary": {
        "recommended_scheme": "balanced",
        "key_findings": ["max_drawdown_60 与 momentum_20 高相关"]
      },
      "g3_checklist": [
        {"item": "风控组评审", "checked": false},
        {"item": "合规组审核", "checked": false},
        {"item": "CRO 最终批准", "checked": false}
      ]
    }
  }
}
```

## 5. Application Design

## 5.1 Correlation Alerts

输入：`analysis.correlation_matrix` + `threshold`

规则：

- 枚举上三角因子对
- `abs(corr) >= threshold` 生成 alert
- `severity` 分级：
  - `high`: `abs(corr) >= 0.8`
  - `medium`: `0.7 <= abs(corr) < 0.8`
- `suggestion`：按两因子 Sharpe/IC 较弱者给出“降权/替换”建议

输出：`threshold`、`alerts[]`、`alert_count`

## 5.2 10-Dim Report Builder

输入：`analysis` + `recommendations` + `correlation_analysis`

固定 10 维（首版允许 `N/A`，不做伪造）：

1. IC
2. Sharpe
3. Max Drawdown
4. Correlation Redundancy
5. Coverage
6. Stability (window delta, 首版可 N/A)
7. Data Quality (missing/anomaly)
8. Risk Contribution (from weights, 近似)
9. Incremental Value (vs baseline, 首版可 N/A)
10. Operational Readiness (G3 checklist)

输出：`matrix_10d[]`、`summary`、`g3_checklist[]`

## 5.3 Orchestration

在现有 `run_factor_optimization` 中追加：

1. `analysis = analyze_factors(...)`
2. `recommendations = suggest_weight_schemes(...)`
3. `correlation_analysis = build_correlation_alerts(...)`
4. `report = build_report_10d(...)`
5. 统一组装到 `build_factor_optimization_report(...)`

## 6. CLI Design

命令保持不变：

```bash
hf factor optimize --start-date ... --end-date ... --factors ... --output json|table
```

table 输出新增两个区块：

- `相关性告警`：`factor_a`, `factor_b`, `corr`, `severity`, `suggestion`
- `10维评估摘要`：维度行 + 推荐方案 + G3 checklist 完成状态

json 输出保持完整透传。

## 7. Error Handling

- `correlation_threshold <= 0 or > 1`：返回 `400 INVALID_ARGUMENT`
- `factor_names` 为空：返回 `400 INVALID_ARGUMENT`
- 无 bars/样本不足：返回空告警 + 报告内维度标注 `N/A`，状态仍为 `ok`（可附 warnings）

## 8. Testing Strategy

Quant:

- unit: 告警阈值边界、severity 分级、alert_count
- unit: 10维报告组装（含 N/A 维度）
- contract: `evaluate` 新字段结构与类型

CLI:

- http: request 携带 `correlation_threshold`（可选）
- table: 告警区块与 10 维区块渲染断言

Gate:

- `make architecture-check`
- `make check`

## 9. Rollout

Phase P1-A:

- 先交付 `correlation_analysis`（告警）

Phase P1-B:

- 再交付 `report.matrix_10d + g3_checklist + table` 展示

每阶段独立可测、可回滚。
