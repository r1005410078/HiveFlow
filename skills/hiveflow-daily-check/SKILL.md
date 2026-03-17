---
name: hiveflow-daily-check
description: Daily 5-minute portfolio health check for HiveFlow users. Syncs OKX data, checks risk signals, interprets drawdown trends, and gives a one-sentence verdict. Use when user says "check my portfolio", "今日检查", "daily check", or any similar daily review request.
---

# HiveFlow 每日持仓健康检查

每天 5 分钟，三步完成：同步数据 → 风险检查 → 给出结论。

## 执行步骤

### Step 1：同步数据

```bash
uv run hiveflow sync
```

同步当天持仓和价格。若已在当天同步过，可跳过。

### Step 2：检查风险

```bash
uv run hiveflow check --output json
uv run hiveflow positions list --output json
```

### Step 3：解读并给出结论

收到 JSON 后，按以下框架分析：

**风险信号解读：**
- 看 `signals` 数组中每个资产的 `max_drawdown_7d_pct`
- 不要只看单日数字——结合趋势：连续下跌比单日大跌更危险
- DANGER（< -20%）：必须提及，建议用户认真考虑是否需要减仓
- WARNING（-10% ~ -20%）：提醒关注，不必恐慌
- NORMAL（> -10%）：简单带过即可

**USDT 弹药检查：**
- 从 `positions list` 的 `free` 数组中找到 USDT 的 `weight`
- weight < 0.10（10%）：标注"弹药不足"，建议考虑增加稳定币缓冲
- weight > 0.40（40%）：可以提示"弹药充足，可考虑择机建仓"

**结论规则：**
- 无任何告警：一句话说安全，不需要废话
- 有 WARNING：点名资产，提示关注
- 有 DANGER：明确说危险，建议启动 portfolio-advisor 做深度分析

**何时建议升级到 portfolio-advisor：**
- 任意资产出现 DANGER 信号
- 用户主动询问"该怎么调仓"
- USDT 占比极低（< 5%）且有多个 WARNING

## 输出格式

简洁明了，不超过 10 行。示例：

```
今日检查完成 2026-03-16

[结论] ✅ 安全，无需操作

持仓：BTC 44.6%  USDT 54.8%  弹药充足
风险：BTC -3.2% 正常  ETH -8.1% 正常
```

或：

```
今日检查完成 2026-03-16

[结论] ⚠️ 建议关注 ETH — 近7日回撤 -14.2%

持仓：BTC 45%  ETH 30%  USDT 10%  ⚠️ 弹药偏低
风险：BTC -3.2% 正常  ETH -14.2% 注意  SOL -5.1% 正常
建议：观察 ETH 走势，若继续下跌考虑启动 portfolio-advisor。
```
