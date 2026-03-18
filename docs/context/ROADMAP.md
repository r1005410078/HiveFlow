# ROADMAP

## 为什么要这份文档

这是一份“一眼看懂下一步”的路线图，避免开发变成只看当前小需求。

## 当前位置

- 已完成：Chunk 1 ~ Chunk 30 + M4 + M5 + M6 + M7 + M8
- 当前阶段：M9 规划中

## 三个里程碑

### M1：策略驱动决策闭环（已完成）

目标：
- 策略、当前策略、目标持仓、调仓建议、日志形成完整链路
- 模板可配置且可通过命令维护

代表能力：
- `current set-strategy`
- `targets generate`
- `rebalance preview`
- `targets template-show / template-set`

### M2：策略质量与风控闭环（已完成）

目标：
- 让“策略回测”和“风险门控”成为一等能力，不再只是展示字段

已交付：
1. `positions drift` 偏离检测（低/中/高等级与动作建议）
2. `rebalance preview` 解释增强（类型/维度/风险水位）
3. `targets template-rollback` 模板版本回滚

### M3：自定义策略与发布闭环（已完成）

已交付：
- `hiveflow doctor` 环境/配置诊断
- `hiveflow init-demo` 一键演示数据
- 统一 JSON envelope（`--envelope`）与 `--json-schema`
- 文档与测试收口（全量回归通过）

## M4：行情驱动分析闭环（已完成）

已交付：
- `market-data template / validate` 行情输入契约与校验
- `market-data import / list / summary` 行情落库与查询
- `backtest run / list` 最小回测引擎与结果落库
- `targets set-from-backtest` 从回测配比直接写入目标

## M5：OKX 交易执行闭环（已完成）

已交付：
- `positions list` 区分自由持仓与网格持仓（SPOT/SWAP）
- `trade execute` OKX 现货市价单执行（余额预检 + 确认流程）
- `skills list / install` Skills 纳入版本控制，软链接安装
- `hiveflow-daily-check` + `hiveflow-portfolio-advisor` Skills 迁移到 `skills/`

## M6：量化策略管理（已完成）

已交付：
- `quant list / run / history` 内置 8 种量化策略（EqualWeight / Momentum / MeanReversion / MovingAverageCross / BollingerBand / RiskParity / MaxSharpe / MinVariance）
- 策略结果落库 StrategyRun，支持 `--apply` 写入目标
- `backtest quant-run` 量化策略动态再平衡回测（每隔 N 天重新计算权重，无前视偏差）
- `sync --days` 支持最多 500 天（OKX 分页拉取）

## M7：回测权益曲线可视化（已完成）

已交付：
- `BacktestMetrics.curve` + `BacktestResult.equity_curve` 落库（JSON），含轻量迁移
- `backtest show <id>` 终端 Unicode Sparkline + 指标摘要，支持 `--output json`
- `backtest compare <id1> <id2> ...` 多回测并排对比，含全量 ID 预检与 `--output json`
- `_sparkline()` 上取整采样（避免截断长曲线），旧记录 NULL 降级提示

## M8：风险分析引擎（已完成）

已交付：
- `risk-analysis assets [--symbols] [--output]` 资产年化波动率、日波动率、历史 MDD、Pearson 相关性矩阵
- `risk-analysis portfolio <id> [--output]` 组合年化波动率、胜率、Calmar ratio（从 BacktestResult.equity_curve 派生）
- `backtest show` 追加风险指标节（equity_curve 存在时）
- 无新增第三方依赖，手工实现所有统计计算，年化因子 365

## M9：下一阶段（规划中）

候选方向：
1. 网格机器人管理（`grid create/list/stop`，OKX Grid Trading API）
2. 多策略组合（加权混合多个量化策略输出，`portfolio blend`）
3. 实盘绩效追踪（持仓日志 + 权益曲线与回测对比）
4. 多交易所支持

## 决策规则（防止“抓芝麻”）

- 不新增“看起来很酷但不改变主线结果”的功能
- 所有需求都要回答：是否直接提升“回测质量、风险控制、自定义策略”其中之一
- 如果答案是否定，进入 backlog，不占当前 sprint
