-- L1 async sync: add progress/phase/cancel to sync_runs + create symbol failure audit table

alter table sync_runs
  add column if not exists progress jsonb not null default '{}';

alter table sync_runs
  add column if not exists phase text not null default 'pending';

alter table sync_runs
  add column if not exists cancel_requested_at timestamptz;

create index if not exists idx_sync_runs_status_phase
  on sync_runs (status, phase);

-- Per-symbol failure audit table (PK: run_id + symbol)
create table if not exists sync_run_symbol_failures (
  run_id       uuid        not null references sync_runs(run_id),
  symbol       text        not null,
  attempt_count integer    not null default 1,
  last_error_code    text,
  last_error_message text,
  last_failed_day    date,
  first_failed_at    timestamptz not null default now(),
  last_failed_at     timestamptz not null default now(),
  primary key (run_id, symbol)
);

create index if not exists idx_sync_run_symbol_failures_run_id
  on sync_run_symbol_failures (run_id);
