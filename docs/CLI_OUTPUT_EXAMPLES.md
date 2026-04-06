# HiveFlow CLI 输出示例

> 本文档提供 `CLI_OUTPUT_SCHEMA.json` 的三类最小可用示例，供开发与测试直接复用。
> 文档导航：`DOCUMENTATION_INDEX.md`
> 文档目标：提供可复制的 CLI 输出样例与校验命令。适用对象：CLI 开发、测试、CI 维护。

当前运行方式：

- `quant` 服务端通过 HTTP 生成这些 JSON 契约输出。
- `cli` 作为客户端调用服务端，并将返回结果原样输出给终端与自动化工具。

说明：

- 第 1 节（`signal snapshot`）已在 L3 Phase 1 实装。第 2~3 节（`news-snapshot` / `market web-brief`）仍为 envelope 语义示例，不代表当前 CLI 已提供对应子命令。
- 当前已实现命令面请以 `cargo run -- --help`（或安装后二进制 `hf --help`）为准。

---

## 1. system（主决策分支）

```json
{
  "schema_version": "1.0.0",
  "command": "hf signal snapshot",
  "run_id": "run_20260401_abcd1234",
  "status": "ok",
  "generated_at": "2026-04-01T09:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "signal_matrix": {
      "schema_version": "1.0",
      "generated_at": "2026-04-01T09:00:00+00:00",
      "producer_version": "quant-l3",
      "signal_version": "l3-signal-v1.0",
      "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate", "max_drawdown_60", "trend_stability_20", "relative_strength_vs_index"],
      "coverage_rate": 1.0,
      "rows": [
        {"symbol": "600519.SH", "factor_name": "momentum_20", "raw_value": 0.02, "signal_value": 1.23, "direction": 1},
        {"symbol": "600519.SH", "factor_name": "inv_volatility_20", "raw_value": 2.9, "signal_value": 0.87, "direction": 1}
      ],
      "composite_scores": [
        {"symbol": "600519.SH", "composite_score": 0.54, "factor_count": 6},
        {"symbol": "000001.SZ", "composite_score": -0.12, "factor_count": 6}
      ],
      "transform_stats": [
        {
          "factor_name": "momentum_20",
          "pre_winsorize": {"count": 5, "mean": 0.03, "std": 0.02, "min": -0.01, "max": 0.08},
          "post_zscore": {"count": 5, "mean": 0.0, "std": 1.0, "min": -1.5, "max": 1.8}
        }
      ]
    },
    "technical": {
      "ma5_ma10": {
        "schema_version": "1.0.0",
        "definition": "sma_close_5_10",
        "as_of": "2026-04-01",
        "by_symbol": {
          "600519.SH": {
            "golden_cross": false,
            "death_cross": false,
            "sma5": 1800.12,
            "sma10": 1795.0,
            "available": true
          }
        }
      }
    }
  },
  "warnings": [],
  "errors": []
}
```

### hf signal evaluate

`hf signal evaluate --start-date 2026-03-01 --end-date 2026-04-01 --output json`

In this example, `daily_ic` arrays are truncated for brevity; in production they contain one entry per evaluation day.

```json
{
  "schema_version": "1.0.0",
  "command": "hf signal evaluate",
  "run_id": "run_eval_20260301_20260401_a1b2c3d4",
  "status": "ok",
  "generated_at": "2026-04-03T12:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "eval_version": "l3-eval-v1.0",
    "start_date": "2026-03-01",
    "end_date": "2026-04-01",
    "forward_days": 1,
    "trading_days_evaluated": 20,
    "symbols": ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"],
    "ic_report": {
      "per_factor": [
        {
          "factor_name": "momentum_20",
          "mean_ic": 0.062,
          "ic_std": 0.15,
          "ic_ir": 0.413333,
          "hit_rate": 0.65,
          "daily_ic": [
            {"date": "2026-03-03", "ic": 0.12},
            {"date": "2026-03-04", "ic": -0.05}
          ]
        },
        {
          "factor_name": "inv_volatility_20",
          "mean_ic": 0.035,
          "ic_std": 0.18,
          "ic_ir": 0.194444,
          "hit_rate": 0.55,
          "daily_ic": [
            {"date": "2026-03-03", "ic": 0.08},
            {"date": "2026-03-04", "ic": -0.02}
          ]
        }
      ],
      "composite": {
        "mean_ic": 0.085,
        "ic_std": 0.12,
        "ic_ir": 0.708333,
        "hit_rate": 0.70,
        "daily_ic": [
          {"date": "2026-03-03", "ic": 0.15},
          {"date": "2026-03-04", "ic": 0.02}
        ]
      }
    },
    "drift_diagnostics": {
      "drift_window": 5,
      "baseline_days": 15,
      "factor_drift": [
        {
          "factor_name": "momentum_20",
          "baseline_mean": 0.042,
          "baseline_std": 0.008,
          "recent_mean": 0.039,
          "drift_z": -0.375,
          "drift_flag": false
        },
        {
          "factor_name": "inv_volatility_20",
          "baseline_mean": 1.25,
          "baseline_std": 0.15,
          "recent_mean": 1.28,
          "drift_z": 0.2,
          "drift_flag": false
        }
      ],
      "coverage_drift": {
        "baseline_mean": 1.0,
        "recent_mean": 1.0,
        "drift_z": 0.0,
        "drift_flag": false
      },
      "rank_turnover": {
        "mean_turnover": 0.2,
        "max_turnover": 0.4,
        "stable": true
      }
    }
  },
  "warnings": [],
  "errors": []
}
```

