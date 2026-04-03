from domain.models.signal import (
    CompositeScore,
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
