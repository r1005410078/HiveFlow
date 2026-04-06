"""Unit tests for G2 experiment config snapshot service."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.experiment.experiment_config_service import (
    collect_param_rows,
    get_experiment_config,
    list_experiment_configs,
    snapshot_current,
)


def test_collect_param_rows_count_and_l2_keys() -> None:
    rows = collect_param_rows()
    assert len(rows) == 33
    l2_keys = {r["param_key"] for r in rows if r["layer"] == "l2"}
    expected_l2_keys = {
        "factor_weight_momentum_20",
        "factor_weight_inv_volatility_20",
        "factor_weight_turnover_rate",
        "factor_weight_max_drawdown_60",
        "factor_weight_trend_stability_20",
        "factor_weight_relative_strength_vs_index",
    }
    assert l2_keys == expected_l2_keys


def test_snapshot_persists_via_store() -> None:
    store = MagicMock()
    out = snapshot_current("unit", store=store)
    assert out["status"] == "ok"
    assert out["data"]["params_count"] == 33
    store.insert_experiment_config_rows.assert_called_once()
    inserted = store.insert_experiment_config_rows.call_args[0][0]
    assert len(inserted) == 33
    cid = out["data"]["config_id"]
    assert all(r["config_id"] == cid for r in inserted)
    assert all(r["created_by"] == "system" for r in inserted)


def test_snapshot_no_store_no_insert() -> None:
    out = snapshot_current("x", store=None)
    assert out["status"] == "ok"
    assert out["data"]["params_count"] == 33
    assert any(w.get("code") == "EXPERIMENT_CONFIG_NO_DB" for w in out["warnings"])


def test_list_configs_no_store() -> None:
    out = list_experiment_configs(store=None)
    assert out["data"]["configs"] == []
    assert any(w.get("code") == "EXPERIMENT_CONFIG_NO_DB" for w in out["warnings"])


def test_list_configs_with_store() -> None:
    store = MagicMock()
    store.list_experiment_config_summaries.return_value = [
        {
            "config_id": "abc",
            "params_count": 33,
            "note": "n",
            "created_at": "2026-04-01T00:00:00+00:00",
            "layers": ["l2", "l4"],
        }
    ]
    out = list_experiment_configs(store=store, layer="l2", limit=5)
    assert len(out["data"]["configs"]) == 1
    store.list_experiment_config_summaries.assert_called_once_with(layer="l2", limit=5)


def test_get_config_found() -> None:
    store = MagicMock()
    store.fetch_experiment_config_detail.return_value = {
        "config_id": "x",
        "note": "n",
        "created_at": "2026-04-01T00:00:00+00:00",
        "params": [{"layer": "l2", "param_key": "factor_weight_momentum_20", "param_value": 0.1}],
    }
    out = get_experiment_config("x", store=store)
    assert out["status"] == "ok"
    assert out["data"]["params"][0]["param_key"] == "factor_weight_momentum_20"


def test_get_config_missing() -> None:
    store = MagicMock()
    store.fetch_experiment_config_detail.return_value = None
    out = get_experiment_config("missing", store=store)
    assert out["status"] == "error"
    assert out["errors"][0]["code"] == "CONFIG_NOT_FOUND"


def test_get_config_no_db() -> None:
    out = get_experiment_config("any", store=None)
    assert out["status"] == "error"
    assert out["errors"][0]["code"] == "EXPERIMENT_CONFIG_NO_DB"
