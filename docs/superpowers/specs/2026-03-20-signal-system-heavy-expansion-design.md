# Signal System 重型扩展设计（Phase 1）

## 1. 背景与目标

用户期望 HiveFlow 不止输出“目标权重”，还要提供更完整的信号上下文，交由 AI Agent 进行判断与执行。

本设计的核心目标：

- 构建“大而全”的信号系统（首期 24 个信号）。
- 系统只做确定性计算与结构化输出。
- 不输出投资建议，不推荐风格，不做自动决策。
- 通过回测输出“风格指标排名”，供 Agent 选择。

## 2. 系统宗旨与边界（强约束）

HiveFlow 只做数据与工具，不做智能判断。

### 2.1 HiveFlow 要做

- 计算信号（trend / risk / confirm / regime / quality）。
- 输出统一 JSON 协议（可被 Agent 直接消费）。
- 生成风格回测结果与指标排名（仅数据）。
- 落库保存快照与回测结果，保证可追溯。

### 2.2 HiveFlow 不做

- 不输出 buy / sell / hold 结论。
- 不输出“推荐风格”。
- 不在系统内做信号冲突裁决结论。
- 不替代 Agent 做最终判断。

### 2.3 严格模式硬规则（Phase 1）

- 信号计算采用严格模式：任一关键信号缺失或样本不足，整次 `signal snapshot` 失败。
- 风格排名采用严格模式：任一风格回测失败或数据不足，整次 `style backtest-rank` 失败。
- 严格模式下不返回部分结果，不做降级补齐，不做推荐替代。

## 3. Phase 1 范围

Phase 1 为重型扩展第一阶段，不包含 Agent 订阅接口。

### 3.1 命令面

- `hiveflow signal trend --output json`
- `hiveflow signal risk --output json`
- `hiveflow signal confirm --output json`
- `hiveflow signal regime --output json`
- `hiveflow signal quality --output json`
- `hiveflow signal snapshot --output json`（聚合输出）
- `hiveflow style backtest-rank --output json`（仅排名，不推荐）

### 3.2 风格集合（用于回测排名）

- `Trend-Following`
- `Mean-Reversion`
- `Defensive-RiskOff`
- `Breakout-Aggressive`

## 4. 信号分类与首期 24 信号清单

### 4.1 trend（6）

1. `golden_cross`
2. `death_cross`
3. `breakout_20d`
4. `breakdown_20d`
5. `momentum_20d`
6. `macd_cross`

### 4.2 risk（6）

1. `max_drawdown_7d`
2. `max_drawdown_30d`
3. `atr_volatility_14d`
4. `vol_regime_shift`
5. `concentration_risk`
6. `correlation_spike`

### 4.3 confirm（4）

1. `volume_breakout_confirm`
2. `multi_timeframe_confirm`
3. `signal_consensus`
4. `trend_persistence`

### 4.4 regime（4）

1. `market_regime_label`
2. `trend_strength_adx`
3. `volatility_regime_label`
4. `local_breadth_proxy`

### 4.5 quality（4）

1. `data_freshness`
2. `data_completeness`
3. `signal_stability`
4. `confidence_score`

## 5. 统一输出协议（JSON）

每条信号统一字段：

- `signal_key`
- `category`
- `symbol`
- `as_of`
- `state`
- `value`
- `threshold`
- `triggered`
- `confidence`
- `explanation`

状态字段约定（示例）：

- trend/regime: `bullish | neutral | bearish`
- risk: `low | medium | high`
- quality: `good | warning | bad`

### 5.1 字段类型与空值约定（Agent 消费契约）

- `signal_key`: `string`（唯一键，如 `momentum_20d`）
- `category`: `string`（`trend|risk|confirm|regime|quality`）
- `symbol`: `string`（资产代码；组合级信号可用 `PORTFOLIO`）
- `as_of`: `string`（ISO8601 UTC）
- `state`: `string`（见各分类枚举）
- `value`: `number | string | null`
- `threshold`: `number | string | null`
- `triggered`: `boolean`
- `confidence`: `number`（`0.0 ~ 1.0`）
- `explanation`: `string`

统一规则：

- 无法计算时必须返回记录，`triggered=false`，并在 `explanation` 写明原因。
- `confidence` 不可缺失；无法估计时返回 `0.0`。
- `value/threshold` 若不适用可为 `null`，不得省略字段。
- 所有百分比字段在 JSON 中使用小数（例如 `0.1234`），展示层再转 `%`。

