# HiveFlow 重写设计文档

> 状态：已确认
> 日期：2026-03-31
> 适用对象：架构设计、实现计划编写

---

## 1. 背景与目标

### 1.1 重写动机

main 分支在 M1–M9 迭代后出现三个并发问题，权重大致相等：

1. **分层腐化**：Clean Architecture 层间边界模糊，用例与基础设施职责混淆，新功能越来越难加。
2. **数据可靠性**：存在前视数据风险（PIT 纪律缺失）、数据版本管理混乱、回测结果难以复现。
3. **AI 协作契约不稳定**：CLI 输出格式不一致，AI Skill 消费时频繁出错，缺乏机器可校验的 schema 约束。

本次重写为完全推倒重来，main 分支代码仅作参考实现，不迁移。

### 1.2 系统定位

**个人资产决策工具（升级版）**——个人规模、自用，但架构严谨：

- 系统职责：提供可信数据、可追溯因子信号、可执行调仓计划。
- 系统不做：投资判断、策略选择推荐、自动下单（需用户确认）。
- AI/Skill 职责：消费 CLI 输出，做决策推断，提出建议。

### 1.3 核心原则（继承自 ARCHITECTURE.md）

- **先可复现，再追收益**：任何结果必须能用同版本代码 + 数据复算。
- **先安全，再自动化**：执行以风控门控通过为前提。
- **先契约，再扩展**：层间 I/O schema 先定义，再实现。
- **先验证，再上线**：无验证报告的参数变更不得执行。

---

## 2. 资产范围与数据源

### 2.1 资产范围

- **第一版主链路**：A 股（沪深两市，日频）
- **第一版执行适配**：OKX 加密货币保留为 L6 的薄适配接口占位，不要求第一版完整实现
- **扩展路径**：A 股主链路稳定后，加密货币作为第二市场增量接入

### 2.2 数据源

| 优先级 | 数据源 | 用途 |
|--------|--------|------|
| 主力 | 腾讯数跟 | 日频行情、复权、基本面 |
| 降级 | akshare | 腾讯数跟不可用时的兜底 |

降级必须在 `data_manifest.fallback_used=true` 中记录，下游层感知数据来源。

---

## 3. 技术栈

见 `docs/TECH_STACK_DECISION.md`，要点摘录：

- **Python**：L0–L8 与 G1–G3 全部逻辑（pandas + polars 按需 + cvxpy + pytest + ruff + uv）
- **Rust CLI**：命令接口层（clap + serde_json + thiserror），通过 subprocess 调用 Python
- **数据持久化**：Parquet（行情/因子/信号）+ NDJSON append-only（manifest/log）
- **不引入数据库服务**

---

## 4. 整体架构

### 4.1 Python Quant Core 分包结构

```
src/hiveflow/
  l0_universe/    # 标的池（可交易集合过滤：流动性/ST/停牌/上市时长）
  l1_data/        # 数据采集、清洗、PIT 存储
  l2_factor/      # 因子计算
  l3_signal/      # 去极值、中性化、标准化、聚合
  l4_optimize/    # 组合优化（cvxpy）
  l5_risk/        # 风控门控（规则硬拦截）
  l6_execute/     # 执行层（miniQMT 适配 + OKX 薄适配占位）
  l8_monitor/     # 盘中监控 + 日终复盘
  g1_governance/  # data_manifest、PIT 纪律、run_id 管理
  pipeline/       # 日频批处理编排
  cli.py          # Python CLI 入口（python -m hiveflow.cli）
  errors.py       # 统一错误码枚举
```

### 4.2 层间数据流

```
腾讯数跟 / akshare
      ↓
   L1 数据层  ─── G1 governance（PIT + data_manifest）
      ↓
   L2 因子层
      ↓
   L3 信号工程层
      ↓
   L4 组合优化层
      ↓
   L5 风控门控层
      ↓ pass
   L6 执行层（miniQMT 预检 + 用户确认）
      ↓
   L8 监控复盘层 ←── 盘中轻量监控（独立进程）
```

