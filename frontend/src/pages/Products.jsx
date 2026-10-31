import { useState } from 'react';
import { api } from '../api';
import { inr, label, Badge, Icon, Empty, DataView, Pager, SearchBox, Tabs, Field, Check, FormModal, Confirm, useAsync, useForm, useToast } from '../ui';
import { useListState, can } from './shared';

const TYPES = ['software', 'addon', 'service', 'goods'];
const money = v => (v === '' || v === null || v === undefined || isNaN(+v) || +v < 0) ? null : (+v).toFixed(2);
const priceErr = v => money(v) === null && 'Enter an amount of 0 or more.';
const blankVariant = () => ({ key: Math.random().toString(36).slice(2), attribute: '', value: '', extraPrice: '0' });

function ProductForm({ product, onClose, onDone }) {
  const f = useForm({
    name: product?.name || '', type: product?.type || 'software', salesPrice: product?.salesPrice || '', costPrice: product?.costPrice || '',
    notes: product?.notes || '', isActive: product?.isActive ?? true, variants: [],
  });
  const v = f.values;
  const setVariant = (i, patch) => f.set('variants')(v.variants.map((x, k) => (k === i ? { ...x, ...patch } : x)));
  const save = () => f.submit(
    x => ({
      name: !x.name.trim() && 'Name is required.', salesPrice: priceErr(x.salesPrice), costPrice: priceErr(x.costPrice),
      variants: x.variants.some(a => !a.attribute.trim() || !a.value.trim() || money(a.extraPrice) === null) ? 'Each variant needs an attribute, a value and a price of 0 or more.' : null,
    }),
    async x => {
      const body = { name: x.name.trim(), type: x.type, salesPrice: money(x.salesPrice), costPrice: money(x.costPrice), notes: x.notes.trim() || null, isActive: x.isActive };
      if (product) return onDone(await api.updateProduct(product.id, body));
      body.variants = x.variants.map(a => ({ attribute: a.attribute.trim(), value: a.value.trim(), extraPrice: money(a.extraPrice) }));
      onDone(await api.createProduct(body));
    },
  );
  return (
    <FormModal title={product ? 'Edit product' : 'New product'} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message} wide={!product}>
      <div className="row">
        <Field label="Name *" error={f.errors.name}><input className={`input ${f.errors.name ? 'err' : ''}`} value={v.name} onChange={f.set('name')} autoFocus /></Field>
        <Field label="Type"><select className="input" value={v.type} onChange={f.set('type')}>{TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}</select></Field>
      </div>
      <div className="row">
        <Field label="Sales price *" error={f.errors.salesPrice}><input className={`input ${f.errors.salesPrice ? 'err' : ''}`} type="number" min="0" step="0.01" value={v.salesPrice} onChange={f.set('salesPrice')} /></Field>
        <Field label="Cost price *" error={f.errors.costPrice}><input className={`input ${f.errors.costPrice ? 'err' : ''}`} type="number" min="0" step="0.01" value={v.costPrice} onChange={f.set('costPrice')} /></Field>
      </div>
      <Field label="Notes"><textarea className="input" rows="2" value={v.notes} onChange={f.set('notes')} /></Field>
      <Check checked={v.isActive} onChange={f.set('isActive')}>Active (can be sold)</Check>
      {!product && <Field label="Variants" className="mt">
        <div className="lines">
          {v.variants.map((a, i) => (
            <div className="line variant" key={a.key}>
              <input className="input" placeholder="Attribute (e.g. Brand)" aria-label="Attribute" value={a.attribute} onChange={e => setVariant(i, { attribute: e.target.value })} />
              <input className="input" placeholder="Value (e.g. Odoo)" aria-label="Value" value={a.value} onChange={e => setVariant(i, { value: e.target.value })} />
              <input className="input" type="number" min="0" step="0.01" placeholder="Extra ₹" aria-label="Extra price" value={a.extraPrice} onChange={e => setVariant(i, { extraPrice: e.target.value })} />
              <button type="button" className="icon-btn sm" aria-label="Remove variant" onClick={() => f.set('variants')(v.variants.filter((_, k) => k !== i))}><Icon name="trash" /></button>
            </div>))}
          <div className="lines-f"><button type="button" className="btn btn-sm btn-ghost" onClick={() => f.set('variants')([...v.variants, blankVariant()])}><Icon name="plus" />Add variant</button></div>
          {f.errors.variants && <div className="err-txt">{f.errors.variants}</div>}
        </div>
      </Field>}
    </FormModal>
  );
}

