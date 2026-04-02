alter table sync_runs
  add column if not exists manifest_ids text[];

update sync_runs
set manifest_ids = coalesce(manifest_ids, array[]::text[])
where manifest_ids is null;

alter table sync_runs
  alter column manifest_ids set default array[]::text[];

alter table sync_runs
  alter column manifest_ids set not null;
