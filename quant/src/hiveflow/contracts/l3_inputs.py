"""L3 信号工程建议消费的 L2 产出契约（文档 + TypedDict，供类型提示与跨模块对齐）。

.. note::

   L3 实现应依赖 **字段语义与版本策略**，而非隐式字典结构。破坏性变更需升
   ``snapshot_version`` / ``factor_version``，并保留兼容窗口（见 AGENTS.md）。
"""

from __future__ import annotations

from typing import Literal, TypedDict


class L2FactorSnapshotRow(TypedDict):
    """单条因子快照行：与 ``compute_basic_factor_snapshot*`` 产出 ``rows[]`` 对齐。"""

    as_of: str
    symbol: str
    factor_name: str
    factor_version: str
    raw_value: float
    direction: int
    unit: str
    missing_strategy: str
    source: Literal["real", "deterministic_fallback", "benchmark_proxy_fallback"]


class L2FactorSnapshotPayload(TypedDict, total=False):
    """``pipeline daily`` 中 ``data.factor_snapshot`` 的推荐消费子集。"""

    snapshot_version: str
    factor_names: list[str]
    coverage_rate: float
    rows: list[L2FactorSnapshotRow]
    stability_metrics: list[dict]
