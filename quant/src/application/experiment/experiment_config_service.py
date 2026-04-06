"""G2 Phase 1: snapshot hard-coded strategy parameters for audit (no config-driven runtime yet)."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from application.contracts.cli_output import error_output, ok_output
from application.decision.l2_decision_service import SCORE_PROFILES, SCORE_VERSION
from application.execution import execution_service
from application.portfolio.portfolio_optimize_service import run_portfolio_optimize
from application.pretrade import pretrade_service
from application.risk.risk_gate_service import (
    REGIME_CRISIS_VOL_THRESHOLD,
    REGIME_WARNING_VOL_THRESHOLD,
    _THRESHOLDS,
)
from application.experiment.experiment_config_ports import ExperimentConfigStore

_WARN_NO_DB = {
    "code": "EXPERIMENT_CONFIG_NO_DB",
    "message": "bar_store unavailable; config not persisted",
}


def collect_param_rows() -> list[dict[str, Any]]:
    """Single source for enumerated params; keep aligned with run_daily defaults."""
    rows: list[dict[str, Any]] = []

    profile = SCORE_PROFILES[SCORE_VERSION]
    for name, w in profile["weights"].items():
        rows.append(
            {
                "layer": "l2",
                "param_key": f"factor_weight_{name}",
                "param_value": float(w),
            }
        )

    sig = inspect.signature(run_portfolio_optimize)
    rows.append(
        {"layer": "l4", "param_key": "w_max", "param_value": float(sig.parameters["w_max"].default)}
    )
    rows.append(
        {"layer": "l4", "param_key": "ind_max", "param_value": float(sig.parameters["ind_max"].default)}
    )
    rows.append(
        {
            "layer": "l4",
            "param_key": "lambda_risk",
            "param_value": float(sig.parameters["lambda_risk"].default),
        }
    )
    rows.append(
        {
            "layer": "l4",
            "param_key": "lambda_tc",
            "param_value": float(sig.parameters["lambda_tc"].default),
        }
    )

    rows.append(
        {
            "layer": "l5",
            "param_key": "regime_crisis_vol_threshold",
            "param_value": float(REGIME_CRISIS_VOL_THRESHOLD),
        }
    )
    rows.append(
        {
            "layer": "l5",
            "param_key": "regime_warning_vol_threshold",
            "param_value": float(REGIME_WARNING_VOL_THRESHOLD),
        }
    )
    for regime, thresh in _THRESHOLDS.items():
        for metric, val in thresh.items():
            rows.append(
                {
                    "layer": "l5",
                    "param_key": f"{regime}_{metric}",
                    "param_value": float(val),
                }
            )

    rows.append({"layer": "l5.5", "param_key": "eta", "param_value": float(pretrade_service.ETA)})
    rows.append(
        {
            "layer": "l5.5",
            "param_key": "max_participation_tradable",
            "param_value": float(pretrade_service.MAX_PARTICIPATION_TRADABLE),
        }
    )
    rows.append(
        {
            "layer": "l5.5",
            "param_key": "lookback_trading_days",
            "param_value": float(pretrade_service.LOOKBACK_TRADING_DAYS),
        }
    )

    rows.append(
        {
            "layer": "l6",
            "param_key": "slippage_bp",
            "param_value": float(execution_service.SLIPPAGE_BP),
        }
    )
    rows.append(
        {
            "layer": "l6",
            "param_key": "min_rel_delta",
            "param_value": float(execution_service.MIN_REL_DELTA),
        }
    )

    # Deferred to avoid circular import: walk_forward_service -> daily_run_service -> here
    from application.walk_forward_service import _DEFAULT_THRESHOLDS, run_walk_forward

    wf_sig = inspect.signature(run_walk_forward)
    rows.append(
        {
            "layer": "l7",
            "param_key": "warm_up_days",
            "param_value": float(wf_sig.parameters["warm_up_days"].default),
        }
    )
    for k, v in _DEFAULT_THRESHOLDS.items():
        rows.append({"layer": "l7", "param_key": k, "param_value": float(v)})

    return rows


def snapshot_current(
    note: str,
    *,
    store: ExperimentConfigStore | None = None,
) -> dict[str, Any]:
    config_id = str(uuid4())
    run_id = f"cfg_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{config_id[:8]}"
    base_rows = collect_param_rows()
    params_count = len(base_rows)
    created_iso = datetime.now(timezone.utc).isoformat()
    warnings: list[dict[str, str]] = []

    if store is None:
        warnings.append(dict(_WARN_NO_DB))
    else:
        created_by = "system"
        insert_rows: list[dict[str, Any]] = []
        for r in base_rows:
            insert_rows.append(
                {
                    "config_id": config_id,
                    "layer": r["layer"],
                    "param_key": r["param_key"],
                    "param_value": r["param_value"],
                    "note": note or None,
                    "created_by": created_by,
                }
            )
        store.insert_experiment_config_rows(insert_rows)

    return ok_output(
        command="hf config snapshot",
        run_id=run_id,
        data={
            "config_id": config_id,
            "params_count": params_count,
            "note": note,
            "created_at": created_iso,
        },
        warnings=warnings,
    )


def list_experiment_configs(
    *,
    store: ExperimentConfigStore | None = None,
    layer: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    run_id = f"cfg_list_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{str(uuid4())[:8]}"
    warnings: list[dict[str, str]] = []
    if store is None:
        warnings.append(dict(_WARN_NO_DB))
        return ok_output(
            command="hf config list",
            run_id=run_id,
            data={"configs": []},
            warnings=warnings,
        )
    summaries = store.list_experiment_config_summaries(layer=layer, limit=limit)
    return ok_output(
        command="hf config list",
        run_id=run_id,
        data={"configs": summaries},
        warnings=warnings,
    )


def get_experiment_config(
    config_id: str,
    *,
    store: ExperimentConfigStore | None = None,
) -> dict[str, Any]:
    run_id = f"cfg_get_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{str(uuid4())[:8]}"
    if store is None:
        return error_output(
            command="hf config get",
            run_id=run_id,
            errors=[{"code": "EXPERIMENT_CONFIG_NO_DB", "message": "database store unavailable"}],
        )
    detail = store.fetch_experiment_config_detail(config_id)
    if detail is None:
        return error_output(
            command="hf config get",
            run_id=run_id,
            errors=[{"code": "CONFIG_NOT_FOUND", "message": "config_id not found"}],
        )
    return ok_output(command="hf config get", run_id=run_id, data=detail)
