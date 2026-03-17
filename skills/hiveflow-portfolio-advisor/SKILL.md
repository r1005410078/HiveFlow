---
name: hiveflow-portfolio-advisor
description: Deep portfolio analysis and rebalancing for HiveFlow users. Runs backtests on candidate allocations, recommends optimal allocation based on investment theory, generates rebalancing orders, and executes on OKX after user confirmation. Use when user says "调仓", "rebalance", "分析配比", "我该怎么动", or any request for portfolio decision-making beyond daily risk check.
---

# HiveFlow Portfolio Advisor

深度决策工具。从回测配比到 OKX 执行，全程辅助。

## 前置条件

确保已执行 `hiveflow sync --days 30` 积累至少 30 天行情数据。

## 执行流程

### Step 1：获取当前自由持仓

```bash
uv run hiveflow positions list --output json
```

从 `free` 数组提取持仓资产列表（排除 USDT）。

### Step 2：生成候选配比并写入策略

根据持仓资产，生成三组候选配比：

**生成规则：**
- USDT 最低 10%（弹药底线，不可低于此值）
- 单资产上限 60%（避免过度集中）
- BTC 作为核心资产，建议权重不低于 20%

**三个模板（根据实际持仓资产动态调整权重，确保加总为 1）：**

| 模板 | 特点 | USDT | BTC | 其他 |
|---|---|---|---|---|
| 激进版 | 高风险高收益 | 10% | 50%+ | 剩余均分 |
| 均衡版 | 风险收益平衡 | 20% | 40% | 剩余均分 |
| 保守版 | 低风险稳健 | 40% | 30% | 剩余均分 |

对每个配比执行：
```bash
uv run hiveflow targets import --strategy "激进版" --mode replace
uv run hiveflow backtest run --strategy "激进版"
```

### Step 3：比较回测结果

```bash
uv run hiveflow backtest list --output json
```

展示对比表格（只看最近三次回测）：

| 策略 | 总收益 | 最大回撤 | 夏普比率 |
|---|---|---|---|
| 激进版 | ... | ... | ... |
| 均衡版 | ... | ... | ... |
| 保守版 | ... | ... | ... |

### Step 4：给出推荐并说明理由

**投资理论框架（按优先级应用）：**

1. **回撤优先**：最大回撤是第一过滤条件。加密市场暴跌频繁，-30% 以下的配比要明确警示风险。优先推荐最大回撤控制在 -25% 以内的配比。

2. **风险调整收益（夏普比率）**：在同等回撤约束下，优先选夏普更高的。夏普 > 1.0 为优秀，0.5~1.0 为可接受，< 0.5 需谨慎。

3. **USDT 弹药原则**：保留 USDT 不是保守，是保留机会。市场突然下跌时，手头有 USDT 才能低位补仓。

4. **分散但不稀释**：3-5 个资产足够。超过 5 个资产时，权重过小的资产（< 5%）等于没有。

**推荐格式示例：**
```
推荐：均衡版（BTC 40% ETH 25% SOL 15% USDT 20%）

理由：
- 最大回撤 -18%，低于激进版的 -28%，风险可控
- 夏普比率 1.35，是三个配比中最高的
- USDT 20% 保留足够弹药

激进版回撤过大（-28%），在加密市场波动环境下不建议。
保守版总收益明显低，当前持仓中高波动资产较多时意义不大。
```

**帮助用户了解自己的风险偏好：**
每次分析结束后问一句：
> "这个配比的最大回撤 -18% 你能接受吗？如果市值一个月内从 10 万跌到 8.2 万，你会慌吗？"

**其他策略科普（仅教育）：**
- 动量策略：过去表现好的资产持续持有，适合牛市
- 均值回归：跌多了买，涨多了卖，适合震荡市
- 网格交易：横盘震荡时效果好，当前系统不执行，可以建议手动在 OKX 设置
- 合约/杠杆：放大收益也放大风险，不在本系统范围内，高风险谨慎参与

### Step 5：用户选定配比后设置目标

```bash
uv run hiveflow targets set-from-backtest <backtest_id>
```

### Step 6：预览调仓建议

```bash
uv run hiveflow rebalance preview --output json
```

分析 `suggestions` 数组，生成人类可读的调仓报告：
- HIGH priority：需要立即处理
- MEDIUM：建议处理
- LOW：可选

### Step 7：生成订单并确认执行

将调仓建议转换为订单列表，展示给用户：

```
调仓计划：
  买入 ETH  约 500 USDT（当前 25% → 目标 30%）
  卖出 SOL  约 200 USDT（当前 20% → 目标 15%）
  保留 BTC（偏差 < 2%，无需调整）

总交易量：约 700 USDT
预估手续费：~0.1%（约 0.7 USDT）

确认执行？
```

用户确认后：
```bash
uv run hiveflow trade execute --orders '[{"symbol":"ETH","action":"buy","usdt":500},{"symbol":"SOL","action":"sell","usdt":200}]'
```

### Step 8：执行后汇报

展示执行结果，记录本次调仓决策。

## 注意事项

- 执行前确保 `.env` 中已配置 Trade API Key（`HIVEFLOW_OKX_TRADE_API_KEY` 等）
- 网格持仓中的资产不计入调仓计算，请从 `positions list` 的 `grid` 区块确认
- 市价单会产生滑点，实际成交价格可能与预览略有偏差
- 若执行部分失败，系统会给出成功的订单 ID，请在 OKX 手动确认账户状态
