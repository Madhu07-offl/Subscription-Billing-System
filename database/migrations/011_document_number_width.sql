-- 011_document_number_width.sql
-- next_document_number() padded with lpad(), which TRUNCATES when the number is longer than the padding:
-- with padding = 4 the 10,000th document became '...-1000', colliding with the 1,000th and failing the insert
-- on the UNIQUE number column (invoices reset yearly, subscriptions never do).
-- Fix: pad only numbers shorter than the padding; longer ones simply grow (INV-2026-10000).
-- Re-runnable: CREATE OR REPLACE with the same signature. Existing numbers are unchanged.

create or replace function next_document_number(p_key text)
returns text
language plpgsql
as $$
declare
  v_year integer := extract(year from now())::integer;
  s document_sequences%rowtype;
  v_digits text;
begin
  update document_sequences
     set last_value   = case when include_year and current_year is distinct from v_year then 1
                             else last_value + 1 end,
         current_year = case when include_year then v_year else null end
   where key = p_key
   returning * into s;

  if not found then
    raise exception 'unknown document sequence: %', p_key;
  end if;

  v_digits := s.last_value::text;
  if length(v_digits) < s.padding then
    v_digits := lpad(v_digits, s.padding, '0');
  end if;

  return s.prefix || '-'
      || case when s.include_year then s.current_year::text || '-' else '' end
      || v_digits;
end;
$$;
comment on function next_document_number(text) is
  'Returns the next formatted number for a document_sequences key, e.g. SUB-0001 or INV-2026-0001. '
  'Numbers wider than the padding are not truncated (INV-2026-10000).';
