// ===================================================================
//  Real API client: talks to the FastAPI backend (contract/openapi.yaml).
//  It returns the SAME shapes the mock returns, because the pages were
//  written against those. Every place where a field is derived here
//  (the contract does not return it) is marked  "DERIVED:".
// ===================================================================
import { ApiError } from './errors';

const TOKEN_KEY = 'bl_token';
const USER_KEY  = 'bl_user';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TERM_DAYS = { immediate: 0, net_15: 15, net_30: 30, net_45: 45, net_60: 60 };

// A token only counts while the user record exists: App.jsx's sign-out removes bl_user without
// calling api.logout(), so an orphaned token is dropped here instead of being sent.
export const getToken = () => {
  if (!localStorage.getItem(USER_KEY) && !loggingIn) { localStorage.removeItem(TOKEN_KEY); return null; }
  return localStorage.getItem(TOKEN_KEY);
};
let loggingIn = false;

let redirecting = false;
function sessionExpired() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  if (!redirecting) { redirecting = true; window.location.assign('/'); }   // App shows <Login/> when bl_user is gone
}

/** Contract errors name fields like "lines.0.quantity"; the pages look for "quantity". */
const normDetails = d => Array.isArray(d)
  ? d.map(x => ({ ...x, field: String(x.field ?? '').split('.').pop() }))
  : [];

const qs = params => {
  const u = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') u.set(k, v); });
  const s = u.toString();
  return s ? `?${s}` : '';
};

const money2 = v => Number(v).toFixed(2);
const mapPage = (res, fn) => ({ data: (res.data || []).map(fn), meta: res.meta });
const replace = (arr, rows) => { arr.length = 0; arr.push(...rows); };

/* --------------------------- contract -> UI mappers --------------------------- */
const mapUser = u => ({ ...u });

const mapSubLine = l => ({
  ...l,
  variantName: l.variantLabel ?? null,                 // DERIVED: UI reads variantName, contract has variantLabel
  taxName: l.taxName ?? '',
});

const mapSub = s => ({
  ...s,
  customerId: s.customer?.id,                          // DERIVED: flat id, contract nests it in customer
  planId: s.plan?.id ?? null,                          // DERIVED: flat id, contract nests it in plan
  plan: s.plan ?? { id: null, name: '—', billingPeriod: '—' },   // DERIVED: draft with no plan yet
  paymentTerms: TERM_DAYS[s.paymentTerms] ?? 0,        // DERIVED: UI shows "<n> days", contract has 'net_15'
  discountTotal: s.discountTotal ?? '0.00',            // DERIVED: subscriptions carry no discount, it is applied on invoices
  lines: (s.lines || []).map(mapSubLine),
});

const mapInvLine = l => ({
  ...l,
  productName: l.description,                          // DERIVED: contract has description only
  variantName: null,                                   // DERIVED: invoice lines carry no variant
  taxName: l.taxName ?? '',
});

const mapPayment = p => ({
  ...p,
  customerId: p.customer?.id,                          // DERIVED
  customerName: p.customer?.name,                      // DERIVED
  reference: p.reference ?? '',
});

const mapInvoice = i => ({
  ...i,
  customerId: i.customer?.id,                          // DERIVED
  // DERIVED: list rows have no customerDetails; use the customer ref (the detail snapshot wins when present)
  customerDetails: { name: i.customer?.name, email: i.customer?.email, ...(i.customerDetails || {}) },
  lines: (i.lines || []).map(mapInvLine),
  payments: (i.payments || []).map(mapPayment),
});

const mapDiscount = d => ({ ...d, usageLimit: d.usageLimit ?? '∞' });   // DERIVED: null limit -> infinity sign

const monthKey = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
const addYear = iso => { const [y, m, d] = iso.split('-').map(Number); return dayKey(new Date(y + 1, m - 1, d)); };
const dayKey   = d => `${monthKey(d)}-${String(d.getDate()).padStart(2, '0')}`;

