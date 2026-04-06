-- L6 Phase 1: persisted target notionals per (symbol, as_of) for execution planning.
CREATE TABLE IF NOT EXISTS positions (
    symbol        TEXT        NOT NULL,
    as_of         DATE        NOT NULL,
    notional      DOUBLE PRECISION NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, as_of)
);
