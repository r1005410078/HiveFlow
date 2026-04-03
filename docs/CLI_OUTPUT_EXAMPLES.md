# HiveFlow CLI 输出示例

> 本文档提供 `CLI_OUTPUT_SCHEMA.json` 的三类最小可用示例，供开发与测试直接复用。
> 文档导航：`DOCUMENTATION_INDEX.md`
> 文档目标：提供可复制的 CLI 输出样例与校验命令。适用对象：CLI 开发、测试、CI 维护。

当前运行方式：

- `quant` 服务端通过 HTTP 生成这些 JSON 契约输出。
- `cli` 作为客户端调用服务端，并将返回结果原样输出给终端与自动化工具。

说明：

- 第 1~3 节（`signal snapshot` / `news-snapshot` / `market web-brief`）用于说明 envelope 语义，不代表当前 CLI 已提供对应子命令。
- 当前已实现命令面请以 `cargo run -- --help`（或安装后二进制 `hf --help`）为准。

---

## 1. system（主决策分支）

```json
{
  "schema_version": "1.0.0",
  "command": "hf signal snapshot",
  "run_id": "run_20260401_001",
  "status": "ok",
  "generated_at": "2026-04-01T09:00:00+08:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "strategy_id": "strategy_A",
    "as_of": "2026-04-01",
    "signal": -0.73,
    "regime": "warning"
  },
  "warnings": [],
  "errors": []
}
```

---

---

## 2. news_system（主决策分支）

```json
{
  "schema_version": "1.0.0",
  "command": "hf data news-snapshot",
  "run_id": "run_20260401_002",
  "status": "warning",
  "generated_at": "2026-04-01T09:01:00+08:00",
  "source": "news_system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "event_id": "evt_policy_001",
    "event_timestamp": "2026-04-01T08:30:00+08:00",
    "publish_timestamp": "2026-04-01T08:35:00+08:00",
    "effective_timestamp": "2026-04-01T08:35:00+08:00",
    "headline": "政策会议释放稳增长信号",
    "impact_hint": "positive"
  },
  "warnings": [
    {
      "code": "PARTIAL_COVERAGE",
      "message": "仅覆盖 3/5 重点来源，建议补齐后再用于主决策分支"
    }
  ],
  "errors": []
}
```

---

## 3. web_search（情报分支）

```json
{
  "schema_version": "1.0.0",
  "command": "hf market web-brief",
  "run_id": "run_20260401_003",
  "status": "ok",
  "generated_at": "2026-04-01T09:02:00+08:00",
  "source": "web_search",
  "advice_only": true,
  "decision_weight": 0,
  "data": {
    "query": "最新宏观政策 市场影响",
    "items": [
      {
        "title": "某媒体：政策预期升温",
        "url": "https://example.com/news/1",
        "credibility": "low",
        "verified": false
      }
    ],
    "note": "仅用于情报备注，不进入主决策分支期望价值计算"
  },
  "warnings": [
    "UNVERIFIED_SOURCE"
  ],
  "errors": []
}
```

---

## 4. 快速校验示例

以下命令请在仓库根目录执行。

推荐直接使用校验脚本：

```bash
scripts/validate_cli_output.sh sample.json
```

批量回归 fixtures：

```bash
scripts/validate_cli_output_fixtures.sh
```

统一入口（推荐）：

```bash
make validate-cli-output
```

CI 已接入：`.github/workflows/validate-cli-output.yml`

或使用 `jq` 做最小检查：

```bash
jq . sample.json >/dev/null
```

可选：检查 `web_search` 语义约束（`advice_only=true` 且 `decision_weight=0`）：

```bash
jq -e 'if .source=="web_search" then (.advice_only==true and .decision_weight==0) else true end' sample.json >/dev/null
```

---

## 5. hf data sync（JSON 示例）

```json
{
  "schema_version": "1.0.0",
  "command": "hf data sync",
  "run_id": "run_8f3a2c9e1d77",
  "status": "ok",
  "generated_at": "2026-04-01T12:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "timeframe": "1d",
    "days": 5,
    "end_date": "2026-04-01",
    "effective_symbols_count": 4,
    "selection_mode": "default",
    "symbols_hash": "2b8c5f5cbf5f65f17fd4fd0fc2b6a1a53f70f13a6c3ab2e0f5fcdb6f6d4b24f5",
    "manifest_ids": [
      "mf_bce12a9031"
    ]
  },
  "warnings": [],
  "errors": []
}
```

