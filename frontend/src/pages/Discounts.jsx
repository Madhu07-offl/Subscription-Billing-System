import { useState } from 'react';
import { api, fetchAll } from '../api';
import { inr, nice, label, Badge, Icon, Empty, DataView, Pager, SearchBox, Field, Check, FormModal, Confirm, useAsync, useForm, useToast } from '../ui';
import { useListState, can } from './shared';

function DiscountForm({ discount, onClose, onDone }) {
  const prods = useAsync(() => fetchAll(api.products), []);
  const d = discount;
  const f = useForm({
    name: d?.name || '', type: d?.type || 'percentage', value: d?.value ?? '', scope: d?.scope || 'products',
    minPurchaseAmount: d?.minPurchaseAmount ?? '', minQuantity: d?.minQuantity ?? '', startDate: d?.startDate || '', endDate: d?.endDate || '',
    usageLimit: d?.usageLimit ?? '', productIds: d?.productIds || [], isActive: d?.isActive ?? true,
  });
  const v = f.values;
  const toggle = id => f.set('productIds')(v.productIds.includes(id) ? v.productIds.filter(x => x !== id) : [...v.productIds, id]);
  const save = () => f.submit(
    x => ({
      name: !x.name.trim() && 'Name is required.',
      value: (x.value === '' || +x.value <= 0) ? 'Enter a value above 0.' : (x.type === 'percentage' && +x.value > 100) ? 'A percentage cannot be above 100.' : null,
      startDate: !x.startDate && 'Choose a start date.',
      endDate: x.endDate && x.startDate && x.endDate < x.startDate && 'Must not be before the start date.',
      minQuantity: x.minQuantity !== '' && (!Number.isInteger(+x.minQuantity) || +x.minQuantity < 1) && 'Whole number, at least 1.',
      usageLimit: x.usageLimit !== '' && (!Number.isInteger(+x.usageLimit) || +x.usageLimit < 1) && 'Whole number, at least 1.',
    }),
    async x => {
      const body = {
        name: x.name.trim(), type: x.type, value: (+x.value).toFixed(2), scope: x.scope, startDate: x.startDate, endDate: x.endDate || null,
        minPurchaseAmount: x.minPurchaseAmount === '' ? null : (+x.minPurchaseAmount).toFixed(2),
        minQuantity: x.minQuantity === '' ? null : +x.minQuantity, usageLimit: x.usageLimit === '' ? null : +x.usageLimit,
        productIds: x.scope === 'products' ? x.productIds : [], isActive: x.isActive,
      };
      onDone(d ? await api.updateDiscount(d.id, body) : await api.createDiscount(body));
    },
  );
  const num = (k, props) => <input className={`input ${f.errors[k] ? 'err' : ''}`} type="number" min="0" step="any" value={v[k]} onChange={f.set(k)} {...props} />;
  return (
    <FormModal title={d ? 'Edit discount' : 'New discount'} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message} wide>
      <Field label="Name *" error={f.errors.name}><input className={`input ${f.errors.name ? 'err' : ''}`} value={v.name} onChange={f.set('name')} autoFocus /></Field>
      <div className="row">
        <Field label="Type"><select className="input" value={v.type} onChange={f.set('type')}><option value="percentage">Percentage</option><option value="fixed">Fixed amount</option></select></Field>
        <Field label={v.type === 'percentage' ? 'Percent *' : 'Amount *'} error={f.errors.value}>{num('value')}</Field>
        <Field label="Applies to"><select className="input" value={v.scope} onChange={f.set('scope')}><option value="products">Selected products</option><option value="subscriptions">Whole subscription</option></select></Field>
      </div>
      <div className="row">
        <Field label="Start date *" error={f.errors.startDate}><input className={`input ${f.errors.startDate ? 'err' : ''}`} type="date" value={v.startDate} onChange={f.set('startDate')} /></Field>
        <Field label="End date" hint="Optional" error={f.errors.endDate}><input className={`input ${f.errors.endDate ? 'err' : ''}`} type="date" value={v.endDate} onChange={f.set('endDate')} /></Field>
      </div>
      <div className="row">
        <Field label="Min purchase" hint="Optional" error={f.errors.minPurchaseAmount}>{num('minPurchaseAmount', { step: '0.01' })}</Field>
        <Field label="Min quantity" hint="Optional" error={f.errors.minQuantity}>{num('minQuantity', { step: '1' })}</Field>
        <Field label="Usage limit" hint="Empty = unlimited" error={f.errors.usageLimit}>{num('usageLimit', { step: '1' })}</Field>
      </div>
      {v.scope === 'products' && <Field label="Products" hint="Leave all unticked to cover every product.">
        {prods.error ? <div className="err-txt">{prods.error.message}</div> : !prods.data ? <span className="dim">Loading…</span> :
          <div className="checks">{prods.data.map(p => <Check key={p.id} checked={v.productIds.includes(p.id)} onChange={() => toggle(p.id)}>{p.name}</Check>)}</div>}
      </Field>}
      <Check checked={v.isActive} onChange={f.set('isActive')}>Active</Check>
    </FormModal>
  );
}

