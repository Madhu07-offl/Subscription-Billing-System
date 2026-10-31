# Database

PostgreSQL schema for the Subscription Billing System. Designed from
[`contract/openapi.yaml`](../contract/openapi.yaml) and [`contract/API.md`](../contract/API.md):
column names are the contract's camelCase fields in `snake_case`, and enum values are copied verbatim.
Diagram: [`ERD.md`](ERD.md).

Requires **PostgreSQL 15+** (Supabase projects qualify). Tested on PostgreSQL 16.

## Running it

Files are numbered and must run in order. Each is idempotent, so re-running is safe.

### Supabase

1. Dashboard -> **SQL Editor**.
2. Paste and run `migrations/001...` to `008...` in order, then optionally `seed.sql`.

Or from your machine (get the connection string from *Project Settings -> Database*):

```bash
for f in database/migrations/*.sql database/seed.sql; do
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f" || break
done
```

### Local Postgres (Docker)

```bash
docker run -d --name sbs-pg -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres:16
export DATABASE_URL=postgresql://postgres:pw@localhost:5432/postgres
for f in database/migrations/*.sql database/seed.sql; do
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f" || break
done
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/smoke.sql   # optional behaviour check
bash database/tests/concurrency.sh                                      # optional, uses $DATABASE_URL
```

The seed creates `admin@brightloop.test` with the **development-only** password `ChangeMe#2026`.
Change it or delete the user before real use. Never commit real credentials; keep connection strings in `.env`.

## Layout

| File | Contents |
|---|---|
| `migrations/001_extensions_and_helpers.sql` | `pgcrypto`, `pg_trgm`, `citext`; `set_updated_at()` and `attach_updated_at(table)` |
| `migrations/002_identity.sql` | `customers`, `users`, `password_reset_tokens` |
| `migrations/003_catalogue.sql` | `products`, `product_variants`, `plans`, `taxes`, `tax_product_types`, `quotation_templates`, `quotation_template_lines` |
| `migrations/004_discounts.sql` | `discounts`, `discount_products`, `discount_subscriptions`, `discount_usages` (+ used_count trigger) |
| `migrations/005_subscriptions.sql` | `document_sequences` + `next_document_number()`, `subscriptions`, `subscription_lines`, `subscription_status_history` |
| `migrations/006_billing.sql` | `billing_runs`, `invoices`, `invoice_lines`, `payments` (+ payment sync trigger) |
| `migrations/007_views_and_indexes.sql` | views `v_customers`, `v_subscriptions`, `v_invoices`, `v_discounts`, `v_report_*`; all secondary indexes |
| `migrations/008_rls.sql` | RLS on every table, no policies, anon/authenticated privileges revoked |
| `seed.sql` | admin, customer, "Brightloop CRM" + Brand=Odoo (+560), monthly plan, GST 18%, one discount |
| `tests/smoke.sql` | rollback-only assertions for the rules below |
| `tests/concurrency.sh` | parallel-session check that `next_document_number()` never repeats (needs `psql`) |

## Design decisions

