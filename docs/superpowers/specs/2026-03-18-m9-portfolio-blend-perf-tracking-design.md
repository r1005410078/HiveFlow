# M9 设计文档：多策略混合 + 实盘绩效追踪

**日期**：2026-03-18
**阶段**：M9
**状态**：已审核

---

## 背景

M9 在已完成的 M6（量化策略管理）、M7（回测权益曲线可视化）、M8（风险分析引擎）基础上，
交付两个紧密关联的能力：

1. **多策略混合**（`portfolio blend`）：把多个量化策略的输出加权混合，生成统一目标配比
2. **实盘绩效追踪**（`perf`）：定时快照实际持仓价值，与回测权益曲线对比

两者形成完整链路：`blend 生成目标 → trade execute → perf 追踪 → perf compare 对比`

---

## 整体架构

### 数据流

```
quant run (StrategyRun × N)
    ↓
quant blend run <name> → 混合权重 → [--apply] → TargetAllocation
    ↓
trade execute
    ↓
perf snapshot (定时/手动) → PortfolioSnapshot 落库
    ↓
perf compare <backtest_id> → Sparkline 对比 + 指标
```

### 命令结构

```
# Part 1: 多策略混合
hiveflow quant blend create <name> --strategies s1,s2,s3 [--weights 0.4,0.3,0.3]
hiveflow quant blend run <name> [--apply]
hiveflow quant blend list
hiveflow quant blend show <name>

# Part 2: 实盘绩效追踪
hiveflow perf snapshot              # 手动触发一次快照
hiveflow perf list                  # 列出历史快照
hiveflow perf compare <backtest_id> # 实盘 vs 回测 Sparkline + 指标
hiveflow perf setup-cron            # 读取配置文件，安装 cron job
```

---

## 数据模型

### `BlendConfig`（新表）

```python
class BlendConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str                    # 唯一名称
    strategy_names: str          # JSON list，如 ["momentum", "equal_weight"]
    weights: str                 # JSON dict，如 {"momentum": 0.6, "equal_weight": 0.4}
    auto_optimized: bool         # 权重是否由系统自动计算
    optimize_metric: str         # "sharpe" | "calmar" | "return"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### `PortfolioSnapshot`（新表）

```python
class PortfolioSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_value_usd: float       # 总持仓价值（USD）
    positions_json: str          # 持仓快照（JSON）
    source: str                  # "manual" | "cron"
    notes: Optional[str] = None
```

---

## 功能设计

### 多策略混合

**创建 blend 配置**

- `--strategies`：指定参与混合的策略名称（对应 `quant run` 中的策略名）
- `--weights`：可选，手动指定各策略权重（需归一化为 1.0）
- 未指定 `--weights` 时，`auto_optimized=True`，权重在 `blend run` 时计算

**自动权重优化逻辑**

基于各策略最近一次 `BacktestResult` 的指标，无新增第三方依赖：

| `optimize_metric` | 计算方式 |
|---|---|
| `sharpe` | 各策略回测 Sharpe 值归一化（默认） |
| `calmar` | 各策略回测 Calmar ratio 归一化 |
| `return` | 各策略回测总收益率归一化 |

若某策略没有 `BacktestResult`，退回等权分配。

**`blend run` 输出**

读取各策略最新 `StrategyRun` 的 `result_json`（权重字典），按 blend 权重加权平均，
输出混合后的资产权重字典。`--apply` 写入 `TargetAllocation`（复用 `quant run --apply` 逻辑）。

### 实盘绩效追踪

**快照机制**

`perf snapshot` 执行：
1. 从 OKX 同步最新持仓（复用 `positions list` 逻辑）
2. 从 `market-data` 取各资产最新价格
3. 计算总持仓价值（USD），落库 `PortfolioSnapshot`

**定时配置**（`config/tracking.json`）

```json
{
  "snapshot_interval": "1h",
  "auto_sync_positions": true
}
```

支持 `1h` / `6h` / `daily` 三档。`perf setup-cron` 读取此文件，向系统 `crontab` 写入：

```
0 * * * * cd /path/to/project && uv run hiveflow perf snapshot --source cron
```

**`perf compare <backtest_id>`**

从 `PortfolioSnapshot` 序列派生实盘权益曲线，与 `BacktestResult.equity_curve` 对比：

- 终端输出：两条 Sparkline 并排（复用 M7 的 `_sparkline()`）
- 对比指标：总收益率、年化收益率、最大回撤（MDD）
- `--output json` 输出结构化数据供 Agent 使用

---

## 实现边界

| 做 | 不做 |
|---|---|
| blend 权重计算（手动 + 自动优化） | 策略参数调优 |
| PortfolioSnapshot 落库 | 实时推送/告警 |
| `perf compare` Sparkline + 指标 | 多账户支持 |
| cron 安装（系统 crontab） | Web UI |
| `--output json` 全覆盖 | 多交易所支持 |

---

## 测试策略

遵循 TDD，先写测试再实现：

1. `BlendConfig` CRUD + 权重归一化验证
2. 自动优化：给定 mock `StrategyRun` + `BacktestResult`，验证权重计算结果
3. 手动权重：验证归一化检查与错误提示
4. `PortfolioSnapshot` 落库与查询
5. `perf compare`：mock 两条 equity_curve，验证 Sparkline 输出与指标计算
6. `perf setup-cron`：验证生成的 crontab 字符串格式正确（不实际写入 crontab）

---

## 交付顺序

### Phase 1：portfolio blend（先交付）
- `BlendConfig` 实体 + 仓储
- `quant blend create / run / list / show`
- 自动权重优化（sharpe / calmar / return）
- `--apply` 写入 TargetAllocation
- 测试 + 文档

### Phase 2：实盘绩效追踪（后交付）
- `PortfolioSnapshot` 实体 + 仓储
- `perf snapshot / list`
- `config/tracking.json` + `perf setup-cron`
- `perf compare` Sparkline + 指标
- 测试 + 文档
