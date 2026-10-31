-- 005_subscriptions.sql
-- Subscriptions, their lines, an audit trail of lifecycle events, and human-readable numbering.
-- State machine (API.md section 2): draft -> quotation -> confirmed -> active -> closed.
-- "Paused" is a flag (is_paused), not a status.

-- ------------------------------------------------------- document_sequences
-- Gap-tolerant, concurrency-safe counters for SUB-0001 / INV-2026-0001 style numbers.
-- Add a new document type by inserting one row; nothing else changes.
create table if not exists document_sequences (
  key           text primary key,                          -- e.g. 'subscription', 'invoice'
  prefix        text    not null,                          -- e.g. 'SUB', 'INV'
  include_year  boolean not null default false,            -- true: PREFIX-YYYY-NNNN and counter resets each year
  padding       integer not null default 4 check (padding between 1 and 12),
  current_year  integer,                                   -- year of last_value (only used when include_year)
  last_value    bigint  not null default 0 check (last_value >= 0)
);
comment on table document_sequences is
  'Counters behind subscriptions.number and invoices.number. Use next_document_number(key).';

insert into document_sequences (key, prefix, include_year, padding) values
  ('subscription', 'SUB', false, 4),
  ('invoice',      'INV', true,  4)
on conflict (key) do nothing;

-- Atomically takes the next number. The UPDATE row-locks the counter, so concurrent callers queue
-- instead of colliding. A rolled-back transaction rolls the counter back too (no gaps from rollbacks).
create or replace function next_document_number(p_key text)
returns text
language plpgsql
as $$
declare
  v_year integer := extract(year from now())::integer;
  s document_sequences%rowtype;
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

  return s.prefix || '-'
      || case when s.include_year then s.current_year::text || '-' else '' end
      || lpad(s.last_value::text, s.padding, '0');
end;
$$;
comment on function next_document_number(text) is
  'Returns the next formatted number for a document_sequences key, e.g. SUB-0001 or INV-2026-0001.';

-- ------------------------------------------------------------ subscriptions
create table if not exists subscriptions (
  id                     uuid primary key default gen_random_uuid(),
  number                 text        not null unique default next_document_number('subscription'),
  status                 text        not null default 'draft'
                           check (status in ('draft', 'quotation', 'confirmed', 'active', 'closed')),
  is_paused              boolean     not null default false,   -- billing pause flag; NOT a status
  customer_id            uuid        not null references customers (id) on delete restrict,
  plan_id                uuid        not null references plans (id) on delete restrict,
  template_id            uuid        references quotation_templates (id) on delete set null,
  start_date             date        not null,
  expiry_date            date        not null,
  payment_terms          text        not null default 'immediate'
                           check (payment_terms in ('immediate', 'net_15', 'net_30', 'net_45', 'net_60')),
  quotation_valid_until  date,                                 -- set when the quotation is sent
  next_billing_date      date,                                 -- null until activated; moved forward by the billing run
  notes                  text,
  created_by             uuid        references users (id) on delete restrict,
  closed_at              timestamptz,
  close_reason           text,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint subscriptions_dates_ck  check (expiry_date >= start_date),
  -- closed_at is filled exactly when the subscription is closed.
  constraint subscriptions_closed_ck check ((status = 'closed') = (closed_at is not null))
);
comment on table subscriptions is
  'A customer''s recurring contract. Totals are not stored here: see v_subscriptions (sum of lines).';
comment on column subscriptions.is_paused is
  'Billing is skipped while true. Kept as a flag so the five contract statuses stay exact.';
comment on column subscriptions.next_billing_date is
  'Billing run candidates: status=active AND NOT is_paused AND next_billing_date <= as_of.';
comment on constraint subscriptions_closed_ck on subscriptions is
  'closed_at is not null if and only if status = closed.';
select attach_updated_at('subscriptions');

-- Now that subscriptions exist, finish the FK left open in 004.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'fk_discount_subscriptions_subscription') then
    alter table discount_subscriptions
      add constraint fk_discount_subscriptions_subscription
      foreign key (subscription_id) references subscriptions (id) on delete cascade;
  end if;
end $$;

-- ------------------------------------------------------ subscription_lines
-- product_name / variant_label / tax_* are snapshots, so a locked (confirmed+) subscription keeps
-- showing what was agreed even if the catalogue is edited later.
create table if not exists subscription_lines (
  id               uuid primary key default gen_random_uuid(),
  subscription_id  uuid          not null references subscriptions (id) on delete cascade,
  product_id       uuid          not null references products (id) on delete restrict,
  variant_id       uuid,
  product_name     text          not null,
  variant_label    text,                                          -- e.g. 'Brand Odoo'
  quantity         integer       not null check (quantity >= 1),
  unit_price       numeric(12,2) not null check (unit_price >= 0), -- product price + variant extra, or override
  tax_id           uuid          references taxes (id) on delete set null,
  tax_name         text,
  tax_rate         numeric(12,4),                                 -- percent, or the fixed amount for computation=fixed
  tax_amount       numeric(12,2) not null default 0 check (tax_amount >= 0),
  amount           numeric(12,2) generated always as (round(quantity * unit_price, 2)) stored,
  sort_order       integer       not null default 0,
  constraint fk_sl_variant foreign key (variant_id, product_id)
    references product_variants (id, product_id) on delete set null (variant_id)
);
comment on table subscription_lines is
  'Lines of a subscription. amount = quantity * unit_price (generated, before tax). Editable only in draft/quotation.';
comment on column subscription_lines.tax_amount is
  'Computed by the application on the line amount, rounded half up to 2 decimals (API.md rule 5).';

-- ------------------------------------------------ subscription_status_history
create table if not exists subscription_status_history (
  id               uuid primary key default gen_random_uuid(),
  subscription_id  uuid        not null references subscriptions (id) on delete cascade,
  event            text        not null default 'status_change'
                     check (event in ('status_change', 'pause', 'resume', 'renew')),
  from_status      text        check (from_status is null or from_status in ('draft', 'quotation', 'confirmed', 'active', 'closed')),
  to_status        text        not null check (to_status in ('draft', 'quotation', 'confirmed', 'active', 'closed')),
  note             text,
  changed_by       uuid        references users (id) on delete restrict,   -- null = system job (e.g. auto-close)
  changed_at       timestamptz not null default now()
);
comment on table subscription_status_history is
  'Append-only audit log of lifecycle changes. Pause/resume/renew rows keep to_status = current status.';
