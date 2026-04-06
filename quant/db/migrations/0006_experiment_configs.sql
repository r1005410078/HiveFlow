-- G2 Phase 1: append-only experiment parameter snapshots (audit trail).

CREATE TABLE IF NOT EXISTS experiment_configs (
    config_id   TEXT        NOT NULL,
    layer       TEXT        NOT NULL,
    param_key   TEXT        NOT NULL,
    param_value DOUBLE PRECISION NOT NULL,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  TEXT        NOT NULL DEFAULT 'system',
    PRIMARY KEY (config_id, layer, param_key)
);

CREATE INDEX IF NOT EXISTS idx_experiment_configs_layer_created
    ON experiment_configs (layer, created_at DESC);
