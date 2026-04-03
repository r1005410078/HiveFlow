# Pipeline Compare Phase2 Analytics Design

## 1. Goal

在现有 `pipeline compare`（v1 vs v1.1 逐日明细 + 汇总）基础上，新增 Phase 2 收益与稳定性评估能力，支持：

- 收益与风险指标：`top1_next_day_return`、区间累计收益、胜率、最大回撤、年化波动率、Sharpe
- 时序输出：日度收益序列（按版本）
- 分组稳定性：按 `industry + market_cap_bucket` 统计表现差异

## 2. Scope

In Scope:

- 扩展 `POST /api/v1/pipeline/compare` 的响应 `data` 字段（保持兼容）
- 在 `quant/application/pipeline_compare_service.py` 内完成指标编排与计算（方案 1）
- CLI `hf pipeline compare --output json|table` 展示新增关键统计
- 增加对应 unit/contract/CLI 测试

Out of Scope:

- 新增独立 compare analytics 服务（本期不拆文件）
- 交易成本/滑点/冲击成本建模
- 横截面归因与因子贡献分解

## 3. Architecture

- `interfaces/http`
  - 保持“DTO + service 调用”职责
  - 扩展 compare response schema，禁止写业务算法
- `application`
  - 在 `pipeline_compare_service.py` 内新增 analytics 计算流程
  - 复用现有 daily compare 结果，追加收益/风险/分组统计
- `domain`
  - 不引入 HTTP/框架依赖

依赖方向保持：`interfaces -> application -> domain`

## 4. Data & Metric Definitions

## 4.1 基础收益口径

以每个交易日 Top1 标的的“次日收益”作为该日策略收益：

- `top1_next_day_return = close(t+1)/close(t)-1`
- 若缺失次日价格，记为不可计算并在 warnings 中计数

版本收益序列：

- `daily_return_series_v1[]`
- `daily_return_series_v1_1[]`

## 4.2 区间统计

对各版本分别计算：

- `cumulative_return`
- `win_rate`
- `max_drawdown`
- `annualized_volatility`
- `sharpe`（无风险利率首版固定为 0）

并计算差异：

- `excess_cumulative_return_v1_1_vs_v1`
- `excess_sharpe_v1_1_vs_v1`

## 4.3 分组稳定性口径

分组键：`industry + market_cap_bucket`

- `industry`：来自证券基础信息（若缺失记 `UNKNOWN`）
- `market_cap_bucket`：按市值分桶（首版固定）：
  - `SMALL`、`MID`、`LARGE`
  - 分桶阈值来自统一配置（无配置时使用默认阈值）

分组统计输出：

- 每组样本数
- 各版本累计收益/胜率/Sharpe
- 版本差值（v1.1 - v1）
- 稳定性标识（样本数不足标记 `LOW_SAMPLE`）

## 5. API Contract Extension

## 5.1 Request

保持现有字段，不新增必填参数：

```json
{
  "start_date": "2026-03-01",
  "end_date": "2026-03-30",
  "top_n": 5
}
```

## 5.2 Response（新增核心字段）

在现有 `data` 下新增：

```json
{
  "data": {
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
        "v1": [{"as_of": "2026-03-01", "top1_next_day_return": 0.0042}],
        "v1_1": [{"as_of": "2026-03-01", "top1_next_day_return": 0.0061}]
      },
      "group_stability": {
        "group_key": "industry_market_cap_bucket",
        "items": [
          {
            "industry": "Bank",
            "market_cap_bucket": "LARGE",
            "sample_days": 8,
            "v1": {"cumulative_return": 0.012, "win_rate": 0.50, "sharpe": 0.42},
            "v1_1": {"cumulative_return": 0.021, "win_rate": 0.63, "sharpe": 0.71},
            "diff": {"excess_cumulative_return": 0.009, "excess_sharpe": 0.29},
            "stability_flag": "OK"
          }
        ]
      }
    }
  }
}
```

## 6. CLI Design

命令保持不变：

```bash
hf pipeline compare --start-date 2026-03-01 --end-date 2026-03-30 --top-n 5 --output table
```

输出增强：

- `json`：透传完整 analytics 结构
- `table`：新增两个区块
  - `收益与风险统计`（两版本 + 差值）
  - `分组稳定性（industry + market_cap_bucket）`（TopN 组）

表格展示字段（首版）：

- return_metrics: `cum_return`, `win_rate`, `max_dd`, `vol`, `sharpe`
- group_stability: `industry`, `cap_bucket`, `sample_days`, `v1_cum`, `v1.1_cum`, `diff_cum`, `flag`

## 7. Error Handling & Warnings

- 价格缺失导致某日无法计算次日收益：
  - 该日在收益序列中跳过或标记 null
  - warnings 增加 `MISSING_NEXT_DAY_PRICE`
- 分组元数据缺失：
  - `industry=UNKNOWN`
  - `market_cap_bucket=UNKNOWN`
- 样本不足（如 `<5` 天）组：
  - `stability_flag=LOW_SAMPLE`

## 8. Testing Strategy

## 8.1 Quant Unit

- 收益序列与累计收益计算正确
- 最大回撤、波动率、Sharpe 计算正确（含边界值）
- 分组逻辑（industry/cap bucket）与 `LOW_SAMPLE` 标记正确

## 8.2 Quant Contract

- `/api/v1/pipeline/compare` 新增 `analytics` 字段结构正确
- 旧字段仍保持兼容（不破坏 Phase 1）

## 8.3 CLI

- `http_pipeline_compare`：新增字段解析/透传断言
- `http_pipeline_compare_table`：新增收益统计与分组区块断言

## 8.4 Gate

- `make architecture-check`
- `make check`

## 9. Rollout Plan

Phase 2-A:

- 服务端先交付 analytics JSON + contract 回归

Phase 2-B:

- CLI table 展示增强 + 文档更新

Phase 2-C:

- 评审稳定性阈值与分组配置，决定是否拆分独立 analytics service（Phase 3 预留）

## 10. Open Decisions（默认值）

首版默认：

- 无风险利率：0
- `market_cap_bucket` 阈值：使用配置默认值
- `group_stability` 输出排序：按 `sample_days` 降序，其次按 `excess_cumulative_return` 降序

若后续需要策略化参数，将在 Phase 3 暴露可选请求参数。
