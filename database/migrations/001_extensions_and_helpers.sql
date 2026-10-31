-- 001_extensions_and_helpers.sql
-- Extensions and shared helper functions. Safe to re-run.
--
-- Supabase installs extensions into the "extensions" schema, which is already on
-- the search_path, so no schema qualifier is used here. On plain Postgres they land
-- in "public". Either way the types/operators below resolve without changes.

create extension if not exists pgcrypto;   -- gen_random_uuid(), crypt() for seed password
create extension if not exists pg_trgm;    -- trigram GIN indexes for ILIKE '%q%' search
create extension if not exists citext;     -- case-insensitive text (emails)

-- Generic BEFORE UPDATE trigger body: keeps updated_at current.
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

comment on function set_updated_at() is
  'Trigger function: stamps updated_at on every UPDATE. Attach with attach_updated_at(table).';

-- One-liner to wire the trigger onto a table that has an updated_at column.
-- Idempotent, so every migration can call it right after its CREATE TABLE.
create or replace function attach_updated_at(p_table regclass)
returns void
language plpgsql
as $$
declare
  v_name text := 'trg_' || (select relname from pg_class where oid = p_table) || '_updated_at';
begin
  execute format('drop trigger if exists %I on %s', v_name, p_table);
  execute format(
    'create trigger %I before update on %s for each row execute function set_updated_at()',
    v_name, p_table);
end;
$$;

comment on function attach_updated_at(regclass) is
  'Helper used by migrations: (re)creates the updated_at trigger on the given table.';
