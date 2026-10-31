# API Guide

Companion to [`openapi.yaml`](openapi.yaml). The YAML is the source of truth for shapes (fields, types, required, enums). This file explains the behaviour the YAML cannot: who can call what, state machines, and business rules. If the two disagree, fix this file to match the YAML, or change both in one PR.

Base URL: `/api/v1`. Auth: `Authorization: Bearer <jwt>`. Mock server: `npx @stoplight/prism-cli mock contract/openapi.yaml -p 4010`.

Legend for roles: **A** admin, **S** staff, **C** customer (own data only, scoped by the server), **—** public.

## 1. Endpoint index

### Auth
| Method and path | Roles | What it does | Input | Output |
|---|---|---|---|---|
| POST `/auth/signup` | — | Customer creates an account | name, email, password (+company, phone) | 201 token + user |
| POST `/auth/login` | — | Log in | email, password | 200 token + user |
| POST `/auth/forgot-password` | — | Email a reset link | email | 202 message (always) |
| POST `/auth/reset-password` | — | Set new password from token | token, newPassword | 200 message |
| POST `/auth/change-password` | A S C | Change own password | currentPassword, newPassword | 200 message |
| GET `/auth/me` | A S C | Current user | — | user |
| PATCH `/auth/me` | A S C | Update own profile | name, phone, company, address | user |

### Users and customers
| Method and path | Roles | What it does | Input | Output |
|---|---|---|---|---|
| GET `/users` | A | List users | page, limit, q, role, isActive | page of users |
| POST `/users/staff` | A | Add staff (only way) | name, email, password | 201 user |
| GET `/users/{id}` | A | One user | — | user |
| PATCH `/users/{id}` | A | Rename or deactivate | name, isActive | user |
| GET `/customers` | A S | List customers | page, limit, q | page of customers |
| POST `/customers` | A S | Create customer (no login) | name, email (+phone, company, taxId, address) | 201 customer |
| GET `/customers/{id}` | A S | One customer | — | customer |
| PATCH `/customers/{id}` | A S | Update customer | same as create | customer |

### Catalogue
| Method and path | Roles | What it does | Input | Output |
|---|---|---|---|---|
| GET `/products` | A S C | List products (C: active only) | page, limit, q, type, isActive | page of products |
| POST `/products` | A | Create product | name, type, salesPrice, costPrice, notes, variants[] | 201 product |
| GET `/products/{id}` | A S C | Product with variants | — | product |
| PATCH `/products/{id}` | A | Update product | same as create | product |
| DELETE `/products/{id}` | A | Archive product | — | 204 |
| POST `/products/{id}/variants` | A | Add variant | attribute, value, extraPrice | 201 variant |
| PATCH `/products/{id}/variants/{variantId}` | A | Update variant | same | variant |
| DELETE `/products/{id}/variants/{variantId}` | A | Remove variant | — | 204 |
| GET `/plans` | A S C | List plans (C: active and in date range) | page, limit, q, billingPeriod, isActive | page of plans |
| POST `/plans` | A | Create plan | name, price, billingPeriod, minQuantity, availableFrom/To, autoClose, allowEarlyClose, allowPause, allowRenew | 201 plan |
| GET `/plans/{id}` | A S C | One plan | — | plan |
| PATCH `/plans/{id}` | A | Update plan | same | plan |
| DELETE `/plans/{id}` | A | Deactivate plan | — | 204 |
| GET `/quotation-templates` | A S | List templates | page, limit, q | page of templates |
| POST `/quotation-templates` | A | Create template | name, planId, validityDays, lines[], notes | 201 template |
| GET `/quotation-templates/{id}` | A S | One template | — | template |
| PATCH `/quotation-templates/{id}` | A | Update template | same | template |
| DELETE `/quotation-templates/{id}` | A | Delete template | — | 204 |
| GET `/taxes` | A S | List tax rules | page, limit, isActive | page of taxes |
| POST `/taxes` | A | Create tax rule | name, computation, value, appliesToProductTypes[] | 201 tax |
| GET `/taxes/{id}` | A S | One tax | — | tax |
| PATCH `/taxes/{id}` | A | Update tax | same | tax |
| DELETE `/taxes/{id}` | A | Deactivate tax | — | 204 |
| GET `/discounts` | A S | List discount rules | page, limit, q, isActive, validOn | page of discounts |
| POST `/discounts` | A | Create discount rule | name, type, value, scope, productIds / subscriptionIds, minPurchaseAmount, minQuantity, startDate, endDate, usageLimit | 201 discount |
| GET `/discounts/{id}` | A S | One discount | — | discount |
| PATCH `/discounts/{id}` | A | Update discount | same | discount |
| DELETE `/discounts/{id}` | A | Deactivate discount | — | 204 |