export default function Discounts({ user }) {
  const toast = useToast();
  const st = useListState('all');
  const [dialog, setDialog] = useState(null);
  const admin = can(user, 'admin');
  const r = useAsync(() => api.discounts({ q: st.dq, page: st.page, limit: 20 }), [st.dq, st.page]);
  const done = msg => { setDialog(null); toast(msg); r.reload(); };

  return (
    <div className="fade">
      <div className="toolbar"><SearchBox value={st.q} onChange={st.setQ} placeholder="Search discounts" /><span className="spacer" />
        {admin && <button className="btn btn-primary" onClick={() => setDialog({ type: 'form' })}><Icon name="plus" />New discount</button>}</div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="discounts" title={st.dq ? `No discounts match “${st.dq}”` : 'No discounts yet'} hint={admin && !st.dq ? 'Create a discount rule to apply on invoices.' : undefined} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Name</th><th>Type</th><th className="num">Value</th><th>Scope</th><th>Valid</th><th className="num">Used</th><th>Status</th>{admin && <th />}</tr></thead>
              <tbody>{data.data.map(x => (
                <tr key={x.id}>
                  <td className="strong">{x.name}</td><td className="dim">{label(x.type)}</td>
                  <td className="num">{x.type === 'percentage' ? `${+x.value}%` : inr(x.value)}</td>
                  <td><span className="badge b-quotation"><i className="dot" />{x.scope === 'products' ? 'Products' : 'Subscription'}</span></td>
                  <td className="dim">{nice(x.startDate)} – {x.endDate ? nice(x.endDate) : 'open'}</td>
                  <td className="num">{x.usedCount}{x.usageLimit ? ` / ${x.usageLimit}` : ''}</td>
                  <td><Badge status={x.status} /></td>
                  {admin && <td className="num"><div className="row-actions">
                    <button className="icon-btn sm" aria-label={`Edit ${x.name}`} onClick={() => setDialog({ type: 'form', x })}><Icon name="edit" /></button>
                    <button className="icon-btn sm" aria-label={`Delete ${x.name}`} onClick={() => setDialog({ type: 'delete', x })}><Icon name="trash" /></button>
                  </div></td>}
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
      {dialog?.type === 'form' && <DiscountForm discount={dialog.x} onClose={() => setDialog(null)} onDone={() => done(dialog.x ? 'Discount updated.' : 'Discount created.')} />}
      {dialog?.type === 'delete' && <Confirm title={`Delete ${dialog.x.name}?`} danger confirmLabel="Delete discount" onClose={() => setDialog(null)}
        body="Invoices that already used it are not changed." onConfirm={async () => { await api.deleteDiscount(dialog.x.id); done('Discount deleted.'); }} />}
    </div>
  );
}