### 4.3 Rust CLI

纯命令接口层，通过 `std::process::Command` 调用 `python -m hiveflow.cli <subcommand>`，透传 stdout/stderr。

职责：参数校验（clap derive）、统一错误码（thiserror 枚举）、JSON schema 输出包装（serde_json）。不承载任何策略逻辑。

---

## 5. 运行模式

### 5.1 日频批处理（主流水线）

收盘后触发，顺序执行：

```
pipeline/daily_run.py
  │
  ├─ Step 1  L1: 拉取今日行情 → Parquet 落盘 → 生成 data_manifest → 记录 run_id
  ├─ Step 2  L2: 计算因子矩阵（as_of=今日，引用 data_manifest）
  ├─ Step 3  L3: 因子标准化（去极值 → 缺失处理 → 行业中性化 → zscore）
  ├─ Step 4  L4: 组合优化（输出目标权重 + 求解状态）
  ├─ Step 5  L5: 风控门控（pass → 继续，block → 记录原因终止）
  ├─ Step 6  L6: 生成执行计划（预检流动性/涨跌停/资金，输出调仓清单 JSON）
  └─ Step 7  L8: 落库本次运行记录（run_id + 权重快照 + 风控状态）
```

每步失败立即终止并写入错误码，不做静默降级。

### 5.2 盘中轻量监控（独立进程，L8）

- 默认每 30 分钟轮询一次
- 检查：实际持仓 vs 目标权重偏离度、风控信号变化
- 触发条件满足时写入 `data/alerts/`（JSON），AI Skill 轮询读取

---

## 6. 层间契约规范

### 6.1 公共字段（所有层输出必须包含）

```python
{
  "schema_version": "1.0.0",      # 破坏性变更升主版本
  "generated_at": "<ISO-8601>",   # 生产时间
  "producer_version": "<semver>", # 代码版本
  "run_id": "<uuid>",             # 全链路追踪 ID
  "as_of": "<YYYY-MM-DD>",        # 业务时间点（PIT 锚点）
  "data_manifest_id": "<id>"      # 引用的数据版本
}
```

### 6.2 各层契约要点

| 契约 | 关键字段 | PIT 约束 |
|------|---------|---------|
| L1 输出 | `symbols`、`close`、`volume`、`adj_factor`、`effective_date` | 只包含 `effective_date <= as_of` 的数据 |
| L2 输出 | `factor_name`、`factor_version`、`raw_value`、`coverage_rate` | 因子窗口数据只用 `as_of` 之前 |
| L3 输出 | `signal_value`、`neutralized`、`coverage_rate`、`ic_lag1` | 继承 L2 的 `as_of` |
| L4 输出 | `target_weights`、`solver_status`、`fallback_flag` | `fallback_flag=true` 时必须记录原因 |
| L5 输出 | `gate_result: pass/block`、`block_reason`、`evidence_snapshot` | block 时必须输出完整证据快照 |
| L6 输出 | `execution_plan`、`pre_check_result`、`estimated_cost` | 涨跌停/流动性预检结果必须记录 |

### 6.3 G1 data_manifest 结构

```json
{
  "manifest_id": "dm_20260401_run001",
  "run_id": "run_20260401_001",
  "as_of": "2026-04-01",
  "data_source": "tengxun_shuge",
  "fallback_used": false,
  "symbols_count": 487,
  "hash": "<sha256 of raw data files>",
  "created_at": "2026-04-01T16:30:00+08:00"
}
```

规则：
- 每次 L1 落盘后生成，后续各层只能引用已存在的 `manifest_id`
- 禁止跨 `manifest_id` 混用数据
- `hash` 覆盖原始数据文件，支持篡改检测

### 6.4 L4 Fallback 优先级