function VariantManager({ product, onClose, onChanged }) {
  const toast = useToast();
  const f = useForm({ attribute: '', value: '', extraPrice: '0' });
  const v = f.values;
  const add = () => f.submit(
    x => ({ attribute: !x.attribute.trim() && 'Required.', value: !x.value.trim() && 'Required.', extraPrice: priceErr(x.extraPrice) }),
    async x => { await api.addVariant(product.id, { attribute: x.attribute.trim(), value: x.value.trim(), extraPrice: money(x.extraPrice) }); f.setValues({ attribute: '', value: '', extraPrice: '0' }); toast('Variant added.'); onChanged(); },
  );
  const remove = async vr => {
    try { await api.deleteVariant(product.id, vr.id); toast('Variant removed.'); onChanged(); } catch (e) { toast(e.message, true); }
  };
  const live = product.variants.filter(x => !x.isArchived);
  return (
    <FormModal title={`Variants · ${product.name}`} onClose={onClose} onSubmit={add} busy={f.busy} message={f.message} submitLabel="Add variant">
      {live.length === 0 ? <p className="dim" style={{ marginBottom: 16 }}>No variants yet.</p> :
        <div style={{ marginBottom: 18 }}>{live.map(x => (
          <div className="kv" key={x.id}><span className="k">{x.attribute}: {x.value}</span>
            <span className="v">+{inr(x.extraPrice)} <button type="button" className="icon-btn sm" aria-label={`Remove ${x.value}`} onClick={() => remove(x)}><Icon name="trash" /></button></span></div>))}</div>}
      <div className="row">
        <Field label="Attribute" error={f.errors.attribute}><input className="input" value={v.attribute} onChange={f.set('attribute')} placeholder="Brand" /></Field>
        <Field label="Value" error={f.errors.value}><input className="input" value={v.value} onChange={f.set('value')} placeholder="Odoo" /></Field>
        <Field label="Extra price" error={f.errors.extraPrice}><input className="input" type="number" min="0" step="0.01" value={v.extraPrice} onChange={f.set('extraPrice')} /></Field>
      </div>
    </FormModal>
  );
}

export default function Products({ user }) {
  const toast = useToast();
  const st = useListState('all');
  const [dialog, setDialog] = useState(null);
  const admin = can(user, 'admin');
  const r = useAsync(() => api.products({ q: st.dq, type: st.tab === 'all' ? undefined : st.tab, page: st.page, limit: 20 }), [st.dq, st.tab, st.page]);
  const done = msg => { setDialog(null); toast(msg); r.reload(); };
  // keep the variant dialog showing fresh data after add/remove
  const variantProduct = dialog?.type === 'variants' ? (r.data?.data.find(p => p.id === dialog.p.id) || dialog.p) : null;

  return (
    <div className="fade">
      <div className="toolbar">
        <Tabs tabs={['all', ...TYPES]} value={st.tab} onChange={st.setTab} />
        <span className="spacer" />
        <SearchBox value={st.q} onChange={st.setQ} placeholder="Search products" />
        {admin && <button className="btn btn-primary" onClick={() => setDialog({ type: 'form' })}><Icon name="plus" />New product</button>}
      </div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="products" title={st.dq ? `No products match “${st.dq}”` : 'No products yet'} hint={admin && !st.dq ? 'Add what you sell to start building plans.' : undefined} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Name</th><th>Type</th><th>Variants</th><th className="num">Sales price</th><th className="num">Cost</th><th>Status</th>{admin && <th />}</tr></thead>
              <tbody>{data.data.map(p => (
                <tr key={p.id}>
                  <td className="strong">{p.name}</td><td className="dim">{label(p.type)}</td>
                  <td className="wrap">{p.variants.filter(x => !x.isArchived).length === 0 ? <span className="dim">—</span> :
                    p.variants.filter(x => !x.isArchived).map(x => <span key={x.id} className="chip">{x.value}{+x.extraPrice > 0 && ` +${inr(x.extraPrice)}`}</span>)}</td>
                  <td className="num">{inr(p.salesPrice)}</td><td className="num dim">{inr(p.costPrice)}</td>
                  <td><Badge status={p.isActive ? 'active' : 'inactive'} text={p.isActive ? 'Active' : 'Inactive'} /></td>
                  {admin && <td className="num"><div className="row-actions">
                    <button className="btn btn-sm" onClick={() => setDialog({ type: 'variants', p })}>Variants</button>
                    <button className="icon-btn sm" aria-label={`Edit ${p.name}`} onClick={() => setDialog({ type: 'form', p })}><Icon name="edit" /></button>
                    <button className="icon-btn sm" aria-label={`Delete ${p.name}`} onClick={() => setDialog({ type: 'delete', p })}><Icon name="trash" /></button>
                  </div></td>}
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
      {dialog?.type === 'form' && <ProductForm product={dialog.p} onClose={() => setDialog(null)} onDone={() => done(dialog.p ? 'Product updated.' : 'Product created.')} />}
      {variantProduct && <VariantManager product={variantProduct} onClose={() => setDialog(null)} onChanged={r.reload} />}
      {dialog?.type === 'delete' && <Confirm title={`Delete ${dialog.p.name}?`} danger confirmLabel="Delete product" onClose={() => setDialog(null)}
        body="Products that are already used on a subscription cannot be deleted; deactivate them instead."
        onConfirm={async () => { await api.deleteProduct(dialog.p.id); done('Product deleted.'); }} />}
    </div>
  );
}
