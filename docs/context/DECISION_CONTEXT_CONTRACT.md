# DECISION_CONTEXT_CONTRACT

## 目的

定义 `hiveflow context decision` 输出契约，供 Agent、前端和下游服务稳定消费轻量决策上下文。

## 适用范围

- `context decision` 成功输出（`--output json`）
- `context decision` envelope 输出（`--output json --envelope`）
- `context decision` 严格失败输出（缺失 signal/style 历史）

## 版本

- 当前版本：沿用全局 envelope `schema_version = "1.0.0"`
- 兼容策略：新增字段只增不删，保持已有字段语义稳定。

## 成功输出字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `as_of` | `string` | 最新信号快照时间（ISO8601） |
| `decision_boundary` | `object` | 系统与 Agent 职责边界（固定 `system=data_only`） |
| `source_meta` | `object` | signal/style 来源记录元信息（record_id/as_of/age_hours） |
| `policy` | `object` | 规则门控结果 |
| `evaluation` | `object` | 策略健康度评价快照 |
| `execution_plan` | `object` | 执行计划（可执行订单与跳过项） |

### `policy.rebalance`

| 字段 | 类型 | 含义 |
|---|---|---|
| `rebalance_allowed` | `boolean` | 是否允许调仓 |
| `buy_allowed` | `boolean` | 是否允许买入 |
| `sell_allowed` | `boolean` | 是否允许卖出 |
| `cooldown_active` | `boolean` | 是否处于冷却期 |
| `reason_codes` | `string[]` | 门控原因码 |

### `policy.strategy_switch`

| 字段 | 类型 | 含义 |
|---|---|---|
| `switch_allowed` | `boolean` | 是否允许切换策略 |
| `switch_threshold_passed` | `boolean` | 优势分阈值是否通过 |
| `cooldown_active` | `boolean` | 切换冷却期是否生效 |
| `advantage_score` | `number` | 候选策略相对当前策略优势分 |
| `reason_codes` | `string[]` | 门控原因码 |
| `current_strategy` | `string` | 当前策略名 |
| `candidate_strategy` | `string` | 候选策略名 |

### `evaluation`

| 字段 | 类型 | 含义 |
|---|---|---|
| `strategy` | `string` | 当前策略名 |
| `current_market_fit` | `string` | 当前市场适配度（`low/medium/high`） |
| `backtest_quality_score` | `number` | 回测质量分（0~1） |
| `stability_score` | `number` | 稳定性分（0~1） |
| `composite_score` | `number` | 综合分（0~1） |
| `strategy_health` | `string` | 健康状态（`healthy/watch/paused`） |
| `degradation_flag` | `boolean` | 是否触发退化标记 |
| `as_of` | `string` | 评价时间（ISO8601） |

### `execution_plan`

| 字段 | 类型 | 含义 |
|---|---|---|
| `plan_state` | `string` | 执行状态（`ready_for_confirmation/review_only`） |
| `orders` | `object[]` | 可执行动作列表 |
| `skipped` | `object[]` | 被门控跳过动作列表 |

## 严格失败输出

缺失快照时返回统一错误对象（参考全局错误协议）：

- 缺少 signal 历史：`code = E_SIGNAL_REQUIRED_MISSING`
- 缺少 style 历史：`code = E_STYLE_EVAL_FAILED`
- `context = "context.decision"`
- `details.strict_mode = true`
- 含 `trace_id`，并写入 `systemlog`

## 示例（成功）

```json
{
  "as_of": "2026-03-23T09:20:31.000000",
  "decision_boundary": {
    "system": "data_only",
    "agent": "analysis_and_decision"
  },
  "source_meta": {
    "signal_latest": {
      "record_id": 12,
      "snapshot_id": "sig-202603230920310001",
      "as_of": "2026-03-23T09:20:31.000000",
      "age_hours": 0.12
    },
    "style_latest": {
      "record_id": 7,
      "run_id": "style-202603230920320001",
      "as_of": "2026-03-23T09:20:32.000000",
      "age_hours": 0.12
    }
  },
  "policy": {
    "rebalance": {
      "rebalance_allowed": true,
      "buy_allowed": true,
      "sell_allowed": true,
      "cooldown_active": false,
      "reason_codes": []
    },
    "strategy_switch": {
      "switch_allowed": false,
      "switch_threshold_passed": false,
      "cooldown_active": false,
      "advantage_score": 0.03,
      "reason_codes": ["advantage_not_enough"],
      "current_strategy": "MomentumStrategy",
      "candidate_strategy": "aggressive_growth"
    }
  },
  "evaluation": {
    "strategy": "MomentumStrategy",
    "current_market_fit": "medium",
    "backtest_quality_score": 0.62,
    "stability_score": 0.58,
    "composite_score": 0.60,
    "strategy_health": "watch",
    "degradation_flag": false,
    "as_of": "2026-03-23T09:20:33.000000+00:00"
  },
  "execution_plan": {
    "plan_state": "ready_for_confirmation",
    "orders": [],
    "skipped": []
  }
}
```