- **Contract mapping.** `salesPrice` -> `sales_price`, `isPaused` -> `is_paused`, and so on. Nested `Address` is flattened to `address_line1 ... country`. `appliesToProductTypes[]`, `productIds[]`, `subscriptionIds[]` are join tables.
- **Keys and types.** UUID PKs (`gen_random_uuid()`), money `numeric(12,2)`, all timestamps `timestamptz`, `created_at`/`updated_at` on mutable tables (trigger-maintained).
- **Enums are `text` + `CHECK`**, not Postgres `ENUM`. To add a value, drop and re-add one constraint in a new migration; no `ALTER TYPE`, no table rewrite.
- **Case-insensitive email**: `citext` + `UNIQUE` on `users` and `customers`.
- **Computed, never stored**: `amount_due` and `is_overdue` (in `v_invoices`), subscription `subtotal/tax_total/total` (in `v_subscriptions`), discount `status` (in `v_discounts`), `hasLogin`/`activeSubscriptions` (in `v_customers`). `is_overdue = status = 'confirmed' AND due_date < current_date AND amount_due > 0`. Stored `invoices.amount_paid` is the only payment total.
- **Double billing blocked in the DB**: partial unique index `uq_invoices_subscription_period` on `invoices (subscription_id, period_start) WHERE status <> 'cancelled'`. Cancelling an invoice frees its period.
- **Immutable invoices**: `invoice_lines` copy description, unit price, discount (id/name/amount) and tax (id/name/rate/amount). Catalogue edits never alter issued invoices. Header totals are checked: `total = subtotal - discount_total + tax_total`.
- **Pause is a flag** (`subscriptions.is_paused`), so there are exactly the contract's five statuses. `subscription_status_history` records status changes plus pause/resume/renew events. `closed_at` is set iff `status = 'closed'`.
- **Delete behaviour**: child lines `CASCADE`; financial records (`invoices`, `payments`, `invoice_lines`, customers/plans/products referenced by subscriptions) `RESTRICT`; optional references (`template_id`, subscription-line `tax_id`/`variant_id`) `SET NULL`. Invoices and payments are cancelled/voided, never deleted.
- **Variant belongs to product**: composite FK `(variant_id, product_id)` on template and subscription lines.
- **Numbering**: `document_sequences` + `next_document_number('subscription'|'invoice')` give `SUB-0001` and `INV-2026-0001` (yearly reset), concurrency-safe via row lock. A new document type is one `INSERT`.
- **Search**: `pg_trgm` GIN indexes on names, emails, numbers. Email indexes are on `(email::text)`, so query with `email::text ILIKE '%q%'`.
- **Indexes** (all in 007):  `status`, `customer_id`, `due_date`, `next_billing_date`, `payment_date`, plus the partial `idx_subscriptions_billable` (`status='active' AND NOT is_paused`) for the billing run.

### Triggers (the only logic in the database)

Kept deliberately small, because they protect money:

| Trigger | Effect |
|---|---|
| `trg_<table>_updated_at` | stamps `updated_at` |
| `trg_discount_usages_sync` | inserting a `discount_usages` row does `used_count + 1`; setting `released_at` (invoice cancelled) does `- 1`. `CHECK (used_count <= usage_limit)` rejects over-use, even under concurrent runs |
| `trg_invoices_release_discounts` | cancelling an invoice sets `released_at` on its `discount_usages`, which hands the usage back via the trigger above |
| `trg_payments_sync_invoice` | after any payment change: recomputes `invoices.amount_paid` from non-voided payments and flips `confirmed <-> paid`. Rejects a payment on a non-`confirmed` invoice. Void a payment by setting `voided_at` (`is_voided` is a generated column). `CHECK (amount_paid <= total)` rejects overpayment |

**The backend must therefore not update `discounts.used_count`, `invoices.amount_paid`, or the `paid` status by hand.** Insert the usage / payment row instead. To remove a trigger, drop it and move the logic to the API.

### Security (Supabase)

`008_rls.sql` enables RLS on every table with **no policies**, and revokes `anon`/`authenticated` privileges. The only way in is the backend, using the `service_role` key or a direct Postgres connection (both bypass RLS). Views are `security_invoker`, so they obey the same lock-down. Role-based and per-customer scoping (customer sees own data, 404 otherwise) is enforced in the API per `API.md`. After adding tables in a later migration, re-run `008_rls.sql`.

### What the database does NOT enforce

These need the backend (they span rows or depend on rules in `API.md`): state-machine transition order, plan checks (min quantity, availability window), picking the tax/discount and computing amounts, rolling `next_billing_date` forward, scope consistency of discount join tables with `discounts.scope`, and clearing `is_paused` when closing.

## Extending

- **New enum value**: `ALTER TABLE ... DROP CONSTRAINT ...; ADD CONSTRAINT ... CHECK (... in (...))` in a new migration (inline column checks are auto-named `<table>_<column>_check`, e.g. `subscriptions_status_check`).
- **New column on a table that has a view**: add the column in a new migration, then `DROP VIEW` + recreate the view (views list columns explicitly on purpose).
- **New updated_at table**: add the column, then `select attach_updated_at('my_table');`.
- **New migration**: add `009_*.sql`, idempotent (`if not exists`), and re-run `008_rls.sql`.
