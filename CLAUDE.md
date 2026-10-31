# CLAUDE.md

Rules for every session in this repo. Sources of truth: `contract/openapi.yaml` + `contract/API.md` (the API) and `database/` (the schema, already deployed on Supabase). If code and contract disagree, the contract wins; change the contract only through a reviewed change. **Never edit `database/`** from backend work; a schema change is a separate, reviewed migration.

## Backend stack

FastAPI, SQLAlchemy 2.0 (typed ORM, `Mapped[...]`), psycopg 3, Pydantic v2, pydantic-settings, PyJWT, bcrypt.

- ORM models are mapped to the EXISTING tables. **Never** `Base.metadata.create_all`, never Alembic autogenerate. Tables change only via `database/migrations`.
- Config comes from `backend/.env` (`DATABASE_URL`, `JWT_SECRET`, ...). Never commit `.env`. Keep `backend/.env.example` up to date when adding a setting.
- Supabase pooler note: the engine disables psycopg prepared statements (`prepare_threshold=None`) and uses `pool_pre_ping`.

## Layout

```
backend/
  app/
    main.py  config.py  db.py
    models/    SQLAlchemy models, one module per migration area
    schemas/   Pydantic request/response models
    routers/   thin HTTP layer: parse, call a service, return
    services/  ALL business logic
    core/      security.py  deps.py  errors.py  pagination.py
  tests/
```

## API conventions

- Base path `/api/v1`. JSON is camelCase: Pydantic `alias_generator=to_camel`, `populate_by_name=True`.
- Money is a **string with two decimals** (`"560.00"`), never a float. Use the shared `Money` type.
- Errors have exactly the shape in `contract/API.md` section 4: `{"error": {"code", "message", "details?"}}` with 400 `VALIDATION_ERROR`, 401 `UNAUTHENTICATED`, 403 `FORBIDDEN`, 404 `NOT_FOUND`, 409 `CONFLICT`, 422 `BUSINESS_RULE`, 500 `INTERNAL`. Raise `AppError` from services; never return ad-hoc error bodies.
- RBAC follows `x-roles` on each operation in `openapi.yaml` (`require_roles(...)`). Customers see only their own data; another customer's record is **404**, not 403.
- Every list endpoint paginates (`page`, `limit` max 100) and returns `{data, meta: {page, limit, total, totalPages}}` via `core/pagination.py`.
- Routers stay thin. State machine, plan checks, tax/discount math and the billing run live in `services/`.

## Database-owned fields (READ-ONLY in code)

The database maintains these with triggers/defaults. Application code must never write them:

- `invoices.amount_paid` and the `confirmed` <-> `paid` transition (derived from payments by trigger)
- `discounts.used_count` (insert/release `discount_usages` rows instead)
- `payments.is_voided` (generated). **Void a payment by setting `voided_at`.**
- `subscriptions.number`, `invoices.number` (DB default `next_document_number(...)`)
- `invoices.billing_*` snapshot (filled by trigger on insert when omitted)
- generated `amount` columns on lines

Derived values come from views, not code: subscription `subtotal/taxTotal/total` from `v_subscriptions`; invoice `amountDue/isOverdue` from `v_invoices`; discount `status` from `v_discounts`.

## Commits

Judged on history: at least one commit per hour, small and logical, never one giant commit. Do not push unless asked. Never commit `.env` or credentials.

```
<type>(<scope>): <summary, max 72 chars>

What:
- ...
Why:
- business rule / contract reference
Notes:
- ...
```

Types: feat, fix, refactor, docs, perf, test, chore. Scope: `backend` (or `db`, `contract`).