1. 维持上期权重（最常用）
2. 当前 universe 等权分配
3. 全仓现金（极端情况，必须写告警）

每次 fallback 写入 `run_id` 对应审计日志。

---

## 7. 错误处理

### 7.1 原则：严格模式，不静默降级

| 场景 | 错误码 | 行为 |
|------|--------|------|
| L1 数据拉取失败 | `DATA_FETCH_FAILED` | 终止流水线 |
| 数据源降级（主 → akshare） | — | 允许，`fallback_used=true` 记录，继续 |
| 因子覆盖率低于阈值（<80%） | `LOW_COVERAGE` | 写警告，继续，L6 输出中标注 |
| L4 求解失败 | `SOLVER_FALLBACK` | 触发 fallback 规则，不终止 |
| L5 block | `RISK_GATE_BLOCKED` | 终止执行计划生成，输出证据快照 |
| L6 预检失败 | `EXECUTION_PRECHECK_FAILED` | 输出可执行子集或整体拒绝 |

### 7.2 错误码统一管理

- Python：`hiveflow/errors.py` 集中枚举
- Rust：`thiserror` 镜像同一套枚举
- CLI 输出中错误码出现在 `errors[]` 数组，格式遵循 `CLI_OUTPUT_SCHEMA.json`

---

## 8. 测试策略

### 8.1 三层测试

**单元测试（pytest）**
- 每层核心计算逻辑独立测试，使用固定 fixture Parquet，不请求外部接口
- PIT 纪律测试：断言因子窗口不含 `as_of` 之后的数据
- L5 规则测试：各 block 条件的边界值覆盖

**集成测试（pytest + 本地 Parquet fixture）**
- 跑通 L1→L5 完整链路
- 验证 `run_id` / `data_manifest_id` 全链路传递一致
- 验证 L4 fallback 路径可触发且有审计记录

**契约测试（make validate-cli-output）**
- 所有 CLI 命令输出符合 `CLI_OUTPUT_SCHEMA.json`
- valid / invalid fixture 各一批，CI 必过

### 8.2 CI 检查项

```bash
uv run python -m pytest -q          # 全量测试
uv run ruff check .                  # lint
make validate-cli-output             # CLI 契约校验
cargo test                           # Rust CLI 测试
```

### 8.3 不做的事

- 不 mock 数据库（无数据库）
- 不 mock 外部数据源（用 fixture Parquet 代替）
- 不写负载测试

---

## 9. 薄切片 MVP（第一个里程碑）

目标：**用真实数据跑通一次完整日频流水线，输出可执行调仓清单 JSON，全程无前视数据，结果可用 `run_id` 复现。**

| 层 | MVP 实现深度 |
|----|-------------|
| G1 | data_manifest 生成与引用，run_id 全链路传递 |
| L0 | 静态规则过滤（排除 ST/停牌/上市不足 60 日），输出可交易标的列表 |
| L1 | 拉取日频行情（复权），Parquet 落盘，PIT 分区 |
| L2 | 3 个基础因子：动量（20日）、波动率倒数、换手率 |
| L3 | 去极值（winsorize）+ zscore，暂不做行业中性化 |
| L4 | 风险平价（不用 cvxpy），cvxpy 在 MVP 后引入 |
| L5 | 单资产上限 + 最大回撤两条硬规则 |
| L6 | 输出调仓清单 JSON，miniQMT 推送接口占位 |
| L8 | 落库 run_id + 权重快照 |

MVP 不要求盘中监控、行业中性化、完整因子库、cvxpy 优化、OKX 执行。

---

## 10. 非目标（明确不做）

- 不做加密货币主链路（OKX 仅 L6 薄适配占位）
- 不做分钟/小时级高频流水线
- 不做 AI 自动下单（用户确认是硬性流程）
- 不做无审计的黑盒参数自动生效
- 不做 main 分支代码迁移（完全重写）
- 不引入数据库服务（SQLite / PostgreSQL 等）
