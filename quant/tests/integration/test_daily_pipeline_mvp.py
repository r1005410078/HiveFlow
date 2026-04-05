from datetime import date, timedelta

import application.daily_run_service as daily_run_module
from application.daily_run_service import run_daily


def test_daily_run_includes_l2_decision() -> None:
    """验证 daily 编排包含 l2_decision 输出"""
    result = run_daily(as_of="2026-04-01", root=None)

    assert "technical" in result["data"]
    assert result["data"]["technical"] is None
    assert "l2_decision" in result["data"]
    l2d = result["data"]["l2_decision"]

    assert l2d["score_version"] == "l2-score-v1.1"
    assert l2d["universe_size"] >= 0
    assert isinstance(l2d["top_candidates"], list)
    assert isinstance(l2d["score_breakdown"], list)
    assert isinstance(l2d["factor_availability"], list)

    scores = [c["score"] for c in l2d["top_candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_daily_pipeline_end_to_end(tmp_path):
    """验证日频流水线输出包含 run_id、manifest_id、L2.1 因子快照与 execution_plan。"""
    out = run_daily(as_of="2026-04-01", root=tmp_path)
    assert out["status"] in {"ok", "warning"}
    assert out["run_id"].startswith("run_")
    assert "data_manifest_id" in out["data"]
    assert "factor_snapshot" in out["data"]
    assert out["data"]["factor_snapshot"]["snapshot_version"] == "l2-basic-v1.1"
    assert set(out["data"]["factor_snapshot"]["factor_names"]) >= {
        "max_drawdown_60",
        "trend_stability_20",
        "relative_strength_vs_index",
    }
    assert out["data"]["factor_snapshot"]["coverage_rate"] == 1.0
    assert "execution_plan" in out["data"]
    assert out["data"]["as_of"] == "2026-04-01"
    assert "technical" in out["data"]
    assert out["data"]["technical"] is None
    assert out["data"]["execution_plan"]["orders"] == []


def _bars_for_symbol(symbol: str, days: int = 90) -> list[dict]:
    rows = []
    for i in range(days):
        d = date(2026, 1, 1) + timedelta(days=i)
        close = 100 + i
        rows.append(
            {
                "symbol": symbol,
                "timeframe": "1d",
                "bar_time": f"{d.isoformat()}T15:00:00+08:00",
                "open": close - 0.5,
                "high": close + 0.5,
                "low": close - 1.0,
                "close": close,
                "volume": 5000 + i,
                "amount": (5000 + i) * close,
                "adj_factor": 1.0,
                "data_source": "test",
            }
        )
    return list(reversed(rows))


def test_daily_pipeline_prefers_real_bars_when_available() -> None:
    class _BarStore:
        def list_bars(self, symbols=None, timeframe=None, start_date=None, end_date=None, limit=None):
            del timeframe, start_date, end_date, limit
            out = []
            for s in symbols or []:
                out.extend(_bars_for_symbol(s))
            return out

        def list_storage_bars(
            self,
            symbols=None,
            storage_timeframe="1m",
            start_date=None,
            end_date=None,
            limit=None,
            order="asc",
        ):
            del storage_timeframe, start_date, end_date, limit, order
            return []

        def list_symbols_with_min_bars_in_window(self, **kwargs):
            return ([], False)

    out = run_daily(as_of="2026-04-01", root=None, bar_store=_BarStore())
    tech = out["data"]["technical"]
    assert tech is not None
    ma = tech["ma5_ma10"]
    assert ma["schema_version"] == "1.0.0"
    assert ma["definition"] == "sma_close_5_10"
    assert ma["as_of"] == "2026-04-01"
    from domain.universe.universe_loader import load_universe

    expected_symbols = set(load_universe("default"))
    assert set(ma["by_symbol"]) == expected_symbols
    for st in ma["by_symbol"].values():
        assert "golden_cross" in st
        assert "death_cross" in st
        assert "available" in st
        assert st["available"] is True
    rows = out["data"]["factor_snapshot"]["rows"]
    trend_rows = [r for r in rows if r["factor_name"] == "trend_stability_20"]
    assert len(trend_rows) == len(expected_symbols)
    assert all(r["raw_value"] == 1.0 for r in trend_rows)


def test_daily_pipeline_warns_when_factor_availability_is_low(monkeypatch) -> None:
    def _stub_l2_decision(*, factor_snapshot, top_n, score_version):
        del factor_snapshot, top_n, score_version
        return {
            "schema_version": "1.0",
            "generated_at": "2026-04-01T00:00:00+00:00",
            "producer_version": "quant-l2",
            "score_version": "l2-score-v1.1",
            "universe_size": 5,
            "top_candidates": [],
            "score_breakdown": [],
            "factor_availability": [
                {
                    "factor_name": "relative_strength_vs_index",
                    "present_count": 3,
                    "missing_count": 2,
                    "availability_rate": 0.6,
                }
            ],
        }

    monkeypatch.setattr(daily_run_module, "compute_l2_decision_from_snapshot", _stub_l2_decision)

    out = run_daily(as_of="2026-04-01", root=None)
    assert out["warnings"]
    assert out["warnings"][0]["code"] == "FACTOR_AVAILABILITY_LOW"
