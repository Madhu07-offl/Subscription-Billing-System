import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, fetchAll } from '../api';
import {
  inr, nice, niceTime, isoDate, initials, label, TERMS, Badge, Icon, Empty, DataView, Pager, SearchBox, Tabs,
  Field, FormModal, Confirm, useAsync, useForm, useToast, errText,
} from '../ui';
import { useListState, useCatalog, LineEditor, blankLine, checkLines, toLineInput, can } from './shared';

const TABS = ['all', 'draft', 'quotation', 'confirmed', 'active', 'closed'];
const STEPS = ['draft', 'quotation', 'confirmed', 'active', 'closed'];

function Flow({ status }) {
  const at = STEPS.indexOf(status);
  return (
    <ol className="flow">
      {STEPS.map((s, i) => (
        <li key={s} className={`flow-step ${i < at ? 'done' : ''} ${i === at ? 'now' : ''}`}>
          {i > 0 && <i className={`flow-line ${i <= at ? 'done' : ''}`} />}
          <span className="n">{i < at ? <Icon name="check" /> : i + 1}</span>{label(s)}
        </li>
      ))}
    </ol>
  );
}

function StatusCell({ s }) {
  return <div className="badges"><Badge status={s.status} />{s.isPaused && <Badge status="paused" />}</div>;
}