---

## `hf portfolio optimize`

### JSON output (`--output json`)

```json
{
  "schema_version": "1.0.0",
  "command": "hf portfolio optimize",
  "run_id": "run_20260401_abc12345",
  "status": "ok",
  "generated_at": "2026-04-01T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "optimize_version": "l4-optimize-v1.0",
    "optimization_status": "optimal",
    "fallback_reason": null,
    "target_weights": [
      {"symbol": "600519.SH", "weight": 0.298700, "prev_weight": 0.0, "delta": 0.298700},
      {"symbol": "000001.SZ", "weight": 0.234100, "prev_weight": 0.0, "delta": 0.234100},
      {"symbol": "300750.SZ", "weight": 0.182300, "prev_weight": 0.0, "delta": 0.182300},
      {"symbol": "601318.SH", "weight": 0.152100, "prev_weight": 0.0, "delta": 0.152100},
      {"symbol": "000333.SZ", "weight": 0.132800, "prev_weight": 0.0, "delta": 0.132800}
    ],
    "optimization_report": {
      "objective_value": 0.423100,
      "risk_contribution": 0.031200,
      "turnover_cost": 0.001800,
      "solver": "CLARABEL",
      "solve_time_ms": 42
    }
  },
  "warnings": [],
  "errors": []
}
```

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

## 6. hf task list --output json（JSON 示例）

子命令 **`task list`** 列出同步任务元数据；别名 **`hf task sync-runs`**。近窗 K 线用 **`hf data query`**；显式区间用 **`hf data bars`**。

```json
{
  "schema_version": "1.0.0",
  "command": "hf task list",
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

### hf task progress --output json（信封示例）

CLI 默认 **`--output table`** 为可读摘要；**`--output json`** 时 stdout 为 **服务端单条 sync-run 详情**（与 `GET /v1/market-data/sync-runs/{run_id}` 一致）。下列为 Skills 校验用信封示例（字段与 `task_progress_ok.json` fixture 对齐）。

```json
{
  "schema_version": "1.0.0",
  "command": "hf task progress",
  "run_id": "run_valid_task_progress_001",
  "status": "ok",
  "generated_at": "2026-04-01T12:01:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "run_id": "run_demo_running_001",
    "status": "running",
    "phase": "fetching_bars",
    "progress": {
      "total_symbols": 100,
      "completed_symbols": 42,
      "current_symbol": "600519.SH",
      "total_days": 30,
      "completed_days": 12
    },
    "selection_mode": "universe",
    "end_date": "2026-04-01",
    "timeframe": "1d",
    "days": 30
  },
  "warnings": [],
  "errors": []
}
```

### hf data query --output json

`hf data query` 打印 **服务端 bars 形状** 的 JSON（`data.items`）；默认 **`--output tui`** 为分页表格，脚本用 **`--output json`**。若存在 `quant/config/universes/symbol_names.json`（由 **`hf data universe-sync`** 合并写入），每条 bar 对象通常还带 **`symbol_name_zh`**（中文简称，无映射时为空字符串）；其它含 `symbol` 字段的 HTTP JSON 响应同样会由服务端中间件附带该字段。

```json
{
  "schema_version": "1.0.0",
  "command": "hf data query",
  "run_id": "run_valid_data_query_bars_001",
  "status": "ok",
  "generated_at": "2026-04-01T12:01:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "items": [
      {
        "symbol": "600519.SH",
        "timeframe": "1d",
        "bar_time": "2026-04-01T15:00:00+08:00",
        "open": 1450.0,
        "high": 1468.0,
        "low": 1442.0,
        "close": 1459.44,
        "volume": 29125.0
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
    },
    "signal_matrix": {
      "schema_version": "1.0",
      "generated_at": "2026-04-02T09:00:00+00:00",
      "producer_version": "quant-l3",
      "signal_version": "l3-signal-v1.0",
      "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate"],
      "coverage_rate": 1.0,
      "rows": [
        {"symbol": "600519.SH", "factor_name": "momentum_20", "raw_value": 0.02, "signal_value": 1.23, "direction": 1}
      ],
      "composite_scores": [
        {"symbol": "600519.SH", "composite_score": 0.54, "factor_count": 3}
      ],
      "transform_stats": [
        {
          "factor_name": "momentum_20",
          "pre_winsorize": {"count": 5, "mean": 0.03, "std": 0.02, "min": -0.01, "max": 0.08},
          "post_zscore": {"count": 5, "mean": 0.0, "std": 1.0, "min": -1.5, "max": 1.8}
        }
      ]
    },
    "technical": null
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

