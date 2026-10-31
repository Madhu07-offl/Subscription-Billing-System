-- 006_billing.sql
-- Billing runs, invoices (+ immutable line snapshots) and payments.
-- Financial records use ON DELETE RESTRICT: they are cancelled/voided, never deleted.

-- ------------------------------------------------------------- billing_runs
create table if not exists billing_runs (
  id              uuid primary key default gen_random_uuid(),
  as_of           date        not null,
  dry_run         boolean     not null default false,
  due_count       integer     not null default 0 check (due_count >= 0),
  created_count   integer     not null default 0 check (created_count >= 0),
  already_billed  integer     not null default 0 check (already_billed >= 0),
  failed_count    integer     not null default 0 check (failed_count >= 0),
  failures        jsonb       not null default '[]'::jsonb,   -- [{subscriptionId, number, reason}]
  triggered_by    uuid        references users (id) on delete restrict,   -- null = scheduled job
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  constraint billing_runs_finished_ck check (finished_at is null or finished_at >= started_at)
);
comment on table billing_runs is
  'One row per POST /billing/run (BillingRunResult.runId + counts). Invoices link back via invoices.billing_run_id.';

-- ----------------------------------------------------------------- invoices
create table if not exists invoices (
  id               uuid primary key default gen_random_uuid(),
  number           text          not null unique default next_document_number('invoice'),
  status           text          not null default 'draft'
                     check (status in ('draft', 'confirmed', 'paid', 'cancelled')),
  subscription_id  uuid          not null references subscriptions (id) on delete restrict,
  customer_id      uuid          not null references customers (id) on delete restrict,   -- copied from the subscription at billing time
  billing_run_id   uuid          references billing_runs (id) on delete set null,
  period_start     date          not null,
  period_end       date          not null,
  issue_date       date,                                   -- set on confirm
  due_date         date,                                   -- issue_date + payment terms, set on confirm
  subtotal         numeric(12,2) not null default 0 check (subtotal >= 0),
  discount_total   numeric(12,2) not null default 0 check (discount_total >= 0),
  tax_total        numeric(12,2) not null default 0 check (tax_total >= 0),
  total            numeric(12,2) not null default 0 check (total >= 0),
  amount_paid      numeric(12,2) not null default 0 check (amount_paid >= 0),
  sent_at          timestamptz,
  notes            text,
  created_by       uuid          references users (id) on delete restrict,
  created_at       timestamptz   not null default now(),
  updated_at       timestamptz   not null default now(),
  constraint invoices_period_ck       check (period_end >= period_start),
  constraint invoices_due_ck          check (due_date is null or issue_date is null or due_date >= issue_date),
  -- API.md rule 7: total = subtotal - discountTotal + taxTotal
  constraint invoices_total_ck        check (total = subtotal - discount_total + tax_total),
  constraint invoices_not_overpaid_ck check (amount_paid <= total),
  -- Confirmed and paid invoices must carry their dates.
  constraint invoices_dates_set_ck    check (status not in ('confirmed', 'paid') or (issue_date is not null and due_date is not null)),
  -- A cancelled invoice cannot have money on it ("Cancel (no payments allowed)").
  constraint invoices_cancel_ck       check (status <> 'cancelled' or amount_paid = 0)
);
comment on table invoices is
  'Invoices. amount_due and is_overdue are NOT stored: see v_invoices. Header amounts are a snapshot taken at billing time.';
comment on column invoices.amount_paid is
  'Sum of non-voided payments. Maintained by trg_payments_sync_invoice; also flips confirmed <-> paid.';
comment on constraint invoices_total_ck on invoices is
  'total = subtotal - discount_total + tax_total (API.md rule 7).';
select attach_updated_at('invoices');

-- Double-billing guard (API.md rule 8): one live invoice per subscription per period.
-- Partial, so a cancelled invoice releases its key and the period can be billed again.
create unique index if not exists uq_invoices_subscription_period
  on invoices (subscription_id, period_start)
  where status <> 'cancelled';
comment on index uq_invoices_subscription_period is
  'Blocks double billing: unique (subscription_id, period_start) for all non-cancelled invoices.';