---

## 6. hf data query --output json（JSON 示例）

```json
{
  "schema_version": "1.0.0",
  "command": "hf data query",
  "run_id": "run_7ec4f94ab221",
  "status": "ok",
  "generated_at": "2026-04-01T12:01:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "items": [
      {
        "run_id": "run_demo_001",
        "request_id": "req_demo_001",
        "status": "success",
        "days": 5,
        "end_date": "2026-04-01",
        "timeframe": "1d",
        "selection_mode": "symbols",
        "symbols_hash": "abc123",
        "effective_symbols_count": 4,
        "written_rows": 8,
        "manifest_ids": [
          "mf_demo_001"
        ],
        "started_at": "2026-04-01T09:30:00+08:00",
        "finished_at": "2026-04-01T09:31:00+08:00",
        "error_code": null,
        "error_message": null
      }
    ]
  },
  "warnings": [],
  "errors": []
}
```

---

## 7. hf pipeline daily（JSON 示例，含 L2 因子快照）

```json
{
  "schema_version": "1.0.0",
  "command": "hf pipeline daily",
  "run_id": "run_16e4d4f2b8bc",
  "status": "ok",
  "generated_at": "2026-04-02T09:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "data_manifest_id": "dm_20260401_a1b2c3",
    "factor_snapshot": {
      "factor_version": "l2-basic-v1",
      "factor_names": [
        "momentum_20",
        "inv_volatility_20",
        "turnover_rate"
      ],
      "coverage_rate": 1.0,
      "rows": [
        {
          "as_of": "2026-04-01",
          "symbol": "600519.SH",
          "factor_name": "momentum_20",
          "factor_version": "l2-basic-v1",
          "raw_value": 0.02
        },
        {
          "as_of": "2026-04-01",
          "symbol": "600519.SH",
          "factor_name": "inv_volatility_20",
          "factor_version": "l2-basic-v1",
          "raw_value": 2.9
        }
      ]
    },
    "execution_plan": {
      "orders": []
    }
  },
  "warnings": [],
  "errors": []
}
```

---

## 8. hf factor optimize（JSON 示例，含 Top5 与 release_gate）

```json
{
  "schema_version": "1.0.0",
  "command": "hf factor optimize",
  "run_id": "run_factor_opt_001",
  "status": "ok",
  "generated_at": "2026-04-02T10:00:00+08:00",
  "source": "web_search",
  "advice_only": true,
  "decision_weight": 0,
  "data": {
    "factor_names": [
      "momentum_20",
      "inv_volatility_20",
      "turnover_rate",
      "max_drawdown_60",
      "trend_stability_20",
      "relative_strength_vs_index"
    ],
    "analysis": {
      "factor_health": [
        {
          "factor_name": "momentum_20",
          "coverage_rate": 0.98,
          "health_score": 0.91
        }
      ],
      "coverage": {
        "symbols": 30,
        "bars": 2000
      }
    },
    "correlation_analysis": {
      "threshold": 0.7,
      "alert_count": 1,
      "alerts": [
        {
          "pair": ["momentum_20", "trend_stability_20"],
          "correlation": 0.82
        }
      ]
    },
    "top_combinations": {
      "search_space": {
        "factor_pool_size": 6,
        "combination_size_min": 2,
        "combination_size_max": 4,
        "candidate_count": 15
      },
      "ranking_profile": "balanced_v1",
      "items": [
        {
          "rank": 1,
          "factors": ["momentum_20", "inv_volatility_20"],
          "composite_score": 1.18,
          "return_score": 1.22,
          "risk_score": 0.96,
          "redundancy_penalty": 0.00,
          "alerts_inside": []
        },
        {
          "rank": 2,
          "factors": ["momentum_20", "turnover_rate"],
          "composite_score": 1.11,
          "return_score": 1.16,
          "risk_score": 0.93,
          "redundancy_penalty": 0.02,
          "alerts_inside": ["near_duplicate_risk"]
        },
        {
          "rank": 3,
          "factors": ["inv_volatility_20", "max_drawdown_60"],
          "composite_score": 1.08,
          "return_score": 1.10,
          "risk_score": 0.97,
          "redundancy_penalty": 0.01,
          "alerts_inside": []
        },
        {
          "rank": 4,
          "factors": ["trend_stability_20", "relative_strength_vs_index"],
          "composite_score": 1.02,
          "return_score": 1.05,
          "risk_score": 0.94,
          "redundancy_penalty": 0.02,
          "alerts_inside": []
        },
        {
          "rank": 5,
          "factors": ["momentum_20", "relative_strength_vs_index"],
          "composite_score": 0.99,
          "return_score": 1.00,
          "risk_score": 0.95,
          "redundancy_penalty": 0.01,
          "alerts_inside": []
        }
      ]
    },
    "release_gate": {
      "status": "watch",
      "blocking_reasons": [],
      "watch_items": ["correlation_alert_count:1"]
    },
    "report": {
      "matrix_10d": [
        [1.0, 0.82],
        [0.82, 1.0]
      ],
      "summary": {
        "coverage_ok": true,
        "alert_count": 1
      },
      "g3_checklist": [
        "review_top1_combination",
        "confirm_release_gate_status"
      ]
    },
    "recommendations": [
      {
        "scheme": "balanced_v1",
        "decision_weight": 0,
        "advice_only": true,
        "summary": "Top1 组合可作为审批前建议，但需先处理相关性告警"
      }
    ]
  },
  "warnings": [],
  "errors": []
}
```

