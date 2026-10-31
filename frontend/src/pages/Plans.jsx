import { useState } from 'react';
import { api } from '../api';
import { inr, nice, isoDate, label, Badge, Icon, Empty, DataView, Pager, SearchBox, Tabs, Field, Check, FormModal, Confirm, useAsync, useForm, useToast } from '../ui';
import { useListState, can } from './shared';

const PERIODS = ['daily', 'weekly', 'monthly', 'yearly'];

function PlanForm({ plan, onClose, onDone }) {
  const f = useForm({
    name: plan?.name || '', price: plan?.price || '', billingPeriod: plan?.billingPeriod || 'monthly', minQuantity: plan?.minQuantity ?? 1,
    availableFrom: plan?.availableFrom || isoDate(), availableTo: plan?.availableTo || '',
    autoClose: plan?.autoClose ?? false, allowEarlyClose: plan?.allowEarlyClose ?? false, allowPause: plan?.allowPause ?? false, allowRenew: plan?.allowRenew ?? true,
    isActive: plan?.isActive ?? true,
  });
  const v = f.values;
  const save = () => f.submit(
    x => ({
      name: !x.name.trim() && 'Name is required.',
      price: (x.price === '' || +x.price < 0) && 'Enter a price of 0 or more.',
      minQuantity: (!Number.isInteger(+x.minQuantity) || +x.minQuantity < 1) && 'Whole number, at least 1.',
      availableFrom: !x.availableFrom && 'Choose a start date.',
      availableTo: x.availableTo && x.availableFrom && x.availableTo < x.availableFrom && 'Must not be before the start date.',
    }),
    async x => {
      const body = {
        name: x.name.trim(), price: (+x.price).toFixed(2), billingPeriod: x.billingPeriod, minQuantity: +x.minQuantity,
        availableFrom: x.availableFrom, availableTo: x.availableTo || null,
        autoClose: x.autoClose, allowEarlyClose: x.allowEarlyClose, allowPause: x.allowPause, allowRenew: x.allowRenew, isActive: x.isActive,
      };
      onDone(plan ? await api.updatePlan(plan.id, body) : await api.createPlan(body));
    },
  );
  return (
    <FormModal title={plan ? 'Edit plan' : 'New plan'} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message}>
      <Field label="Name *" error={f.errors.name}><input className={`input ${f.errors.name ? 'err' : ''}`} value={v.name} onChange={f.set('name')} autoFocus /></Field>
      <div className="row">
        <Field label="Price *" error={f.errors.price}><input className={`input ${f.errors.price ? 'err' : ''}`} type="number" min="0" step="0.01" value={v.price} onChange={f.set('price')} /></Field>
        <Field label="Billing period"><select className="input" value={v.billingPeriod} onChange={f.set('billingPeriod')}>{PERIODS.map(p => <option key={p} value={p}>{label(p)}</option>)}</select></Field>
        <Field label="Min quantity" error={f.errors.minQuantity}><input className={`input ${f.errors.minQuantity ? 'err' : ''}`} type="number" min="1" step="1" value={v.minQuantity} onChange={f.set('minQuantity')} /></Field>
      </div>
      <div className="row">
        <Field label="Available from *" error={f.errors.availableFrom}><input className={`input ${f.errors.availableFrom ? 'err' : ''}`} type="date" value={v.availableFrom} onChange={f.set('availableFrom')} /></Field>
        <Field label="Available until" hint="Leave empty for no end date" error={f.errors.availableTo}><input className={`input ${f.errors.availableTo ? 'err' : ''}`} type="date" value={v.availableTo} onChange={f.set('availableTo')} /></Field>
      </div>
      <div className="checks">
        <Check checked={v.allowPause} onChange={f.set('allowPause')}>Customers can pause</Check>
        <Check checked={v.allowEarlyClose} onChange={f.set('allowEarlyClose')}>Can be closed early</Check>
        <Check checked={v.allowRenew} onChange={f.set('allowRenew')}>Can be renewed</Check>
        <Check checked={v.autoClose} onChange={f.set('autoClose')}>Auto-close at expiry</Check>
        <Check checked={v.isActive} onChange={f.set('isActive')}>Active</Check>
      </div>
    </FormModal>
  );
}

export default function Plans({ user }) {
  const toast = useToast();
  const st = useListState('all');
  const [dialog, setDialog] = useState(null);
  const admin = can(user, 'admin');
  const r = useAsync(() => api.plans({ q: st.dq, billingPeriod: st.tab === 'all' ? undefined : st.tab, page: st.page, limit: 20 }), [st.dq, st.tab, st.page]);
  const done = msg => { setDialog(null); toast(msg); r.reload(); };

  return (
    <div className="fade">
      <div className="toolbar">
        <Tabs tabs={['all', ...PERIODS]} value={st.tab} onChange={st.setTab} />
        <span className="spacer" />
        <SearchBox value={st.q} onChange={st.setQ} placeholder="Search plans" />
        {admin && <button className="btn btn-primary" onClick={() => setDialog({ type: 'form' })}><Icon name="plus" />New plan</button>}
      </div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="plans" title={st.dq ? `No plans match “${st.dq}”` : 'No plans yet'} hint={admin && !st.dq ? 'Plans define price, period and rules for subscriptions.' : undefined} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Name</th><th>Billing</th><th className="num">Price</th><th className="num">Min qty</th><th>Available</th><th>Rules</th><th>Status</th>{admin && <th />}</tr></thead>
              <tbody>{data.data.map(p => (
                <tr key={p.id}>
                  <td className="strong">{p.name}</td>
                  <td><span className="badge b-confirmed"><i className="dot" />{label(p.billingPeriod)}</span></td>
                  <td className="num">{inr(p.price)}</td><td className="num">{p.minQuantity}</td>
                  <td className="dim">{nice(p.availableFrom)} – {p.availableTo ? nice(p.availableTo) : 'open'}</td>
                  <td className="wrap">{[['Pause', p.allowPause], ['Close', p.allowEarlyClose], ['Renew', p.allowRenew], ['Auto-close', p.autoClose]].filter(([, on]) => on).map(([l]) => <span key={l} className="chip on">{l}</span>)}</td>
                  <td><Badge status={p.isActive ? 'active' : 'inactive'} text={p.isActive ? 'Active' : 'Inactive'} /></td>
                  {admin && <td className="num"><div className="row-actions">
                    <button className="icon-btn sm" aria-label={`Edit ${p.name}`} onClick={() => setDialog({ type: 'form', p })}><Icon name="edit" /></button>
                    <button className="icon-btn sm" aria-label={`Delete ${p.name}`} onClick={() => setDialog({ type: 'delete', p })}><Icon name="trash" /></button>
                  </div></td>}
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
      {dialog?.type === 'form' && <PlanForm plan={dialog.p} onClose={() => setDialog(null)} onDone={() => done(dialog.p ? 'Plan updated.' : 'Plan created.')} />}
      {dialog?.type === 'delete' && <Confirm title={`Delete ${dialog.p.name}?`} danger confirmLabel="Delete plan" onClose={() => setDialog(null)}
        body="Plans used by a subscription cannot be deleted; deactivate them instead."
        onConfirm={async () => { await api.deletePlan(dialog.p.id); done('Plan deleted.'); }} />}
    </div>
  );
}
