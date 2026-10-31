import { useState } from 'react';
import { api } from '../api';
import { inr, label, Icon, Empty, DataView, Pager, SearchBox, Field, FormModal, Confirm, useAsync, useForm, useToast, errText } from '../ui';
import { useListState, useCatalog, LineEditor, blankLine, checkLines, toLineInput, can } from './shared';

function TemplateForm({ template, onClose, onDone }) {
  const cat = useCatalog();
  const f = useForm({
    name: template?.name || '', planId: template?.planId || '', validityDays: template?.validityDays ?? 30, notes: template?.notes || '',
    lines: template?.lines?.length ? template.lines.map(l => ({ key: Math.random().toString(36).slice(2), productId: l.productId, variantId: l.variantId || '', quantity: l.quantity })) : [blankLine()],
  });
  const v = f.values;
  const save = () => f.submit(
    x => ({
      name: !x.name.trim() && 'Name is required.', planId: !x.planId && 'Choose a plan.',
      validityDays: (!Number.isInteger(+x.validityDays) || +x.validityDays < 1) && 'Whole number of days, at least 1.', lines: checkLines(x.lines),
    }),
    async x => {
      const body = { name: x.name.trim(), planId: x.planId, validityDays: +x.validityDays, lines: toLineInput(x.lines), notes: x.notes.trim() || null };
      onDone(template ? await api.updateTemplate(template.id, body) : await api.createTemplate(body));
    },
  );
  return (
    <FormModal title={template ? 'Edit template' : 'New quotation template'} onClose={onClose} onSubmit={save} busy={f.busy || !cat.data} message={f.message || (cat.error && errText(cat.error))} wide>
      {!cat.data ? <p className="dim">Loading…</p> : <>
        <Field label="Name *" error={f.errors.name}><input className={`input ${f.errors.name ? 'err' : ''}`} value={v.name} onChange={f.set('name')} autoFocus /></Field>
        <div className="row">
          <Field label="Plan *" error={f.errors.planId}><select className={`input ${f.errors.planId ? 'err' : ''}`} value={v.planId} onChange={f.set('planId')}>
            <option value="">Choose a plan…</option>{cat.data.plans.map(p => <option key={p.id} value={p.id}>{p.name} · {inr(p.price)} / {p.billingPeriod}</option>)}</select></Field>
          <Field label="Valid for (days) *" error={f.errors.validityDays}><input className={`input ${f.errors.validityDays ? 'err' : ''}`} type="number" min="1" step="1" value={v.validityDays} onChange={f.set('validityDays')} /></Field>
        </div>
        <Field label="Lines *"><LineEditor lines={v.lines} onChange={f.set('lines')} products={cat.data.products} error={f.errors.lines} /></Field>
        <Field label="Notes"><textarea className="input" rows="2" value={v.notes} onChange={f.set('notes')} /></Field>
      </>}
    </FormModal>
  );
}

export default function Templates({ user }) {
  const toast = useToast();
  const st = useListState('all');
  const [dialog, setDialog] = useState(null);
  const admin = can(user, 'admin');
  const r = useAsync(() => api.templates({ q: st.dq, page: st.page, limit: 20 }), [st.dq, st.page]);
  const done = msg => { setDialog(null); toast(msg); r.reload(); };

  return (
    <div className="fade">
      <div className="toolbar"><SearchBox value={st.q} onChange={st.setQ} placeholder="Search templates" /><span className="spacer" />
        {admin && <button className="btn btn-primary" onClick={() => setDialog({ type: 'form' })}><Icon name="plus" />New template</button>}</div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="templates" title={st.dq ? `No templates match “${st.dq}”` : 'No templates yet'} hint={admin && !st.dq ? 'Templates pre-fill a plan and lines when creating a subscription.' : undefined} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Name</th><th>Plan</th><th className="num">Lines</th><th className="num">Valid for</th><th>Notes</th>{admin && <th />}</tr></thead>
              <tbody>{data.data.map(t => (
                <tr key={t.id}>
                  <td className="strong">{t.name}</td><td>{t.planName}</td><td className="num">{t.lines.length}</td>
                  <td className="num">{t.validityDays} days</td><td className="dim trunc">{t.notes || '—'}</td>
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
      {dialog?.type === 'form' && <TemplateForm template={dialog.t} onClose={() => setDialog(null)} onDone={() => done(dialog.t ? 'Template updated.' : 'Template created.')} />}
      {dialog?.type === 'delete' && <Confirm title={`Delete ${dialog.t.name}?`} danger confirmLabel="Delete template" onClose={() => setDialog(null)}
        body="Subscriptions created from it are not affected." onConfirm={async () => { await api.deleteTemplate(dialog.t.id); done('Template deleted.'); }} />}
    </div>
  );
}