### 5.2 全局错误码与错误对象（已冻结）

全局统一错误码（信号与风格回测共用）：

1. `E_DATA_SOURCE_EMPTY`
2. `E_DATA_INSUFFICIENT_SAMPLES`
3. `E_SIGNAL_REQUIRED_MISSING`
4. `E_STYLE_EVAL_FAILED`
5. `E_PARAM_INVALID`
6. `E_CONFIG_INVALID`
7. `E_DEPENDENCY_UNAVAILABLE`
8. `E_PIPELINE_ABORTED_STRICT`
9. `E_STORAGE_WRITE_FAILED`
10. `E_INTERNAL_UNEXPECTED`

错误对象统一结构：

- `code`
- `message`
- `context`
- `as_of`
- `details`
- `trace_id`
- `hint`（仅补数/修复提示，不含投资建议）

`details` 推荐字段：

- `signal_key`
- `style_name`
- `symbols`
- `required_samples`
- `actual_samples`
- `missing_fields`
- `data_window_start`
- `data_window_end`
- `params`

## 6. 聚合输出（signal snapshot）

`signal snapshot` 返回：

- `signals[]`：全量原始信号（标准字段协议）
- `category_metrics`：各分类统计（数量、触发数、均值、分位）
- `conflict_matrix`：仅描述冲突事实（例如 trend bullish + risk high）
- `as_of` 与 `data_window` 元信息

说明：`conflict_matrix` 只描述冲突，不提供裁决建议。

### 6.1 `conflict_matrix` 固定结构

`conflict_matrix` 使用如下结构输出（数组）：

- `conflict_key`: `string`（如 `trend_risk_conflict`）
- `lhs_category`: `string`
- `lhs_state`: `string`
- `rhs_category`: `string`
- `rhs_state`: `string`
- `severity`: `string`（`low|medium|high`）
- `symbols`: `string[]`
- `count`: `integer`

示例：

```json
[
  {
    "conflict_key": "trend_risk_conflict",
    "lhs_category": "trend",
    "lhs_state": "bullish",
    "rhs_category": "risk",
    "rhs_state": "high",
    "severity": "high",
    "symbols": ["ETH", "SOL"],
    "count": 2
  }
]
```

## 7. 风格回测排名输出（style backtest-rank）

每个风格输出：

- `style_name`
- `total_return`
- `max_drawdown`
- `sharpe`
- `calmar`
- `win_rate`
- `annualized_volatility`
- `periods`
- `backtest_window`

同时输出：

- `rank_table`（按指定指标排序）
- `sort_key`（如 `calmar`）
- `tie_breaker`（固定规则描述）

严格禁止输出：

- `recommended_style`
- `suggested_action`

默认排序规则（无显式指定 `sort_key` 时）：

1. `calmar` 降序
2. `max_drawdown` 升序（绝对回撤更小优先）
3. `sharpe` 降序
4. `total_return` 降序

## 7.1 与 `backtest quant-run` 的关系与映射

关系定义：

- `backtest quant-run`：底层单策略动态回测执行器（engine）。
- `style backtest-rank`：上层风格批量编排与排名器（orchestrator + ranker）。
- `style backtest-rank` 不替代 `quant-run`，而是复用其回测能力，对多个“风格模板”批量执行并聚合结果。

### 风格到现有策略映射（Phase 1）

> 以下为首版默认映射，用于统一实验口径；后续可通过配置文件扩展。

| 风格 | `quant-run` 策略 | 默认参数（示例） | 设计意图 |
|---|---|---|---|
| `Trend-Following` | `MomentumStrategy` | `lookback_days=30, top_k=3, min_usdt=0.10` | 捕捉中期趋势延续 |
| `Mean-Reversion` | `MeanReversionStrategy` | `window=20, min_usdt=0.10` | 捕捉偏离均值后的回归 |
| `Defensive-RiskOff` | `RiskParityStrategy` | `window=30` | 以波动率约束控制回撤 |
| `Breakout-Aggressive` | `MovingAverageCrossStrategy` | `fast=7, slow=30, min_usdt=0.10` | 偏进攻，追踪突破与加速 |

### 7.2 Phase 1 实现约束对齐

