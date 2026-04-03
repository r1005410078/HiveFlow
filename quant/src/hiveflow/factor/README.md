# L2 Factor Subdomain

## Purpose
L2 负责从 L1 标准行情生成原始因子，不承担组合决策。

## Responsibilities
- 计算基础因子（MVP: 动量20日、波动率倒数、换手率）
- 记录因子版本与覆盖率
- 保证窗口只使用 `as_of` 及之前数据

## Input / Output
- Input: L1 标准行情与标的池
- Output: `factor_matrix(as_of, symbol, factor_name, raw_value, factor_version, coverage_rate)`

## DDD Layers
- `domain/`: 因子定义、窗口约束、版本对象（如 `FactorValue`）
- `application/`: `compute_use_case.compute_basic_factors` **委托** `application.factor.basic_factor_service`（与日线快照同一公式，避免双实现）
- `infrastructure/`: 因子结果读写与外部依赖适配（日频主路径在 `application` + `interfaces` bar_store）
- `interfaces/`: 因子子域 DTO

L3 消费侧建议字段见 `hiveflow/contracts/l3_inputs.py`（`L2FactorSnapshotRow` / `L2FactorSnapshotPayload`）。
