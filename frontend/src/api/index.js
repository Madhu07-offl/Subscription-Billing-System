// ===================================================================
//  API layer — Brightloop Subscription Billing
//  Matches contract/openapi.yaml  (base /api/v1, Bearer JWT)
//  Real backend by default. Set VITE_USE_MOCK=true for the offline demo
//  (in-memory data below, no server needed).
// ===================================================================
import { ApiError } from './errors';
import { createRealApi } from './real';

export const USE_MOCK  = import.meta.env.VITE_USE_MOCK === 'true';
// Set VITE_API_URL at build time (see .env.example); the FastAPI backend runs on port 8000 locally.
export const BASE_URL  = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const money = n => n.toFixed(2);
const today = new Date();
const iso   = d => d.toISOString().slice(0, 10);
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const uid = (p, n) => `${p}-${String(n).padStart(4, '0')}`;

/* ------------------------------ seed data ------------------------------ */
export const db = {
  users: [
    { id:'u1', name:'Madhumitha K', email:'admin@brightloop.io',  role:'admin',    isActive:true },
    { id:'u2', name:'Asad Ahmed',   email:'staff@brightloop.io',  role:'staff',    isActive:true },
    { id:'u3', name:'Nithya Raman', email:'nithya@kochicafe.in',  role:'customer', isActive:true },
  ],
  customers: [
    { id:'c1', name:'Kochi Cafe Co',     email:'nithya@kochicafe.in', company:'Kochi Cafe Co',   phone:'+91 98470 11223', taxId:'32AABCU9603R1ZX' },
    { id:'c2', name:'Nimbus Logistics',  email:'ops@nimbus.in',       company:'Nimbus Logistics',phone:'+91 99620 44551', taxId:'33AAGCN2234K1Z2' },
    { id:'c3', name:'Trivandrum Textiles',email:'accounts@tvmtex.in', company:'TVM Textiles',    phone:'+91 94470 88123', taxId:'32AAICT1123M1ZP' },
    { id:'c4', name:'Peak Analytics',    email:'finance@peak.ai',     company:'Peak Analytics',  phone:'+91 80889 33442', taxId:'29AAFCP5521L1ZQ' },
  ],
  products: [
    { id:'p1', name:'Brightloop Core',     type:'service', salesPrice:money(2400), costPrice:money(900),  isActive:true,
      variants:[{id:'v1',attribute:'Brand',value:'Odoo',extraPrice:money(560)},{id:'v2',attribute:'Brand',value:'Standard',extraPrice:money(0)}] },
    { id:'p2', name:'Analytics Add-on',    type:'service', salesPrice:money(850),  costPrice:money(300),  isActive:true, variants:[] },
    { id:'p3', name:'Priority Support',    type:'service', salesPrice:money(1200), costPrice:money(450),  isActive:true, variants:[] },
    { id:'p4', name:'Onboarding Workshop', type:'goods',   salesPrice:money(5000), costPrice:money(2000), isActive:true, variants:[] },
  ],
  plans: [
    { id:'pl1', name:'Monthly Standard', price:money(2400), billingPeriod:'monthly', minQuantity:1,
      availableFrom:'2026-01-01', availableTo:'2026-12-31', autoClose:false, allowEarlyClose:true,  allowPause:true,  allowRenew:true,  isActive:true },
    { id:'pl2', name:'Annual Pro',       price:money(24000),billingPeriod:'yearly',  minQuantity:2,
      availableFrom:'2026-01-01', availableTo:'2026-12-31', autoClose:true,  allowEarlyClose:false, allowPause:false, allowRenew:true,  isActive:true },
    { id:'pl3', name:'Weekly Starter',   price:money(700),  billingPeriod:'weekly',  minQuantity:1,
      availableFrom:'2026-01-01', availableTo:'2026-12-31', autoClose:false, allowEarlyClose:true,  allowPause:true,  allowRenew:false, isActive:true },
  ],
  taxes: [
    { id:'t1', name:'GST 18%', computation:'percentage', value:'18.00', appliesToProductTypes:['service'], isActive:true },
    { id:'t2', name:'GST 12%', computation:'percentage', value:'12.00', appliesToProductTypes:['goods'],   isActive:true },
  ],
  discounts: [
    { id:'d1', name:'Volume 10%',  type:'percentage', value:'10.00',  scope:'products',      minQuantity:5, minPurchaseAmount:money(0),
      startDate:'2026-10-01', endDate:'2026-12-31', usageLimit:100, usedCount:12, isActive:true },
    { id:'d2', name:'Launch ₹500', type:'fixed',      value:money(500), scope:'subscriptions', minQuantity:1, minPurchaseAmount:money(2000),
      startDate:'2026-10-01', endDate:'2026-11-30', usageLimit:50,  usedCount:8,  isActive:true },
  ],
  subscriptions: [], invoices: [], payments: [], history: [],
};

