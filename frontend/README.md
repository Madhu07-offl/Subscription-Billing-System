# Brightloop — Subscription Management System (Frontend)

React + Vite frontend for the Odoo x Make-A-Ton 9.0 Subscription Management System.
Built against `contract/openapi.yaml` (base path `/api/v1`, Bearer JWT).

## Run

```bash
npm install
npm run dev        # http://localhost:5173
```

## Connecting the real backend

All data goes through one file: `src/api/index.js`. Nothing else knows where data comes from.

```js
export const USE_MOCK = false;                          // was true
export const BASE_URL = 'http://localhost:4000/api/v1';
```

Until then the app runs on in-memory mock data shaped exactly like the contract:
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
