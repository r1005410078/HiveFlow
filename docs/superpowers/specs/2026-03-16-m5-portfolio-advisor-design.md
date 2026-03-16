# M5 Portfolio Advisor + 调仓执行闭环

**日期**：2026-03-16
**状态**：已通过用户确认

---

## 背景

M4 完成了 `hiveflow sync` + `hiveflow check`，用户现在可以每天看到持仓风险信号。但系统还缺两个关键能力：

1. **从"看到问题"到"知道怎么动"**：check 告诉你有回撤，但不告诉你该怎么调仓
2. **从"建议"到"执行"**：调仓建议需要用户手动去 OKX 操作，缺少闭环

M5 的目标是打通这两个缺口，同时引入智能分析层（Skill），让 Claude 作为有投资知识的分析师来辅助决策。

---

## 架构设计

```
用户
 │
 ▼
Claude Agent
 ├── hiveflow-daily-check Skill     ← 每天（5 分钟）
 │    └── hiveflow sync / check --output json
 │
 └── hiveflow-portfolio-advisor Skill  ← 需要做决策时
      ├── hiveflow backtest run / list --output json
      ├── hiveflow targets set-from-backtest
      ├── hiveflow rebalance preview --output json
      └── hiveflow trade execute（用户 confirm 后）
           └── OKX 市价单
```

**核心原则**：
- HiveFlow = 数据层 + 执行层（确定性、可测试、纯 CLI）
- Skill = 分析逻辑 + 投资框架 + 工作流提示词（写给 Claude 读的）
- 智能判断在 Skill 里，不在 HiveFlow 代码里

---

## 能力一：网格持仓区分

### 问题

当前 `sync` 从 `/api/v5/account/balance` 拉取所有现货资产，包括锁在网格机器人里的资产。网格持仓不应被 rebalance 计算，但目前无法区分。

### 设计

新增 `GridPosition` domain 模型，`sync` 额外调用 OKX 网格接口。

**OKX 接口**：`GET /api/v5/tradingBot/grid/positions`（需要 Read 权限）

**数据模型**：
```
GridPosition
  symbol: str          # 资产名（BTC）
  grid_id: str         # 网格机器人 ID
  inst_id: str         # 交易对（BTC-USDT）
  quantity: float      # 持有数量
  market_value: float  # 市值（USDT）
  state: str           # 运行状态（running / stopped）
```

**`positions list` 输出**：

```
:: 自由持仓 ::
  BTC    0.000439   692.78   44.62%
  USDT   250.00     850.17   54.76%

:: 网格持仓（不参与调仓计算）::
  ETH    0.5   网格 #001  BTC-USDT  运行中
  SOL    2.0   网格 #002  SOL-USDT  运行中
```

**rebalance preview** 只使用自由持仓计算偏离，网格持仓展示但不干预。

---

## 能力二：`backtest run` 从 DB 读行情

### 问题

当前 `backtest run --strategy X --file data.csv` 要求 CSV 文件。用户已通过 `hiveflow sync --days` 在 DB 里积累了行情数据，应可直接使用。

### 设计

`--file` 变为可选参数：

```bash
hiveflow backtest run --strategy X           # 从 DB 的 MarketBar 表读行情
hiveflow backtest run --strategy X --file f  # 从 CSV 读（保留，兼容测试/其他平台）
```

从 DB 读时，按持仓中的所有 symbol 自动拉取 `MarketBar` 数据，时间范围取 DB 中最早到最新。

---

## 能力三：`targets set-from-backtest`

将选定回测的目标配比写入 `Target` 表，供 `rebalance preview` 使用。

```bash
hiveflow targets set-from-backtest <backtest_id>
```

输出确认信息：
```
已设置目标配比（来自回测 #3，2026-03-15）：
  BTC   40%
  ETH   30%
  SOL   20%
  USDT  10%
```

---

## 能力四：`hiveflow trade execute`

### 设计原则

- 只执行现货市价单，不做合约/网格
- 执行前打印完整订单列表，用户输入 `confirm` 才提交
- 需要 Trade 权限的 OKX API Key（与现有 Read Key 分开配置）
- 全成功或全失败，任一订单失败不继续执行剩余订单

