# Subscription Billing System

One platform to run plans, subscriptions and recurring billing in one place.

This is the subscription management system for **Brightloop Software**, a company that sells business software, add-ons and product variants on monthly and yearly subscriptions. It replaces spreadsheets, hand-typed invoices and manual revenue reports with a single system that covers the full life of a subscription: setting up products and plans, generating invoices, collecting payments and reporting revenue.

## The problem

Brightloop tracks subscriptions in a spreadsheet, remembers renewals by whoever notices first, types invoices by hand, matches payments by scrolling through bank statements and builds revenue reports manually each quarter. Renewals get missed, invoices go out wrong, and nobody can say how much recurring revenue the company has.

## Repository structure

| Folder | Contents |
| --- | --- |
| `contract/` | The API contract between frontend and backend: `openapi.yaml` (OpenAPI 3.0.3) and `API.md` with extra detail per endpoint. Frozen at v1; changes go through a reviewed PR. |
| `database/` | Database schema and related files. |
| `frontend/` | User interface for the admin, staff and customer portal. |

The contract is the source of truth. Frontend and backend are both built against `contract/openapi.yaml`, and a Prism mock server can serve the same paths so the frontend can be developed before the backend is ready.

## Roles

| Role | Access |
| --- | --- |
| `admin` | Controls the whole system. Only the admin can add staff, and only the admin manages products, plans, quotation templates, taxes and discounts. |
| `staff` | Day-to-day work with limited access: customers, subscriptions, billing, invoices, payments and the finance dashboard. |
| `customer` | Self-service portal. Sees only their own subscriptions, invoices and payments; the server scopes shared endpoints automatically. |

## Features

### Accounts and access
- Sign-up with email and password. Each email can belong to only one account.
- Password must be longer than 8 characters, with an uppercase letter, a lowercase letter and a special character.
- Password reset by emailed single-use link (valid 30 minutes). The forgot-password endpoint always returns 202, so accounts cannot be probed.
- If staff already created a customer record with the same email, sign-up links to it and keeps its subscriptions instead of creating a duplicate.
- Admins can deactivate users to block login without deleting history.

### Products, variants and plans
- Products have a name, type (`software`, `addon`, `service`, `goods`), sales price, cost price and notes.
- Variants are an attribute value with a price adjustment, for example Brand = Odoo adds 560.00.
- Plans have a price, billing period (`daily`, `weekly`, `monthly`, `yearly`), minimum quantity and availability dates.
- Four per-plan flags set by the admin decide what can happen to subscriptions: `autoClose`, `allowEarlyClose`, `allowPause`, `allowRenew`.
- Price and plan changes affect future billing only; issued invoices are untouched.

### Quotations and subscriptions
- Quotation templates fix the plan, the product lines and how many days a quotation stays valid.
- Each subscription gets its own number (for example `SUB-0001`), a customer, plan, start date, expiry date and payment terms (`immediate`, `net_15`, `net_30`, `net_45`, `net_60`), with lines for product, quantity, unit price, taxes and amount.
- Customers can request a subscription themselves; staff take it from draft onward.
- Every status change, pause, resume and renewal is recorded in a history anyone with access can read.

```
Draft → Quotation → Confirmed → Active → Closed
```

| Action | What it does |
| --- | --- |
| `send-quotation` | Draft to Quotation. Requires customer, plan, dates, payment terms and at least one line. |
| `confirm` | Quotation to Confirmed. Fails if the quotation expired. Locks lines and totals. |
| `activate` | Confirmed to Active. Sets the next billing date to the start date. |
| `close` | Active to Closed, if the plan allows early close. Stops further billing. |
| `pause` / `resume` | Skips billing while paused, with no catch-up invoices on resume. |
| `renew` | Extends the expiry date by one plan term, if the plan allows it. |

### Billing
- One call (`POST /billing/run`) creates a draft invoice for every due subscription, with customer, lines, discounts, taxes and totals filled in.
- **Nothing is billed twice or skipped.** A unique rule on (subscription, billing period) makes the run safe to repeat, and failures are reported so they can be retried.
- Missed periods are caught up one invoice per period, never past the expiry date.
- `GET /billing/due` previews what is due, and `dryRun=true` shows what a run would create without saving. Real runs are stored and can be reviewed under `/billing/runs`.

### Invoices
- Created from subscriptions. Draft invoices can be corrected; the server recomputes discount, tax and totals.
- Confirm (sets issue and due dates), cancel, email to the customer, or print as PDF.
- Cancelling releases the billing period and discount usage, so the next run bills that period again.

```
Draft → Confirmed → Paid        (or Cancelled)
```

### Taxes and discounts
- Admin-defined tax rules apply automatically to lines by product type.
- Discounts are created by the admin only: fixed amount or percentage, with minimum purchase and quantity, start and end dates, and a usage limit.
- A discount applies to specific products or to subscriptions, shows up on the next invoice on its own, and stops when it expires or the usage limit is reached.

