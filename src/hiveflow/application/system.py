"""系统诊断与演示数据应用服务。"""

from dataclasses import dataclass
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.application.current import set_current_strategy
from hiveflow.application.rebalance import preview_rebalance
from hiveflow.application.targets import generate_targets_for_strategy
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.decision_logs import DecisionLog, UserPreference
from hiveflow.domain.positions import Position
from hiveflow.domain.risk import RiskSignal
from hiveflow.domain.strategies import Strategy
from hiveflow.domain.suggestions import RebalanceSuggestion
from hiveflow.services.bootstrap import bootstrap_all


@dataclass(frozen=True)
class DoctorCheckView:
    """单项诊断结果。"""

    # 检查项名称。
    name: str
    # 诊断状态：ok / warn / fail。
    status: str
    # 详细信息。
    detail: str

    def to_dict(self) -> dict[str, str]:
        """转换为字典，便于 JSON 输出。"""
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class DoctorResult:
    """系统诊断结果。"""

    # 总体状态：ok / warn / fail。
    overall_status: str
    # 诊断项列表。
    checks: list[DoctorCheckView]

    def to_dict(self) -> dict[str, object]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "overall_status": self.overall_status,
            "checks": [item.to_dict() for item in self.checks],
        }


@dataclass(frozen=True)
class InitDemoResult:
    """演示数据初始化结果。"""

    # 持仓数量。
    positions: int
    # 策略数量。
    strategies: int
    # 风险信号数量。
    risks: int
    # 目标持仓数量。
    targets: int
    # 当前策略。
    current_strategy: str

    def to_dict(self) -> dict[str, int | str]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "positions": self.positions,
            "strategies": self.strategies,
            "risks": self.risks,
            "targets": self.targets,
            "current_strategy": self.current_strategy,
        }


def run_doctor() -> DoctorResult:
    """执行本地环境诊断。"""
    checks: list[DoctorCheckView] = []
    settings = Settings()

    try:
        create_all_tables()
        checks.append(DoctorCheckView(name="database", status="ok", detail="数据库可连接并已建表"))
    except Exception as exc:  # pragma: no cover - 防御性分支
        checks.append(DoctorCheckView(name="database", status="fail", detail=str(exc)))

    template_file = Path(settings.target_template_file)
    if template_file.exists():
        checks.append(
            DoctorCheckView(
                name="target_template_file",
                status="ok",
                detail=f"已找到模板配置：{template_file}",
            )
        )
    else:
        checks.append(
            DoctorCheckView(
                name="target_template_file",
                status="warn",
                detail=f"模板配置不存在，将使用内置默认模板：{template_file}",
            )
        )

    with get_session() as session:
        strategy_count = len(session.exec(select(Strategy)).all())
        position_count = len(session.exec(select(Position)).all())
    checks.append(
        DoctorCheckView(
            name="data_presence",
            status="ok" if (strategy_count > 0 or position_count > 0) else "warn",
            detail=f"策略={strategy_count}，持仓={position_count}",
        )
    )

    if any(item.status == "fail" for item in checks):
        overall = "fail"
    elif any(item.status == "warn" for item in checks):
        overall = "warn"
    else:
        overall = "ok"
    return DoctorResult(overall_status=overall, checks=checks)


def init_demo_data(reset: bool = True) -> InitDemoResult:
    """初始化一套可直接演示的本地数据。"""
    bootstrap_all()
    create_all_tables()
    with get_session() as session:
        if reset:
            session.exec(delete(RebalanceSuggestion))
            session.exec(delete(TargetAllocation))
            session.exec(delete(RiskSignal))
            session.exec(delete(Position))
            session.exec(delete(UserPreference))
            session.exec(delete(DecisionLog))
            session.exec(delete(Strategy))

        session.add_all(
            [
                Strategy(
                    name="进攻突破策略",
                    category="进攻型",
                    thesis="趋势突破与动量确认",
                    dimension="趋势|动量",
                    market_regime="趋势市",
                    backtest_summary="年化 18%，最大回撤 16%",
                ),
                Strategy(
                    name="防守稳健策略",
                    category="防守型",
                    thesis="波动收敛与回撤控制",
                    dimension="波动|防守",
                    market_regime="震荡市",
                    backtest_summary="年化 10%，最大回撤 7%",
                ),
            ]
        )
        session.add_all(
            [
                Position(symbol="BTC", quantity=1.0, market_value=100000.0, weight=0.50),
                Position(symbol="ETH", quantity=6.0, market_value=60000.0, weight=0.30),
                Position(symbol="USDT", quantity=40000.0, market_value=40000.0, weight=0.20),
            ]
        )
        session.add_all(
            [
                RiskSignal(symbol="BTC", waterline="medium", score=0.58, note="趋势有效但波动上升"),
                RiskSignal(symbol="ETH", waterline="high", score=0.81, note="短期波动放大"),
                RiskSignal(symbol="USDT", waterline="low", score=0.10, note="稳定"),
            ]
        )
        session.commit()

    set_current_strategy(name="进攻突破策略")
    generate_targets_for_strategy(strategy_name="进攻突破策略")
    preview_rebalance(strategy="进攻突破策略", save=True)

    with get_session() as session:
        return InitDemoResult(
            positions=len(session.exec(select(Position)).all()),
            strategies=len(session.exec(select(Strategy)).all()),
            risks=len(session.exec(select(RiskSignal)).all()),
            targets=len(session.exec(select(TargetAllocation)).all()),
            current_strategy="进攻突破策略",
        )
