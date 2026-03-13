# HiveFlow M4（策略质量与可发布能力）Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐“策略回测、风险计算、自定义策略发布、AI 接口契约”四大缺口，让系统从“可演示”升级到“可持续使用”。

**Architecture:** 在现有 CLI + 应用服务 + SQLite 架构上增量扩展，不改主框架。新增回测与风险计算服务层，保持 JSON 契约稳定，并通过命令化工作流落地。每个能力先做 v1（可用、可测、可复现），再迭代精度与性能。

**Tech Stack:** Python 3.12, Typer, SQLModel, pytest, Rich, CSV/JSON

---

## 一、剩余未开发功能（相对当前状态）

1. 策略回测引擎仍缺失：当前只有“回测摘要字段”，没有可运行回测流程与结果存档。
2. 风险分析仍以导入为主：缺少由价格/波动数据计算风险水位的能力。
3. 自定义策略发布流程缺失：没有“策略定义 -> 校验 -> 激活 -> 回滚”的完整链路。
4. AI/Skills 接口仍是预备层：已有 `--envelope/--json-schema`，但缺少 schema 版本治理与兼容策略。
5. 发布流程未收口：缺少固定的冒烟脚本、版本发布清单与回归门禁。

## 二、实施前约束（避免返工）

1. 先冻结行情输入契约（CSV 列、单位、时区、缺失值规则），再做回测与风险计算。
2. 所有新 JSON 输出遵循“向后兼容”：不删除旧字段，只新增可选字段。
3. 新能力优先接入现有 CLI 主链路（`current run / positions drift / summary`），避免孤立命令。
4. 测试按能力拆分，避免继续膨胀单一 `tests/test_cli.py`。

---

## Chunk 0：行情输入契约冻结（先行任务）

### Task 0.1：定义价格数据 schema 与导入模板

**Files:**
- Create: `docs/architecture/market-data-contract.md`
- Create: `src/hiveflow/application/market_data.py`
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_market_data.py`
- Test: `tests/test_cli_market_data.py`

- [x] **Step 1: Write failing tests**
  - 校验 `prices.csv` 最低列约束：`symbol,timestamp,open,high,low,close,volume`
  - 校验时区与时间格式（ISO8601 UTC）。
- [x] **Step 2: Run test to verify it fails**
  - Run: `uv run python -m pytest -q tests/test_market_data.py tests/test_cli_market_data.py`
- [x] **Step 3: Write minimal implementation**
  - 增加 `market-data template/validate` 能力。
- [x] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 冻结行情输入契约并提供模板校验`

---

## Chunk 1：策略回测 v1（可运行、可复现）

### Task 1.1：建立回测领域与存储模型

**Files:**
- Create: `src/hiveflow/domain/backtests.py`
- Modify: `src/hiveflow/db.py`
- Test: `tests/test_backtest_engine.py`
- Test: `tests/test_cli_backtest.py`

- [x] **Step 1: Write the failing test**
  - 断言可保存一条回测结果（策略名、窗口、收益、回撤、sharpe、created_at）。
- [x] **Step 2: Run test to verify it fails**
  - Run: `uv run python -m pytest -q tests/test_backtest_engine.py::test_save_backtest_result`
- [x] **Step 3: Write minimal implementation**
  - 增加 `BacktestResult` SQLModel。
- [x] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**
  - `feat: 增加回测结果领域模型`

### Task 1.2：实现回测服务（单策略单窗口）

**Files:**
- Create: `src/hiveflow/services/backtest_engine.py`
- Create: `src/hiveflow/application/backtest.py`
- Test: `tests/test_backtest_engine.py`

- [x] **Step 1: Write failing tests**
  - 给定价格序列和目标权重，计算收益曲线、累计收益、最大回撤。
- [x] **Step 2: Run failing tests**
- [x] **Step 3: Implement minimal engine**
  - 支持固定费率、固定滑点（v1 常量参数）。
- [x] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 实现回测引擎v1`

### Task 1.3：开放 CLI 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_cli_backtest.py`
- Docs: `docs/cli/README.md`

- [x] **Step 1: Write failing CLI tests**
  - `hiveflow backtest run`
  - `hiveflow backtest list`
- [x] **Step 2: Run failing tests**
- [x] **Step 3: Implement commands**
  - `backtest run --strategy --from --to --fee-bps --slippage-bps`
  - `backtest list --strategy --output`
- [x] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 增加回测命令闭环`

---

## Chunk 2：风险分析引擎 v1（从导入升级为计算）

### Task 2.1：实现风险计算服务

**Files:**
- Modify: `src/hiveflow/services/risk_engine.py`
- Create: `src/hiveflow/application/risk_compute.py`
- Test: `tests/test_risk_engine.py`
- Test: `tests/test_cli_risk.py`

- [ ] **Step 1: Write failing tests**
  - 输入价格序列，输出 `score + waterline`。
- [ ] **Step 2: Run failing tests**
- [ ] **Step 3: Implement minimal risk formula**
  - v1 使用波动率 + 回撤近似分数，阈值映射 low/medium/high。
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 实现风险计算引擎v1`