### Payments
- Record each payment against a confirmed invoice with method (`cash`, `bank_transfer`, `card`, `upi`, `cheque`, `other`), amount, date and a note.
- Payments cannot exceed the amount still due. When it reaches zero the invoice moves to Paid automatically.
- Admins can void a payment, which restores the invoice balance.
- Filter invoices by `isOverdue` or `hasBalance` to see what is outstanding.

### Reporting
- `GET /reports/summary` returns active subscriptions, revenue collected, amount still owed, overdue invoices and MRR, with filters.
- `GET /reports/revenue` returns invoiced versus collected amounts by day, week or month.
- Target: every page responds in under two seconds with thousands of subscriptions.

## API at a glance

Base path: `/api/v1` (local: `http://localhost:4000/api/v1`).

| Area | Endpoints |
| --- | --- |
| Auth | `/auth/signup`, `/auth/login`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/auth/me` |
| Users | `/users`, `/users/staff`, `/users/{id}` |
| Customers | `/customers`, `/customers/{id}` |
| Products | `/products`, `/products/{id}`, `/products/{id}/variants` |
| Plans | `/plans`, `/plans/{id}` |
| Quotation templates | `/quotation-templates`, `/quotation-templates/{id}` |
| Subscriptions | `/subscriptions`, `/subscriptions/{id}`, lifecycle actions, `/subscriptions/request`, `/subscriptions/{id}/invoices`, `/subscriptions/{id}/history` |
| Billing | `/billing/due`, `/billing/run`, `/billing/runs` |
| Invoices | `/invoices`, `/invoices/{id}`, `confirm`, `cancel`, `send`, `print` |
| Taxes | `/taxes`, `/taxes/{id}` |
| Discounts | `/discounts`, `/discounts/{id}` |
| Payments | `/payments`, `/payments/{id}` |
| Reports | `/reports/summary`, `/reports/revenue` |

### Conventions
- JSON bodies and `Authorization: Bearer <jwt>` on everything except the public auth endpoints.
- Ids are UUID strings. Dates are `YYYY-MM-DD`. Timestamps are ISO 8601 UTC.
- Money is a decimal string with exactly two decimals (for example `"560.00"`), never a JSON float, in a single system currency.
- Lists are paginated with `?page=1&limit=20` (max 100) and return `{ data: [...], meta: {...} }`.
- Errors share one shape: `{ error: { code, message, details? } }`.

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | Bad input, with field-level details |
| 401 | `UNAUTHENTICATED` | Missing or invalid token |
| 403 | `FORBIDDEN` | Role not allowed |
| 404 | `NOT_FOUND` | No such record |
| 409 | `CONFLICT` | Duplicate, or action not allowed in the current state |
| 422 | `BUSINESS_RULE` | A plan, billing or payment rule was violated |

Full request and response schemas are in [`contract/openapi.yaml`](contract/openapi.yaml), with more detail per endpoint in `contract/API.md`.

## Getting started

> Fill in the exact commands once the stack is finalised.

```bash
# Clone the repository
git clone https://github.com/Madhu07-offl/Subscription-Billing-System.git
cd Subscription-Billing-System

# Optional: serve a mock API from the contract (same /api/v1 paths)
npx @stoplight/prism-cli mock contract/openapi.yaml -p 4000

# Database: see database/
# Frontend: see frontend/
```

## Design principles

- **Contract first:** frontend and backend meet at `contract/openapi.yaml`.
- **No double billing:** one invoice per subscription per billing period, enforced at the database level.
- **Enforced lifecycles:** subscription and invoice statuses only move along the allowed paths.
- **Server-side authority:** totals, taxes, discounts and role scoping are computed and enforced by the server, never trusted from the client.
- **History is preserved:** products, plans, taxes and discounts are soft-deleted, so old subscriptions and invoices keep working.
- **Fast reports:** indexes, pagination and summary queries keep pages under two seconds.

## Scaling and archiving

Built to stay fast with millions of records (target: pages under 2 seconds).

- **Indexes** on the fields filtered most: status, customer, due date and billing period.
- **Pagination** on every list (`page`, `limit`, max 100). Nothing returns everything at once.
- **Summary queries** for the dashboard, so reports don't scan every row.
- **Archiving:** old data (closed subscriptions, paid invoices and their payments past a set age) moves to archive tables. Archived records stay readable for history and audits but are left out of daily queries.
- **Never deleted:** products, plans, taxes and discounts are soft-deleted, so old invoices keep working.

## Out of scope for v1

- No proration or credit notes: closing a subscription early leaves issued invoices untouched.
- A single system currency.

## License

Add a license of your choice.