-- Finish the FK left open in 004.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'fk_discount_usages_invoice') then
    alter table discount_usages
      add constraint fk_discount_usages_invoice
      foreign key (invoice_id) references invoices (id) on delete cascade;
  end if;
end $$;

-- ------------------------------------------------------------ invoice_lines
-- Every value that can change in the catalogue is copied here, so an issued invoice never changes
-- when a product is renamed, a price is edited or a tax rate moves.
create table if not exists invoice_lines (
  id               uuid primary key default gen_random_uuid(),
  invoice_id       uuid          not null references invoices (id) on delete cascade,
  product_id       uuid          not null references products (id) on delete restrict,
  description      text          not null,                  -- snapshot: product name + variant label
  quantity         integer       not null check (quantity >= 1),
  unit_price       numeric(12,2) not null check (unit_price >= 0),
  discount_id      uuid          references discounts (id) on delete restrict,
  discount_name    text,                                    -- snapshot
  discount_amount  numeric(12,2) not null default 0 check (discount_amount >= 0),
  tax_id           uuid          references taxes (id) on delete restrict,
  tax_name         text,                                    -- snapshot
  tax_rate         numeric(12,4),                           -- snapshot: percent, or fixed amount for computation=fixed
  tax_amount       numeric(12,2) not null default 0 check (tax_amount >= 0),
  amount           numeric(12,2) generated always as (round(quantity * unit_price - discount_amount, 2)) stored,
  sort_order       integer       not null default 0,
  constraint invoice_lines_discount_ck check (discount_amount <= round(quantity * unit_price, 2)),
  constraint invoice_lines_discount_ref_ck check (discount_amount = 0 or discount_id is not null)
);
comment on table invoice_lines is
  'Invoice lines with snapshots (description, unit_price, discount_*, tax_*). amount = qty*unit_price - discount_amount, before tax.';

-- ----------------------------------------------------------------- payments
create table if not exists payments (
  id            uuid primary key default gen_random_uuid(),
  invoice_id    uuid          not null references invoices (id) on delete restrict,
  method        text          not null check (method in ('cash', 'bank_transfer', 'card', 'upi', 'cheque', 'other')),
  amount        numeric(12,2) not null check (amount > 0),
  payment_date  date          not null,
  reference     text,                                      -- bank ref, cheque number, transaction id
  note          text,
  is_voided     boolean       not null default false,      -- DELETE /payments/{id} voids, never deletes
  voided_at     timestamptz,
  voided_by     uuid          references users (id) on delete restrict,
  recorded_by   uuid          references users (id) on delete restrict,
  created_at    timestamptz   not null default now(),
  updated_at    timestamptz   not null default now(),
  constraint payments_void_ck check (is_voided = (voided_at is not null))
);
comment on table payments is
  'Money received against an invoice. Voided rows stay for audit and are ignored by amount_paid and revenue reports.';
select attach_updated_at('payments');

-- Keeps invoices.amount_paid and the confirmed <-> paid status consistent with payments, in the
-- same transaction as the payment change (API.md rule 9 and section 2: "paid is set by the server
-- when payments cover the total. Voiding a payment moves it back to confirmed").
create or replace function sync_invoice_payment_state()
returns trigger
language plpgsql
as $$
declare
  v_invoice_id uuid := coalesce(new.invoice_id, old.invoice_id);
  v_status     text;
begin
  -- Lock the invoice first so concurrent payments are summed one after another.
  select status into v_status from invoices where id = v_invoice_id for update;

  if tg_op = 'INSERT' and v_status <> 'confirmed' then
    raise exception 'payments can only be recorded on confirmed invoices (invoice is %)', v_status
      using errcode = 'check_violation';
  end if;

  update invoices i
     set amount_paid = p.paid,
         status = case
                    when i.status in ('confirmed', 'paid')
                      then case when p.paid >= i.total then 'paid' else 'confirmed' end
                    else i.status
                  end
    from (select coalesce(sum(amount), 0) as paid
            from payments
           where invoice_id = v_invoice_id and not is_voided) p
   where i.id = v_invoice_id;

  return null;
end;
$$;

drop trigger if exists trg_payments_sync_invoice on payments;
create trigger trg_payments_sync_invoice
  after insert or update of amount, is_voided or delete on payments
  for each row execute function sync_invoice_payment_state();
