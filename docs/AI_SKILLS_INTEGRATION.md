# HiveFlow AI 集成方案（军师模型）

> AI 扮演军师角色：解读行情、解读数据、建议决策。主公拍板，令旗不在军师手里。
> 核心原则：系统提供数据，AI 推断判断，人做最终决策。
> 文档导航：`DOCUMENTATION_INDEX.md`
> 文档目标：定义 AI 与量化系统解耦协作规则。适用对象：AI/Agent 开发、策略研发、风控与审计。

## 快速目录

1. AI 角色定位
2. 总体架构
3. 数据架构
4. 触发机制
5. 决策报告格式
6. AI 完整职责范围
7. Skill 设计
8. CLI 交互契约
9. 与分层架构的映射
10. 安全与审计
11. 完整运行流程
12. 非目标
13. 一句话原则

---

## 1. AI 角色定位

**军师，不是指挥官。**

- AI 负责：读懂战局、分析情景、给出带期望价值的决策建议
- 人负责：听取建议，拍板决策
- 系统负责：执行规则、控制风险、留下审计

AI 永远不在执行链路上。L5 风控说过就过，AI 的判断不能阻断或放行任何交易。

### 1.1 硬规则速览

- AI 只通过 Skills 调用白名单 CLI，不直连交易网关/数据库。
- `web_search` 固定为情报分支：`advice_only=true`、`decision_weight=0`。
- 主决策分支只用 `system/news_system`，且需可审计快照。
- AI 只给建议，不自动生效；任何实盘变更都走 G3 审批。
- 所有输出遵循 `CLI_OUTPUT_SCHEMA.json`，并通过脚本校验。

### 1.2 术语约定（统一写法）

- 告警事件：`alert`（不再混用“告警文件/告警消息”）
- 主决策分支：`system + news_system`（不再简写“主分支”）
- 情报分支：`web_search`（仅解释，不入主公式）
- 变更提案：`proposal`（提交审批流的唯一对象）
- 决策历史日志：`decision_log`（append-only NDJSON）
- 数据版本清单：`data_manifest`（研究/回测/执行统一引用）

---

## 2. 总体架构

```text
外部数据系统（新闻/宏观）─┐
Agent 浏览器检索（降级）──┤
                          ▼
Quant Core（L0~L8）──► 数据汇聚层
  └─ L8 监控层检测到触发信号
      └─ 写入告警事件（alert）
          └─ AI Runtime 读取告警事件
              └─ Skills（调用 CLI + 外部数据）
                  └─ AI 生成决策报告 → 通知用户
                                          └─ 用户拍板
                                              └─ G3 审批 → 系统执行
```

职责划分：

- **Quant Core**：执行规则，产生信号，写告警事件（`alert`）。
- **外部数据系统**：提供新闻、公告、宏观事件（结构化）。进入主决策分支时必须具备可审计快照（L1/G1 或等价 `data_manifest`）。
- **Agent 浏览器检索**：外部数据系统无数据时兜底，标注来源。
- **Skills**：收到告警事件后调用 CLI + 外部数据，组装完整上下文。
- **AI Runtime**：综合系统数据与外部事件，推断情景概率，生成决策树报告。
- **用户**：阅读报告，做最终决策。
- **G3**：审批变更，执行落地。

---

## 3. 数据架构

决策树输入分为“主决策分支”与“情报分支”：

```
决策树输入
  ├─ 主决策分支（可执行）
  │   ├─ 系统信号（L2/L3，CLI 提供）      source: system        可审计
  │   └─ 结构化外部数据（独立新闻系统）    source: news_system   可审计
  └─ 情报分支（解释辅助）
      └─ Agent 检索（降级兜底）           source: web_search    不可审计，标注
```

### 外部数据系统

- 独立部署，不与 Quant Core 耦合
- AI 可直接读取外部数据系统用于“情报分支”解释；
- 若要进入“主决策分支”或用于历史回测，必须先落入可审计数据快照（L1/G1 或等价 `data_manifest`）
- 强制记录时间戳：
  - `event_timestamp`：事件发生时间
  - `publish_timestamp`：公开发布时间
  - `effective_timestamp`：策略可使用时间
- 覆盖：财经新闻、上市公司公告、宏观政策事件

### Agent 浏览器检索（降级）

- 触发条件：外部数据系统无对应事件数据
- 检索结果标注 `source: web_search, unverified`
- 默认 `advice_only=true`，`decision_weight=0`
- 仅用于解释与风险提示，不参与主决策分支期望价值计算
- 需二次验证（官方公告/权威媒体）后，才可人工升级为主决策分支证据
- 若情报分支与主决策分支冲突，默认主决策分支优先
- 不进入 G1 数据治理链路

---

## 4. 触发机制

AI 由系统信号主动触发，用户无需每天主动查询。

### 触发优先级

**P0 — 立即通知**

