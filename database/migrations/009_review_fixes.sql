-- 009_review_fixes.sql
-- Changes from the team schema review. Re-runnable. 001-008 are left untouched.
--   1. Drafts only need a customer (contract: SubscriptionInput requires only customerId).
--   2. Invoices carry a billing snapshot of the customer.
--   3. product_variants can be archived instead of deleted.

-- ------------------------------------------- 1. nullable fields on draft subscriptions
alter table subscriptions alter column plan_id     drop not null;
alter table subscriptions alter column start_date  drop not null;
alter table subscriptions alter column expiry_date drop not null;

-- Everything past 'draft' must be fully specified. subscriptions_dates_ck (expiry_date >= start_date)
-- is left as is: a comparison with NULL is unknown, which CHECK treats as passing.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'subscriptions_complete_ck') then
    alter table subscriptions add constraint subscriptions_complete_ck
      check (status = 'draft' or (plan_id is not null and start_date is not null and expiry_date is not null));
  end if;
end $$;
comment on constraint subscriptions_complete_ck on subscriptions is
  'Only drafts may lack plan_id / start_date / expiry_date.';

-- LEFT JOIN plans so drafts without a plan still show (same columns, same order as 007).
create or replace view v_subscriptions with (security_invoker = true) as
select s.id, s.number, s.status, s.is_paused,
       s.customer_id, c.name as customer_name, c.email as customer_email,
       s.plan_id, p.name as plan_name, p.billing_period,
       p.allow_early_close, p.allow_pause, p.allow_renew, p.auto_close,
       s.template_id, s.start_date, s.expiry_date, s.payment_terms,
       s.quotation_valid_until, s.next_billing_date,
       coalesce(t.subtotal, 0)::numeric(12,2)  as subtotal,
       coalesce(t.tax_total, 0)::numeric(12,2) as tax_total,
       (coalesce(t.subtotal, 0) + coalesce(t.tax_total, 0))::numeric(12,2) as total,
       s.notes, s.created_by, s.created_at, s.updated_at, s.closed_at, s.close_reason
  from subscriptions s
  join customers c      on c.id = s.customer_id
  left join plans p     on p.id = s.plan_id
  left join lateral (
        select sum(l.amount) as subtotal, sum(l.tax_amount) as tax_total
          from subscription_lines l where l.subscription_id = s.id
       ) t on true;
comment on view v_subscriptions is
  'subscriptions + customer/plan names + subtotal/tax_total/total summed from subscription_lines. Plan columns are null for drafts without a plan.';

-- ------------------------------------------------------ 2. invoice billing snapshot
alter table invoices
  add column if not exists billing_name    text,
  add column if not exists billing_email   citext,
  add column if not exists billing_company text,
  add column if not exists billing_address jsonb;   -- {line1, line2, city, state, postalCode, country}
comment on column invoices.billing_name is
  'Snapshot of customers.name/email/company/address (+ tax id in billing_address) taken at invoice creation, so editing a customer never changes old invoices.';

-- Fill from the customer when the caller did not supply a snapshot.
create or replace function fill_invoice_billing_snapshot()
returns trigger
language plpgsql
as $$
declare
  c customers%rowtype;
begin
  if new.billing_name is null or new.billing_email is null then
    select * into c from customers where id = new.customer_id;
    new.billing_name    := coalesce(new.billing_name, c.name);
    new.billing_email   := coalesce(new.billing_email, c.email);
    new.billing_company := coalesce(new.billing_company, c.company);
    new.billing_address := coalesce(new.billing_address, jsonb_strip_nulls(jsonb_build_object(
      'line1', c.address_line1, 'line2', c.address_line2, 'city', c.city, 'state', c.state,
      'postalCode', c.postal_code, 'country', c.country, 'taxId', c.tax_id)));
  end if;
  return new;
end;
$$;

drop trigger if exists trg_invoices_billing_snapshot on invoices;
create trigger trg_invoices_billing_snapshot
  before insert on invoices
  for each row execute function fill_invoice_billing_snapshot();

-- Existing invoices get the customer's current details (best available), then the snapshot is required.
update invoices i
   set billing_name    = c.name,
       billing_email   = c.email,
       billing_company = c.company,
       billing_address = jsonb_strip_nulls(jsonb_build_object(
         'line1', c.address_line1, 'line2', c.address_line2, 'city', c.city, 'state', c.state,
         'postalCode', c.postal_code, 'country', c.country, 'taxId', c.tax_id))
  from customers c
 where c.id = i.customer_id and i.billing_name is null;

alter table invoices alter column billing_name  set not null;
alter table invoices alter column billing_email set not null;

-- v_invoices is deliberately NOT changed: 007 re-creates it with CREATE OR REPLACE, which cannot drop
-- columns, so adding some here would break re-running 007. Read the snapshot from invoices.billing_*.

-- ---------------------------------------------------------- 3. archive product variants
alter table product_variants add column if not exists is_active boolean not null default true;
comment on column product_variants.is_active is
  'Archive instead of delete when a variant is referenced by lines or templates.';
create index if not exists idx_product_variants_is_active on product_variants (is_active);