### Subscriptions and billing
| Method and path | Roles | What it does | Input | Output |
|---|---|---|---|---|
| GET `/subscriptions` | A S C | List (C: own) | page, limit, q, status, customerId, planId, expiringBefore | page of subscriptions |
| POST `/subscriptions` | A S | Create a draft | customerId, templateId?, planId, startDate, expiryDate, paymentTerms, lines[] | 201 subscription |
| GET `/subscriptions/{id}` | A S C | One subscription with lines and totals | — | subscription |
| PATCH `/subscriptions/{id}` | A S | Edit (draft or quotation only) | any create field | subscription |
| DELETE `/subscriptions/{id}` | A S | Delete (draft only) | — | 204 |
| POST `/subscriptions/{id}/send-quotation` | A S | draft → quotation | — | subscription |
| POST `/subscriptions/{id}/confirm` | A S | quotation → confirmed | — | subscription |
| POST `/subscriptions/{id}/activate` | A S | confirmed → active | — | subscription |
| POST `/subscriptions/{id}/close` | A S C | active → closed (needs plan.allowEarlyClose) | reason? | subscription |
| POST `/subscriptions/{id}/pause` | A S C | Pause billing (needs plan.allowPause) | — | subscription |
| POST `/subscriptions/{id}/resume` | A S C | Resume billing | — | subscription |
| POST `/subscriptions/{id}/renew` | A S C | Extend expiry (needs plan.allowRenew) | newExpiryDate? | subscription |
| GET `/subscriptions/{id}/invoices` | A S C | Invoices of one subscription | page, limit | page of invoices |
| GET `/billing/due` | A S | Preview what is due | asOf?, page, limit | page of due subscriptions |
| POST `/billing/run` | A S | Generate draft invoices for everything due | asOf?, subscriptionIds?, dryRun? | counts + created + failed |

### Invoices, payments, reports
| Method and path | Roles | What it does | Input | Output |
|---|---|---|---|---|
| GET `/invoices` | A S C | List (C: own) | page, limit, q, status, customerId, subscriptionId, isOverdue, hasBalance, issuedFrom, issuedTo | page of invoice summaries |
| GET `/invoices/{id}` | A S C | Invoice with lines and payments | — | invoice |
| POST `/invoices/{id}/confirm` | A S | draft → confirmed | — | invoice |
| POST `/invoices/{id}/cancel` | A S | Cancel (no payments allowed) | — | invoice |
| POST `/invoices/{id}/send` | A S | Email to customer | to?, message? | invoice |
| GET `/invoices/{id}/print` | A S C | PDF for print or download | — | application/pdf |
| GET `/payments` | A S C | List (C: own) | page, limit, invoiceId, customerId, method, paidFrom, paidTo | page of payments |
| POST `/payments` | A S | Record a payment | invoiceId, method, amount, paymentDate, reference?, note? | 201 payment |
| GET `/payments/{id}` | A S C | One payment | — | payment |
| DELETE `/payments/{id}` | A | Void a payment | — | 204 |
| GET `/reports/summary` | A S | Dashboard cards | from, to, planId, customerId | summary |
| GET `/reports/revenue` | A S | Invoiced vs collected over time | from, to, groupBy, planId | `{data: [{period, invoiced, collected}]}` |

## 2. State machines

**Subscription**: `draft → quotation → confirmed → active → closed`. Each step is its own endpoint; anything else returns 409. Paused is a flag (`isPaused`), not a status, so the five statuses stay exactly as the brief names them.
- `draft`/`quotation` are editable. From `confirmed` on, lines and totals are locked.
- `autoClose` plans: a daily job moves `active` subscriptions past `expiryDate` to `closed`.
- Close, pause and renew by anyone (including the customer) are allowed only if the plan flag permits it, otherwise 422 `BUSINESS_RULE`.

