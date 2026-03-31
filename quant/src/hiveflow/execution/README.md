# L6 Execution Subdomain

## Purpose
L6 负责把通过风控的目标权重转换为可执行调仓计划。

## Responsibilities
- 执行前检查（流动性/涨跌停/资金约束）
- 生成订单计划（非自动下单）
- 输出预估成本与预检结果

## Input / Output
- Input: L5 通过结果 + L4 目标权重 + 账户上下文
- Output: `execution_plan, pre_check_result, estimated_cost`

## DDD Layers
- `domain/`: 订单与执行计划对象
- `application/`: 执行计划生成用例
- `infrastructure/`: 券商/交易通道适配（MVP 可占位）
- `interfaces/`: 执行输出 DTO
