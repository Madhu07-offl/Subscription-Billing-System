-- seed.sql
-- Minimal DEVELOPMENT data matching the contract's happy path. Run after all migrations.
-- Idempotent: fixed UUIDs + ON CONFLICT DO NOTHING, so it can be re-run safely.
--
-- !! The admin password below is a development placeholder. Change it (or delete this user)
-- !! before using the database for anything real. Never reuse it elsewhere.
--   admin@brightloop.test  /  ChangeMe#2026   (meets the contract's password rule)

-- Admin user. crypt()/gen_salt('bf') from pgcrypto produce a bcrypt hash that standard bcrypt
-- libraries can verify.
insert into users (id, name, email, password_hash, role)
values ('00000000-0000-4000-8000-000000000001', 'Admin', 'admin@brightloop.test',
        crypt('ChangeMe#2026', gen_salt('bf', 10)), 'admin')
on conflict do nothing;

-- A customer (no login).
insert into customers (id, name, email, phone, company, tax_id,
                       address_line1, city, state, postal_code, country)
values ('00000000-0000-4000-8000-000000000101', 'Asha Rao', 'asha.rao@example.com', '+91 98765 43210',
        'Rao Textiles Pvt Ltd', '29ABCDE1234F1Z5',
        '12 MG Road', 'Bengaluru', 'Karnataka', '560001', 'India')
on conflict do nothing;

-- Product "Brightloop CRM" with variant Brand = Odoo (+560.00).
insert into products (id, name, type, sales_price, cost_price, notes)
values ('00000000-0000-4000-8000-000000000201', 'Brightloop CRM', 'software', 1000.00, 400.00,
        'Seed product from the contract example')
on conflict do nothing;

insert into product_variants (id, product_id, attribute, value, extra_price, is_active)
values ('00000000-0000-4000-8000-000000000211', '00000000-0000-4000-8000-000000000201', 'Brand', 'Odoo', 560.00, true)
on conflict do nothing;

-- Monthly plan. Pause and early close allowed so those flows can be tried right away.
insert into plans (id, name, price, billing_period, min_quantity, available_from,
                   auto_close, allow_early_close, allow_pause, allow_renew)
values ('00000000-0000-4000-8000-000000000301', 'Business Monthly', 1000.00, 'monthly', 1, '2026-01-01',
        false, true, true, true)
on conflict do nothing;

-- GST 18%. No tax_product_types rows = applies to every product type.
insert into taxes (id, name, computation, value)
values ('00000000-0000-4000-8000-000000000401', 'GST 18%', 'percentage', 18)
on conflict do nothing;

-- One discount: 10% off Brightloop CRM lines, first 100 invoices, from 2026-01-01.
insert into discounts (id, name, type, value, scope, min_quantity, start_date, end_date, usage_limit)
values ('00000000-0000-4000-8000-000000000501', 'CRM launch 10% off', 'percentage', 10, 'products',
        1, '2026-01-01', null, 100)
on conflict do nothing;

insert into discount_products (discount_id, product_id)
values ('00000000-0000-4000-8000-000000000501', '00000000-0000-4000-8000-000000000201')
on conflict do nothing;

-- A draft needs only a customer: no plan, dates or lines yet (contract: SubscriptionInput).
-- WHERE NOT EXISTS (not ON CONFLICT) so a re-run does not burn a SUB- number.
insert into subscriptions (id, customer_id)
select '00000000-0000-4000-8000-000000000601', '00000000-0000-4000-8000-000000000101'
where not exists (select 1 from subscriptions where id = '00000000-0000-4000-8000-000000000601');
