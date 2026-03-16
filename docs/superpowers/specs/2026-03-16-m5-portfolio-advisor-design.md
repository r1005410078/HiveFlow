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

**Skill 文件位置**：`~/.agents/skills/hiveflow-daily-check/` 和 `~/.agents/skills/hiveflow-portfolio-advisor/`，Markdown 格式，与现有 Skill 规范保持一致。

---

## 能力一：网格持仓区分

### 问题

当前 `sync` 从 `/api/v5/account/balance` 拉取所有现货资产，包括锁在网格机器人里的资产。网格持仓不应被 rebalance 计算，但目前无法区分。

### 数据模型

新增 `GridPosition` SQLModel 表（持久化），`sync` 每次全量清除再写入（与 `Position` 行为一致）：

```python
class GridPosition(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str        # 资产名（BTC）
    grid_id: str       # 网格机器人 ID
    inst_id: str       # 交易对（BTC-USDT）
    quantity: float    # 持有数量
    market_value: float  # 市值（USDT）
    state: str         # running / stopped
    synced_at: datetime = Field(default_factory=utc_now)
```

### OKX 接口

`GET /api/v5/tradingBot/grid/positions?instType=SPOT`（需要 Read 权限，仅查现货网格，不含合约网格）。若用户没有网格持仓，返回空列表，正常写入空数据。

### `positions list` 修改

现有命令新增第二区块，`rebalance preview` 读取 `Position` 表（自由持仓），不读 `GridPosition`：

```
:: 自由持仓 ::
  标的     数量        市值      权重
  BTC    0.000439   692.78   44.62%
  USDT   250.00     850.17   54.76%

:: 网格持仓（不参与调仓计算）::
  标的   数量   网格 ID   交易对      状态
  ETH    0.5    001      BTC-USDT   运行中
  SOL    2.0    002      SOL-USDT   运行中
```

若无网格持仓，不显示第二区块。

### JSON 输出

```json
{
  "free": [{"symbol": "BTC", "quantity": 0.000439, "market_value": 692.78, "weight": 0.4462}],
  "grid": [{"symbol": "ETH", "quantity": 0.5, "grid_id": "001", "inst_id": "BTC-USDT", "state": "running"}]
}
```

---

## 能力二：`backtest run` 从 DB 读行情

### 设计

`--file` 变为可选参数。`BacktestResult` 新增两个字段：

```python
prices_source: str   # "DB:MarketBar" 或 CSV 文件路径（替代原 prices_file，nullable=False，默认 "DB:MarketBar"）
weights_snapshot: str  # JSON 字符串，存储回测使用的配比，如 '{"BTC":0.4,"ETH":0.3,"USDT":0.3}'
```

原 `prices_file` 字段迁移为 `prices_source`，含义扩展：CSV 路径或哨兵值 `"DB:MarketBar"`。

```bash
hiveflow backtest run --strategy X           # 从 DB 的 MarketBar 表读行情
hiveflow backtest run --strategy X --file f  # 从 CSV 读（保留，兼容测试/其他平台）
```

**DB 行情的 symbol 范围**：取该策略 `TargetAllocation` 中所有 symbol（不用当前持仓），时间范围取这些 symbol 在 `MarketBar` 中的最早到最新交集。若某个 symbol 无 MarketBar 数据，打印警告并跳过该 symbol。

---

## 能力三：`targets set-from-backtest`

从 `BacktestResult.weights_snapshot` 读取配比，写入 `TargetAllocation` 表。

```bash
hiveflow targets set-from-backtest <backtest_id>
```

`weights_snapshot` 存储了回测时的精确配比，不依赖当前 `TargetAllocation` 状态，避免配比已变更导致语义错误。

输出：
```
已设置目标配比（来自回测 #3，夏普 1.42，最大回撤 -18.3%，2026-03-15）：
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
- 全成功或全失败：**提交前**做余额预检，余额不足则拒绝，不提交任何订单；**提交后**若部分成功部分失败，打印每笔订单的状态和 OKX 订单 ID，提示用户手动处理失败订单
- 需要 Trade 权限的 OKX API Key（与现有 Read Key 分开配置）

### 配置（新增至 Settings）

```python
okx_trade_api_key: str | None = None
okx_trade_api_secret: str | None = None
okx_trade_passphrase: str | None = None
```

环境变量：`HIVEFLOW_OKX_TRADE_API_KEY` / `_SECRET` / `_PASSPHRASE`

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
  ❌ 卖出 ETH  200 USDT → 失败：余额不足

⚠️  部分订单失败，请在 OKX 手动确认账户状态。成功订单 ID：123456
```

### 错误处理

| 场景 | 行为 |
|---|---|
| 余额不足（提交前预检） | 打印错误，退出码 1，不提交任何订单 |
| Trade API Key 未配置 | 提示配置方法，退出码 1 |
| 鉴权失败 | 检查 Trade API Key，退出码 1 |
| 网络超时 | 打印错误，建议手动检查 OKX 订单状态 |
| 部分订单提交后失败 | 打印每笔状态 + 订单 ID，退出码 1，提示手动处理 |

---

## 能力五：`hiveflow-daily-check` Skill

每日轻量工作流，5 分钟完成。

**工作流**：
```
1. hiveflow sync
2. hiveflow check --output json
3. hiveflow positions list --output json（看 USDT 弹药占比）
4. 解读风险信号
5. 给出今日一句话结论
6. 必要时建议启动 portfolio-advisor
```

**Skill 提示词方向**：
- 回撤不只看单日数字，结合趋势（连续下跌 vs 单日波动）
- USDT 占比低于 10% 时标注"弹药不足"，建议减少风险敞口
- 有任何 DANGER 信号时，主动建议启动 portfolio-advisor

---

## 能力六：`hiveflow-portfolio-advisor` Skill

深度决策工作流，需要调仓时使用。

**工作流**：
```
1. hiveflow positions list --output json（获取自由持仓资产列表）
2. 根据持仓资产生成三组候选配比（激进/均衡/保守），写入三个临时策略
   → hiveflow targets import（每个配比对应一个策略名）
3. hiveflow backtest run --strategy <名称>（对每个候选配比分别运行）
4. hiveflow backtest list --output json（获取完整指标）
5. 展示回测指标对比 + 推荐配比（说明推荐理由）
6. 用户选定配比
7. hiveflow targets set-from-backtest <id>
8. hiveflow rebalance preview --output json
9. 生成调仓报告 + 订单列表
10. 用户确认
11. hiveflow trade execute
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

- `GridPosition` 同步：mock OKX 网格接口，验证写入、全量清除、无网格时空列表处理
- `backtest run` 从 DB：集成测试，验证从 `MarketBar` 读取、symbol 范围取 TargetAllocation、缺数据时警告并跳过
- `targets set-from-backtest`：验证从 `weights_snapshot` 读配比并写入 Target 表
- `trade execute`：mock OKX 下单接口，覆盖：余额预检失败、全成功、提交后部分失败三个路径
- Skill 文件：不做自动化测试，通过实际使用验证