**Invoice**: `draft → confirmed → paid`, plus `cancelled`.
- Billing creates `draft`. Staff confirm (sets `issueDate`, `dueDate = issueDate + paymentTerms`).
- `paid` is set by the server when payments cover the total. Voiding a payment moves it back to `confirmed`.
- `isOverdue` = status `confirmed` and `dueDate < today` and `amountDue > 0`. Computed, never stored.

## 3. Business rules the code must enforce

1. **Auth**: email unique (409). Password more than 8 chars with upper, lower and special character (400 with field details). Reset tokens are single-use, 30 minutes. Only `POST /users/staff` creates staff; signup always creates a customer.
2. **Scoping**: a customer asking for another customer's record gets 404, not 403.
3. **Variant pricing**: line `unitPrice` = `product.salesPrice + variant.extraPrice` unless overridden. Example: Odoo brand adds 560.00.
4. **Plan checks on subscription create/confirm**: `quantity >= plan.minQuantity`, and `startDate` inside `[availableFrom, availableTo]`, else 422.
5. **Taxes**: for each line, pick the active tax whose `appliesToProductTypes` contains the product type (or is empty). `percentage`: `amount * value / 100`; `fixed`: `value` per line. Round half up to 2 decimals per line.
6. **Discounts** (evaluated at invoice generation, per line then per subscription):
   - Active, `startDate <= period start <= endDate`, `usedCount < usageLimit`.
   - `minQuantity` against the line (product scope) or total quantity (subscription scope); `minPurchaseAmount` against the line or subscription subtotal.
   - `scope=products` only touches lines of those products; `scope=subscriptions` with empty `subscriptionIds` applies to all.
   - One discount per line, the largest wins. `usedCount` goes up by 1 per invoice it applies to, in the same transaction. Cancelling the invoice gives it back.
7. **Totals**: `amount = quantity * unitPrice`; `discountTotal` from rule 6; `taxTotal` from rule 5 on the discounted amount; `total = subtotal - discountTotal + taxTotal`.
8. **Billing run** (`POST /billing/run`):
   - Candidates: `status=active`, `isPaused=false`, `nextBillingDate <= asOf`.
   - Unique key `(subscriptionId, periodStart)` on invoices makes reruns safe; cancelled invoices release their key.
   - One transaction per subscription, so one failure does not block the rest; failures are listed in `failed`.
   - After creating the invoice, `nextBillingDate` moves forward by one `billingPeriod`. If several periods were missed, the run loops until caught up.
9. **Payments**: only on `confirmed` invoices; `amount > 0` and `<= amountDue`. Partial payments are fine.
10. **Reports**: `outstanding` and `overdue` are as of today; `revenueCollected` uses `paymentDate` in `[from, to]`; `revenueInvoiced` uses `issueDate`. All list endpoints paginate; add indexes on `status`, `customerId`, `dueDate`, `nextBillingDate`, `paymentDate`.

## 4. Errors

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid input", "details": [{ "field": "password", "message": "Needs a special character" }] } }
```

| HTTP | code | When |
|---|---|---|
| 400 | VALIDATION_ERROR | Bad or missing fields |
| 401 | UNAUTHENTICATED | Missing, invalid or expired token; wrong login |
| 403 | FORBIDDEN | Role not allowed; deactivated user |
| 404 | NOT_FOUND | Missing id, or someone else's record for a customer |
| 409 | CONFLICT | Duplicate email, or action invalid in the current status |
| 422 | BUSINESS_RULE | Valid shape but breaks a rule (plan flag, minimum quantity, overpayment) |
| 500 | INTERNAL | Unexpected |

## 5. Example: the happy path in calls

1. `POST /auth/login` as admin.
2. `POST /taxes`, `POST /products` (with a variant), `POST /plans`, `POST /quotation-templates`.
3. `POST /subscriptions` with `templateId` and `customerId`, then `/send-quotation`, `/confirm`, `/activate`.
4. `POST /discounts` for the product or subscription.
5. `POST /billing/run`, then `POST /invoices/{id}/confirm` and `/send`.
6. `POST /payments` against the invoice; invoice becomes `paid`.
7. `GET /reports/summary` shows active subscriptions, revenue, outstanding and overdue.
