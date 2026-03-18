# CURRENT_STATE

## 当前时间点

- 日期：2026-03-18
- 当前分支：`main`

## 已完成阶段（按计划文档）

- Chunk 1 ~ Chunk 30 已落地
- M5 全部六个能力已交付
- M6 量化策略管理系统已交付
- 最近完成重点：
  - `market-data template / validate / import / list / summary` 行情全链路
  - `backtest run / list` 含从 DB 读行情、`weights_snapshot` 落库
  - `targets set-from-backtest` 从回测配比直接写入目标
  - `trade execute` OKX 现货市价单执行（含余额预检、确认流程）
  - `positions list` 区分自由持仓与网格持仓（含 inst_type：SPOT/SWAP）
  - `skills list / install` Skills 纳入版本控制，软链接安装到 `~/.agents/skills/`
  - `hiveflow-daily-check` + `hiveflow-portfolio-advisor` Skills 已迁移到 `skills/`
  - `quant list / run / history` 内置 8 种量化策略，结果落库，支持 `--apply`

## 当前可用命令（核心）

- `hiveflow positions ...`
- `hiveflow risk ...`
- `hiveflow strategies ...`
- `hiveflow slots ...`
- `hiveflow current ...`
- `hiveflow targets ...`
- `hiveflow rebalance preview ...`
- `hiveflow logs ...`
- `hiveflow backtest ...`
- `hiveflow market-data ...`
- `hiveflow trade execute`
- `hiveflow quant list / run / history`
- `hiveflow skills list / install`
- `hiveflow summary`
- `hiveflow doctor`
- `hiveflow init-demo`

## 当前状态说明

- 全量测试最近结果：`193 passed`
- `skills/` 目录已纳入版本控制，`~/.agents/skills/hiveflow-*` 为软链接
- 本地存在未跟踪数据文件：`data/`、`strategies.csv`、`prices.csv`（不应提交）

## 下一步建议

1. M7：网格机器人创建/管理
2. 多交易所支持
3. 多策略组合（加权混合多个策略输出）
