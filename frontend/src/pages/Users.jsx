import { useState } from 'react';
import { api } from '../api';
import { initials, Badge, Icon, Empty, DataView, Pager, SearchBox, Tabs, Field, FormModal, Confirm, useAsync, useForm, useToast } from '../ui';
import { useListState } from './shared';

const pwOk = p => p.length > 8 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /[^A-Za-z0-9]/.test(p);

function StaffForm({ onClose, onDone }) {
  const f = useForm({ name: '', email: '', password: '' });
  const v = f.values;
  const save = () => f.submit(
    x => ({
      name: !x.name.trim() && 'Name is required.',
      email: !/^\S+@\S+\.\S+$/.test(x.email) && 'Enter a valid email address.',
      password: !pwOk(x.password) && 'More than 8 characters, with an uppercase letter, a lowercase letter and a symbol.',
    }),
    async x => onDone(await api.createStaff({ name: x.name.trim(), email: x.email.trim(), password: x.password })),
  );
  return (
    <FormModal title="Add staff member" onClose={onClose} onSubmit={save} busy={f.busy} message={f.message} submitLabel="Add staff">
      <Field label="Name *" error={f.errors.name}><input className={`input ${f.errors.name ? 'err' : ''}`} value={v.name} onChange={f.set('name')} autoFocus /></Field>
      <Field label="Email *" error={f.errors.email}><input className={`input ${f.errors.email ? 'err' : ''}`} type="email" value={v.email} onChange={f.set('email')} /></Field>
      <Field label="Temporary password *" error={f.errors.password} hint="Share it securely; they can change it after signing in.">
        <input className={`input ${f.errors.password ? 'err' : ''}`} type="password" autoComplete="new-password" value={v.password} onChange={f.set('password')} /></Field>
    </FormModal>
  );
}

function RenameForm({ user, onClose, onDone }) {
  const f = useForm({ name: user.name });
  const save = () => f.submit(x => ({ name: !x.name.trim() && 'Name is required.' }), async x => onDone(await api.updateUser(user.id, { name: x.name.trim() })));
  return (
    <FormModal title={`Edit ${user.email}`} onClose={onClose} onSubmit={save} busy={f.busy} message={f.message}>
      <Field label="Name" error={f.errors.name}><input className={`input ${f.errors.name ? 'err' : ''}`} value={f.values.name} onChange={f.set('name')} autoFocus /></Field>
    </FormModal>
  );
}

export default function Users({ user: me }) {
  const toast = useToast();
  const st = useListState('all');
  const [dialog, setDialog] = useState(null);
  const r = useAsync(() => api.users({ q: st.dq, role: st.tab === 'all' ? undefined : st.tab, page: st.page, limit: 20 }), [st.dq, st.tab, st.page]);
  const done = msg => { setDialog(null); toast(msg); r.reload(); };

  return (
    <div className="fade">
      <div className="toolbar">
        <Tabs tabs={['all', 'admin', 'staff', 'customer']} value={st.tab} onChange={st.setTab} />
        <span className="spacer" />
        <SearchBox value={st.q} onChange={st.setQ} placeholder="Search name or email" />
        <button className="btn btn-primary" onClick={() => setDialog({ type: 'add' })}><Icon name="plus" />Add staff</button>
      </div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="users" title={st.dq ? `No users match “${st.dq}”` : 'No users here'} />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead>
              <tbody>{data.data.map(u => (
                <tr key={u.id}>
                  <td><div className="who"><span className="avatar">{initials(u.name)}</span><span className="strong">{u.name}</span>{u.id === me.id && <span className="tag">you</span>}</div></td>
                  <td className="dim">{u.email}</td>
                  <td><Badge status={u.role} /></td>
                  <td><Badge status={u.isActive ? 'active' : 'inactive'} text={u.isActive ? 'Active' : 'Deactivated'} /></td>
                  <td className="num"><div className="row-actions">
                    <button className="icon-btn sm" aria-label={`Edit ${u.name}`} onClick={() => setDialog({ type: 'edit', u })}><Icon name="edit" /></button>
                    {u.id !== me.id && <button className="btn btn-sm" onClick={() => setDialog({ type: 'toggle', u })}>{u.isActive ? 'Deactivate' : 'Reactivate'}</button>}
                  </div></td>
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
      {dialog?.type === 'add' && <StaffForm onClose={() => setDialog(null)} onDone={u => done(`${u.name} added as staff.`)} />}
      {dialog?.type === 'edit' && <RenameForm user={dialog.u} onClose={() => setDialog(null)} onDone={() => done('User updated.')} />}
      {dialog?.type === 'toggle' && <Confirm title={`${dialog.u.isActive ? 'Deactivate' : 'Reactivate'} ${dialog.u.name}?`} danger={dialog.u.isActive}
        confirmLabel={dialog.u.isActive ? 'Deactivate' : 'Reactivate'} onClose={() => setDialog(null)}
        body={dialog.u.isActive ? 'They will no longer be able to sign in. Their records stay.' : 'They will be able to sign in again.'}
        onConfirm={async () => { await api.updateUser(dialog.u.id, { isActive: !dialog.u.isActive }); done(dialog.u.isActive ? 'User deactivated.' : 'User reactivated.'); }} />}
    </div>
  );
}
