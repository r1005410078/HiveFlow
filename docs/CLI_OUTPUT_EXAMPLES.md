# HiveFlow CLI 输出示例

> 本文档提供 `CLI_OUTPUT_SCHEMA.json` 的三类最小可用示例，供开发与测试直接复用。
> 文档导航：`DOCUMENTATION_INDEX.md`
> 文档目标：提供可复制的 CLI 输出样例与校验命令。适用对象：CLI 开发、测试、CI 维护。

当前运行方式：

- `quant` 服务端通过 HTTP 生成这些 JSON 契约输出。
- `cli` 作为客户端调用服务端，并将返回结果原样输出给终端与自动化工具。

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
