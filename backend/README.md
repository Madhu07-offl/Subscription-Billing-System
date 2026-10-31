# Backend (FastAPI)

REST API for the Subscription Billing System. Contract: [`../contract/openapi.yaml`](../contract/openapi.yaml) and
[`../contract/API.md`](../contract/API.md). Database: [`../database/`](../database/README.md) (already deployed on
Supabase; the backend never creates or alters tables). Project rules: [`../CLAUDE.md`](../CLAUDE.md).

Requires **Python 3.11 or newer** (developed on 3.12).

## Setup

### Windows (PowerShell)

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env      # then edit .env
```

### Linux / macOS

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env             # then edit .env
```

### Configure `.env`

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Supabase connection string (*Project Settings -> Database*). Plain `postgresql://...` is fine; the app switches to the psycopg 3 driver itself. A raw `@` in the password is tolerated; percent-encoded is also accepted. |
| `JWT_SECRET` | Long random string: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_EXPIRES_SECONDS` | Token lifetime, default 28800 (8 h) |
| `RESET_TOKEN_MINUTES` | Password reset link lifetime, default 30 |
| `FRONTEND_URL` | Base of the reset link that is printed to the console, default `http://localhost:5173` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins |

`.env` is git-ignored. Keep `.env.example` in step when you add a setting.

## Run

```bash
uvicorn app.main:app --reload --port 4000
```

- API base: `http://localhost:4000/api/v1` (the contract's server URL)
- Interactive docs: `http://localhost:4000/docs`
- Health: `GET /api/v1/health` runs `SELECT 1` against the database

## The admin account

The database seed (`database/seed.sql`) creates the admin; the backend has no endpoint that creates admins
(staff come from `POST /users/staff`, signup always creates customers). To get one:

1. Run the migrations and `database/seed.sql` on your database (see [`../database/README.md`](../database/README.md)).
2. Log in with the **development-only** credentials `admin@brightloop.test` / `ChangeMe#2026`, then change the
   password via `POST /api/v1/auth/change-password`.

To create a different admin, insert a row using a bcrypt hash made with this project's own code:

```bash
python -c "from app.core.security import hash_password; print(hash_password('YourStrong#Pass1'))"
```

```sql
insert into users (name, email, password_hash, role) values ('Me', 'me@example.com', '<hash>', 'admin');
```

## Try it

```bash
curl -s localhost:4000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@brightloop.test","password":"ChangeMe#2026"}'
curl -s localhost:4000/api/v1/auth/me -H 'authorization: Bearer <token>'
```

Until email sending exists, `POST /auth/forgot-password` prints the reset link to the server console.

## Demo data

`scripts/demo_data.py` fills an empty database with realistic data for demos and manual testing. It uses the service
layer (signup, subscriptions and their lifecycle, the billing run, invoices, payments); the catalogue and customer rows
use the ORM models because those services do not exist yet.

```bash
python scripts/demo_data.py            # create (does nothing if Demo data is already there)
python scripts/demo_data.py --reset    # delete everything it created
```

It needs the seeded admin (`database/seed.sql`). What you get, all prefixed `Demo` (customers are `demo-customerN@example.com`):

- 8 customers; `demo-customer1@example.com` / `Demo#Pass2026` can log in to see the customer views
- 3 products with variants, a Demo GST 18% tax, 3 plans (2 monthly, 1 yearly), 2 discounts
- 15 subscriptions across every status: draft (2, one bare), quotation (2), confirmed (2), active (7, one of them paused), closed (2)
- one billing run covering the active subscriptions (several months back, so catch-up invoices appear), then the invoices are
  confirmed and dated in their own period; about three in five are paid in full, one in five partly, one in five unpaid,
  so older unpaid ones are overdue; the newest invoice of every third subscription stays a draft

Dates are relative to the day you run it. Run it only against a development database: it writes real rows.

## Daily jobs

Two jobs keep subscriptions moving. Run them **once a day, in this order**, from cron or any scheduler:

| Order | Job | Call |
|---|---|---|
| 1 | Billing run: draft invoices for everything due (reruns are safe) | `POST /api/v1/billing/run` (admin or staff token) |
| 2 | Auto-close: `active` subscriptions past `expiryDate` on `autoClose` plans become `closed`, `nextBillingDate` is cleared, history gets an entry with no user | `POST /api/v1/billing/auto-close` (admin token) |

Billing goes first because closing clears the billing date. Auto-close can also run without HTTP, from this directory:
`python -m app.services.auto_close_service`. Invoices created by the run stay `draft` until staff confirm them.
Outgoing invoice emails (`POST /invoices/{id}/send`) are logged to the console for now.

## Tests

```bash
pytest
```

The billing, invoice and payment tests build their catalogue with SQL (there are no catalogue endpoints yet) and always
pass `subscriptionIds` to `/billing/run`, so they never bill rows they did not create. `tests/test_auto_close.py` calls
the real job: on a shared database it also closes any other expired `autoClose` subscription, which the daily job would
do anyway. A full run takes several minutes against a remote database; run single files while developing.

Tests run against the database in `DATABASE_URL`, so point them at a development database. They create users and
customers whose emails start with `pytest-` and delete them afterwards. They need the seeded admin. The suite also
checks that every ORM model matches the live tables column by column, so a drifting model fails loudly.

## Layout

```
app/
  main.py        app factory, CORS, routers under /api/v1
  config.py      settings from backend/.env
  db.py          engine (pool_pre_ping, pooler-safe), session, Base
  models/        SQLAlchemy models for the existing tables (never create_all)
  schemas/       Pydantic models, camelCase on the wire, Money as "560.00"
  routers/       thin HTTP layer
  services/      business logic
  core/          security.py (bcrypt, JWT, password rule), deps.py (get_db, get_current_user, require_roles),
                 errors.py (API.md section 4 error shape), pagination.py
tests/
```

## Status

Phase 1 done: health, auth (signup, login, forgot/reset/change password, `GET`/`PATCH /auth/me`), all 22 models.
Next: users and customers, catalogue, subscriptions, billing, payments, reports.