| 触发条件 | 说明 |
|----------|------|
| 市场进入高波动 regime | 整体风险环境变化，所有决策前提改变 |
| 策略信号从正转负 | 直接影响当前持仓方向 |

**P1 — 次日通知**

| 触发条件 | 说明 |
|----------|------|
| 因子 IC 持续下滑 | 策略慢性失效，军师主动发起因子选择评估 |
| 因子间相关性突破阈值 | 现有因子出现冗余，建议替换候选 |

**P2 — 定期汇总**

| 触发条件 | 说明 |
|----------|------|
| 持仓偏离目标配置 | 再平衡参考 |
| 实盘 vs 回测偏差扩大 | 执行质量监控 |

### 触发实现

L8 监控层检测到上述条件时，写入本地结构化告警事件（`alert`），AI 轮询读取并触发对应 Skill。

```json
{
  "alert_id": "alt_20260401_001",
  "priority": "P0",
  "trigger": "signal_flip",
  "subject": "策略A信号从正转负",
  "as_of": "2026-04-01",
  "data_manifest": "dm_20260401"
}
```

---

## 5. 决策报告格式

每次触发后，AI 输出一份“情景概率 × 期望价值”报告，固定包含以下 6 个部分：

1. 触发上下文：`trigger`、`as_of`、`data_manifest`
2. 主决策分支：仅 `system/news_system` 数据参与主公式
3. 情报分支：`web_search` 仅作备注（`advice_only=true`、`decision_weight=0`）
4. 动作候选：至少包含“基准动作 + 两个备选动作”
5. 期望价值：列出每个动作的公式与结果
6. 来源与置信度：明确数据来源、AI 置信度、不确定性声明

最小模板（示意）：

```text
触发：signal_flip | as_of: 2026-04-01 | data_manifest: dm_20260401
主决策分支：system + news_system（进入期望价值公式）
情报分支：web_search（仅备注，不入主公式）
候选动作：持仓不动 / 减仓50% / 全部清仓
建议：减仓50%（EV +4.0%）| 置信度：0.67
来源：system(auditable), news_system(auditable), web_search(unverified, advice_only)
```

---

## 6. AI 完整职责范围

四类职责（按优先级）：

1. 触发驱动  
- 触发：regime 切换、信号翻转、因子衰减/冗余  
- 输出：决策树报告或因子处置建议（留用/降权/退役）

2. 研究助手  
- 任务：回测解读、策略对比、参数敏感性、regime 表现  
- 典型命令：`hf backtest run`、`hf validate walk-forward`

3. 市场解读  
- 任务：把宏观/公告事件转为“情景节点”  
- 规则：外部结构化数据优先，`web_search` 仅降级备注

4. 复盘诊断  
- 任务：实盘 vs 回测偏差归因、风控误报漏报、执行偏差追踪  
- 输出：诊断结论 + 建议动作（不自动生效）

---

## 7. Skill 设计

### Skill 路由矩阵（运行手册）

| 触发类型 | 入口 Skill | 执行 Skill | 主要命令 | 标准输出 |
|---|---|---|---|---|
| 交易/持仓类（P0/P2） | `signal-watcher` | `strategy-advisor` | `hf signal snapshot`, `hf factor health`, `hf backtest summary`, `hf monitor snapshot` | 决策树报告（建议动作 + EV + 置信度） |
| 因子类（P1） | `signal-watcher` | `research-assistant` | `hf factor health`, `hf factor correlation`, `hf validate walk-forward` | 因子处置建议（留用/降权/退役） |
| 复盘类 | `signal-watcher` | `strategy-diagnosis` | `hf attribution diff-live-vs-backtest`, `hf attribution summary` | 偏差归因报告 + 建议动作 |
| 风控类 | `signal-watcher` | `risk-monitor` | `hf monitor risk-events` | 误报漏报分析 + 阈值重标定建议 |
| 外部事件补充 | `strategy-advisor` | `market-interpreter`（内部调用） | 外部数据系统优先，必要时降级 `web_search` | 情报节点（`advice_only=true`, `decision_weight=0`） |

### Skill 执行规则

- 只允许调用白名单命令。
- 只允许使用显式参数，不允许隐式默认关键参数。
- 每一步命令与结果写入 `run log`。
- 报告必须包含：结论、证据（数据来源引用）、AI 置信度、下一步建议。
- AI 概率推断必须标注"基于 AI 推理，非精确计算"。
- 外部检索数据必须标注来源与可信度。

---

## 8. CLI 交互契约

### 输入契约

每个命令支持：

- `--as-of`：业务时间点（防止时间错位）
- `--config-version`：参数版本
- `--data-manifest`：数据版本引用（对齐 G1）
- `--run-id`：任务唯一标识（审计串联）
- `--output json`：机器可解析输出

### 输出契约