/* --------------------------- generated records --------------------------- */
(function seed() {
  const specs = [
    ['c1','pl1','active',   1, 3, false],
    ['c2','pl2','active',   2, 6, false],
    ['c3','pl1','active',   1, 2, true ],
    ['c4','pl3','quotation',1, 0, false],
    ['c1','pl1','draft',    1, 0, false],
    ['c2','pl1','confirmed',1, 0, false],
    ['c3','pl2','closed',   2, 4, false],
  ];
  specs.forEach(([cid, plid, status, qty, nInv, paused], i) => {
    const plan = db.plans.find(p => p.id === plid);
    const cust = db.customers.find(c => c.id === cid);
    const prod = db.products[i % 3];
    const variant = prod.variants[0] || null;
    const unit = (+prod.salesPrice) + (variant ? +variant.extraPrice : 0);
    const amount = unit * qty;
    const taxRate = prod.type === 'service' ? 18 : 12;
    const taxTotal = amount * taxRate / 100;
    const start = addDays(today, -(90 - i * 9));
    const sub = {
      id: `s${i+1}`, number: uid('SUB', i+1),
      customerId: cid, customer: { id:cust.id, name:cust.name, email:cust.email },
      planId: plid, plan: { id:plan.id, name:plan.name, billingPeriod:plan.billingPeriod },
      status, isPaused: paused,
      startDate: iso(start),
      expiryDate: iso(addDays(start, plan.billingPeriod === 'yearly' ? 365 : 180)),
      nextBillingDate: status === 'active' ? iso(addDays(today, (i % 9) + 1)) : null,
      paymentTerms: 15,
      quotationValidUntil: status === 'quotation' ? iso(addDays(today, 21)) : null,
      lines: [{
        id:`sl${i+1}`, productId:prod.id, productName:prod.name,
        variantId: variant?.id ?? null, variantName: variant ? `${variant.attribute}: ${variant.value}` : null,
        quantity: qty, unitPrice: money(unit), taxName:`GST ${taxRate}%`, amount: money(amount),
      }],
      subtotal: money(amount), discountTotal: money(0), taxTotal: money(taxTotal), total: money(amount + taxTotal),
    };
    db.subscriptions.push(sub);
    db.history.push({ id:`h${i}a`, subscriptionId:sub.id, from:null, to:'draft',
      at:new Date(start).toISOString(), by:'Madhumitha K' });
    if (status !== 'draft')
      db.history.push({ id:`h${i}b`, subscriptionId:sub.id, from:'draft', to:status,
        at:addDays(start,1).toISOString(), by:'Asad Ahmed' });

    for (let k = 0; k < nInv; k++) {
      const issue = addDays(today, -(k * 30 + 6));
      const due = addDays(issue, sub.paymentTerms);
      const overdue = due < today && k === 0 && i % 3 === 0;
      const st = overdue ? 'confirmed' : (k === 0 && i % 2 === 0 ? 'confirmed' : 'paid');
      const n = db.invoices.length + 1;
      const inv = {
        id:`i${n}`, number: uid('INV', n), subscriptionId: sub.id, subscriptionNumber: sub.number,
        customerId: cid, customerDetails: { name:cust.name, email:cust.email, company:cust.company },
        status: st, issueDate: iso(issue), dueDate: iso(due),
        periodStart: iso(addDays(issue,-30)), periodEnd: iso(issue),
        lines: sub.lines.map(l => ({ ...l, id:`il${n}` })),
        subtotal: sub.subtotal, discountTotal: sub.discountTotal, taxTotal: sub.taxTotal, total: sub.total,
        amountPaid: st === 'paid' ? sub.total : money(0),
        amountDue:  st === 'paid' ? money(0)  : sub.total,
        isOverdue: overdue, sentAt: iso(issue),
      };
      db.invoices.push(inv);
      if (st === 'paid') db.payments.push({
        id:`pay${db.payments.length+1}`, invoiceId:inv.id, invoiceNumber:inv.number,
        customerId:cid, customerName:cust.name, method:['bank_transfer','upi','card','cash'][n%4],
        amount:inv.total, paymentDate: iso(addDays(due,-3)), reference:`TXN${90000+n}`, isVoided:false,
      });
    }
  });
})();

