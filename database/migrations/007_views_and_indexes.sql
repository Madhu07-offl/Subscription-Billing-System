-- 007_views_and_indexes.sql
-- Derived data (views) and every secondary index. Re-runnable: views use CREATE OR REPLACE and
-- indexes use IF NOT EXISTS. Views list their columns explicitly so adding a column to a base table
-- never silently changes a view; to change a view's columns, DROP VIEW then recreate it here.
--
-- security_invoker = true (Postgres 15+, all current Supabase projects): views run with the CALLER's
-- permissions, so the RLS lock-down in 008 also covers them. Without it a view would run as its
-- owner and leak rows through Supabase's auto-generated REST API.

-- =============================================================== VIEWS

-- customers + hasLogin + activeSubscriptions (contract: Customer)
create or replace view v_customers with (security_invoker = true) as
select c.id, c.name, c.email, c.phone, c.company, c.tax_id,
       c.address_line1, c.address_line2, c.city, c.state, c.postal_code, c.country,
       c.created_at, c.updated_at,
       exists (select 1 from users u where u.customer_id = c.id) as has_login,
       (select count(*) from subscriptions s
         where s.customer_id = c.id and s.status = 'active')::integer as active_subscriptions
  from customers c;
comment on view v_customers is 'customers + has_login + active_subscriptions (contract Customer schema).';

-- subscriptions + totals computed from lines (never stored, so they cannot drift)
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
  join customers c on c.id = s.customer_id
  join plans p     on p.id = s.plan_id
  left join lateral (
        select sum(l.amount) as subtotal, sum(l.tax_amount) as tax_total
          from subscription_lines l where l.subscription_id = s.id
       ) t on true;
comment on view v_subscriptions is
  'subscriptions + customer/plan names + subtotal/tax_total/total summed from subscription_lines.';

-- Invoice summary: amount_due and is_overdue live ONLY here (API.md section 2).
create or replace view v_invoices with (security_invoker = true) as
select i.id, i.number, i.status,
       i.subscription_id, s.number as subscription_number,
       i.customer_id, c.name as customer_name, c.email as customer_email,
       i.billing_run_id, i.period_start, i.period_end, i.issue_date, i.due_date,
       i.subtotal, i.discount_total, i.tax_total, i.total, i.amount_paid,
       (i.total - i.amount_paid) as amount_due,
       (i.status = 'confirmed' and i.due_date < current_date and (i.total - i.amount_paid) > 0) as is_overdue,
       i.sent_at, i.notes, i.created_by, i.created_at, i.updated_at
  from invoices i
  join subscriptions s on s.id = i.subscription_id
  join customers c     on c.id = i.customer_id;
comment on view v_invoices is
  'Invoice summary. amount_due = total - amount_paid. is_overdue = status confirmed AND due_date < today AND amount_due > 0.';

-- Discount status: scheduled / running / expired / exhausted / inactive (contract Discount.status)
create or replace view v_discounts with (security_invoker = true) as
select d.id, d.name, d.type, d.value, d.scope, d.min_purchase_amount, d.min_quantity,
       d.start_date, d.end_date, d.usage_limit, d.used_count, d.is_active,
       case
         when not d.is_active                                         then 'inactive'
         when d.usage_limit is not null and d.used_count >= d.usage_limit then 'exhausted'
         when d.start_date > current_date                             then 'scheduled'
         when d.end_date is not null and d.end_date < current_date    then 'expired'
         else 'running'
       end as status,
       d.created_at, d.updated_at
  from discounts d;
comment on view v_discounts is 'discounts + derived status (inactive > exhausted > scheduled > expired > running).';

-- ----------------------------------------------------------------- reports
-- Row counts per status for dashboard cards (subscriptions.byStatus, invoicesByStatus).
create or replace view v_report_status_counts with (security_invoker = true) as
select 'subscription'::text as entity, status, count(*)::integer as count from subscriptions group by status
union all
select 'invoice'::text, status, count(*)::integer from invoices group by status;
comment on view v_report_status_counts is 'Counts per status for subscriptions and invoices. Missing statuses mean zero.';

-- Monthly recurring revenue per active, non-paused subscription (subtotal, before tax).
-- yearly / 12, weekly * 52 / 12, daily * 365 / 12 (contract DashboardSummary.mrr). SUM(monthly_amount) = MRR.
create or replace view v_report_mrr with (security_invoker = true) as
select v.id as subscription_id, v.customer_id, v.plan_id, v.billing_period,
       v.subtotal as period_amount,
       round(v.subtotal * case v.billing_period
                            when 'daily'   then 365.0 / 12
                            when 'weekly'  then 52.0 / 12
                            when 'monthly' then 1
                            when 'yearly'  then 1.0 / 12
                          end, 2) as monthly_amount
  from v_subscriptions v
 where v.status = 'active' and not v.is_paused;
comment on view v_report_mrr is 'Per-subscription monthly-normalised amount; sum it for MRR. Filter by plan_id/customer_id as needed.';

-- One fact table for revenue reports. Filter by day (+ customer_id / plan_id), then SUM(amount) per kind.
--   kind = 'invoiced'  -> invoice total on issue_date (confirmed + paid; drafts and cancelled excluded)
--   kind = 'collected' -> non-voided payment amount on payment_date (method filled for paymentsByMethod)
-- Group by date_trunc('day'|'week'|'month', day) for /reports/revenue.
create or replace view v_report_revenue_facts with (security_invoker = true) as
select i.issue_date as day, 'invoiced'::text as kind, i.customer_id, s.plan_id,
       i.subscription_id, i.id as invoice_id, null::text as method, i.total as amount
  from invoices i
  join subscriptions s on s.id = i.subscription_id
 where i.status in ('confirmed', 'paid')