### Task 2.2：接入命令工作流

**Files:**
- Modify: `src/hiveflow/cli.py`
- Modify: `src/hiveflow/config.py`
- Test: `tests/test_cli_risk.py`
- Docs: `docs/cli/README.md`

- [ ] **Step 1: Write failing CLI tests**
  - `hiveflow risk compute --file prices.csv`
  - `hiveflow risk refresh`（基于已配置数据源/文件）
- [ ] **Step 2: Run failing tests**
- [ ] **Step 3: Implement commands**
  - 明确 `risk refresh` 配置优先级：CLI 参数 > ENV > 默认文件路径。
  - 明确无数据源时降级行为：返回可读错误 + `doctor` 给出修复建议。
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 风险命令支持计算与刷新`

---

## Chunk 3：资产配比建议闭环（补齐 MVP 主线）

### Task 3.1：席位/资产配比偏离分析

**Files:**
- Create: `src/hiveflow/application/allocation_drift.py`
- Modify: `src/hiveflow/services/allocation_engine.py`
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_allocation_engine.py`
- Test: `tests/test_cli_allocation.py`

- [ ] **Step 1: Write failing tests**
  - 给定席位目标权重与当前权重，输出偏离等级与建议动作。
- [ ] **Step 2: Run failing tests**
- [ ] **Step 3: Implement minimal logic**
  - 命令：`hiveflow allocation drift`、`hiveflow allocation suggest`。
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 增加资产配比偏离与建议命令`

---

## Chunk 4：自定义策略发布闭环（定义、校验、生效、回滚）

### Task 3.1：策略定义文件与校验器

**Files:**
- Create: `src/hiveflow/application/strategy_spec.py`
- Create: `src/hiveflow/services/strategy_validator.py`
- Test: `tests/test_strategy_spec.py`
- Docs: `docs/architecture/strategy-spec.md`

- [ ] **Step 1: Write failing tests**
  - 校验字段完整性、权重合法性、维度规范化。
- [ ] **Step 2: Run failing tests**
- [ ] **Step 3: Implement validator**
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 增加策略定义校验器`

### Task 3.2：发布与回滚命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Modify: `src/hiveflow/application/strategies.py`
- Modify: `src/hiveflow/application/current.py`
- Test: `tests/test_cli_strategy_publish.py`
- Docs: `docs/cli/README.md`

- [ ] **Step 1: Write failing CLI tests**
  - `hiveflow strategies publish --file strategy.json`
  - `hiveflow strategies rollback --version N`
- [ ] **Step 2: Run failing tests**
- [ ] **Step 3: Implement publish/rollback**
  - 发布成功后写决策日志，保存版本快照。
  - 明确与 `current strategy` 联动：
    - 若回滚目标版本存在当前策略同名配置，则保持 current；
    - 若不存在，自动回退到“最近可用策略”并记录日志。
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 增加策略发布与回滚闭环`

---

## Chunk 5：AI/Skills 契约治理与发布收口

### Task 5.1：固定 JSON schema 版本策略

**Files:**
- Modify: `src/hiveflow/cli.py`
- Create: `docs/architecture/json-contract.md`
- Test: `tests/test_cli_contract.py`

- [ ] **Step 1: Write failing tests**
  - `--json-schema` 返回固定版本，变更需显式升级版本号。
- [ ] **Step 2: Run failing tests**
- [ ] **Step 3: Implement schema version policy**
  - `schema_version` 与兼容说明写入文档。
  - 增加兼容测试：旧字段不可删除，破坏性变更必须升级主版本号。
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**
  - `feat: 固化JSON契约版本策略`

### Task 5.2：发布前回归与冒烟脚本

**Files:**
- Create: `scripts/smoke_cli.sh`
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/ROADMAP.md`
- Modify: `docs/context/SESSION_LOG.md`

- [ ] **Step 1: Write smoke script**
  - 覆盖 `init-demo -> current run -> positions drift -> summary --envelope`。
- [ ] **Step 2: Run smoke locally**
- [ ] **Step 3: Update release checklist docs**
- [ ] **Step 4: Commit**
  - `chore: 增加发布冒烟脚本与收口文档`

---

## 验收标准（M4 Done）

- [ ] 行情输入契约已冻结并可由命令校验。
- [ ] 可运行回测命令，并可查询历史回测结果。
- [ ] 风险可由计算引擎产出，不再只依赖手工导入。
- [ ] 可生成资产配比偏离与建议（席位层）。
- [ ] 可通过文件发布策略并支持回滚。
- [ ] JSON 契约有版本治理与兼容说明。
- [ ] 全量测试通过，冒烟脚本通过。

---

## 执行顺序建议

1. Chunk 0（行情输入契约）  
2. Chunk 1（回测）  
3. Chunk 2（风险计算）  
4. Chunk 3（资产配比建议）  
5. Chunk 4（策略发布）  
6. Chunk 5（契约与发布）  

这样可以保证每一步都直接提升主线能力，不会陷入“先做边角再补核心”。