/* ------------------------------- helpers ------------------------------- */
const wait = (ms=260) => new Promise(r => setTimeout(r, ms));
const page = (rows, { page:pg=1, limit=20 } = {}) => ({
  data: rows.slice((pg-1)*limit, pg*limit),
  meta: { page:pg, limit, total:rows.length, totalPages:Math.max(1,Math.ceil(rows.length/limit)) },
});
const sum = (rows, f) => rows.reduce((a,r) => a + (+f(r)), 0);
export { ApiError };

/* ------------------------- subscription lifecycle ------------------------ */
export const SUB_FLOW = ['draft','quotation','confirmed','active','closed'];
const NEXT = { draft:'quotation', quotation:'confirmed', confirmed:'active', active:'closed' };
const logHistory = (sub, from, to) => db.history.unshift({
  id:`h${Date.now()}`, subscriptionId:sub.id, from, to, at:new Date().toISOString(), by:'You',
});

/* --------------------------------- API --------------------------------- */
const mockApi = {
  /* auth */
  async login(email, password, role) {
    await wait();
    const user = db.users.find(u => u.role === role) || db.users[0];
    return { token:'mock.jwt.token', user:{ ...user, email: email || user.email } };
  },
  logout() { localStorage.removeItem('bl_user'); },
  async me() { await wait(80); return JSON.parse(localStorage.getItem('bl_user') || 'null'); },

  /* catalogue */
  async products(q={})  { await wait(); return page(db.products, q); },
  async plans(q={})     { await wait(); return page(db.plans, q); },
  async customers(q={}) { await wait(); return page(db.customers, q); },
  async taxes(q={})     { await wait(); return page(db.taxes, q); },
  async discounts(q={}) { await wait(); return page(db.discounts, q); },
  async users(q={})     { await wait(); return page(db.users, q); },

  /* subscriptions */
  async subscriptions({ status, customerId, q:text, ...pg } = {}) {
    await wait();
    let rows = [...db.subscriptions];
    if (status)     rows = rows.filter(s => s.status === status);
    if (customerId) rows = rows.filter(s => s.customerId === customerId);
    if (text) { const t = text.toLowerCase();
      rows = rows.filter(s => s.number.toLowerCase().includes(t) || s.customer.name.toLowerCase().includes(t)); }
    return page(rows, pg);
  },
  async subscription(id) { await wait(120); return db.subscriptions.find(s => s.id === id); },
  async subscriptionHistory(id) { await wait(100); return { data: db.history.filter(h => h.subscriptionId === id) }; },

  async transition(id, action) {
    await wait(300);
    const sub  = db.subscriptions.find(s => s.id === id);
    const plan = db.plans.find(p => p.id === sub.planId);
    const from = sub.status;

    if (action === 'pause') {
      if (!plan.allowPause) throw new ApiError('BUSINESS_RULE','This plan does not allow pausing.');
      sub.isPaused = true;  logHistory(sub,'active','paused');  return sub;
    }
    if (action === 'resume') { sub.isPaused = false; logHistory(sub,'paused','active'); return sub; }
    if (action === 'renew') {
      if (!plan.allowRenew) throw new ApiError('BUSINESS_RULE','This plan does not allow renewal.');
      sub.expiryDate = iso(addDays(new Date(sub.expiryDate), plan.billingPeriod === 'yearly' ? 365 : 30));
      logHistory(sub,'active','renewed'); return sub;
    }
    if (action === 'close' && !plan.allowEarlyClose)
      throw new ApiError('BUSINESS_RULE','This plan does not allow closing early.');

    const to = NEXT[from];
    if (!to) throw new ApiError('CONFLICT', `Cannot move a ${from} subscription forward.`);
    if (from === 'draft' && sub.lines.length === 0)
      throw new ApiError('BUSINESS_RULE','Add at least one line before sending the quotation.');
    sub.status = to;
    if (to === 'active') sub.nextBillingDate = sub.startDate;
    if (to === 'closed') sub.nextBillingDate = null;
    logHistory(sub, from, to);
    return sub;
  },

  async createSubscription(input) {
    await wait(320);
    const cust = db.customers.find(c => c.id === input.customerId);
    const plan = db.plans.find(p => p.id === input.planId);
    const prod = db.products.find(p => p.id === input.productId);
    const qty  = +input.quantity || 1;
    if (qty < plan.minQuantity)
      throw new ApiError('BUSINESS_RULE', `This plan needs at least ${plan.minQuantity} units.`, [{field:'quantity',message:`Minimum is ${plan.minQuantity}`}]);
    const unit = +prod.salesPrice, amount = unit*qty;
    const rate = prod.type === 'service' ? 18 : 12, tax = amount*rate/100;
    const n = db.subscriptions.length + 1;
    const sub = {
      id:`s${n}`, number: uid('SUB', n), customerId:cust.id,
      customer:{id:cust.id,name:cust.name,email:cust.email},
      planId:plan.id, plan:{id:plan.id,name:plan.name,billingPeriod:plan.billingPeriod},
      status:'draft', isPaused:false, startDate: input.startDate || iso(today),
      expiryDate: iso(addDays(new Date(input.startDate||today), 180)),
      nextBillingDate:null, paymentTerms:15, quotationValidUntil:null,
      lines:[{ id:`sl${n}`, productId:prod.id, productName:prod.name, variantId:null, variantName:null,
               quantity:qty, unitPrice:money(unit), taxName:`GST ${rate}%`, amount:money(amount) }],
      subtotal:money(amount), discountTotal:money(0), taxTotal:money(tax), total:money(amount+tax),
    };
    db.subscriptions.unshift(sub);
    logHistory(sub, null, 'draft');
    return sub;
  },

  /* invoices */
  async invoices({ status, isOverdue, subscriptionId, customerId, q:text, ...pg } = {}) {
    await wait();
    let rows = [...db.invoices].sort((a,b) => b.issueDate.localeCompare(a.issueDate));
    if (status)         rows = rows.filter(i => i.status === status);
    if (isOverdue)      rows = rows.filter(i => i.isOverdue);
    if (subscriptionId) rows = rows.filter(i => i.subscriptionId === subscriptionId);
    if (customerId)     rows = rows.filter(i => i.customerId === customerId);
    if (text) { const t = text.toLowerCase();
      rows = rows.filter(i => i.number.toLowerCase().includes(t) || i.customerDetails.name.toLowerCase().includes(t)); }
    return page(rows, pg);
  },
  async invoice(id) { await wait(120); return db.invoices.find(i => i.id === id); },
  async invoiceAction(id, action) {
    await wait(280);
    const inv = db.invoices.find(i => i.id === id);
    if (action === 'confirm') {
      if (inv.status !== 'draft') throw new ApiError('CONFLICT','Only a draft invoice can be confirmed.');
      inv.status='confirmed'; inv.issueDate=iso(today); inv.dueDate=iso(addDays(today,15));
    }
    if (action === 'cancel') {
      if (+inv.amountPaid > 0) throw new ApiError('BUSINESS_RULE','This invoice already has a payment.');
      inv.status='cancelled'; inv.amountDue=money(0);
    }
    if (action === 'send') { inv.sentAt = iso(today); }
    return inv;
  },
  async recordPayment({ invoiceId, amount, method, paymentDate, reference }) {
    await wait(300);
    const inv = db.invoices.find(i => i.id === invoiceId);
    if (inv.status !== 'confirmed') throw new ApiError('BUSINESS_RULE','Payments are only allowed on a confirmed invoice.');
    const amt = +amount;
    if (amt <= 0)              throw new ApiError('VALIDATION_ERROR','Amount must be greater than zero.',[{field:'amount',message:'Must be more than 0'}]);
    if (amt > +inv.amountDue)  throw new ApiError('BUSINESS_RULE',`Amount cannot be more than the ${inv.amountDue} still due.`,[{field:'amount',message:'Exceeds amount due'}]);
    const cust = db.customers.find(c => c.id === inv.customerId);
    const pay = { id:`pay${db.payments.length+1}`, invoiceId, invoiceNumber:inv.number, customerId:inv.customerId,
      customerName:cust?.name ?? inv.customerDetails.name, method, amount:money(amt),
      paymentDate: paymentDate || iso(today), reference: reference || '', isVoided:false };
    db.payments.unshift(pay);
    inv.amountPaid = money(+inv.amountPaid + amt);
    inv.amountDue  = money(+inv.total - +inv.amountPaid);
    if (+inv.amountDue <= 0) { inv.status='paid'; inv.isOverdue=false; }
    return pay;
  },
  async payments({ invoiceId, ...pg } = {}) {
    await wait();
    let rows = [...db.payments];
    if (invoiceId) rows = rows.filter(p => p.invoiceId === invoiceId);
    return page(rows, pg);
  },

  /* billing */
  async billingDue(asOf) {
    await wait();
    const cut = asOf || iso(addDays(today, 10));
    const rows = db.subscriptions.filter(s => s.status==='active' && !s.isPaused && s.nextBillingDate && s.nextBillingDate <= cut);
    return page(rows, {});
  },
  async billingRun({ dryRun = false } = {}) {
    await wait(700);
    const due = db.subscriptions.filter(s => s.status==='active' && !s.isPaused && s.nextBillingDate);
    const created = [];
    due.forEach(sub => {
      if (dryRun) { created.push({ subscriptionNumber: sub.number, total: sub.total }); return; }
      const n = db.invoices.length + 1;
      const cust = db.customers.find(c => c.id === sub.customerId);
      const inv = {
        id:`i${n}`, number: uid('INV', n), subscriptionId:sub.id, subscriptionNumber:sub.number,
        customerId:sub.customerId, customerDetails:{ name:cust.name, email:cust.email, company:cust.company },
        status:'draft', issueDate:null, dueDate:null,
        periodStart: sub.nextBillingDate, periodEnd: iso(addDays(new Date(sub.nextBillingDate),30)),
        lines: sub.lines.map(l => ({...l, id:`il${n}`})),
        subtotal:sub.subtotal, discountTotal:sub.discountTotal, taxTotal:sub.taxTotal, total:sub.total,
        amountPaid:money(0), amountDue:sub.total, isOverdue:false, sentAt:null,
      };
      db.invoices.unshift(inv);
      sub.nextBillingDate = iso(addDays(new Date(sub.nextBillingDate), sub.plan.billingPeriod==='yearly'?365:30));
      created.push({ subscriptionNumber: sub.number, invoiceNumber: inv.number, total: inv.total });
    });
    return { dryRun, createdCount: created.length, failedCount: 0, created, failed: [] };
  },

  /* reports */
  async summary() {
    await wait(200);
    const active    = db.subscriptions.filter(s => s.status === 'active');
    const confirmed = db.invoices.filter(i => i.status === 'confirmed');
    const paid      = db.invoices.filter(i => i.status === 'paid');
    return {
      activeSubscriptions: active.length,
      pausedSubscriptions: active.filter(s => s.isPaused).length,
      mrr:              money(sum(active.filter(s=>s.plan.billingPeriod==='monthly'), s=>s.total)),
      revenueCollected: money(sum(paid, i => i.total)),
      outstanding:      money(sum(confirmed, i => i.amountDue)),
      overdueCount:     db.invoices.filter(i => i.isOverdue).length,
      overdueAmount:    money(sum(db.invoices.filter(i=>i.isOverdue), i => i.amountDue)),
      totalCustomers:   db.customers.length,
    };
  },
  async revenueSeries() {
    await wait(200);
    const months = ['May','Jun','Jul','Aug','Sep','Oct'];
    const base = [48000, 61000, 57500, 74000, 83500, 96000];
    return { data: months.map((m,i) => ({
      period: m, invoiced: base[i], collected: Math.round(base[i] * (0.76 + i*0.035)),
    })) };
  },
  async planMix() {
    await wait(150);
    return { data: db.plans.map(p => ({
      name: p.name, value: db.subscriptions.filter(s => s.planId === p.id).length,
    })).filter(r => r.value > 0) };
  },
};

/* ---------------------------- mock or real ---------------------------- */
let real = null;
if (!USE_MOCK) {
  // The mock seed above must not leak into real mode: the pages read db.* directly.
  Object.keys(db).forEach(k => { db[k].length = 0; });
  real = createRealApi(db, BASE_URL);
  if (localStorage.getItem('bl_user')) real.hydrate().catch(() => {});   // page reload while signed in
}
export const api = USE_MOCK ? mockApi : real.api;

/** Clear the session (token + stored user). Call from the sign-out handler. */
export const logout = () => api.logout();
