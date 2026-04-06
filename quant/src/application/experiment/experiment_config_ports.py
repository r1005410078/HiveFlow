from __future__ import annotations

from typing import Any, Protocol


class ExperimentConfigStore(Protocol):
    def insert_experiment_config_rows(self, rows: list[dict[str, Any]]) -> None:
        """Persist rows: config_id, layer, param_key, param_value, note, created_by."""

    def list_experiment_config_summaries(
        self, *, layer: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Return {config_id, params_count, note, created_at, layers} per snapshot."""

    def fetch_experiment_config_detail(self, config_id: str) -> dict[str, Any] | None:
        """Return {config_id, note, created_at, params} or None if missing."""
