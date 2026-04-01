create extension if not exists timescaledb;

create table if not exists bars (
  symbol text not null,
  timeframe text not null,
  bar_time timestamptz not null,
  open double precision not null,
  high double precision not null,
  low double precision not null,
  close double precision not null,
  volume double precision not null,
  amount double precision not null,
  adj_factor double precision not null default 1.0,
  data_source text not null,
  ingested_at timestamptz not null default now(),
  primary key (symbol, timeframe, bar_time)
);

select create_hypertable('bars','bar_time', if_not_exists => true);

create index if not exists idx_bars_timeframe_bar_time_desc
  on bars (timeframe, bar_time desc);

create index if not exists idx_bars_symbol_bar_time_desc
  on bars (symbol, bar_time desc);

create table if not exists sync_runs (
  run_id uuid primary key,
  request_id text null,
  status text not null,
  days integer not null,
  end_date date not null,
  timeframe text not null,
  symbols_hash text not null,
  effective_symbols_count integer not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz null,
  error_code text null,
  error_message text null
);

create unique index if not exists uq_sync_runs_request_id_nonnull
  on sync_runs (request_id)
  where request_id is not null;

create index if not exists idx_sync_runs_started_at_desc
  on sync_runs (started_at desc);

create index if not exists idx_sync_runs_status_started_at_desc
  on sync_runs (status, started_at desc);

create index if not exists idx_sync_runs_timeframe_started_at_desc
  on sync_runs (timeframe, started_at desc);

create table if not exists sync_checkpoints (
  symbol text not null,
  timeframe text not null,
  last_bar_time timestamptz not null,
  updated_at timestamptz not null default now(),
  last_run_id uuid not null,
  primary key (symbol, timeframe)
);

create index if not exists idx_sync_checkpoints_timeframe_last_bar_time_desc
  on sync_checkpoints (timeframe, last_bar_time desc);

-- upsert 模板（供实现层参考）：
-- insert into bars (...)
-- values (...)
-- on conflict (symbol, timeframe, bar_time)
-- do update set
--   open = excluded.open,
--   high = excluded.high,
--   low = excluded.low,
--   close = excluded.close,
--   volume = excluded.volume,
--   amount = excluded.amount,
--   adj_factor = excluded.adj_factor,
--   data_source = excluded.data_source,
--   ingested_at = now();