export function createRealApi(db, baseUrl) {
  const BASE = String(baseUrl).replace(/\/+$/, '');

  async function request(path, { method = 'GET', params, body, auth = true, raw = false } = {}) {
    const headers = { Accept: 'application/json' };
    const token = getToken();
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (auth && token) headers.Authorization = `Bearer ${token}`;

    let res;
    try {
      res = await fetch(`${BASE}${path}${qs(params)}`, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError('NETWORK', 'Cannot reach the server. Check your connection and try again.');
    }

    if (res.ok && raw) return res;
    if (res.status === 204) return null;
    const text = await res.text();
    let json = null;
    try { json = text ? JSON.parse(text) : null; } catch { /* not JSON */ }

    if (!res.ok) {
      if (res.status === 401 && auth && token) sessionExpired();
      const e = json?.error;
      throw new ApiError(
        e?.code ?? (res.status === 401 ? 'UNAUTHENTICATED' : 'INTERNAL'),
        e?.message ?? `Request failed (${res.status})`,
        normDetails(e?.details),
      );
    }
    return json;
  }

  /** Every page of a list (limit 100 is the contract maximum), capped so a bug cannot loop forever. */
  async function fetchAll(path, params = {}) {
    const rows = [];
    for (let page = 1; page <= 20; page++) {
      const res = await request(path, { params: { ...params, page, limit: 100 } });
      rows.push(...(res.data || []));
      if (page >= (res.meta?.totalPages ?? 1)) break;
    }
    return rows;
  }

  /* The pages read db.plans / db.products / db.customers / db.subscriptions directly (dropdowns, plan
     rules, "next billing" tile). In real mode we fill those arrays from the API instead of the seed. */
  let hydrating = null;
  function hydrate(force = false) {
    if (!force && hydrating) return hydrating;
    hydrating = (async () => {
      if (!getToken()) return;
      const safe = p => p.catch(() => []);        // e.g. customers are 403 for a customer login
      const [plans, products, customers] = await Promise.all([
        safe(fetchAll('/plans')), safe(fetchAll('/products')), safe(fetchAll('/customers')),
      ]);
      replace(db.plans, plans);
      replace(db.products, products);
      replace(db.customers, customers);
    })();
    return hydrating;
  }
  const ready = () => hydrating ?? hydrate();

  const customerFilter = id => (UUID.test(id || '') ? id : undefined);
  // DERIVED: the pages hardcode customerId 'c1' for customer logins; the server already scopes
  // customers to their own records, so any non-UUID filter is dropped.

  const pick = (id, rows) => (rows.some(r => r.id === id) ? id : rows[0]?.id ?? id);
  // DERIVED: NewSubscription starts from mock ids ('c1','pl1','p1') that no <option> matches,
  // so the select shows the first row; send what the user sees.

  const api = {
    /* auth */
    async login(email, password) {
      const res = await request('/auth/login', { method: 'POST', body: { email, password }, auth: false });
      localStorage.setItem(TOKEN_KEY, res.token);
      redirecting = false;
      loggingIn = true;   // bl_user is written by the caller after we return; keep the token valid until then
      try { await hydrate(true); } catch { /* catalogue dropdowns are best effort */ }
      finally { loggingIn = false; }
      return { token: res.token, user: mapUser(res.user) };
    },
    logout() {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      hydrating = null;
      ['plans', 'products', 'customers', 'subscriptions'].forEach(k => { db[k].length = 0; });
    },
    async me() {
      if (!getToken()) return null;
      return mapUser(await request('/auth/me'));
    },

    /* catalogue */
    async products(q = {})  { return mapPage(await request('/products',  { params: q }), x => x); },
    async plans(q = {})     { return mapPage(await request('/plans',     { params: q }), x => x); },
    async customers(q = {}) { return mapPage(await request('/customers', { params: q }), x => x); },
    async taxes(q = {})     { return mapPage(await request('/taxes',     { params: q }), x => x); },
    async discounts(q = {}) { return mapPage(await request('/discounts', { params: q }), mapDiscount); },
    async users(q = {})     { return mapPage(await request('/users',     { params: q }), mapUser); },

    /* subscriptions */
    async subscriptions({ status, customerId, q, ...pg } = {}) {
      await ready();
      const res = await request('/subscriptions', {
        params: { status, customerId: customerFilter(customerId), q, ...pg },
      });
      return mapPage(res, mapSub);
    },
    async subscription(id) { await ready(); return mapSub(await request(`/subscriptions/${id}`)); },

    async subscriptionHistory(id) {
      const res = await request(`/subscriptions/${id}/history`, { params: { limit: 100 } });
      return {
        data: (res.data || []).map(e => {
          // DERIVED: pause/resume/renew events keep status 'active' -> 'active' in the contract;
          // the page prints "from -> to", so show the event itself like the mock does.
          const from = e.event === 'paused' ? 'active' : e.event === 'resumed' ? 'paused'
                     : e.event === 'renewed' ? 'active' : e.fromStatus;
          const to   = e.event === 'paused' ? 'paused' : e.event === 'resumed' ? 'active'
                     : e.event === 'renewed' ? 'renewed' : e.toStatus;
          return { id: e.id, subscriptionId: id, from, to, at: e.createdAt, by: e.changedBy?.name ?? 'System' };
        }),
      };
    },

    async transition(id, action) {
      let path = action;                                   // pause | resume | renew | close
      if (action === 'next') {
        const cur = await request(`/subscriptions/${id}`);
        path = { draft: 'send-quotation', quotation: 'confirm', confirmed: 'activate' }[cur.status];
        if (!path) throw new ApiError('CONFLICT', `Cannot move a ${cur.status} subscription forward.`);
      }
      return mapSub(await request(`/subscriptions/${id}/${path}`, { method: 'POST', body: {} }));
    },

    async createSubscription(f) {
      await ready();
      const body = {
        customerId: pick(f.customerId, db.customers),
        planId: pick(f.planId, db.plans),
        startDate: f.startDate || undefined,
        // DERIVED: the form has no expiry or payment-terms fields, but the server refuses to send a
        // quotation without them. Same defaults as the mock: net 15, and a one-year term.
        expiryDate: f.startDate ? addYear(f.startDate) : undefined,
        paymentTerms: 'net_15',
        lines: [{ productId: pick(f.productId, db.products), quantity: Number(f.quantity) }],
      };
      return mapSub(await request('/subscriptions', { method: 'POST', body }));
    },

    /* invoices */
    async invoices({ status, isOverdue, subscriptionId, customerId, q, ...pg } = {}) {
      const res = await request('/invoices', {
        params: { status, isOverdue, subscriptionId, customerId: customerFilter(customerId), q, ...pg },
      });
      return mapPage(res, mapInvoice);
    },
    async invoice(id) { return mapInvoice(await request(`/invoices/${id}`)); },
    async invoiceAction(id, action) {
      return mapInvoice(await request(`/invoices/${id}/${action}`, { method: 'POST', body: {} }));
    },
    /** Blob URL of the invoice PDF (GET /invoices/{id}/print); the UI still uses window.print(). */
    async invoicePdf(id) {
      const res = await request(`/invoices/${id}/print`, { raw: true });
      return URL.createObjectURL(await res.blob());
    },

    /* payments */
    async recordPayment({ invoiceId, amount, method, paymentDate, reference }) {
      const body = { invoiceId, method, amount: money2(amount), paymentDate };
      if (reference) body.reference = reference;
      return mapPayment(await request('/payments', { method: 'POST', body }));
    },
    async payments({ invoiceId, customerId, ...pg } = {}) {
      return mapPage(await request('/payments', {
        params: { invoiceId, customerId: customerFilter(customerId), ...pg },
      }), mapPayment);
    },

    /* billing */
    async billingDue(asOf) {
      await ready();
      const [due, active] = await Promise.all([
        request('/billing/due', { params: { asOf, limit: 100 } }),
        fetchAll('/subscriptions', { status: 'active' }),
      ]);
      const byId = new Map(active.map(s => [s.id, s]));
      return {
        meta: due.meta,
        data: (due.data || []).map(d => ({
          id: d.subscriptionId,
          number: d.number,
          customer: d.customer,
          // DERIVED: the due list has no plan; look it up on the active subscriptions
          plan: byId.get(d.subscriptionId)?.plan ?? { name: '—', billingPeriod: '—' },
          nextBillingDate: d.nextBillingDate,
          total: d.estimatedTotal,                         // DERIVED: renamed
        })),
      };
    },
    async billingRun({ dryRun = false } = {}) {
      const r = await request('/billing/run', { method: 'POST', body: { dryRun } });
      return {
        dryRun: r.dryRun,
        createdCount: r.counts?.created ?? 0,              // DERIVED: contract nests counts
        failedCount: r.counts?.failed ?? 0,
        alreadyBilled: r.counts?.alreadyBilled ?? 0,
        created: (r.created || []).map(c => ({
          subscriptionNumber: c.subscriptionNumber,
          invoiceNumber: r.dryRun ? null : c.number,       // DERIVED: a dry run saves nothing, so no real number
          total: c.total,
        })),
        failed: r.failed || [],
      };
    },

    /* reports */
    async summary() {
      await ready();
      const [s, active, customers] = await Promise.all([
        request('/reports/summary'),
        fetchAll('/subscriptions', { status: 'active' }),
        request('/customers', { params: { limit: 1 } }),
      ]);
      replace(db.subscriptions, active.map(mapSub));       // the "Next billing" tile reads db.subscriptions
      return {
        activeSubscriptions: s.subscriptions?.active ?? active.length,
        pausedSubscriptions: active.filter(x => x.isPaused).length,   // DERIVED: summary has no paused count
        mrr: s.mrr,
        revenueCollected: s.revenueCollected,
        outstanding: s.outstanding,
        overdueCount: s.overdue?.count ?? 0,
        overdueAmount: s.overdue?.amount ?? '0.00',
        totalCustomers: customers.meta?.total ?? 0,         // DERIVED: summary has no customer count
      };
    },
    async revenueSeries() {
      const now = new Date();
      const first = new Date(now.getFullYear(), now.getMonth() - 5, 1);
      const res = await request('/reports/revenue', {
        params: { from: dayKey(first), to: dayKey(now), groupBy: 'month' },
      });
      const byMonth = new Map((res.data || []).map(p => [String(p.period).slice(0, 7), p]));
      // DERIVED: always six months, zero-filled, with numeric amounts and a short month label ("Oct"):
      // the dashboard chart does arithmetic on invoiced/collected and compares the last two points.
      return {
        data: Array.from({ length: 6 }, (_, i) => {
          const d = new Date(now.getFullYear(), now.getMonth() - 5 + i, 1);
          const p = byMonth.get(monthKey(d));
          return {
            period: d.toLocaleString('en-US', { month: 'short' }),
            invoiced: Number(p?.invoiced ?? 0),
            collected: Number(p?.collected ?? 0),
          };
        }),
      };
    },
    async planMix() {
      const subs = await fetchAll('/subscriptions');       // DERIVED: no endpoint; counted client-side
      const counts = {};
      subs.forEach(s => { const n = s.plan?.name; if (n) counts[n] = (counts[n] || 0) + 1; });
      return { data: Object.entries(counts).map(([name, value]) => ({ name, value })) };
    },
  };

  return { api, hydrate };
}
