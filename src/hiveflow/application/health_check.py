# src/hiveflow/application/health_check.py
"""每日持仓健康检查用例。"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.services.risk_engine import calculate_max_drawdown

WARNING_DD = -0.10
DANGER_DD = -0.20


class AlertLevel(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    DANGER = "danger"


@dataclass(frozen=True)
class AssetRiskSignal:
    symbol: str
    max_drawdown_7d: float
    alert_level: AlertLevel
    action_hint: str


@dataclass
class HealthCheckResult:
    signals: list[AssetRiskSignal] = field(default_factory=list)
    has_no_history: bool = False

    @property
    def verdict(self) -> str:
        if any(s.alert_level == AlertLevel.DANGER for s in self.signals):
            return "danger"
        if any(s.alert_level == AlertLevel.WARNING for s in self.signals):
            return "watch"
        return "safe"

    @property
    def verdict_summary(self) -> str:
        if self.verdict == "safe":
            return "今天安全，无需操作"
        flagged = [
            s.symbol for s in self.signals
            if s.alert_level in (AlertLevel.DANGER, AlertLevel.WARNING)
        ]
        desc = "、".join(flagged)
        if self.verdict == "danger":
            return f"危险，建议处理 — {desc} 回撤超过 20%"
        return f"建议关注 — {desc} 近7日回撤较大"


def run_health_check(
    positions: list[Position],
    bars_by_symbol: dict[str, list[MarketBar]],
) -> HealthCheckResult:
    result = HealthCheckResult()
    if not bars_by_symbol:
        result.has_no_history = True
        return result

    for pos in positions:
        bars = sorted(bars_by_symbol.get(pos.symbol, []), key=lambda b: b.timestamp)[-7:]
        if not bars:
            continue
        dd = calculate_max_drawdown(bars)
        if dd <= DANGER_DD:
            level = AlertLevel.DANGER
            hint = f"{pos.symbol} 回撤超过 20%，建议评估是否止损"
        elif dd <= WARNING_DD:
            level = AlertLevel.WARNING
            hint = f"{pos.symbol} 回撤偏大，留意是否触发止损线"
        else:
            level = AlertLevel.NORMAL
            hint = ""
        result.signals.append(AssetRiskSignal(
            symbol=pos.symbol, max_drawdown_7d=dd,
            alert_level=level, action_hint=hint,
        ))
    return result
