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
export const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
```

`BASE_URL` comes from the `VITE_API_URL` environment variable and falls back to the local FastAPI backend on port 8000.
Copy `.env.example` to `.env` to change it for local development.

Until then the app runs on in-memory mock data shaped exactly like the contract:
money as a two-decimal string, lists as `{ data, meta: { page, limit, total, totalPages } }`,
errors as `{ error: { code, message, details[] } }`.

## Deploy

The frontend is a static site (Render **Static Site**, or any static host):

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm install && npm run build` |
| Publish directory | `dist` |
| Environment variable | `VITE_API_URL` = the deployed API, e.g. `https://subscription-billing-api.onrender.com/api/v1` |
| Redirects / Rewrites | `/*` -> `/index.html` (rewrite, not redirect), so deep links like `/invoices/123` survive a reload |

Notes:

- `VITE_API_URL` is read **at build time** (Vite inlines it), so change it and redeploy; it is not a runtime setting.
  It is public: never put secrets in a `VITE_` variable.
- The API must allow this site's origin: set `FRONTEND_ORIGINS` on the backend to the static site's URL
  (see `backend/README.md`, "Deploy to Render").
- **Today the app runs on mock data only.** `USE_MOCK` in `src/api/index.js` is `true` and the file has no HTTP client
  yet, so nothing reads `BASE_URL` / `VITE_API_URL` (the bundler drops the unused constant). The setting is in place for
  when the real client is added; flipping `USE_MOCK` alone is not enough until then.

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
