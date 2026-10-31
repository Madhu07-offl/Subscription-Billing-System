import { useState } from 'react';
import { api } from '../api';
import { inr, label, Badge, Icon, Empty, DataView, Pager, Field, Check, FormModal, Confirm, useAsync, useForm, useToast } from '../ui';
import { useListState, can } from './shared';

const TYPES = ['software', 'addon', 'service', 'goods'];

function TaxForm({ tax, onClose, onDone }) {
  const f = useForm({
    name: tax?.name || '', computation: tax?.computation || 'percentage', value: tax?.value ?? '',
    appliesToProductTypes: tax?.appliesToProductTypes || [], isActive: tax?.isActive ?? true,
  });
  const v = f.values;
  const toggle = t => f.set('appliesToProductTypes')(v.appliesToProductTypes.includes(t) ? v.appliesToProductTypes.filter(x => x !== t) : [...v.appliesToProductTypes, t]);
  const save = () => f.submit(
    x => ({
      name: !x.name.trim() && 'Name is required.',
      value: (x.value === '' || +x.value < 0) ? 'Enter a value of 0 or more.' : (x.computation === 'percentage' && +x.value > 100) ? 'A percentage cannot be above 100.' : null,
    }),
    async x => {
      const body = { name: x.name.trim(), computation: x.computation, value: +x.value, appliesToProductTypes: x.appliesToProductTypes, isActive: x.isActive };
      onDone(tax ? await api.updateTax(tax.id, body) : await api.createTax(body));
    },
  );
  return (
    <FormModal title={tax ? 'Edit tax' : 'New tax'} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message}>
      <Field label="Name *" error={f.errors.name}><input className={`input ${f.errors.name ? 'err' : ''}`} value={v.name} onChange={f.set('name')} placeholder="GST 18%" autoFocus /></Field>
      <div className="row">
        <Field label="Computation"><select className="input" value={v.computation} onChange={f.set('computation')}><option value="percentage">Percentage</option><option value="fixed">Fixed amount</option></select></Field>
        <Field label={v.computation === 'percentage' ? 'Rate (%) *' : 'Amount per line *'} error={f.errors.value}>
          <input className={`input ${f.errors.value ? 'err' : ''}`} type="number" min="0" step="0.01" value={v.value} onChange={f.set('value')} /></Field>
      </div>
      <Field label="Applies to" hint="Leave all unticked to apply to every product type.">
        <div className="checks">{TYPES.map(t => <Check key={t} checked={v.appliesToProductTypes.includes(t)} onChange={() => toggle(t)}>{label(t)}</Check>)}</div></Field>
      <Check checked={v.isActive} onChange={f.set('isActive')}>Active</Check>
    </FormModal>
  );
}

export default function Taxes({ user }) {
  const toast = useToast();
  const st = useListState('all');
  const [dialog, setDialog] = useState(null);
  const admin = can(user, 'admin');
  const r = useAsync(() => api.taxes({ page: st.page, limit: 20 }), [st.page]);
  const done = msg => { setDialog(null); toast(msg); r.reload(); };

  return (
    <div className="fade">
      <div className="toolbar"><span className="spacer" />
        {admin && <button className="btn btn-primary" onClick={() => setDialog({ type: 'form' })}><Icon name="plus" />New tax</button>}</div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="taxes" title="No taxes yet" hint={admin ? 'Add a tax rule to have it applied on subscription lines.' : undefined} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Name</th><th>Computation</th><th className="num">Value</th><th>Applies to</th><th>Status</th>{admin && <th />}</tr></thead>
              <tbody>{data.data.map(t => (
                <tr key={t.id}>
                  <td className="strong">{t.name}</td><td className="dim">{label(t.computation)}</td>
                  <td className="num">{t.computation === 'percentage' ? `${+t.value}%` : inr(t.value)}</td>
                  <td className="wrap">{t.appliesToProductTypes.length === 0 ? <span className="chip">All types</span> : t.appliesToProductTypes.map(x => <span key={x} className="chip">{label(x)}</span>)}</td>
                  <td><Badge status={t.isActive ? 'active' : 'inactive'} text={t.isActive ? 'Active' : 'Inactive'} /></td>
                  {admin && <td className="num"><div className="row-actions">
                    <button className="icon-btn sm" aria-label={`Edit ${t.name}`} onClick={() => setDialog({ type: 'form', t })}><Icon name="edit" /></button>
                    <button className="icon-btn sm" aria-label={`Delete ${t.name}`} onClick={() => setDialog({ type: 'delete', t })}><Icon name="trash" /></button>
                  </div></td>}
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
      {dialog?.type === 'form' && <TaxForm tax={dialog.t} onClose={() => setDialog(null)} onDone={() => done(dialog.t ? 'Tax updated.' : 'Tax created.')} />}
      {dialog?.type === 'delete' && <Confirm title={`Delete ${dialog.t.name}?`} danger confirmLabel="Delete tax" onClose={() => setDialog(null)}
        body="Existing invoices keep the tax they were billed with." onConfirm={async () => { await api.deleteTax(dialog.t.id); done('Tax deleted.'); }} />}
    </div>
  );
}