union all
select p.payment_date, 'collected', i.customer_id, s.plan_id,
       i.subscription_id, i.id, p.method, p.amount
  from payments p
  join invoices i      on i.id = p.invoice_id
  join subscriptions s on s.id = i.subscription_id
 where not p.is_voided;
comment on view v_report_revenue_facts is
  'Invoiced (by issue_date) and collected (by payment_date) amounts as rows; aggregate with SUM(amount) per kind.';

-- =============================================================== INDEXES
-- Primary keys and UNIQUE constraints already create their own indexes; only extras are listed.
-- Text search: queries must use the same expression, e.g.  WHERE email::text ILIKE '%q%'.

-- identity
create index if not exists idx_users_role              on users (role);
create index if not exists idx_users_is_active         on users (is_active);
create index if not exists idx_users_name_trgm         on users using gin (name gin_trgm_ops);
create index if not exists idx_users_email_trgm        on users using gin ((email::text) gin_trgm_ops);
create index if not exists idx_customers_name_trgm     on customers using gin (name gin_trgm_ops);
create index if not exists idx_customers_email_trgm    on customers using gin ((email::text) gin_trgm_ops);
create index if not exists idx_customers_company_trgm  on customers using gin (company gin_trgm_ops);
create index if not exists idx_prt_user_id             on password_reset_tokens (user_id);
create index if not exists idx_prt_open_expiry         on password_reset_tokens (expires_at) where used_at is null;

-- catalogue
create index if not exists idx_products_type           on products (type);
create index if not exists idx_products_is_active      on products (is_active);
create index if not exists idx_products_name_trgm      on products using gin (name gin_trgm_ops);
create index if not exists idx_plans_billing_period    on plans (billing_period);
create index if not exists idx_plans_is_active         on plans (is_active);
create index if not exists idx_plans_availability      on plans (available_from, available_to);
create index if not exists idx_plans_name_trgm         on plans using gin (name gin_trgm_ops);
create index if not exists idx_taxes_is_active         on taxes (is_active);
create index if not exists idx_qt_plan_id              on quotation_templates (plan_id);
create index if not exists idx_qt_name_trgm            on quotation_templates using gin (name gin_trgm_ops);
create index if not exists idx_qtl_template_id         on quotation_template_lines (template_id);
create index if not exists idx_qtl_product_id          on quotation_template_lines (product_id);

-- discounts
create index if not exists idx_discounts_is_active     on discounts (is_active);
create index if not exists idx_discounts_dates         on discounts (start_date, end_date);
create index if not exists idx_discounts_name_trgm     on discounts using gin (name gin_trgm_ops);
create index if not exists idx_discount_products_product on discount_products (product_id);
create index if not exists idx_discount_subs_subscription on discount_subscriptions (subscription_id);
create index if not exists idx_discount_usages_invoice on discount_usages (invoice_id);

-- subscriptions
create index if not exists idx_subscriptions_status        on subscriptions (status);
create index if not exists idx_subscriptions_customer_id   on subscriptions (customer_id);
create index if not exists idx_subscriptions_plan_id       on subscriptions (plan_id);
create index if not exists idx_subscriptions_next_billing  on subscriptions (next_billing_date);
create index if not exists idx_subscriptions_expiry        on subscriptions (expiry_date);
create index if not exists idx_subscriptions_number_trgm   on subscriptions using gin (number gin_trgm_ops);
-- The billing run's candidate query: tiny index containing only billable subscriptions.
create index if not exists idx_subscriptions_billable
  on subscriptions (next_billing_date) where status = 'active' and not is_paused;
create index if not exists idx_sub_lines_subscription_id   on subscription_lines (subscription_id);
create index if not exists idx_sub_lines_product_id        on subscription_lines (product_id);
create index if not exists idx_sub_history_subscription    on subscription_status_history (subscription_id, changed_at desc);

-- billing
create index if not exists idx_billing_runs_started_at     on billing_runs (started_at desc);
create index if not exists idx_invoices_status             on invoices (status);
create index if not exists idx_invoices_customer_id        on invoices (customer_id);
create index if not exists idx_invoices_subscription_id    on invoices (subscription_id);
create index if not exists idx_invoices_billing_run_id     on invoices (billing_run_id);
create index if not exists idx_invoices_due_date           on invoices (due_date);
create index if not exists idx_invoices_issue_date         on invoices (issue_date);
create index if not exists idx_invoices_number_trgm        on invoices using gin (number gin_trgm_ops);
-- Overdue / outstanding lookups only ever look at confirmed invoices.
create index if not exists idx_invoices_confirmed_due
  on invoices (due_date) where status = 'confirmed';
create index if not exists idx_invoice_lines_invoice_id    on invoice_lines (invoice_id);
create index if not exists idx_invoice_lines_product_id    on invoice_lines (product_id);
create index if not exists idx_invoice_lines_discount_id   on invoice_lines (discount_id) where discount_id is not null;
create index if not exists idx_payments_invoice_id         on payments (invoice_id);
create index if not exists idx_payments_payment_date       on payments (payment_date);
create index if not exists idx_payments_method             on payments (method);
