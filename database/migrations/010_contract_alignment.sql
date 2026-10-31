-- 010_contract_alignment.sql
-- Fixes from the PR #1 review (Prakash). Re-runnable. 001-006, 008 and 009 are left untouched.
--   1. subscription_status_history.event uses the contract's StatusChange.event values.
--   2. payment_terms is only required once a subscription leaves 'draft'.
--   3. A cancelled invoice can never be moved back (discount usage was already released).
--   4. A 'paid' invoice must be fully paid.
--   5. Payments are immutable except for voiding and annotating.
--   6. v_invoices exposes the billing snapshot columns.

-- ------------------------------------------ 1. status history event matches the contract
-- Contract StatusChange.event: created, status_change, paused, resumed, renewed.
alter table subscription_status_history drop constraint if exists subscription_status_history_event_check;

update subscription_status_history set event = 'paused'  where event = 'pause';
update subscription_status_history set event = 'resumed' where event = 'resume';
update subscription_status_history set event = 'renewed' where event = 'renew';

alter table subscription_status_history
  add constraint subscription_status_history_event_check
  check (event in ('created', 'status_change', 'paused', 'resumed', 'renewed'));
alter table subscription_status_history alter column event set default 'status_change';
comment on table subscription_status_history is
  'Append-only audit log of lifecycle changes. paused/resumed/renewed rows keep to_status = current status.';

-- ------------------------------------------------- 2. payment_terms required after draft
alter table subscriptions alter column payment_terms drop not null;
alter table subscriptions alter column payment_terms drop default;

-- Existing rows keep the value they have; only new drafts start with null.
alter table subscriptions drop constraint if exists subscriptions_complete_ck;
alter table subscriptions add constraint subscriptions_complete_ck
  check (status = 'draft'
         or (plan_id is not null and start_date is not null and expiry_date is not null
             and payment_terms is not null));
comment on constraint subscriptions_complete_ck on subscriptions is
  'Only drafts may lack plan_id / start_date / expiry_date / payment_terms.';

-- ------------------------------------------- 3. a cancelled invoice stays cancelled
-- Cancelling releases the invoice's discount usages (trg_invoices_release_discounts). Reviving the
-- invoice would leave used_count lower than the discounts actually in force.
create or replace function block_uncancel_invoice()
returns trigger
language plpgsql
as $$
begin
  raise exception 'invoice % is cancelled and cannot change status; create a new invoice instead', old.number
    using errcode = 'check_violation';
end;
$$;

drop trigger if exists trg_invoices_block_uncancel on invoices;
create trigger trg_invoices_block_uncancel
  before update of status on invoices
  for each row
  when (old.status = 'cancelled' and new.status <> 'cancelled')
  execute function block_uncancel_invoice();

-- ------------------------------------------------ 4. paid implies fully paid
alter table invoices drop constraint if exists invoices_paid_ck;
alter table invoices add constraint invoices_paid_ck
  check (status <> 'paid' or amount_paid >= total);
comment on constraint invoices_paid_ck on invoices is
  'An invoice may only be paid when non-voided payments cover the total.';

-- ---------------------------------------------------- 5. payments are immutable
-- Only voided_at, voided_by, note and reference may change. Anything else would silently move money
-- between invoices or change what was received.
create or replace function reject_payment_edit()
returns trigger
language plpgsql
as $$
begin
  if new.id           is distinct from old.id
  or new.invoice_id   is distinct from old.invoice_id
  or new.amount       is distinct from old.amount
  or new.method       is distinct from old.method
  or new.payment_date is distinct from old.payment_date
  or new.recorded_by  is distinct from old.recorded_by
  or new.created_at   is distinct from old.created_at then
    raise exception 'payments cannot be edited (only voided_at, voided_by, note and reference); void and re-record instead'
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_payments_immutable on payments;
create trigger trg_payments_immutable
  before update on payments
  for each row execute function reject_payment_edit();

-- ------------------------------------------------ 6. v_invoices with billing snapshot
-- Nothing depends on v_invoices, so it can be dropped and recreated with the extra columns.
drop view if exists v_invoices;
create view v_invoices with (security_invoker = true) as
select i.id, i.number, i.status,
       i.subscription_id, s.number as subscription_number,
       i.customer_id, c.name as customer_name, c.email as customer_email,
       i.billing_name, i.billing_email, i.billing_company, i.billing_address,
       i.billing_run_id, i.period_start, i.period_end, i.issue_date, i.due_date,
       i.subtotal, i.discount_total, i.tax_total, i.total, i.amount_paid,
       (i.total - i.amount_paid) as amount_due,
       (i.status = 'confirmed' and i.due_date < current_date and (i.total - i.amount_paid) > 0) as is_overdue,
       i.sent_at, i.notes, i.created_by, i.created_at, i.updated_at
  from invoices i
  join subscriptions s on s.id = i.subscription_id
  join customers c     on c.id = i.customer_id;
comment on view v_invoices is
  'Invoice summary. customer_* is the live customer; billing_* is the snapshot taken at invoice creation. amount_due = total - amount_paid. is_overdue = status confirmed AND due_date < today AND amount_due > 0.';
