# 2026-03-20 M11 规划：信号上下文契约化与消费闭环

## 1. 目标

在保持“系统只输出数据，Agent 负责判断”边界不变的前提下，把 `context daily` 的窗口审计能力从“可用”提升到“可稳定集成”：

- 契约明确：字段语义、版本、兼容策略可追溯
- 消费友好：Agent/前端可按稳定结构低成本接入
- 变更可控：后续扩展不会破坏已有消费方

## 2. 非目标（保持边界）

- 不新增投资推荐逻辑
- 不新增策略判断逻辑
- 不把 Agent 决策回流为系统自动结论

## 3. 里程碑范围（M11）

### Phase A：契约固化（文档 + schema）

1. `window_audit` 契约文档稳定化（已起步）
2. `context daily --json-schema` 增补 `window_audit` 关键字段约束
3. 增加“兼容矩阵”文档（平铺字段与 `window_audit` 子对象并行期）

### Phase B：消费闭环（CLI 输出稳定）

1. 增加 `contract_meta`（如 `context_contract_version`）
2. 增加 `window_audit` 最小必备字段完整性检查（内部）
3. 增加契约快照测试，防止字段回退/误删

### Phase C：维护策略（演进规则）

1. 冻结 v1 升级规则（新增字段 only，废弃字段先标记后移除）
2. 增加“破坏性变更检查清单”
3. 更新新手文档的 Agent 消费示例

## 4. 验收标准

- 命令层：
  - `context daily --output json` 稳定输出 `window_audit`（含版本号）
  - `strict-window=all` 失败详情同样稳定输出 `window_audit`
- 契约层：
  - `WINDOW_AUDIT_CONTRACT.md` 与 CLI 实际字段一致
  - `json-schema` 包含 `window_audit` 关键字段
- 测试层：
  - `tests/test_signal_cli.py` 继续保持全绿
  - 回归集合继续全绿

## 5. 风险与回滚

- 风险：字段扩展过快导致消费方误解
- 缓解：版本号 + 兼容策略 + 契约文档优先
- 回滚：始终保留平铺字段，出现问题可回退到旧消费路径

## 6. 执行顺序建议

1. 先完成 Phase A（契约与 schema 对齐）
2. 再做 Phase B（输出与测试收口）
3. 最后做 Phase C（演进规则文档化）

