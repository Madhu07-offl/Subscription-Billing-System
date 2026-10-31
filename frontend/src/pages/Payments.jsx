import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { inr, nice, label, initials, Badge, Icon, Empty, DataView, Pager, Confirm, useAsync, useToast } from '../ui';
import { useListState, can } from './shared';
import { METHODS } from './Invoices';

export default function Payments({ user }) {
  const toast = useToast();
  const st = useListState('all');
  const [voiding, setVoiding] = useState(null);
  const staff = can(user, 'admin', 'staff');
  const r = useAsync(() => api.payments({ method: st.tab === 'all' ? undefined : st.tab, page: st.page, limit: 20 }), [st.tab, st.page]);

  return (
    <div className="fade">
      <div className="toolbar">
        <div className="pills" role="tablist">
          {['all', ...METHODS].map(m => <button key={m} role="tab" aria-selected={st.tab === m} className={`pill ${st.tab === m ? 'on' : ''}`} onClick={() => st.setTab(m)}>{label(m)}</button>)}
        </div>
      </div>
      <div className="card">
        <DataView r={r} empty={<Empty icon="payments" title="No payments here" hint="Payments appear once recorded against a confirmed invoice." />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Date</th><th>Invoice</th>{staff && <th>Customer</th>}<th>Method</th><th>Reference</th><th>Status</th><th className="num">Amount</th>{user.role === 'admin' && <th />}</tr></thead>
              <tbody>{data.data.map(p => (
                <tr key={p.id}>
                  <td className="dim">{nice(p.paymentDate)}</td>
                  <td><Link className="mono link" to={`/invoices/${p.invoiceId}`}>{p.invoiceNumber}</Link></td>
                  {staff && <td><div className="who"><span className="avatar">{initials(p.customer.name)}</span>{p.customer.name}</div></td>}
                  <td>{label(p.method)}</td>
                  <td className="dim">{p.reference || '—'}</td>
                  <td>{p.isVoided ? <Badge status="voided" /> : <Badge status="paid" text="Recorded" />}</td>
                  <td className={`num ${p.isVoided ? 'struck' : ''}`}>{inr(p.amount)}</td>
                  {user.role === 'admin' && <td className="num">{!p.isVoided &&
                    <button className="icon-btn sm" aria-label="Void payment" title="Void payment" onClick={() => setVoiding(p)}><Icon name="trash" /></button>}</td>}
                </tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={st.setPage} />
          </>}
        </DataView>
      </div>
      {voiding && <Confirm title={`Void payment of ${inr(voiding.amount)}?`} danger confirmLabel="Void payment" onClose={() => setVoiding(null)}
        body={`This reverses the payment on ${voiding.invoiceNumber}. The invoice goes back to confirmed if it was paid.`}
        onConfirm={async () => { await api.voidPayment(voiding.id); setVoiding(null); toast('Payment voided.'); r.reload(); }} />}
    </div>
  );
}
