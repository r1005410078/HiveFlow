# L3 Signal Subdomain

## Purpose
L3 负责把因子转换为可比较、可聚合的信号。

## Responsibilities
- 去极值（winsorize）
- 缺失处理与标准化（MVP: zscore）
- 输出信号覆盖率与诊断指标

## Input / Output
- Input: L2 因子矩阵
- Output: `signal_matrix(as_of, symbol, signal_value, coverage_rate, diagnostics)`

## DDD Layers
- `domain/`: 信号值对象、变换规则
- `application/`: 信号工程流水线用例
- `infrastructure/`: 信号读写与依赖实现
- `interfaces/`: 对外信号 DTO
