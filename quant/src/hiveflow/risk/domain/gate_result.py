from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateResult:
    gate_result: str
    block_reason: str | None
    evidence_snapshot: list[dict[str, Any]]