## hf risk check（L5 风险门控）

```bash
hf risk check --as-of 2026-04-04
hf risk check --as-of 2026-04-04 --output table
```

Pass 示例（`status=ok`，`risk_gate=pass`）：

```json
{
  "schema_version": "1.0.0",
  "command": "hf risk check",
  "run_id": "run_20260404_abc12345",
  "status": "ok",
  "generated_at": "2026-04-04T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-04",
    "risk_gate": "pass",
    "regime": "normal",
    "regime_vol": 0.182,
    "regime_vol_source": "benchmark",
    "checks": [
      {"name": "portfolio_vol",    "value": 0.22, "threshold": 0.30, "passed": true},
      {"name": "single_asset_max", "value": 0.28, "threshold": 0.35, "passed": true},
      {"name": "industry_max",     "value": 0.35, "threshold": 0.45, "passed": true},
      {"name": "turnover",         "value": 0.45, "threshold": 0.80, "passed": true}
    ],
    "block_codes": []
  },
  "warnings": [],
  "errors": []
}
```

## hf pretrade check（L5.5 预交易模拟）

```bash
hf pretrade check --as-of 2026-04-01
hf pretrade check --as-of 2026-04-01 --output json
```

默认 `table`；两跳：先 `POST /api/v1/portfolio/optimize` 取权重，再 `POST /api/v1/pretrade/check`（名义资金 Phase 1 固定 1_000_000 CNY）。

`status=ok` 示例：

```json
{
  "schema_version": "1.0.0",
  "command": "hf pretrade check",
  "run_id": "run_20260406_pretrade01",
  "status": "ok",
  "generated_at": "2026-04-06T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "notional": 1000000.0,
    "overall_tradable": true,
    "total_impact_bp": 8.3,
    "orders": [
      {
        "symbol": "600519.SH",
        "target_weight": 0.12,
        "target_notional": 120000.0,
        "adv": 850000000.0,
        "participation_rate": 0.000141,
        "sigma": 0.18,
        "impact_bp": 2.1,
        "tradable": true
      }
    ]
  },
  "warnings": [],
  "errors": []
}
```

## hf execution plan（L6 执行计划）

```bash
hf execution plan --as-of 2026-04-01
hf execution plan --as-of 2026-04-01 --output json
```

默认 `table`；三跳：先 `POST /api/v1/portfolio/optimize`，再 `POST /api/v1/pretrade/check`，最后 `POST /v1/execution/plan`（名义资金 Phase 1 固定 1_000_000 CNY）。

`status=ok` 示例：

```json
{
  "schema_version": "1.0.0",
  "command": "hf execution plan",
  "run_id": "exec_20260406_01",
  "status": "ok",
  "generated_at": "2026-04-06T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "slippage_bp": 5,
    "estimated_total_cost_bp": 6.4,
    "orders": [
      {
        "symbol": "600519.SH",
        "direction": "buy",
        "action": "open_long",
        "quantity": 100,
        "target_notional": 120000.0,
        "current_notional": 0.0,
        "close_price": 1180.0,
        "limit_price": 1180.59,
        "order_type": "limit",
        "validity": "day",
        "impact_bp": 2.1
      }
    ]
  },
  "warnings": [],
  "errors": []
}
```

## hf monitor health-report（L8 健康报告）

```bash
hf monitor health-report --as-of 2026-04-01
hf monitor health-report --as-of 2026-04-01 --output json
```

`status=ok`、交易日聚合示例：

```json
{
  "schema_version": "1.0.0",
  "command": "hf monitor health-report",
  "run_id": "hr_20260401_a1b2c3d4",
  "status": "ok",
  "generated_at": "2026-04-01T10:00:00+00:00",
  "source": "system",
  "advice_only": false,
  "decision_weight": 1,
  "data": {
    "as_of": "2026-04-01",
    "overall_rating": "green",
    "factor_health": {
      "total": 2,
      "ok_count": 2,
      "warn_count": 0,
      "miss_count": 0,
      "details": [
        {"factor_name": "momentum_20", "availability_rate": 0.93, "status": "ok"}
      ]
    },
    "signal_health": {
      "coverage_rate": 0.89,
      "composite_score_mean": 0.12,
      "composite_score_std": 0.45,
      "status": "ok"
    },
    "risk_health": {
      "regime": "normal",
      "triggered_rules": [],
      "status": "ok"
    },
    "trend": null,
    "run_daily_warnings": []
  },
  "warnings": [],
  "errors": []
}
```
