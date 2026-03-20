# BOUNDARY_GLOSSARY

## 目标

统一 HiveFlow 与 Agent 的职责边界术语，避免“系统做判断”与“系统输出数据”混淆。

## 术语定义

- 持仓追踪数据输出（系统）  
  含持仓快照、仓位变化、历史记录，不含买卖建议。

- 持仓风险数据输出（系统）  
  含回撤、波动率、相关性、偏离等级、信号状态等结构化数据，不含投资判断。

- 风险分析与决策（Agent）  
  基于系统输出数据，生成解释、偏好匹配、风险取舍与动作建议。

## JSON 边界元信息

对于关键 JSON 输出，统一使用：

```json
{
  "decision_boundary": {
    "system": "data_only",
    "agent": "analysis_and_decision"
  }
}
```

含义：

- `system=data_only`：系统只提供数据，不给投资结论
- `agent=analysis_and_decision`：Agent 负责解释与决策

## 推荐表达

- 推荐：`系统输出风险数据，Agent进行分析与决策`
- 避免：`系统做风险分析并给出推荐`