/* ------------------------------- create ------------------------------- */
function NewSubscription({ onClose, onDone }) {
  const cat = useCatalog({ customers: true });
  const tpl = useAsync(() => fetchAll(api.templates), []);
  const f = useForm({ customerId: '', templateId: '', planId: '', startDate: isoDate(), paymentTerms: 'immediate', notes: '', lines: [blankLine()] });
  const v = f.values;
  const save = () => f.submit(
    x => ({
      customerId: !x.customerId && 'Choose a customer.',
      lines: checkLines(x.lines, { required: !x.templateId }),
    }),
    async x => {
      const body = { customerId: x.customerId, startDate: x.startDate || null, paymentTerms: x.paymentTerms };
      if (x.templateId) body.templateId = x.templateId;
      if (x.planId) body.planId = x.planId;
      if (x.notes.trim()) body.notes = x.notes.trim();
      const lines = toLineInput(x.lines);
      if (lines.length) body.lines = lines;
      const s = await api.createSubscription(body);
      onDone(s);
    },
  );
  return (
    <FormModal title="New subscription" onClose={onClose} onSubmit={save} busy={f.busy || !cat.data} message={f.message || (cat.error && errText(cat.error))} submitLabel="Create draft" wide>
      {!cat.data ? <p className="dim">Loading customers, plans and products…</p> : <>
        <div className="row">
          <Field label="Customer *" error={f.errors.customerId}>
            <select className={`input ${f.errors.customerId ? 'err' : ''}`} value={v.customerId} onChange={f.set('customerId')} autoFocus>
              <option value="">Choose a customer…</option>
              {cat.data.customers.map(c => <option key={c.id} value={c.id}>{c.name} · {c.email}</option>)}
            </select></Field>
          <Field label="Quotation template" hint="Optional: fills plan and lines for you." error={f.errors.templateId}>
            <select className="input" value={v.templateId} onChange={f.set('templateId')}>
              <option value="">None</option>
              {(tpl.data || []).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select></Field>
        </div>
        <div className="row">
          <Field label="Plan" error={f.errors.planId} hint={v.templateId ? 'Leave empty to use the template’s plan.' : 'Needed before the quotation is sent.'}>
            <select className={`input ${f.errors.planId ? 'err' : ''}`} value={v.planId} onChange={f.set('planId')}>
              <option value="">{v.templateId ? 'From template' : 'Choose later'}</option>
              {cat.data.plans.map(p => <option key={p.id} value={p.id}>{p.name} · {inr(p.price)} / {p.billingPeriod}</option>)}
            </select></Field>
          <Field label="Start date" error={f.errors.startDate}>
            <input className={`input ${f.errors.startDate ? 'err' : ''}`} type="date" value={v.startDate} onChange={f.set('startDate')} /></Field>
          <Field label="Payment terms" error={f.errors.paymentTerms}>
            <select className="input" value={v.paymentTerms} onChange={f.set('paymentTerms')}>
              {Object.entries(TERMS).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select></Field>
        </div>
        <Field label={v.templateId ? 'Lines (optional, replaces the template’s lines)' : 'Lines *'}>
          <LineEditor lines={v.lines} onChange={f.set('lines')} products={cat.data.products} error={f.errors.lines} />
        </Field>
        <Field label="Notes" hint="Optional"><textarea className="input" rows="2" value={v.notes} onChange={f.set('notes')} /></Field>
      </>}
    </FormModal>
  );
}

function RequestSubscription({ onClose, onDone }) {
  const cat = useCatalog();
  const f = useForm({ planId: '', startDate: isoDate(), notes: '', lines: [blankLine()] });
  const v = f.values;
  const save = () => f.submit(
    x => ({ planId: !x.planId && 'Choose a plan.', startDate: !x.startDate && 'Choose a start date.', lines: checkLines(x.lines) }),
    async x => {
      const s = await api.requestSubscription({ planId: x.planId, startDate: x.startDate, lines: toLineInput(x.lines), ...(x.notes.trim() ? { notes: x.notes.trim() } : {}) });
      onDone(s);
    },
  );
  return (
    <FormModal title="Request a subscription" onClose={onClose} onSubmit={save} busy={f.busy || !cat.data} message={f.message || (cat.error && errText(cat.error))} submitLabel="Send request" wide>
      {!cat.data ? <p className="dim">Loading plans and products…</p> : <>
        <p className="muted" style={{ marginBottom: 16 }}>Our team reviews your request and sends you a quotation.</p>
        <div className="row">
          <Field label="Plan *" error={f.errors.planId}>
            <select className={`input ${f.errors.planId ? 'err' : ''}`} value={v.planId} onChange={f.set('planId')} autoFocus>
              <option value="">Choose a plan…</option>
              {cat.data.plans.map(p => <option key={p.id} value={p.id}>{p.name} · {inr(p.price)} / {p.billingPeriod}</option>)}
            </select></Field>
          <Field label="Start date *" error={f.errors.startDate}>
            <input className={`input ${f.errors.startDate ? 'err' : ''}`} type="date" value={v.startDate} onChange={f.set('startDate')} /></Field>
        </div>
        <Field label="What do you need? *"><LineEditor lines={v.lines} onChange={f.set('lines')} products={cat.data.products} error={f.errors.lines} /></Field>
        <Field label="Notes" hint="Optional"><textarea className="input" rows="2" value={v.notes} onChange={f.set('notes')} /></Field>
      </>}
    </FormModal>
  );
}

/* -------------------------------- list -------------------------------- */
export function Subscriptions({ user }) {
  const toast = useToast();
  const nav = useNavigate();
  const st = useListState('all');
  const [modal, setModal] = useState(false);
  const staff = can(user, 'admin', 'staff');
  const r = useAsync(() => api.subscriptions({ status: st.tab === 'all' ? undefined : st.tab, q: st.dq, page: st.page, limit: 20 }), [st.tab, st.dq, st.page]);
  const open = id => nav(`/subscriptions/${id}`);

  return (
    <div className="fade">
      <div className="toolbar">
        <Tabs tabs={TABS} value={st.tab} onChange={st.setTab} />
        <span className="spacer" />
        <SearchBox value={st.q} onChange={st.setQ} placeholder="Search number or customer" />
        <button className="btn btn-primary" onClick={() => setModal(true)}><Icon name="plus" />{staff ? 'New subscription' : 'Request subscription'}</button>
      </div>

      <div className="card">
        <DataView r={r} empty={<Empty icon="subscriptions" title={st.dq ? `No subscriptions match “${st.dq}”` : 'No subscriptions here'}
          hint={st.tab !== 'all' ? 'Try another status tab.' : staff ? 'Create the first one to get started.' : 'Request one and we’ll send you a quotation.'} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Number</th>{staff && <th>Customer</th>}<th>Plan</th><th>Status</th><th>Start</th><th>Next billing</th><th className="num">Total</th></tr></thead>
              <tbody>{data.data.map(s => (
                <tr key={s.id} className="row-link" tabIndex={0} onClick={() => open(s.id)} onKeyDown={e => e.key === 'Enter' && open(s.id)}>
                  <td className="mono">{s.number}</td>
                  {staff && <td><div className="who"><span className="avatar">{initials(s.customer.name)}</span>{s.customer.name}</div></td>}
                  <td>{s.plan ? <>{s.plan.name}<div className="dim">{s.plan.billingPeriod}</div></> : <span className="dim">No plan yet</span>}</td>
                  <td><StatusCell s={s} /></td>
                  <td className="dim">{nice(s.startDate)}</td>
                  <td className="dim">{nice(s.nextBillingDate)}</td>
                  <td className="num">{inr(s.total)}</td>
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>

      {modal && (staff
        ? <NewSubscription onClose={() => setModal(false)} onDone={s => { setModal(false); toast(`${s.number} created as a draft.`); open(s.id); }} />
        : <RequestSubscription onClose={() => setModal(false)} onDone={s => { setModal(false); toast(`Request ${s.number} sent.`); open(s.id); }} />)}
    </div>
  );
}

/* ------------------------------- detail ------------------------------- */
function EditDraft({ s, onClose, onDone }) {
  const cat = useCatalog();
  const f = useForm({
    planId: s.plan?.id || '', startDate: s.startDate || '', expiryDate: s.expiryDate || '', paymentTerms: s.paymentTerms || 'immediate',
    notes: s.notes || '',
    lines: s.lines.length ? s.lines.map(l => ({ key: l.id, productId: l.productId, variantId: l.variantId || '', quantity: l.quantity })) : [blankLine()],
  });
  const v = f.values;
  const save = () => f.submit(
    x => ({ lines: checkLines(x.lines) }),
    async x => {
      const body = { paymentTerms: x.paymentTerms, notes: x.notes, lines: toLineInput(x.lines) };
      if (x.planId) body.planId = x.planId;
      if (x.startDate) body.startDate = x.startDate;
      if (x.expiryDate) body.expiryDate = x.expiryDate;
      onDone(await api.updateSubscription(s.id, body));
    },
  );
  return (
    <FormModal title={`Edit ${s.number}`} onClose={onClose} onSubmit={save} busy={f.busy || !cat.data} message={f.message || (cat.error && errText(cat.error))} wide>
      {!cat.data ? <p className="dim">Loading…</p> : <>
        <div className="row">
          <Field label="Plan" error={f.errors.planId}>
            <select className="input" value={v.planId} onChange={f.set('planId')}>
              <option value="">Choose a plan…</option>
              {cat.data.plans.map(p => <option key={p.id} value={p.id}>{p.name} · {inr(p.price)} / {p.billingPeriod}</option>)}
            </select></Field>
          <Field label="Payment terms"><select className="input" value={v.paymentTerms} onChange={f.set('paymentTerms')}>
            {Object.entries(TERMS).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></Field>
        </div>
        <div className="row">
          <Field label="Start date" error={f.errors.startDate}><input className="input" type="date" value={v.startDate} onChange={f.set('startDate')} /></Field>
          <Field label="Expiry date" error={f.errors.expiryDate} hint="Optional"><input className="input" type="date" value={v.expiryDate} onChange={f.set('expiryDate')} /></Field>
        </div>
        <Field label="Lines"><LineEditor lines={v.lines} onChange={f.set('lines')} products={cat.data.products} error={f.errors.lines} /></Field>
        <Field label="Notes"><textarea className="input" rows="2" value={v.notes} onChange={f.set('notes')} /></Field>
      </>}
    </FormModal>
  );
}

const ACTIONS = {
  'send-quotation': { label: 'Send quotation', done: 'Quotation sent.', icon: 'send' },
  confirm:  { label: 'Confirm', done: 'Subscription confirmed.', icon: 'check' },
  activate: { label: 'Activate', done: 'Subscription is now active.', icon: 'bolt' },
  pause:    { label: 'Pause', done: 'Subscription paused.', icon: 'pause' },
  resume:   { label: 'Resume', done: 'Subscription resumed.', icon: 'play' },
};

export function SubscriptionDetail({ user }) {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const staff = can(user, 'admin', 'staff');
  const r = useAsync(() => api.subscription(id), [id]);
  const h = useAsync(() => api.subscriptionHistory(id), [id]);
  const inv = useAsync(() => api.subscriptionInvoices(id), [id]);
  const [busy, setBusy] = useState(null);
  const [dialog, setDialog] = useState(null);
  const refresh = () => { r.reload(); h.reload(); inv.reload(); };

  const run = async action => {
    setBusy(action);
    try { await api.subscriptionAction(id, action); toast(ACTIONS[action].done); refresh(); }
    catch (e) { toast(errText(e), true); }
    setBusy(null);
  };

  if (r.error || !r.data) return <div className="card"><DataView r={r} rows={8}>{() => null}</DataView></div>;
  const s = r.data;
  const p = s.plan;
  const btn = (action, primary) => (
    <button key={action} className={`btn ${primary ? 'btn-primary' : ''}`} disabled={!!busy} onClick={() => run(action)}>
      <Icon name={ACTIONS[action].icon} />{busy === action ? 'Working…' : ACTIONS[action].label}</button>);
  const why = (ok, msg) => (ok ? undefined : msg);

  return (
    <div className="fade">
      <div className="toolbar detail-bar">
        <Link to="/subscriptions" className="btn btn-ghost btn-sm"><Icon name="back" />Subscriptions</Link>
        <h2 className="detail-title">{s.number}</h2>
        <StatusCell s={s} />
        <span className="spacer" />
        <div className="actions">
          {staff && s.status === 'draft' && <>
            <button className="btn" onClick={() => setDialog('delete')}><Icon name="trash" />Delete</button>
            <button className="btn" onClick={() => setDialog('edit')}><Icon name="edit" />Edit</button>
            {btn('send-quotation', true)}</>}
          {staff && s.status === 'quotation' && btn('confirm', true)}
          {staff && s.status === 'confirmed' && btn('activate', true)}
          {s.status === 'active' && <>
            {s.isPaused ? btn('resume')
              : <span title={why(p?.allowPause, 'This plan does not allow pausing')}><button className="btn" disabled={!!busy || !p?.allowPause} onClick={() => run('pause')}><Icon name="pause" />{busy === 'pause' ? 'Working…' : 'Pause'}</button></span>}
            <span title={why(p?.allowRenew, 'This plan does not allow renewal')}><button className="btn" disabled={!!busy || !p?.allowRenew} onClick={() => setDialog('renew')}><Icon name="refresh" />Renew</button></span>
            <span title={why(p?.allowEarlyClose, 'This plan does not allow closing early')}><button className="btn btn-danger" disabled={!!busy || !p?.allowEarlyClose} onClick={() => setDialog('close')}><Icon name="x" />Close</button></span>
          </>}
        </div>
      </div>

      <div className="card flow-card"><Flow status={s.status} /></div>

      <div className="grid-2">
        <div className="col">
          <div className="card">
            <div className="card-h"><h3>Lines</h3></div>
            {s.lines.length === 0 ? <Empty icon="products" title="No lines yet" hint={staff && s.status === 'draft' ? 'Edit the draft to add products.' : undefined} /> : <>
              <div className="tbl-wrap"><table>
                <thead><tr><th>Product</th><th className="num">Qty</th><th className="num">Unit price</th><th>Tax</th><th className="num">Amount</th></tr></thead>
                <tbody>{s.lines.map(l => (
                  <tr key={l.id}><td>{l.productName}{l.variantLabel && <div className="dim">{l.variantLabel}</div>}</td>
                    <td className="num">{l.quantity}</td><td className="num">{inr(l.unitPrice)}</td>
                    <td className="dim">{l.taxName ? `${l.taxName}` : 'No tax'}</td><td className="num">{inr(l.amount)}</td></tr>))}</tbody>
              </table></div>
              <div className="card-b totals">
                <div className="kv"><span className="k">Subtotal</span><span className="v">{inr(s.subtotal)}</span></div>
                <div className="kv"><span className="k">Tax</span><span className="v">{inr(s.taxTotal)}</span></div>
                <div className="kv total-row"><span>Total</span><span>{inr(s.total)}</span></div>
              </div></>}
          </div>

          <div className="card">
            <div className="card-h"><h3>Invoices</h3></div>
            <DataView r={inv} rows={3} empty={<Empty icon="invoices" title="No invoices yet" hint="Invoices appear after the billing run." />}>
              {data => (
                <div className="tbl-wrap"><table>
                  <thead><tr><th>Invoice</th><th>Period</th><th>Status</th><th className="num">Total</th><th className="num">Due</th></tr></thead>
                  <tbody>{data.data.map(i => (
                    <tr key={i.id} className="row-link" tabIndex={0} onClick={() => nav(`/invoices/${i.id}`)} onKeyDown={e => e.key === 'Enter' && nav(`/invoices/${i.id}`)}>
                      <td className="mono">{i.number}</td><td className="dim">{nice(i.periodStart)} – {nice(i.periodEnd)}</td>
                      <td><Badge status={i.status} overdue={i.isOverdue} /></td>
                      <td className="num">{inr(i.total)}</td><td className={`num ${+i.amountDue > 0 ? 'amt-due' : 'dim'}`}>{inr(i.amountDue)}</td></tr>))}</tbody>
                </table></div>)}
            </DataView>
          </div>
        </div>

        <div className="col">
          <div className="card"><div className="card-h"><h3>Details</h3></div><div className="card-b">
            <div className="kv"><span className="k">Customer</span><span className="v">{s.customer.name}</span></div>
            <div className="kv"><span className="k">Plan</span><span className="v">{p ? p.name : '—'}</span></div>
            <div className="kv"><span className="k">Billing</span><span className="v">{p ? label(p.billingPeriod) : '—'}</span></div>
            <div className="kv"><span className="k">Start</span><span className="v">{nice(s.startDate)}</span></div>
            <div className="kv"><span className="k">Expiry</span><span className="v">{nice(s.expiryDate)}</span></div>
            <div className="kv"><span className="k">Next billing</span><span className="v">{nice(s.nextBillingDate)}</span></div>
            <div className="kv"><span className="k">Payment terms</span><span className="v">{TERMS[s.paymentTerms] || '—'}</span></div>
            {s.quotationValidUntil && <div className="kv"><span className="k">Quotation valid until</span><span className="v">{nice(s.quotationValidUntil)}</span></div>}
            {s.closedAt && <div className="kv"><span className="k">Closed</span><span className="v">{nice(s.closedAt)}</span></div>}
            {s.closeReason && <div className="kv"><span className="k">Close reason</span><span className="v">{s.closeReason}</span></div>}
            {s.notes && <div className="note">{s.notes}</div>}
          </div></div>

          {p && <div className="card"><div className="card-h"><h3>Plan rules</h3></div><div className="card-b">
            {[['Close early', 'allowEarlyClose'], ['Pause', 'allowPause'], ['Renew', 'allowRenew']].map(([l, k]) =>
              <div className="kv" key={k}><span className="k">{l}</span>
                <span className={`v ${p[k] ? 'ok' : 'dim'}`}>{p[k] ? 'Allowed' : 'Not allowed'}</span></div>)}
          </div></div>}

          <div className="card"><div className="card-h"><h3>History</h3></div>
            <DataView r={h} rows={3} empty={<Empty icon="billing" title="No history yet" />}>
              {data => <div className="card-b history">{data.data.map(e => (
                <div className="kv" key={e.id}>
                  <span className="k">
                    {e.event === 'created' ? `Created as ${e.toStatus}` : e.event === 'status_change' ? `${label(e.fromStatus)} → ${label(e.toStatus)}` : label(e.event)}
                    <div className="dim">{e.changedBy?.name || 'System'}{e.reason ? ` · ${e.reason}` : ''}</div>
                  </span>
                  <span className="v dim">{niceTime(e.createdAt)}</span></div>))}</div>}
            </DataView>
          </div>
        </div>
      </div>

      {dialog === 'edit' && <EditDraft s={s} onClose={() => setDialog(null)} onDone={() => { setDialog(null); toast('Draft updated.'); refresh(); }} />}
      {dialog === 'delete' && <Confirm title={`Delete ${s.number}?`} danger confirmLabel="Delete draft"
        body="This removes the draft for good. Only drafts can be deleted." onClose={() => setDialog(null)}
        onConfirm={async () => { await api.deleteSubscription(s.id); toast(`${s.number} deleted.`); nav('/subscriptions'); }} />}
      {dialog === 'close' && <CloseDialog s={s} onClose={() => setDialog(null)} onDone={() => { setDialog(null); toast('Subscription closed.'); refresh(); }} />}
      {dialog === 'renew' && <RenewDialog s={s} onClose={() => setDialog(null)} onDone={() => { setDialog(null); toast('Subscription renewed.'); refresh(); }} />}
    </div>
  );
}

function CloseDialog({ s, onClose, onDone }) {
  const [reason, setReason] = useState('');
  return (
    <Confirm title={`Close ${s.number}?`} danger confirmLabel="Close subscription" onClose={onClose}
      body="No more invoices will be created for it. Existing invoices are not affected."
      onConfirm={async () => { await api.subscriptionAction(s.id, 'close', reason.trim() ? { reason: reason.trim() } : {}); onDone(); }}>
      <Field label="Reason" hint="Optional"><input className="input" value={reason} onChange={e => setReason(e.target.value)} autoFocus /></Field>
    </Confirm>
  );
}

function RenewDialog({ s, onClose, onDone }) {
  const [date, setDate] = useState('');
  return (
    <Confirm title={`Renew ${s.number}`} confirmLabel="Renew" onClose={onClose}
      body={`Current expiry: ${nice(s.expiryDate)}. Leave the date empty to extend by one more term.`}
      onConfirm={async () => { await api.subscriptionAction(s.id, 'renew', date ? { newExpiryDate: date } : {}); onDone(); }}>
      <Field label="New expiry date" hint="Optional"><input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} /></Field>
    </Confirm>
  );
}
