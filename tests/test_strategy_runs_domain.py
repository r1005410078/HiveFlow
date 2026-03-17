from datetime import datetime
from hiveflow.domain.strategy_runs import StrategyRun


def test_strategy_run_fields():
    """StrategyRun 模型可以实例化并持有所有字段。"""
    run = StrategyRun(
        strategy_name="MomentumStrategy",
        strategy_file=None,
        params='{"lookback_days": 30}',
        weights='{"BTC": 0.45, "USDT": 0.10}',
        applied=False,
    )
    assert run.strategy_name == "MomentumStrategy"
    assert run.strategy_file is None
    assert run.applied is False
    assert run.run_at is not None