### 配置

```
HIVEFLOW_OKX_TRADE_API_KEY=xxx
HIVEFLOW_OKX_TRADE_API_SECRET=xxx
HIVEFLOW_OKX_TRADE_PASSPHRASE=xxx
```

### 接口

```bash
hiveflow trade execute --orders '[{"symbol":"BTC","action":"buy","usdt":500},{"symbol":"ETH","action":"sell","usdt":200}]'
```

### 输出流程

```
待执行订单：
  买入 BTC  500 USDT（市价）
  卖出 ETH  200 USDT（市价）

输入 confirm 确认执行，其他任意键取消：> confirm

执行中...
  ✅ 买入 BTC  500 USDT → 订单 ID: 123456
  ✅ 卖出 ETH  200 USDT → 订单 ID: 123457

执行完成。
```

### 错误处理

- 余额不足 → 打印错误，退出码 1，不执行任何订单
- 网络超时 → 打印错误，建议手动检查 OKX 订单状态
- 鉴权失败 → 检查 Trade API Key 配置

---

## 能力五：`hiveflow-daily-check` Skill

每日轻量工作流，5 分钟完成。

**工作流**：
```
1. hiveflow sync
2. hiveflow check --output json
3. 解读风险信号
4. 给出今日一句话结论
5. 必要时建议启动 portfolio-advisor
```

**Skill 提示词方向**：
- 回撤不只看单日数字，结合趋势（连续下跌 vs 单日波动）
- USDT 占比低于 10% 时标注"弹药不足"
- 有任何 DANGER 信号时，主动建议启动 portfolio-advisor

---

## 能力六：`hiveflow-portfolio-advisor` Skill

深度决策工作流，需要调仓时使用。

**工作流**：
```
1. 根据自由持仓资产，生成候选配比（激进/均衡/保守）
2. hiveflow backtest run（对每个候选配比）
3. 展示回测指标 + 推荐配比（说明推荐理由）
4. 用户选定配比
5. hiveflow targets set-from-backtest <id>
6. hiveflow rebalance preview --output json
7. 生成调仓报告 + 订单列表
8. 用户确认
9. hiveflow trade execute
```

**候选配比生成规则**（写进 Skill）：
- USDT 最低 10%（弹药底线）
- 单资产上限 60%（不过度集中）
- 激进版：BTC/ETH 主导，USDT 10%
- 均衡版：多资产分散，USDT 20%
- 保守版：USDT 40%+，其余均分

**投资理论框架**（写进 Skill）：

1. **风险调整收益**：不只看涨幅，看夏普比率——同样收益，波动更小的配比更优

2. **回撤优先**：加密市场暴跌常见，最大回撤是选配比的第一过滤条件。回撤超过 30% 的配比需要明确说明风险

3. **USDT 是弹药**：保留稳定币不是保守，是保留机会和应对波动的能力

4. **分散但不稀释**：3-5 个资产比 10 个更容易管理，持仓太多等于没有选择

5. **帮用户校准风险偏好**：每次分析后询问用户对结果的感受（"这个配比的最大回撤你能接受吗？"），逐渐帮用户建立自己的投资风格

6. **其他策略的适用场景**（教育性）：
   - 动量策略：强势市场中表现好
   - 均值回归：震荡市场中表现好
   - 网格交易：横盘震荡适用，当前系统不执行但可以建议
   - 合约：高风险，不在当前系统范围内

---

## 不在 M5 范围

- 自定义策略 DSL（动量、均值回归、风险平价规则化）→ M6
- 网格机器人创建/管理 → M6+
- 合约交易 → M6+
- 多交易所支持 → M6+
- 定时自动调仓 → M6+

---

## 测试策略

- `GridPosition` 同步：mock OKX 网格接口，验证写入和区分逻辑
- `backtest run` 从 DB：集成测试，验证从 `MarketBar` 读取并正确回测
- `targets set-from-backtest`：验证配比写入 Target 表
- `trade execute`：mock OKX 下单接口，验证确认流程和全成功/全失败原子性
- Skill 文件：不做自动化测试，通过实际使用验证
