import { useState } from 'react';
import { api } from '../api';
import { initials, Icon, Empty, DataView, Pager, SearchBox, Field, FormModal, useAsync, useForm, useToast } from '../ui';
import { useListState } from './shared';

const clean = o => Object.fromEntries(Object.entries(o).filter(([, v]) => String(v ?? '').trim() !== '').map(([k, v]) => [k, String(v).trim()]));

function CustomerForm({ customer, onClose, onDone }) {
  const a = customer?.address || {};
  const f = useForm({
    name: customer?.name || '', email: customer?.email || '', phone: customer?.phone || '', company: customer?.company || '', taxId: customer?.taxId || '',
    line1: a.line1 || '', city: a.city || '', state: a.state || '', postalCode: a.postalCode || '', country: a.country || '',
  });
  const v = f.values;
  const save = () => f.submit(
    x => ({ name: !x.name.trim() && 'Name is required.', email: !/^\S+@\S+\.\S+$/.test(x.email) && 'Enter a valid email address.' }),
    async x => {
      const { line1, city, state, postalCode, country, ...rest } = x;
      const address = clean({ line1, city, state, postalCode, country });
      const body = customer
        ? { ...Object.fromEntries(Object.entries(rest).map(([k, val]) => [k, val.trim() || null])), name: rest.name.trim(), email: rest.email.trim(), address }
        : { ...clean(rest), ...(Object.keys(address).length ? { address } : {}) };
      onDone(customer ? await api.updateCustomer(customer.id, body) : await api.createCustomer(body));
    },
  );
  const input = (k, props) => <input className={`input ${f.errors[k] ? 'err' : ''}`} value={v[k]} onChange={f.set(k)} {...props} />;
  return (
    <FormModal title={customer ? 'Edit customer' : 'New customer'} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message} submitLabel={customer ? 'Save changes' : 'Create customer'}>
      <Field label="Name *" error={f.errors.name}>{input('name', { autoFocus: true })}</Field>
      <Field label="Email *" error={f.errors.email}>{input('email', { type: 'email' })}</Field>
      <div className="row">
        <Field label="Phone" error={f.errors.phone}>{input('phone')}</Field>
        <Field label="Company" error={f.errors.company}>{input('company')}</Field>
      </div>
      <Field label="Tax ID" error={f.errors.taxId}>{input('taxId')}</Field>
      <Field label="Address line" error={f.errors.line1}>{input('line1')}</Field>
      <div className="row">
        <Field label="City">{input('city')}</Field>
        <Field label="State">{input('state')}</Field>
      </div>
      <div className="row">
        <Field label="Postal code">{input('postalCode')}</Field>
        <Field label="Country">{input('country')}</Field>
      </div>
    </FormModal>
  );
}

export default function Customers() {
  const toast = useToast();
  const st = useListState('all');
  const [form, setForm] = useState(null);   // null | 'new' | customer
  const r = useAsync(() => api.customers({ q: st.dq, page: st.page, limit: 20 }), [st.dq, st.page]);

  return (
    <div className="fade">
      <div className="toolbar">
        <SearchBox value={st.q} onChange={st.setQ} placeholder="Search name, email or company" />
        <span className="spacer" />
        <button className="btn btn-primary" onClick={() => setForm('new')}><Icon name="plus" />New customer</button>
      </div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="customers" title={st.dq ? `No customers match “${st.dq}”` : 'No customers yet'}
          hint={st.dq ? undefined : 'Add your first customer to get started.'}
          action={!st.dq && <button className="btn btn-primary btn-sm" onClick={() => setForm('new')}><Icon name="plus" />New customer</button>} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Name</th><th>Email</th><th>Company</th><th>Phone</th><th>Tax ID</th><th className="num">Active subs</th><th /></tr></thead>
              <tbody>{data.data.map(c => (
                <tr key={c.id}>
                  <td><div className="who"><span className="avatar">{initials(c.name)}</span><span className="strong">{c.name}</span></div></td>
                  <td className="dim">{c.email}{c.hasLogin && <span className="tag">login</span>}</td>
                  <td className="dim">{c.company || '—'}</td><td className="dim">{c.phone || '—'}</td>
                  <td className="mono dim">{c.taxId || '—'}</td><td className="num">{c.activeSubscriptions}</td>
                  <td className="num"><button className="icon-btn sm" aria-label={`Edit ${c.name}`} onClick={() => setForm(c)}><Icon name="edit" /></button></td>
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
      {form && <CustomerForm customer={form === 'new' ? null : form} onClose={() => setForm(null)}
        onDone={c => { setForm(null); toast(form === 'new' ? `Customer ${c.name} created.` : 'Customer updated.'); r.reload(); }} />}
    </div>
  );
}