为避免“文档参数”与“现有实现”不一致，Phase 1 采用以下强约束：

- `style backtest-rank` 只调用现有策略已支持参数。
- 未实现参数透传前，先按策略默认参数运行（或仅允许白名单参数）。
- 任何未支持参数必须在输出 `status=invalid_config`，并写入 `error_detail`。
- Phase 1 风格排名仅基于现有 `quant-run` 回测结果；信号特征只做并行输出，不直接参与排名计算。
- Phase 2 再引入“信号特征入模”能力，避免本期范围漂移。

## 7.3 风格-信号连接契约（避免两条平行线）

每个风格必须声明“仅数据消费”的特征集合（不产生推荐）：

- `Trend-Following`: `golden_cross`, `momentum_20d`, `trend_persistence`, `trend_strength_adx`
- `Mean-Reversion`: `max_drawdown_7d`, `atr_volatility_14d`, `signal_consensus`
- `Defensive-RiskOff`: `max_drawdown_30d`, `concentration_risk`, `volatility_regime_label`, `confidence_score`
- `Breakout-Aggressive`: `breakout_20d`, `volume_breakout_confirm`, `multi_timeframe_confirm`

说明：

- 上述连接只用于“风格特征画像”和回测分组统计，不用于系统自动推荐。
- Agent 可读取连接关系，自主定义最终判定逻辑。

### `style backtest-rank` 内部执行流程（概念）

1. 读取风格映射配置（风格 -> 策略/参数）。
2. 对每个风格调用与 `quant-run` 一致的动态回测底层逻辑。
3. 汇总每个风格指标（收益、回撤、Sharpe、Calmar、胜率、波动率）。
4. 生成 `rank_table` 并输出 JSON。

说明：

- 输出仅包含事实指标与排名，不包含推荐字段。
- 若某风格在当前环境依赖缺失（例如优化器库）或数据不足，严格模式下整次排名任务直接失败。

## 8. 数据与存储

Phase 1 新增对象（建议）：

- `SignalSnapshot`：某时点聚合快照（JSON blob + metadata）
- `SignalFeature`：可选，逐 signal_key 存储便于查询
- `StyleBacktestResult`：风格级回测结果

基本要求：

- 所有输出可追溯至输入数据窗口。
- 每个快照与回测结果具备唯一 `as_of` / `run_id`。

### 8.1 可复现键（强制）

为保证“同输入得同输出”，每次快照与回测必须落以下键：

- `snapshot_id`（UUID）
- `run_id`（风格回测运行 ID）
- `feature_set_version`（如 `signal-v1.0`）
- `style_preset_version`（如 `style-v1.0`）
- `data_window_start` / `data_window_end`（UTC）
- `symbols_hash`（资产池签名）
- `params_hash`（风格参数签名）
- `code_version`（commit hash）

## 9. 验收标准

满足以下条件即视为 Phase 1 完成：

- 可稳定输出 24 个信号，字段协议统一。
- 分项命令与 `signal snapshot` 均可 `--output json`。
- `style backtest-rank` 可输出多风格排名与指标。
- 输出中不包含任何推荐或结论字段。
- 能从历史记录回放特定日期快照和风格回测。
- 同一 `code_version + data_window + params_hash` 复跑，结果差异在容忍范围内（浮点误差）。
- 在严格模式下：任一关键信号缺失时 `signal snapshot` 返回失败退出码。
- 在严格模式下：任一风格失败时 `style backtest-rank` 返回失败退出码。

## 9.1 24 信号数据依赖与缺失行为

每个信号必须定义：`data_source`、`min_samples`、`on_missing`。

Phase 1 基线约定（严格模式）：

- 任一 `min_samples` 不满足或关键输入缺失时，整批快照任务失败并返回错误原因。
- 不返回部分信号，不进行缺失补位。

### trend

1. `golden_cross`: source=`MarketBar.close`, min=`slow_window`, on_missing=`fail_task`
2. `death_cross`: source=`MarketBar.close`, min=`slow_window`, on_missing=`fail_task`
3. `breakout_20d`: source=`MarketBar.high/close`, min=`20`, on_missing=`fail_task`
4. `breakdown_20d`: source=`MarketBar.low/close`, min=`20`, on_missing=`fail_task`
5. `momentum_20d`: source=`MarketBar.close`, min=`21`, on_missing=`fail_task`
6. `macd_cross`: source=`MarketBar.close`, min=`35`, on_missing=`fail_task`

