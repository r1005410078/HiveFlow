# L5 Risk Subdomain

## Purpose
L5 负责执行前硬门控，不参与收益博弈。

## Responsibilities
- 校验单资产上限、回撤阈值等硬规则（MVP）
- 产出 `pass/block` 结果
- block 时输出完整证据快照

## Input / Output
- Input: L4 目标权重 + 当前风险上下文
- Output: `gate_result, block_reason, evidence_snapshot`

## DDD Layers
- `domain/`: 风控规则与结果对象
- `application/`: 门控执行用例
- `infrastructure/`: 风险数据读取与记录
- `interfaces/`: 风控响应 DTO