---

## 9. hf factor replay（JSON 示例）

```json
{
  "summary": {
    "days": 3,
    "error_days": 0,
    "pass_days": 0,
    "watch_days": 0,
    "fail_days": 3,
    "avg_alert_count": 0.0,
    "top1_change_days": 1
  },
  "daily_items": [
    {
      "as_of": "2026-04-01",
      "fetch_status": "ok",
      "release_gate_status": "fail",
      "alert_count": 0,
      "top1_factors": ["momentum_20", "inv_volatility_20"]
    },
    {
      "as_of": "2026-04-02",
      "fetch_status": "ok",
      "release_gate_status": "fail",
      "alert_count": 0,
      "top1_factors": []
    },
    {
      "as_of": "2026-04-03",
      "fetch_status": "ok",
      "release_gate_status": "fail",
      "alert_count": 0,
      "top1_factors": []
    }
  ]
}
```

---

## 10. hf pipeline compare（JSON 示例，含 Phase2 analytics）

```json
{
  "schema_version": "1.0.0",
  "command": "hf pipeline compare",
  "run_id": "run_compare_001",
  "status": "ok",
  "generated_at": "2026-04-03T09:00:00+08:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "start_date": "2026-03-01",
    "end_date": "2026-03-30",
    "top_n": 5,
    "daily_items": [],
    "summary": {
      "days": 20,
      "avg_warning_count_v1": 0.2,
      "avg_warning_count_v1_1": 0.1,
      "avg_min_availability_v1": 0.93,
      "avg_min_availability_v1_1": 0.96,
      "top1_symbol_change_days": 7
    },
    "analytics": {
      "return_metrics": {
        "v1": {
          "cumulative_return": 0.042,
          "win_rate": 0.53,
          "max_drawdown": 0.081,
          "annualized_volatility": 0.19,
          "sharpe": 0.88
        },
        "v1_1": {
          "cumulative_return": 0.067,
          "win_rate": 0.58,
          "max_drawdown": 0.073,
          "annualized_volatility": 0.18,
          "sharpe": 1.07
        },
        "diff": {
          "excess_cumulative_return_v1_1_vs_v1": 0.025,
          "excess_sharpe_v1_1_vs_v1": 0.19
        }
      },
      "daily_return_series": {
        "v1": [
          {
            "as_of": "2026-03-01",
            "top1_next_day_return": 0.0042
          }
        ],
        "v1_1": [
          {
            "as_of": "2026-03-01",
            "top1_next_day_return": 0.0061
          }
        ]
      },
      "group_stability": {
        "group_key": "industry_market_cap_bucket",
        "items": [
          {
            "industry": "Bank",
            "market_cap_bucket": "LARGE",
            "sample_days": 8,
            "v1": {
              "cumulative_return": 0.012,
              "win_rate": 0.5,
              "sharpe": 0.42
            },
            "v1_1": {
              "cumulative_return": 0.021,
              "win_rate": 0.63,
              "sharpe": 0.71
            },
            "diff": {
              "excess_cumulative_return": 0.009,
              "excess_sharpe": 0.29
            },
            "stability_flag": "OK"
          }
        ]
      }
    }
  },
  "warnings": [],
  "errors": []
}
```
