// ===================================================================
//  API layer — Brightloop Subscription Billing
//  Matches contract/openapi.yaml (base /api/v1, Bearer JWT).
//  Every screen gets its data through this file and nothing else.
// ===================================================================
export const BASE_URL  = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
export const TOKEN_KEY = 'bl_token';
export const USER_KEY  = 'bl_user';

/* Errors follow contract/API.md section 4: { error: { code, message, details? } } */
export class ApiError extends Error {
  constructor(code, message, details = [], status = 0) {
    super(message); this.code = code; this.details = details; this.status = status;
  }
  /** { fieldName: message } from details, for showing errors next to inputs. */
  get fields() {
    const out = {};
    (this.details || []).forEach(d => { if (d.field) out[d.field.split('.').pop()] = d.message; });
    return out;
  }
}

/* Called when a request comes back 401 with a token: the session expired. */
let onSessionExpired = () => {};
export const setSessionExpiredHandler = fn => { onSessionExpired = fn; };

async function http(method, path, { query, body } = {}) {
  const params = new URLSearchParams();
  Object.entries(query || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') params.set(k, v);
  });
  const url = `${BASE_URL}${path}${params.toString() ? `?${params}` : ''}`;
  const headers = { Accept: 'application/json' };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let res;
  try {
    res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError('NETWORK', `Cannot reach the server. Check that the backend is running at ${BASE_URL}.`);
  }
  if (res.status === 204) return null;
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    const e = json?.error;
    if (res.status === 401 && token && !path.startsWith('/auth/login')) onSessionExpired();
    throw new ApiError(e?.code || `HTTP_${res.status}`, e?.message || res.statusText || 'Request failed', e?.details || [], res.status);
  }
  return json;
}

const get   = (p, query) => http('GET', p, { query });
const post  = (p, body)  => http('POST', p, { body });
const patch = (p, body)  => http('PATCH', p, { body });
const del   = p          => http('DELETE', p);

export const api = {
  /* auth */
  async login(email, password) {
    const r = await post('/auth/login', { email, password });
    localStorage.setItem(TOKEN_KEY, r.token);
    return r;
  },
  async signup(input) {
    const r = await post('/auth/signup', input);
    localStorage.setItem(TOKEN_KEY, r.token);
    return r;
  },
  forgotPassword: email => post('/auth/forgot-password', { email }),
  changePassword: (currentPassword, newPassword) => post('/auth/change-password', { currentPassword, newPassword }),
  me: () => get('/auth/me'),

  /* people */
  users:          q => get('/users', q),
  createStaff:    b => post('/users/staff', b),
  updateUser:     (id, b) => patch(`/users/${id}`, b),
  customers:      q => get('/customers', q),
  createCustomer: b => post('/customers', b),
  updateCustomer: (id, b) => patch(`/customers/${id}`, b),

  /* catalogue */
  products:       q => get('/products', q),
  createProduct:  b => post('/products', b),
  updateProduct:  (id, b) => patch(`/products/${id}`, b),
  deleteProduct:  id => del(`/products/${id}`),
  addVariant:     (id, b) => post(`/products/${id}/variants`, b),
  deleteVariant:  (id, vid) => del(`/products/${id}/variants/${vid}`),
  plans:          q => get('/plans', q),
  createPlan:     b => post('/plans', b),
  updatePlan:     (id, b) => patch(`/plans/${id}`, b),
  deletePlan:     id => del(`/plans/${id}`),
  taxes:          q => get('/taxes', q),
  createTax:      b => post('/taxes', b),
  updateTax:      (id, b) => patch(`/taxes/${id}`, b),
  deleteTax:      id => del(`/taxes/${id}`),
  discounts:      q => get('/discounts', q),
  createDiscount: b => post('/discounts', b),
  updateDiscount: (id, b) => patch(`/discounts/${id}`, b),
  deleteDiscount: id => del(`/discounts/${id}`),
  templates:      q => get('/quotation-templates', q),
  createTemplate: b => post('/quotation-templates', b),
  updateTemplate: (id, b) => patch(`/quotation-templates/${id}`, b),
  deleteTemplate: id => del(`/quotation-templates/${id}`),

  /* subscriptions */
  subscriptions:        q => get('/subscriptions', q),
  subscription:         id => get(`/subscriptions/${id}`),
  createSubscription:   b => post('/subscriptions', b),
  requestSubscription:  b => post('/subscriptions/request', b),
  updateSubscription:   (id, b) => patch(`/subscriptions/${id}`, b),
  deleteSubscription:   id => del(`/subscriptions/${id}`),
  subscriptionHistory:  id => get(`/subscriptions/${id}/history`, { limit: 100 }),
  subscriptionInvoices: id => get(`/subscriptions/${id}/invoices`, { limit: 100 }),
  /** action: send-quotation | confirm | activate | close | pause | resume | renew */
  subscriptionAction:   (id, action, body) => http('POST', `/subscriptions/${id}/${action}`, { body }),

  /* invoices & payments */
  invoices:      q => get('/invoices', q),
  invoice:       id => get(`/invoices/${id}`),
  /** action: confirm | cancel | send */
  invoiceAction: (id, action, body) => http('POST', `/invoices/${id}/${action}`, { body }),
  payments:      q => get('/payments', q),
  recordPayment: b => post('/payments', b),
  voidPayment:   id => del(`/payments/${id}`),

  /* billing */
  billingDue:  q => get('/billing/due', q),
  billingRun:  b => post('/billing/run', b),
  billingRuns: q => get('/billing/runs', q),
  autoClose:   b => post('/billing/auto-close', b),

  /* reports */
  summary: q => get('/reports/summary', q),
  revenue: q => get('/reports/revenue', q),
};

/** Fetch every page of a list endpoint (for dropdowns). Stops at 1000 rows. */
export async function fetchAll(fn, query = {}) {
  const rows = [];
  for (let page = 1; page <= 10; page++) {
    const r = await fn({ ...query, page, limit: 100 });
    rows.push(...r.data);
    if (page >= r.meta.totalPages) break;
  }
  return rows;
}
