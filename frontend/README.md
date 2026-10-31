# Brightloop — Subscription Management System (Frontend)

React + Vite frontend for the Odoo x Make-A-Ton 9.0 Subscription Management System.
Built against `contract/openapi.yaml` (base path `/api/v1`, Bearer JWT).

## Run

```bash
npm install
npm run dev        # http://localhost:5173
```

## Connecting the real backend

By default the app talks to the backend at `http://localhost:8000/api/v1` (override with `VITE_API_URL`).
Set `VITE_USE_MOCK=true` to run entirely on mock data instead.

Live over HTTP today: login, `/auth/me`, products, plans, customers, users.
Everything else (subscriptions, invoices, billing, payments, taxes, discounts, reports) still uses the mock
until the backend implements it. All of it lives in `src/api/index.js`.

Mock data is in-memory mock data shaped exactly like the contract:
money as a two-decimal string, lists as `{ data, meta: { page, limit, total, totalPages } }`,
errors as `{ error: { code, message, details[] } }`.

## What is implemented

| Area | Screens |
|---|---|
| Auth | Login with role picker (admin / staff / customer), live password-rule validation |
| Dashboard | MRR, active subscriptions, collected, outstanding + overdue; invoiced-vs-collected area chart; subscriptions-by-plan bar chart; recent invoices |
| Subscriptions | Filterable list, create draft, detail page with lifecycle stepper and history |
| Lifecycle | draft → quotation → confirmed → active → closed, plus pause / resume / renew, each gated by the plan flags (`allowPause`, `allowRenew`, `allowEarlyClose`) |
| Invoices | Filterable list incl. overdue/outstanding, detail with lines and totals, confirm / send / cancel / print |
| Payments | Record payment with validation (confirmed invoices only, cannot exceed amount due, partial allowed); invoice auto-moves to `paid` |
| Billing | Preview what is due, dry run, and a real run that creates draft invoices and advances `nextBillingDate` |
| Config | Products with variants, Plans, Discounts, Taxes, Customers, Users & staff |

## Role-based access

Navigation and actions follow the contract's `x-roles`:

- **admin** — everything, including products, plans, taxes, discounts, users
- **staff** — customers, subscriptions, billing, invoices, payments
- **customer** — own subscriptions and invoices only (portal view)

## Structure

```
src/
  api/index.js    API client + mock data (single swap point)
  ui.jsx          Badge, Flow, Stat, Modal, Toast, Empty, Loading, useAsync
  pages/index.jsx All screens
  App.jsx         Routing, role-aware navigation, app shell
  styles.css      Design system — tokens, dark/light theme, components
```