```json
{
  "schema_version": "1.0.0",
  "command": "hf signal snapshot",
  "run_id": "run_20260401_001",
  "status": "ok",
  "generated_at": "2026-04-01T09:00:00+08:00",
  "source": "system|news_system|web_search",
  "advice_only": false,
  "decision_weight": 1.0,
  "data": {},
  "warnings": [],
  "errors": []
}
```

- `status` 仅允许 `ok|warning|error`
- 失败必须返回可分类错误码（如 `DATA_NOT_READY`、`RISK_GATE_BLOCKED`）
- 输出超过 50KB 时默认返回摘要，完整数据需 `--full-output` 显式请求
- `advice_only` 与 `decision_weight` 仅用于决策树输入语义：
  - 主决策分支（`system/news_system`）：`advice_only=false`，`decision_weight=1.0`
  - 情报分支（`web_search`）：`advice_only=true`，`decision_weight=0`
- 机器校验标准文件：`CLI_OUTPUT_SCHEMA.json`
- 示例文件：`CLI_OUTPUT_EXAMPLES.md`
- 本地/CI 校验脚本：`scripts/validate_cli_output.sh`
- 一键批量校验：`make validate-cli-output`

### CLI 权限分层

| 类型 | 命令 | AI 是否可调用 |
|------|------|--------------|
| 查询/研究 | `hf signal snapshot`、`hf factor health`、`hf factor correlation`、`hf backtest run`、`hf backtest summary`、`hf monitor snapshot`、`hf monitor risk-events`、`hf attribution summary`、`hf attribution diff-live-vs-backtest`、`hf universe snapshot`、`hf validate walk-forward` | 可以 |
| 建议生成 | `hf propose constraint-tuning`、`hf propose factor-retire` | 可以，不直接生效 |
| 交易/高风险 | 下单、撤单、阈值生效、上线发布 | 禁止 |

补充规则：

- 白名单必须按“子命令全名”枚举，禁止使用 `*` 通配授权。

---

## 9. 与分层架构的映射

| 层 | AI 参与方式 |
|----|------------|
| L1 | 外部数据系统接入，走 PIT 时间戳纪律 |
| L2/L3 | 读取因子信号，辅助情景分析 |
| L4 | 建议约束参数调优，不直接修改 |
| L5/L5.5 | 只读门控结果，不参与 gate 判定 |
| L6 | 不参与，任何情况下 |
| L7 | 解读回测结果，识别 regime 切换点 |
| L8 | **核心投入层**：触发告警、情景分析、归因诊断 |
| G1/G2/G3 | AI 产出必须纳入数据、实验、审批链路 |

---

## 10. 安全与审计

### 权限模型

- AI Skill 默认以最小权限运行（`viewer/researcher`）
- 高风险命令必须由人工 `operator` 在 G3 审批后执行

### 审计要求

每次 Skill 运行记录：

- `skill_name`、`skill_version`、`run_id`
- `operator`（人/系统身份）
- CLI 命令序列与参数
- 输入数据版本（`data_manifest`）
- 外部数据来源与检索方式
- 关键输出摘要与错误码
- 最终建议与用户是否采纳

### 决策历史存储

- 每次军师建议及用户决策结果持久化到本地 `decision_log`（append-only NDJSON）
- 记录字段：`run_id`、`trigger`、`recommendation`、`user_decision`、`outcome`（事后填入）
- `strategy-diagnosis` 和 `research-assistant` 在下次运行时读取历史，避免重复提已被拒绝的建议
- `outcome` 由用户或系统在事后手动/自动回填，用于复盘诊断
- 写入要求：文件锁 + 追加写，禁止覆盖写
- 完整性要求：每条记录附 `record_hash` 与前序 `prev_hash`（哈希链），便于篡改检测

### 防越权

- 禁止 shell 任意命令透传，仅允许受控 CLI 子命令
- 命令参数做 schema 校验
- 单次任务设置命令数与时长上限
- 改变实盘状态的命令强制 G3 审批

---

## 11. 完整运行流程

1. L8 检测到触发信号，写入告警事件 `alert`。
2. `signal-watcher` 读取 `alert`，分发到对应 Skill。
3. 执行 Skill 调用 CLI 拉取系统数据。
4. `market-interpreter` 拉取外部结构化数据，必要时降级 `web_search`。
5. AI 生成决策树报告（建议动作 + EV + 置信度 + 来源）。
6. 通知用户，用户拍板。
7. 涉及变更时生成变更提案 `proposal`，进入 G3 审批。
8. 审批通过后系统执行。
9. 结果（采纳/拒绝/后验 outcome）回写 `decision_log` 供下次复盘。

---

## 12. 非目标

- 不做 AI 端到端直接下单
- 不做绕开 G3 审批的自动参数生效
- 不做无版本、不可审计的临时 Skill 上线
- 不做 AI 阻断或放行交易执行

---

## 13. 一句话原则

**军师出谋划策，主公拍板，令旗不在军师手里。**