### risk

1. `max_drawdown_7d`: source=`MarketBar.close`, min=`7`, on_missing=`fail_task`
2. `max_drawdown_30d`: source=`MarketBar.close`, min=`30`, on_missing=`fail_task`
3. `atr_volatility_14d`: source=`MarketBar.ohlc`, min=`14`, on_missing=`fail_task`
4. `vol_regime_shift`: source=`MarketBar.close`, min=`30`, on_missing=`fail_task`
5. `concentration_risk`: source=`Position.market_value`, min=`1`, on_missing=`fail_task`
6. `correlation_spike`: source=`MarketBar.close(all symbols)`, min=`30`, on_missing=`fail_task`

### confirm

1. `volume_breakout_confirm`: source=`MarketBar.volume`, min=`20`, on_missing=`fail_task`
2. `multi_timeframe_confirm`: source=`MarketBar.close`, min=`30`, on_missing=`fail_task`
3. `signal_consensus`: source=`signal outputs`, min=`N/A`, on_missing=`fail_task`
4. `trend_persistence`: source=`trend history`, min=`5 snapshots`, on_missing=`fail_task`

### regime

1. `market_regime_label`: source=`MarketBar.close`, min=`30`, on_missing=`fail_task`
2. `trend_strength_adx`: source=`MarketBar.ohlc`, min=`30`, on_missing=`fail_task`
3. `volatility_regime_label`: source=`MarketBar.close`, min=`30`, on_missing=`fail_task`
4. `local_breadth_proxy`: source=`MarketBar.close(cross symbols in current universe)`, min=`2 symbols x 20`, on_missing=`fail_task`

### quality

1. `data_freshness`: source=`latest timestamp`, min=`N/A`, on_missing=`fail_task`
2. `data_completeness`: source=`missing ratio`, min=`N/A`, on_missing=`fail_task`
3. `signal_stability`: source=`signal history`, min=`5 snapshots`, on_missing=`fail_task`
4. `confidence_score`: source=`f(data_freshness, data_completeness, signal_stability)`, min=`N/A`, on_missing=`fail_task`

## 9.2 24 信号计算规格（输入/阈值/state）

> 说明：阈值为 Phase 1 默认值，后续可配置化；本阶段系统仅输出事实状态，不输出建议动作。

### trend

1. `golden_cross`
- 输入字段：`close`, `ma_fast(7)`, `ma_slow(30)`
- 触发阈值：`ma_fast` 当期上穿 `ma_slow`
- 输出 state：触发上穿=`bullish`；未触发=`neutral`

2. `death_cross`
- 输入字段：`close`, `ma_fast(7)`, `ma_slow(30)`
- 触发阈值：`ma_fast` 当期下穿 `ma_slow`
- 输出 state：触发下穿=`bearish`；未触发=`neutral`

3. `breakout_20d`
- 输入字段：`close`, `high_20d_max`
- 触发阈值：`close > high_20d_max`
- 输出 state：触发=`bullish`；未触发=`neutral`

4. `breakdown_20d`
- 输入字段：`close`, `low_20d_min`
- 触发阈值：`close < low_20d_min`
- 输出 state：触发=`bearish`；未触发=`neutral`

5. `momentum_20d`
- 输入字段：`close_t`, `close_t-20`
- 触发阈值：`(close_t / close_t-20 - 1)`
- 输出 state：`> +5% => bullish`，`< -5% => bearish`，其余=`neutral`

6. `macd_cross`
- 输入字段：`ema12`, `ema26`, `dea9`
- 触发阈值：`diff` 上/下穿 `dea`
- 输出 state：上穿=`bullish`；下穿=`bearish`；其余=`neutral`

### risk

7. `max_drawdown_7d`
- 输入字段：近7期 `close` 序列
- 触发阈值：MDD 绝对值分层
- 输出 state：`<= -20% => high`，`(-20%,-10%] => medium`，`> -10% => low`

8. `max_drawdown_30d`
- 输入字段：近30期 `close` 序列
- 触发阈值：MDD 绝对值分层
- 输出 state：`<= -30% => high`，`(-30%,-15%] => medium`，`> -15% => low`

