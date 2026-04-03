from domain.models.signal import (
    CompositeScore,
    DailyICEntry,
    FactorDriftResult,
    FactorICResult,
    RankTurnoverResult,
    SignalRow,
    TransformStats,
    TransformStatsDetail,
)


def test_signal_row_is_frozen():
    row = SignalRow(
        symbol="600519.SH",
        factor_name="momentum_20",
        raw_value=0.05,
        signal_value=1.23,
        direction=1,
    )
    assert row.symbol == "600519.SH"
    assert row.signal_value == 1.23


def test_transform_stats_detail():
    detail = TransformStatsDetail(count=5, mean=0.0, std=1.0, min_val=-1.5, max_val=1.8)
    assert detail.count == 5
    assert detail.min_val == -1.5


def test_composite_score():
    cs = CompositeScore(symbol="600519.SH", composite_score=0.87, factor_count=6)
    assert cs.factor_count == 6


def test_transform_stats():
    pre = TransformStatsDetail(count=5, mean=0.04, std=0.03, min_val=-0.01, max_val=0.1)
    post = TransformStatsDetail(count=5, mean=0.0, std=1.0, min_val=-1.5, max_val=1.8)
    ts = TransformStats(factor_name="momentum_20", pre_winsorize=pre, post_zscore=post)
    assert ts.factor_name == "momentum_20"
    assert ts.pre_winsorize.mean == 0.04


def test_daily_ic_entry():
    entry = DailyICEntry(date="2026-03-03", ic=0.12)
    assert entry.date == "2026-03-03"
    assert entry.ic == 0.12


def test_factor_ic_result():
    daily = (DailyICEntry(date="2026-03-03", ic=0.12),)
    r = FactorICResult(
        factor_name="momentum_20",
        mean_ic=0.12,
        ic_std=0.05,
        ic_ir=2.4,
        hit_rate=1.0,
        daily_ic=daily,
    )
    assert r.factor_name == "momentum_20"
    assert r.ic_ir == 2.4
    assert len(r.daily_ic) == 1


def test_factor_drift_result():
    d = FactorDriftResult(
        factor_name="momentum_20",
        baseline_mean=0.04,
        baseline_std=0.008,
        recent_mean=0.06,
        drift_z=2.5,
        drift_flag=True,
    )
    assert d.drift_flag is True
    assert d.drift_z == 2.5


def test_rank_turnover_result():
    r = RankTurnoverResult(mean_turnover=0.2, max_turnover=0.4, stable=True)
    assert r.stable is True
