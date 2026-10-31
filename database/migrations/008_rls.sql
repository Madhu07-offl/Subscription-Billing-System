-- 008_rls.sql
-- Lock the database down for Supabase.
--
-- Model: ONLY the backend talks to the database, using the service_role key or a direct Postgres
-- connection (both bypass RLS). The browser never queries tables, so there are intentionally NO
-- policies: with RLS on and no policy, the anon and authenticated roles see nothing.
-- Authorisation (admin/staff/customer scoping) lives in the API, as described in contract/API.md.
--
-- Need direct client access later? Add per-table "create policy" statements in a NEW migration;
-- do not edit this one.

-- Enable RLS on every ordinary table in public, including ones added by future migrations
-- (re-run this file after adding tables). Views need nothing: they are security_invoker (007).
do $$
declare
  t record;
begin
  for t in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind in ('r', 'p')
  loop
    execute format('alter table public.%I enable row level security', t.relname);
  end loop;
end $$;

-- Belt and braces: Supabase grants table privileges to anon/authenticated by default.
-- Take them away so even a mistakenly added policy cannot expose data. Skipped on plain Postgres
-- where those roles do not exist.
do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on all tables    in schema public from %I', r);
      execute format('revoke all on all sequences in schema public from %I', r);
      execute format('revoke all on all functions in schema public from %I', r);
      execute format('alter default privileges in schema public revoke all on tables    from %I', r);
      execute format('alter default privileges in schema public revoke all on sequences from %I', r);
      execute format('alter default privileges in schema public revoke all on functions from %I', r);
    end if;
  end loop;
end $$;

-- next_document_number() would otherwise be callable by anyone as a REST RPC.
revoke all on function next_document_number(text) from public;
