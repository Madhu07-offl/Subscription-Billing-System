import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import {
  inr, nice, niceTime, isoDate, initials, label, Badge, Icon, Empty, DataView, Pager, SearchBox, Tabs,
  Field, FormModal, Confirm, useAsync, useForm, useToast, errText,
} from '../ui';
import { useListState, can } from './shared';

const TABS = ['all', 'draft', 'confirmed', 'paid', 'cancelled', 'overdue'];
export const METHODS = ['upi', 'bank_transfer', 'card', 'cash', 'cheque', 'other'];

export function Invoices({ user }) {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const st = useListState(TABS.includes(params.get('tab')) ? params.get('tab') : 'all');
  const staff = can(user, 'admin', 'staff');
  const setTab = t => { st.setTab(t); setParams(t === 'all' ? {} : { tab: t }, { replace: true }); };
  const r = useAsync(() => api.invoices({
    status: ['all', 'overdue'].includes(st.tab) ? undefined : st.tab,
    isOverdue: st.tab === 'overdue' ? true : undefined,
    q: st.dq, page: st.page, limit: 20,
  }), [st.tab, st.dq, st.page]);
  const open = id => nav(`/invoices/${id}`);

  return (
    <div className="fade">
      <div className="toolbar">
        <Tabs tabs={TABS} value={st.tab} onChange={setTab} />
        <span className="spacer" />
        <SearchBox value={st.q} onChange={st.setQ} placeholder="Search invoice or customer" />
      </div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="invoices" title={st.dq ? `No invoices match “${st.dq}”` : 'No invoices here'}
          hint={st.tab === 'all' ? 'Invoices are created by the billing run.' : 'Try another tab.'} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Invoice</th>{staff && <th>Customer</th>}<th>Subscription</th><th>Issued</th><th>Due</th><th>Status</th><th className="num">Total</th><th className="num">Outstanding</th></tr></thead>
              <tbody>{data.data.map(i => (
                <tr key={i.id} className="row-link" tabIndex={0} onClick={() => open(i.id)} onKeyDown={e => e.key === 'Enter' && open(i.id)}>
                  <td className="mono">{i.number}</td>
                  {staff && <td><div className="who"><span className="avatar">{initials(i.customer.name)}</span>{i.customer.name}</div></td>}
                  <td className="dim mono">{i.subscriptionNumber}</td>
                  <td className="dim">{nice(i.issueDate)}</td>
                  <td className={i.isOverdue ? 'overdue-txt' : 'dim'}>{nice(i.dueDate)}</td>
                  <td><Badge status={i.status} overdue={i.isOverdue} /></td>
                  <td className="num">{inr(i.total)}</td>
                  <td className={`num ${+i.amountDue > 0 ? 'amt-due' : 'dim'}`}>{inr(i.amountDue)}</td>
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
    </div>
  );
}

function PaymentModal({ invoice, onClose, onDone }) {
  const f = useForm({ amount: invoice.amountDue, method: 'upi', paymentDate: isoDate(), reference: '', note: '' });
  const v = f.values;
  const save = () => f.submit(
    x => ({
      amount: !(+x.amount > 0) ? 'Enter an amount greater than zero.' : +x.amount > +invoice.amountDue ? `Cannot be more than ${inr(invoice.amountDue)} still due.` : null,
      paymentDate: !x.paymentDate && 'Choose the payment date.',
    }),
    async x => {
      const body = { invoiceId: invoice.id, method: x.method, amount: (+x.amount).toFixed(2), paymentDate: x.paymentDate };
      if (x.reference.trim()) body.reference = x.reference.trim();
      if (x.note.trim()) body.note = x.note.trim();
      onDone(await api.recordPayment(body));
    },
  );
  return (
    <FormModal title={`Record payment · ${invoice.number}`} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message} submitLabel="Record payment">
      <Field label="Amount *" error={f.errors.amount} hint={`${inr(invoice.amountDue)} still due · partial payments are fine`}>
        <input className={`input ${f.errors.amount ? 'err' : ''}`} type="number" min="0.01" step="0.01" value={v.amount} onChange={f.set('amount')} autoFocus /></Field>
      <div className="row">
        <Field label="Method"><select className="input" value={v.method} onChange={f.set('method')}>
          {METHODS.map(m => <option key={m} value={m}>{label(m)}</option>)}</select></Field>
        <Field label="Date *" error={f.errors.paymentDate}><input className={`input ${f.errors.paymentDate ? 'err' : ''}`} type="date" value={v.paymentDate} onChange={f.set('paymentDate')} /></Field>
      </div>
      <Field label="Reference" hint="Optional — transaction id or cheque number" error={f.errors.reference}>
        <input className="input" value={v.reference} onChange={f.set('reference')} placeholder="TXN…" /></Field>
      <Field label="Note" hint="Optional"><input className="input" value={v.note} onChange={f.set('note')} /></Field>
    </FormModal>
  );
}

function SendModal({ invoice, onClose, onDone }) {
  const f = useForm({ to: invoice.customerDetails?.email || '', message: '' });
  const save = () => f.submit(
    x => ({ to: !/^\S+@\S+\.\S+$/.test(x.to) && 'Enter a valid email address.' }),
    async x => onDone(await api.invoiceAction(invoice.id, 'send', { to: x.to.trim(), ...(x.message.trim() ? { message: x.message.trim() } : {}) })),
  );
  return (
    <FormModal title={`Send ${invoice.number}`} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message} submitLabel="Send invoice">
      <Field label="To" error={f.errors.to}><input className={`input ${f.errors.to ? 'err' : ''}`} type="email" value={f.values.to} onChange={f.set('to')} autoFocus /></Field>
      <Field label="Message" hint="Optional"><textarea className="input" rows="3" value={f.values.message} onChange={f.set('message')} /></Field>
    </FormModal>
  );
}

export function InvoiceDetail({ user }) {
  const { id } = useParams();
  const toast = useToast();
  const staff = can(user, 'admin', 'staff');
  const r = useAsync(() => api.invoice(id), [id]);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  const confirm = async () => {
    setBusy(true);
    try { await api.invoiceAction(id, 'confirm'); toast('Invoice confirmed. It can now be paid.'); r.reload(); }
    catch (e) { toast(errText(e), true); }
    setBusy(false);
  };

  if (r.error || !r.data) return <div className="card"><DataView r={r} rows={8}>{() => null}</DataView></div>;
  const i = r.data;
  const c = i.customerDetails || i.customer;
  const addr = c.address ? [c.address.line1, c.address.line2, c.address.city, c.address.state, c.address.postalCode, c.address.country].filter(Boolean).join(', ') : '';
  const done = msg => { setDialog(null); toast(msg); r.reload(); };

  return (
    <div className="fade">
      <div className="toolbar detail-bar no-print">
        <Link to="/invoices" className="btn btn-ghost btn-sm"><Icon name="back" />Invoices</Link>
        <h2 className="detail-title">{i.number}</h2>
        <Badge status={i.status} overdue={i.isOverdue} />
        <span className="spacer" />
        <div className="actions">
          {staff && ['draft', 'confirmed'].includes(i.status) && +i.amountPaid === 0 &&
            <button className="btn" onClick={() => setDialog('cancel')}><Icon name="x" />Cancel invoice</button>}
          <button className="btn" onClick={() => window.print()}><Icon name="print" />Print</button>
          {staff && ['confirmed', 'paid'].includes(i.status) && <button className="btn" onClick={() => setDialog('send')}><Icon name="send" />{i.sentAt ? 'Send again' : 'Send'}</button>}
          {staff && i.status === 'draft' && <button className="btn btn-primary" disabled={busy} onClick={confirm}><Icon name="check" />{busy ? 'Working…' : 'Confirm'}</button>}
          {staff && i.status === 'confirmed' && +i.amountDue > 0 && <button className="btn btn-primary" onClick={() => setDialog('pay')}><Icon name="payments" />Record payment</button>}
        </div>
      </div>

      <div className="print-only print-head">
        <div className="brand"><span className="brand-mark">B</span> Brightloop</div>
        <div><h2>Invoice {i.number}</h2><div>Status: {label(i.isOverdue ? 'overdue' : i.status)}</div></div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-h"><h3>Lines</h3><span className="spacer" />
            <span className="dim">Period {nice(i.periodStart)} – {nice(i.periodEnd)}</span></div>
          <div className="tbl-wrap"><table>
            <thead><tr><th>Description</th><th className="num">Qty</th><th className="num">Unit</th><th className="num">Discount</th><th>Tax</th><th className="num">Amount</th></tr></thead>
            <tbody>{i.lines.map(l => (
              <tr key={l.id}><td className="wrap">{l.description}</td>
                <td className="num">{l.quantity}</td><td className="num">{inr(l.unitPrice)}</td>
                <td className="num dim">{+l.discountAmount > 0 ? `−${inr(l.discountAmount)}` : '—'}</td>
                <td className="dim">{l.taxName ? `${l.taxName} · ${inr(l.taxAmount)}` : 'No tax'}</td>
                <td className="num">{inr(l.amount)}</td></tr>))}</tbody>
          </table></div>
          <div className="card-b totals">
            <div className="kv"><span className="k">Subtotal</span><span className="v">{inr(i.subtotal)}</span></div>
            <div className="kv"><span className="k">Discount</span><span className="v ok">−{inr(i.discountTotal)}</span></div>
            <div className="kv"><span className="k">Tax</span><span className="v">{inr(i.taxTotal)}</span></div>
            <div className="kv total-row"><span>Total</span><span>{inr(i.total)}</span></div>
            <div className="kv"><span className="k">Paid</span><span className="v ok">{inr(i.amountPaid)}</span></div>
            <div className="kv"><span className="k">Still due</span><span className={`v ${+i.amountDue > 0 ? 'amt-due' : 'ok'}`}>{inr(i.amountDue)}</span></div>
          </div>
        </div>

        <div className="col">
          <div className="card"><div className="card-h"><h3>Bill to</h3></div><div className="card-b">
            <div className="bill-name">{c.name}</div>
            {c.company && <div className="dim">{c.company}</div>}
            <div className="dim">{c.email}</div>
            {c.phone && <div className="dim">{c.phone}</div>}
            {addr && <div className="dim">{addr}</div>}
            {c.taxId && <div className="dim">Tax ID {c.taxId}</div>}
            <div style={{ marginTop: 12 }}>
              <div className="kv"><span className="k">Subscription</span>
                <Link className="v mono link" to={`/subscriptions/${i.subscriptionId}`}>{i.subscriptionNumber}</Link></div>
              <div className="kv"><span className="k">Issued</span><span className="v">{nice(i.issueDate)}</span></div>
              <div className="kv"><span className="k">Due</span><span className={`v ${i.isOverdue ? 'overdue-txt' : ''}`}>{nice(i.dueDate)}</span></div>
              {i.sentAt && <div className="kv"><span className="k">Sent</span><span className="v">{niceTime(i.sentAt)}</span></div>}
            </div>
            {i.notes && <div className="note">{i.notes}</div>}
          </div></div>

          <div className="card"><div className="card-h"><h3>Payments</h3></div>
            {(i.payments || []).length === 0
              ? <Empty icon="payments" title="No payments yet" hint={i.status === 'draft' ? 'Confirm the invoice before recording a payment.' : undefined} />
              : <div className="card-b">{i.payments.map(x => (
                <div className="kv" key={x.id}>
                  <span className="k">{label(x.method)}{x.isVoided && <> <Badge status="voided" /></>}
                    <div className="dim">{nice(x.paymentDate)}{x.reference ? ` · ${x.reference}` : ''}</div></span>
                  <span className={`v ${x.isVoided ? 'struck' : ''}`}>{inr(x.amount)}</span></div>))}</div>}
          </div>
        </div>
      </div>

      {dialog === 'pay' && <PaymentModal invoice={i} onClose={() => setDialog(null)} onDone={p => done(`Payment of ${inr(p.amount)} recorded.`)} />}
      {dialog === 'send' && <SendModal invoice={i} onClose={() => setDialog(null)} onDone={() => done('Invoice sent.')} />}
      {dialog === 'cancel' && <Confirm title={`Cancel ${i.number}?`} danger confirmLabel="Cancel invoice" onClose={() => setDialog(null)}
        body="A cancelled invoice cannot be paid or reopened."
        onConfirm={async () => { await api.invoiceAction(i.id, 'cancel'); done('Invoice cancelled.'); }} />}
    </div>
  );
}
