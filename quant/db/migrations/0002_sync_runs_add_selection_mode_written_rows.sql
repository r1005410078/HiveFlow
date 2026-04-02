alter table sync_runs
  add column if not exists selection_mode text;

update sync_runs
set selection_mode = coalesce(selection_mode, 'default')
where selection_mode is null;

alter table sync_runs
  alter column selection_mode set default 'default';

alter table sync_runs
  alter column selection_mode set not null;

alter table sync_runs
  add column if not exists written_rows integer;

update sync_runs
set written_rows = coalesce(written_rows, 0)
where written_rows is null;

alter table sync_runs
  alter column written_rows set default 0;

alter table sync_runs
  alter column written_rows set not null;
