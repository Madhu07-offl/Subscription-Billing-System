-- 004_discounts.sql
-- Discount rules and their usage accounting (API.md rule 6).
-- Order note: subscriptions (005) and invoices (006) do not exist yet, so the FKs from
-- discount_subscriptions.subscription_id and discount_usages.invoice_id are added in those files.

create table if not exists discounts (
  id                  uuid primary key default gen_random_uuid(),
  name                text          not null check (length(btrim(name)) > 0),
  type                text          not null check (type in ('percentage', 'fixed')),
  value               numeric(12,4) not null check (value >= 0),
  scope               text          not null check (scope in ('products', 'subscriptions')),
  min_purchase_amount numeric(12,2) check (min_purchase_amount is null or min_purchase_amount >= 0),
  min_quantity        integer       check (min_quantity is null or min_quantity >= 1),
  start_date          date          not null,
  end_date            date,                                  -- null = open ended
  usage_limit         integer       check (usage_limit is null or usage_limit >= 1),   -- null = unlimited
  used_count          integer       not null default 0 check (used_count >= 0),
  is_active           boolean       not null default true,   -- DELETE /discounts/{id} deactivates
  created_at          timestamptz   not null default now(),
  updated_at          timestamptz   not null default now(),
  constraint discounts_percentage_range_ck check (type <> 'percentage' or value <= 100),
  constraint discounts_dates_ck            check (end_date is null or end_date >= start_date),
  -- Hard stop against over-use, even if two billing runs race.
  constraint discounts_usage_limit_ck      check (usage_limit is null or used_count <= usage_limit)
);
comment on table discounts is
  'Discount rules. used_count is kept in sync by trigger from discount_usages. '
  'The API "status" (scheduled/running/expired/exhausted/inactive) is derived in v_discounts.';
comment on column discounts.used_count is
  'Number of invoices the discount currently applies to. Maintained by trg_discount_usages_sync; do not update from app code.';
select attach_updated_at('discounts');

-- scope = products: which products the rule touches.
create table if not exists discount_products (
  discount_id uuid not null references discounts (id) on delete cascade,
  product_id  uuid not null references products (id) on delete cascade,
  primary key (discount_id, product_id)
);
comment on table discount_products is 'Products a scope=products discount applies to.';

-- scope = subscriptions: which subscriptions. No rows = applies to ALL subscriptions.
-- FK to subscriptions is added in 005_subscriptions.sql.
create table if not exists discount_subscriptions (
  discount_id     uuid not null references discounts (id) on delete cascade,
  subscription_id uuid not null,
  primary key (discount_id, subscription_id)
);
comment on table discount_subscriptions is
  'Subscriptions a scope=subscriptions discount applies to. No rows = all subscriptions.';

-- One row per (discount, invoice) it was applied to. Cancelling the invoice gives the usage back:
-- set released_at and the trigger below decrements discounts.used_count.
-- FK to invoices is added in 006_billing.sql.
create table if not exists discount_usages (
  id          uuid primary key default gen_random_uuid(),
  discount_id uuid        not null references discounts (id) on delete restrict,
  invoice_id  uuid        not null,
  used_at     timestamptz not null default now(),
  released_at timestamptz,
  constraint uq_discount_usage unique (discount_id, invoice_id),
  constraint discount_usages_release_ck check (released_at is null or released_at >= used_at)
);
comment on table discount_usages is
  'Ledger of discount applications per invoice. Insert = +1 used_count; set released_at (invoice cancelled) = -1.';

-- Keeps discounts.used_count equal to the number of unreleased usages, atomically.
-- The CHECK on discounts then rejects anything beyond usage_limit.
create or replace function sync_discount_used_count()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' then
    if new.released_at is null then
      update discounts set used_count = used_count + 1 where id = new.discount_id;
    end if;
  elsif tg_op = 'UPDATE' then
    if old.released_at is null and new.released_at is not null then
      update discounts set used_count = used_count - 1 where id = new.discount_id;
    elsif old.released_at is not null and new.released_at is null then
      update discounts set used_count = used_count + 1 where id = new.discount_id;
    end if;
  elsif tg_op = 'DELETE' then
    if old.released_at is null then
      update discounts set used_count = used_count - 1 where id = old.discount_id;
    end if;
  end if;
  return null;
end;
$$;

drop trigger if exists trg_discount_usages_sync on discount_usages;
create trigger trg_discount_usages_sync
  after insert or update of released_at or delete on discount_usages
  for each row execute function sync_discount_used_count();
