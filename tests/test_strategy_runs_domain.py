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


def test_strategy_run_persistence(tmp_path):
    """StrategyRun 可以落库并被查询出来。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from sqlmodel import select

    settings = Settings(database_url=f"sqlite:///{tmp_path}/test.db")
    create_all_tables(settings)

    with get_session(settings) as session:
        run = StrategyRun(
            strategy_name="MomentumStrategy",
            strategy_file=None,
            params='{"lookback_days": 30}',
            weights='{"BTC": 0.45, "USDT": 0.10}',
        )
        session.add(run)
        session.commit()

    with get_session(settings) as session:
        row = session.exec(select(StrategyRun)).first()
        assert row is not None
        assert row.strategy_name == "MomentumStrategy"
        assert row.applied is False
        assert row.id is not None
