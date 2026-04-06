# Pipeline Compare Backtest Design

## 1. Goal

新增“版本对比回放”能力，支持在同一日期区间对比 `l2-score-v1` 与 `l2-score-v1.1` 的候选结果与数据质量指标，并提供 `json/table` 双输出。

## 2. Scope

In Scope:

- `quant` 新增 `POST /api/v1/pipeline/compare`
- `cli` 新增 `hf pipeline compare` 命令
- 回放窗口支持 `start_date/end_date`（首版默认 30 天）
- 输出逐日明细与汇总统计

Out of Scope:

- 下单与执行层改造
- 回测收益评估（收益曲线、Sharpe、回撤统计）
- 前端可视化

## 3. Architecture

- `interfaces/http`：
  - 新增 compare 请求/响应 DTO
  - 路由只做参数解析与 service 调用
- `application`：
  - 新增 `pipeline_compare_service.py`，负责逐日编排与对比汇总
  - 复用现有 `run_daily`，通过 `score_version` 参数切换版本
- `domain`：
  - 保持无 HTTP 依赖，不新增框架耦合

依赖方向保持：
`interfaces -> application -> domain`

## 4. API Contract

### 4.1 Request

`POST /api/v1/pipeline/compare`

```json
{
  "start_date": "2026-03-01",
  "end_date": "2026-03-30",
  "top_n": 5
}
```

### 4.2 Response (核心字段)

```json
{
  "schema_version": "1.0.0",
  "command": "hf pipeline compare",
  "status": "ok",
  "data": {
    "start_date": "2026-03-01",
    "end_date": "2026-03-30",
    "daily_items": [
      {
        "as_of": "2026-03-01",
        "v1": {
          "top_candidates": [{"symbol": "600519.SH", "score": 0.72, "rank": 1}],
          "warning_count": 0,
          "min_availability": 1.0
        },
        "v1_1": {
          "top_candidates": [{"symbol": "601318.SH", "score": 0.74, "rank": 1}],
          "warning_count": 0,
          "min_availability": 1.0
        }
      }
    ],
    "summary": {
      "days": 30,
      "avg_warning_count_v1": 0.1,
      "avg_warning_count_v1_1": 0.0,
      "avg_min_availability_v1": 0.95,
      "avg_min_availability_v1_1": 0.98,
      "top1_symbol_change_days": 8
    }
  },
  "warnings": [],
  "errors": []
}
```

## 5. Service Design

新增 `application/pipeline_compare_service.py`：

1. 校验日期区间（`start_date <= end_date`）
2. 生成日期列表（逐日）
3. 每个交易日执行两次 daily 编排：
   - `run_daily(..., score_version="l2-score-v1")`
   - `run_daily(..., score_version="l2-score-v1.1")`
4. 提取逐日 compare 指标：
   - `top_candidates`
   - `warning_count`
   - `min_availability`（`factor_availability` 最小值）
5. 聚合 summary：
   - 天数
   - 两版本平均 warning
   - 两版本平均最小可用率
   - Top1 变更天数

## 6. CLI Design

新增命令：

```bash
hf pipeline compare --start-date 2026-03-01 --end-date 2026-03-30 --output table
```

输出模式：

- `json`：完整透传 compare payload
- `table`：逐日对比摘要 + 汇总行

表头：

- `日期`
- `v1_top1`
- `v1.1_top1`
- `v1_warn`
- `v1.1_warn`
- `v1_min_avail`
- `v1.1_min_avail`

## 7. Error Handling

- 日期不合法：返回 `400`（参数错误）
- 区间为空：返回空 `daily_items` 与 `summary.days=0`
- 单日执行失败：该日记录错误并继续后续日期，最终状态可为 `warning`

## 8. Testing Strategy

### 8.1 Quant

- unit：日期遍历、汇总统计、Top1 变更计数
- contract：`/api/v1/pipeline/compare` 字段契约

### 8.2 CLI

- http 测试：compare endpoint 调用参数正确
- table 渲染测试：核心列存在、值映射正确

### 8.3 Gate

- `make architecture-check`
- `make check`

## 9. Rollout

Phase 1:

- 交付 compare 接口与 CLI 双输出（table/json）

Phase 2:

- 增加收益类统计与回测诊断（IC、命中率、回撤）