9. `atr_volatility_14d`
- 输入字段：`high/low/close`，ATR(14)
- 触发阈值：`ATR / close`
- 输出 state：`> 5% => high`，`(2%,5%] => medium`，`<= 2% => low`

10. `vol_regime_shift`
- 输入字段：20期滚动波动率、历史基线波动率
- 触发阈值：`rolling_vol / baseline_vol`
- 输出 state：`>= 1.5 => high`，`<= 0.7 => low`，其余=`medium`

11. `concentration_risk`
- 输入字段：`Position.market_value`（资产权重）
- 触发阈值：最大单一资产权重
- 输出 state：`>= 50% => high`，`[30%,50%) => medium`，`< 30% => low`

12. `correlation_spike`
- 输入字段：资产池30期收益相关矩阵
- 触发阈值：平均相关系数上升幅度
- 输出 state：`avg_corr >= 0.8 => high`，`[0.6,0.8) => medium`，`< 0.6 => low`

### confirm

13. `volume_breakout_confirm`
- 输入字段：`volume_t`, `volume_ma20`, `breakout_20d`
- 触发阈值：突破同时 `volume_t >= 1.5 * volume_ma20`
- 输出 state：满足=`bullish`；突破但不放量=`neutral`

14. `multi_timeframe_confirm`
- 输入字段：短周期趋势状态 + 长周期趋势状态
- 触发阈值：短长周期同向
- 输出 state：同向多头=`bullish`；同向空头=`bearish`；冲突=`neutral`

15. `signal_consensus`
- 输入字段：trend核心信号集合（如 cross/breakout/momentum/macd）
- 触发阈值：同向比例
- 输出 state：同向比例 `>= 0.75 => bullish/bearish`；否则=`neutral`

16. `trend_persistence`
- 输入字段：近5个快照 trend state 序列
- 触发阈值：同一方向持续期数
- 输出 state：同向连续 `>= 4` 期则延续该方向，否则=`neutral`

### regime

17. `market_regime_label`
- 输入字段：趋势强度 + 波动水平 + 方向一致性
- 触发阈值（v1 冻结）：
  - `bullish`: `ADX(14) >= 25` 且 `momentum_20d >= +5%` 且 `volatility_quantile_90d <= 0.8`
  - `bearish`: `ADX(14) >= 25` 且 `momentum_20d <= -5%` 且 `volatility_quantile_90d >= 0.5`
  - 其余：`neutral`
- 输出 state：`bullish | neutral | bearish`

18. `trend_strength_adx`
- 输入字段：ADX(14)
- 触发阈值：ADX 水平
- 输出 state：`>= 25 => bullish`（强趋势环境），`< 20 => neutral`，中间保留上期状态或 `neutral`

19. `volatility_regime_label`
- 输入字段：波动率分位数
- 触发阈值：当前波动率分位
- 输出 state：高波环境=`bearish`；低波环境=`bullish`；中等=`neutral`

20. `local_breadth_proxy`
- 输入字段：资产池内上涨资产占比
- 触发阈值：`up_ratio`
- 输出 state：`>= 70% => bullish`，`<= 30% => bearish`，其余=`neutral`

### quality

21. `data_freshness`
- 输入字段：`now - latest_bar_timestamp`
- 触发阈值：时延
- 输出 state：`<= 24h => good`，`(24h,72h] => warning`，`> 72h => bad`

22. `data_completeness`
- 输入字段：窗口内缺失率
- 触发阈值：`missing_ratio`
- 输出 state：`<= 1% => good`，`(1%,5%] => warning`，`> 5% => bad`

23. `signal_stability`
- 输入字段：近5快照 state 翻转次数
- 触发阈值：`flip_count`
- 输出 state：`<= 1 => good`，`2~3 => warning`，`>= 4 => bad`

24. `confidence_score`
- 输入字段：`data_freshness`, `data_completeness`, `signal_stability`
- 触发阈值：加权分数 `0~1`
- 输出 state：`>= 0.8 => good`，`[0.5,0.8) => warning`，`< 0.5 => bad`

## 9.3 Phase 1 参数寻优配置（关键层 12 信号）

### 9.3.1 分层基线（已冻结）

- `关键层(12)`：`golden_cross`, `death_cross`, `momentum_20d`, `max_drawdown_7d`, `max_drawdown_30d`, `atr_volatility_14d`, `concentration_risk`, `vol_regime_shift`, `signal_consensus`, `market_regime_label`, `data_freshness`, `confidence_score`
- `增强层(12)`：其余信号（Phase 1 仍按严格模式处理；此分层用于 Phase 2 演进）

