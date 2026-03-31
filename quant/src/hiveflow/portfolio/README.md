# L4 Portfolio Subdomain

## Purpose
L4 负责从信号生成目标权重（组合构建）。

## Responsibilities
- 计算目标权重（MVP: 风险平价近似/简化权重）
- 输出求解状态与 fallback 标记
- 保证权重可审计、可复算

## Input / Output
- Input: L3 信号与约束参数
- Output: `target_weights + optimization_report`

## DDD Layers
- `domain/`: 权重实体、约束和值对象
- `application/`: 权重分配用例
- `infrastructure/`: 优化器适配与结果存储
- `interfaces/`: 组合输出 DTO
