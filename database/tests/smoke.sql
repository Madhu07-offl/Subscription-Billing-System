-- smoke.sql
-- Behavioural checks for the schema. Run AFTER migrations + seed. Everything happens inside one
-- transaction that is rolled back, so it leaves no data behind. Any failed expectation raises.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/smoke.sql

begin;

do $$
declare
  v_sub uuid; v_draft uuid; v_inv uuid; v_inv2 uuid; v_inv3 uuid; v_pay uuid; v_n int; v_row record;
  cust constant uuid := '00000000-0000-4000-8000-000000000101';
  plan constant uuid := '00000000-0000-4000-8000-000000000301';
  prod constant uuid := '00000000-0000-4000-8000-000000000201';
  vari constant uuid := '00000000-0000-4000-8000-000000000211';
  disc constant uuid := '00000000-0000-4000-8000-000000000501';
  tax  constant uuid := '00000000-0000-4000-8000-000000000401';
begin
  -- a draft needs only a customer; later statuses need plan and dates
  insert into subscriptions (customer_id) values (cust) returning id into v_draft;
  select * into v_row from v_subscriptions where id = v_draft;
  assert v_row.status = 'draft' and v_row.plan_id is null and v_row.plan_name is null, 'customer-only draft shows in v_subscriptions';
  begin update subscriptions set status = 'quotation' where id = v_draft; raise exception 'FAIL: quotation without plan_id';
  exception when check_violation then null; end;
  begin insert into subscriptions (customer_id, status, start_date, expiry_date) values (cust, 'quotation', '2026-10-01', '2027-09-30');
        raise exception 'FAIL: quotation insert without plan_id';
  exception when check_violation then null; end;

  -- numbering
  insert into subscriptions (customer_id, plan_id, start_date, expiry_date)
  values (cust, plan, '2026-10-01', '2027-09-30') returning id into v_sub;
  assert (select number from subscriptions where id = v_sub) ~ '^SUB-\d{4}$', 'subscription number format';

  -- variant must belong to the product
  begin
    insert into subscription_lines (subscription_id, product_id, variant_id, product_name, quantity, unit_price)
    values (v_sub, prod, gen_random_uuid(), 'x', 1, 1);
    raise exception 'FAIL: foreign variant accepted';
  exception when foreign_key_violation then null; end;

  -- line amount + view totals (1000 + 560 variant, qty 2, 18% tax)
  insert into subscription_lines (subscription_id, product_id, variant_id, product_name, variant_label,
                                  quantity, unit_price, tax_id, tax_name, tax_rate, tax_amount)
  values (v_sub, prod, vari, 'Brightloop CRM', 'Brand Odoo', 2, 1560.00, tax, 'GST 18%', 18, 561.60);
  select * into v_row from v_subscriptions where id = v_sub;
  assert v_row.subtotal = 3120.00 and v_row.tax_total = 561.60 and v_row.total = 3681.60, 'subscription totals';

  -- CHECK constraints
  begin insert into subscription_lines (subscription_id, product_id, product_name, quantity, unit_price)
        values (v_sub, prod, 'x', 0, 1); raise exception 'FAIL: qty 0 accepted';
  exception when check_violation then null; end;
  begin update subscriptions set expiry_date = '2026-01-01' where id = v_sub; raise exception 'FAIL: expiry < start';
  exception when check_violation then null; end;
  begin update subscriptions set status = 'closed' where id = v_sub; raise exception 'FAIL: closed without closed_at';
  exception when check_violation then null; end;
  begin insert into plans (name, price, billing_period, available_from, available_to)
        values ('bad', 1, 'monthly', '2026-02-01', '2026-01-01'); raise exception 'FAIL: available_to < from';
  exception when check_violation then null; end;

  -- invoice + double billing guard
  insert into invoices (subscription_id, customer_id, period_start, period_end, subtotal, discount_total, tax_total, total)
  values (v_sub, cust, '2026-10-01', '2026-10-31', 3120.00, 312.00, 505.44, 3313.44) returning id into v_inv;
  assert (select number from invoices where id = v_inv) ~ '^INV-\d{4}-\d{4}$', 'invoice number format';
  -- billing snapshot is filled from the customer and survives customer edits
  select * into v_row from invoices where id = v_inv;
  assert v_row.billing_name = 'Asha Rao' and v_row.billing_email = 'asha.rao@example.com'
     and v_row.billing_company = 'Rao Textiles Pvt Ltd' and v_row.billing_address->>'city' = 'Bengaluru', 'invoice snapshot filled';
  update customers set name = 'Renamed', city = 'Pune' where id = cust;
  assert (select billing_name from invoices where id = v_inv) = 'Asha Rao'
     and (select billing_address->>'city' from invoices where id = v_inv) = 'Bengaluru', 'customer edit leaves invoice snapshot alone';
  update customers set name = 'Asha Rao', city = 'Bengaluru' where id = cust;
  begin
    insert into invoices (subscription_id, customer_id, period_start, period_end)
    values (v_sub, cust, '2026-10-01', '2026-10-31'); raise exception 'FAIL: double billing allowed';
  exception when unique_violation then null; end;
  begin
    insert into invoices (subscription_id, customer_id, period_start, period_end, subtotal, total)
    values (v_sub, cust, '2026-11-01', '2026-11-30', 100, 50); raise exception 'FAIL: bad total accepted';
  exception when check_violation then null; end;

  -- discount usage: +1 on insert, limit enforced, give back on release
  insert into discount_usages (discount_id, invoice_id) values (disc, v_inv);
  assert (select used_count from discounts where id = disc) = 1, 'used_count +1';
  update discount_usages set released_at = now() where discount_id = disc and invoice_id = v_inv;
  assert (select used_count from discounts where id = disc) = 0, 'used_count given back';
  update discounts set usage_limit = 1, used_count = 0 where id = disc;
  update discount_usages set released_at = null where discount_id = disc and invoice_id = v_inv;  -- re-activate: +1
  begin update discounts set used_count = 2 where id = disc; raise exception 'FAIL: used_count > limit';
  exception when check_violation then null; end;
  assert (select status from v_discounts where id = disc) = 'exhausted', 'discount status exhausted';

  -- payments: draft invoice rejects payment
  begin insert into payments (invoice_id, method, amount, payment_date) values (v_inv, 'cash', 10, current_date);
        raise exception 'FAIL: payment on draft';
  exception when check_violation then null; end;
  begin insert into payments (invoice_id, method, amount, payment_date) values (v_inv, 'cash', 0, current_date);
        raise exception 'FAIL: zero payment';
  exception when check_violation then null; end;

  -- confirm: overdue logic
  update invoices set status = 'confirmed', issue_date = current_date - 40, due_date = current_date - 10 where id = v_inv;
  assert (select is_overdue from v_invoices where id = v_inv), 'overdue when unpaid and past due';

  -- partial payment keeps confirmed, full payment flips to paid, void flips back
  insert into payments (invoice_id, method, amount, payment_date) values (v_inv, 'upi', 1000, current_date) returning id into v_pay;
  select * into v_row from v_invoices where id = v_inv;
  assert v_row.status = 'confirmed' and v_row.amount_paid = 1000 and v_row.amount_due = 2313.44 and v_row.is_overdue, 'partial payment';
  begin insert into payments (invoice_id, method, amount, payment_date) values (v_inv, 'cash', 5000, current_date);
        raise exception 'FAIL: overpayment';
  exception when check_violation then null; end;
  insert into payments (invoice_id, method, amount, payment_date) values (v_inv, 'cash', 2313.44, current_date);
  select * into v_row from v_invoices where id = v_inv;
  assert v_row.status = 'paid' and v_row.amount_due = 0 and not v_row.is_overdue, 'fully paid';
  update payments set voided_at = now() where id = v_pay;   -- only voided_at is set; is_voided is derived
  assert (select is_voided from payments where id = v_pay), 'is_voided derived from voided_at';
  select * into v_row from v_invoices where id = v_inv;
  assert v_row.status = 'confirmed' and v_row.amount_paid = 2313.44, 'void moves back to confirmed';

  -- cancel is rejected while non-voided payments exist
  begin update invoices set status = 'cancelled' where id = v_inv; raise exception 'FAIL: cancelled with live payment';
  exception when check_violation then null; end;
  assert (select status from invoices where id = v_inv) = 'confirmed', 'rejected cancel left status alone';

  -- cancel releases the period key AND gives discount usage back
  update payments set voided_at = now() where invoice_id = v_inv and not is_voided;
  assert (select amount_paid from invoices where id = v_inv) = 0, 'all payments voided -> amount_paid 0';
  assert (select used_count from discounts where id = disc) = 1, 'usage still held before cancel';
  update invoices set status = 'cancelled' where id = v_inv;
  assert (select used_count from discounts where id = disc) = 0, 'cancel gives discount usage back';
  assert (select released_at is not null from discount_usages where discount_id = disc and invoice_id = v_inv), 'released_at set on cancel';
  insert into invoices (subscription_id, customer_id, period_start, period_end)
  values (v_sub, cust, '2026-10-01', '2026-10-31') returning id into v_inv2;

  -- auth rules
  begin insert into users (name, email, password_hash, role) values ('x', 'ADMIN@brightloop.test', 'h', 'admin');
        raise exception 'FAIL: case-insensitive email dup';
  exception when unique_violation then null; end;
  begin insert into users (name, email, password_hash, role) values ('x', 'c@x.test', 'h', 'customer');
        raise exception 'FAIL: customer without customer_id';
  exception when check_violation then null; end;

  -- reports
  -- cancelled invoice + voided payments must not appear in revenue facts
  select count(*) into v_n from v_report_revenue_facts where invoice_id = v_inv; assert v_n = 0, 'revenue facts exclude cancelled/voided';
  assert (select is_active from product_variants where id = vari), 'variant active by default';
  perform * from v_report_status_counts; perform * from v_report_mrr; perform * from v_customers;

  -- 010: contract alignment
  -- status history events follow the contract
  insert into subscription_status_history (subscription_id, event, from_status, to_status) values (v_sub, 'created', null, 'draft');
  insert into subscription_status_history (subscription_id, event, from_status, to_status) values (v_sub, 'paused', 'active', 'active');
  begin insert into subscription_status_history (subscription_id, event, to_status) values (v_sub, 'pause', 'active');
        raise exception 'FAIL: legacy event name accepted';
  exception when check_violation then null; end;
  -- payment_terms: null on a new draft, required past draft
  assert (select payment_terms is null from subscriptions where id = v_draft), 'new draft has null payment_terms';
  begin insert into subscriptions (customer_id, plan_id, start_date, expiry_date, status)
        values (cust, plan, '2026-10-01', '2027-09-30', 'quotation'); raise exception 'FAIL: quotation without payment_terms';
  exception when check_violation then null; end;
  -- cancelled invoice cannot go back
  begin update invoices set status = 'draft' where id = v_inv; raise exception 'FAIL: cancelled invoice revived';
  exception when check_violation then null; end;
  assert (select status from invoices where id = v_inv) = 'cancelled', 'cancelled invoice stays cancelled';
  -- paid needs full payment
  insert into invoices (subscription_id, customer_id, period_start, period_end, subtotal, total)
  values (v_sub, cust, '2026-12-01', '2026-12-31', 100, 100) returning id into v_inv3;
  begin update invoices set status = 'paid', issue_date = current_date, due_date = current_date where id = v_inv3;
        raise exception 'FAIL: paid without payment';
  exception when check_violation then null; end;
  -- payments are immutable apart from void/note/reference
  update invoices set status = 'confirmed', issue_date = current_date, due_date = current_date where id = v_inv3;
  insert into payments (invoice_id, method, amount, payment_date) values (v_inv3, 'cash', 0.01, current_date) returning id into v_pay;
  begin update payments set invoice_id = v_inv where id = v_pay; raise exception 'FAIL: payment moved to another invoice';
  exception when check_violation then null; end;
  begin update payments set amount = 5 where id = v_pay; raise exception 'FAIL: payment amount edited';
  exception when check_violation then null; end;
  update payments set note = 'ok', reference = 'ref-1' where id = v_pay;
  -- v_invoices exposes the billing snapshot
  assert (select billing_name from v_invoices where id = v_inv) = 'Asha Rao', 'v_invoices exposes billing_name';
  assert (select billing_address->>'city' from v_invoices where id = v_inv) = 'Bengaluru', 'v_invoices exposes billing_address';

  raise notice 'smoke test OK';
end $$;

rollback;
