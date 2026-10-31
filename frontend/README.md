# Brightloop — Subscription Management System (Frontend)

React + Vite frontend for the Odoo x Make-A-Ton 9.0 Subscription Management System.
Built against `contract/openapi.yaml` (base path `/api/v1`, Bearer JWT).

## Run

```bash
npm install
npm run dev        # http://localhost:5173
```

## Connecting the real backend

The app talks to the FastAPI backend by default. All data goes through `src/api/index.js`, which picks a client:

| Variable | Meaning |
|---|---|
| `VITE_API_URL` | Backend base URL. Default `http://localhost:8000/api/v1` |
| `VITE_USE_MOCK` | `true` = in-memory demo data, no server needed (offline demos). Default: real backend |

Local run against the backend (start it first: `cd backend && uvicorn app.main:app --port 8000`):

```bash
npm run dev                            # real backend
VITE_USE_MOCK=true npm run dev         # offline mock
```

- `src/api/real.js` is the fetch client: JSON, `Authorization: Bearer <token>` (token kept in `localStorage`),
  `{error:{code,message,details}}` turned into `ApiError`, a 401 clears the session and returns to the sign-in page.
- It returns the same shapes as the mock, so pages do not care which one runs. Fields the API does not return are
  derived there and marked `DERIVED:` in the code.
- Sign in with a real account (dev seed: see `backend/README.md`, "The admin account").

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
- `VITE_USE_MOCK` is also build-time. Never set it to `true` on a production deploy.

## Structure

```
src/
  api/index.js    picks mock or real client; mock data
  api/real.js     fetch client for the FastAPI backend
  api/errors.js   ApiError
  ui.jsx          Badge, Flow, Stat, Modal, Toast, Empty, Loading, useAsync
  pages/index.jsx All screens
  App.jsx         Routing, role-aware navigation, app shell
  styles.css      Design system — tokens, dark/light theme, components
```
