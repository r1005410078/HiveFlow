"""内置量化策略。"""
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy
from hiveflow.services.strategies.momentum import MomentumStrategy
from hiveflow.services.strategies.mean_reversion import MeanReversionStrategy
from hiveflow.services.strategies.moving_average import MovingAverageCrossStrategy
from hiveflow.services.strategies.bollinger_band import BollingerBandStrategy
from hiveflow.services.strategies.risk_parity import RiskParityStrategy
from hiveflow.services.strategies.max_sharpe import MaxSharpeStrategy
from hiveflow.services.strategies.min_variance import MinVarianceStrategy

__all__ = [
    "BaseStrategy",
    "StrategyContext",
    "EqualWeightStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "MovingAverageCrossStrategy",
    "BollingerBandStrategy",
    "RiskParityStrategy",
    "MaxSharpeStrategy",
    "MinVarianceStrategy",
]