### 9.3.2 寻优目标与约束（已冻结）

- 目标函数：`Calmar` 最大化
- 硬约束：`MDD >= -20%`
- 搜索方法：`Grid Search`
- 预算上限：每个信号最大候选组合 `500`（超出则分批或抽样）
- 输出原则：只输出候选阈值排名与证据，不输出推荐

### 9.3.3 关键层 12 信号网格范围

1. `golden_cross` / `death_cross`
- `fast`: `[5, 7, 10, 12]`
- `slow`: `[20, 30, 40, 60]`
- 约束：`fast < slow`

2. `momentum_20d`
- `lookback_days`: `[10, 20, 30, 60]`
- `bullish_threshold`: `[+3%, +5%, +8%]`
- `bearish_threshold`: `[-3%, -5%, -8%]`

3. `max_drawdown_7d`
- `warning_level`: `[-8%, -10%, -12%]`
- `danger_level`: `[-15%, -20%, -25%]`
- 约束：`danger_level < warning_level`

4. `max_drawdown_30d`
- `warning_level`: `[-12%, -15%, -18%]`
- `danger_level`: `[-25%, -30%, -35%]`
- 约束：`danger_level < warning_level`

5. `atr_volatility_14d`
- `atr_window`: `[10, 14, 20]`
- `medium_threshold`: `[1.5%, 2.0%, 3.0%]`
- `high_threshold`: `[4.0%, 5.0%, 6.0%]`

6. `concentration_risk`
- `medium_threshold`: `[25%, 30%, 35%]`
- `high_threshold`: `[45%, 50%, 55%]`

7. `vol_regime_shift`
- `rolling_window`: `[10, 20, 30]`
- `baseline_window`: `[60, 90, 120]`
- `low_ratio`: `[0.6, 0.7, 0.8]`
- `high_ratio`: `[1.3, 1.5, 1.8]`

8. `signal_consensus`
- `signal_pool_size`: `[3, 4, 5]`
- `consensus_ratio`: `[0.6, 0.75, 0.9]`

9. `market_regime_label`
- `trend_strength_threshold(ADX)`: `[20, 25, 30]`
- `high_vol_quantile`: `[0.7, 0.8, 0.9]`
- `low_vol_quantile`: `[0.1, 0.2, 0.3]`

10. `data_freshness`
- `good_hours`: `[12, 24, 36]`
- `warning_hours`: `[48, 72, 96]`

11. `confidence_score`
- `w_freshness`: `[0.3, 0.4, 0.5]`
- `w_completeness`: `[0.2, 0.3, 0.4]`
- `w_stability`: `[0.2, 0.3, 0.4]`
- `good_threshold`: `[0.75, 0.8, 0.85]`
- `warning_threshold`: `[0.45, 0.5, 0.6]`
- 约束：`w_freshness + w_completeness + w_stability = 1`

## 9.4 回测报告输出契约（必须字段）

为保证 Agent 可稳定消费，参数寻优与风格排名报告必须输出以下字段：

- `run_id`
- `trace_id`
- `code_version`
- `feature_set_version`
- `style_preset_version`
- `data_window_start`
- `data_window_end`
- `objective`（固定为 `calmar`）
- `constraints`（固定包含 `mdd_floor=-0.20`）
- `search_method`（固定为 `grid_search`）
- `candidates_count`
- `valid_candidates_count`
- `rank_table[]`（每项含 `params`, `total_return`, `max_drawdown`, `sharpe`, `calmar`, `win_rate`, `annualized_volatility`）
- `best_candidate`（仅指排名第一候选，不得写推荐语义）
- `failure_detail`（失败时必填，含全局错误码 + 详细错误对象）

说明：

- 报告层允许出现 `best_candidate`，其含义是“指标排序第一”，不是“推荐执行”。
- 任一关键输入缺失时，整次任务失败并输出 `failure_detail`，不返回部分排名。

## 10. 非目标（Phase 1 不做）

- Agent 订阅接口（push/webhook/stream）。
- 自动调仓执行联动。
- 系统内策略推荐与动作推荐。
- 高阶在线学习与自动参数寻优。
