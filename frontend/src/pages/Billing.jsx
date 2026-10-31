import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { inr, nice, niceTime, isoDate, Badge, Icon, Empty, DataView, Pager, Confirm, useAsync, useToast, errText } from '../ui';
import { useListState, can } from './shared';

export default function Billing({ user }) {
  const toast = useToast();
  const [asOf, setAsOf] = useState(isoDate());
  const [busy, setBusy] = useState(null);
  const [result, setResult] = useState(null);
  const [closing, setClosing] = useState(false);
  const dueSt = useListState('all');
  const runSt = useListState('all');
  const due = useAsync(() => api.billingDue({ asOf, page: dueSt.page, limit: 10 }), [asOf, dueSt.page]);
  const runs = useAsync(() => api.billingRuns({ page: runSt.page, limit: 5 }), [runSt.page]);

  const run = async dryRun => {
    setBusy(dryRun ? 'dry' : 'run');
    try {
      const res = await api.billingRun({ asOf, dryRun });
      setResult(res);
      if (!dryRun) { toast(`${res.counts.created} invoice(s) created.`); due.reload(); runs.reload(); }
    } catch (e) { toast(errText(e), true); }
    setBusy(null);
  };

  return (
    <div className="fade">
      <div className="card gap">
        <div className="card-h"><h3>Billing day</h3><span className="spacer" />
          <label className="inline-field">Bill as of <input className="input" type="date" value={asOf} onChange={e => e.target.value && setAsOf(e.target.value)} /></label>
          <button className="btn" onClick={() => run(true)} disabled={!!busy}>{busy === 'dry' ? 'Checking…' : 'Preview (dry run)'}</button>
          <button className="btn btn-primary" onClick={() => run(false)} disabled={!!busy}><Icon name="bolt" />{busy === 'run' ? 'Running…' : 'Run billing'}</button>
        </div>
        <div className="card-b">
          <p className="muted">Creates one draft invoice for every active, unpaused subscription whose billing date has been reached.</p>
          <p className="dim" style={{ marginTop: 4 }}>Safe to run twice: a period that is already billed is skipped, never billed again.</p>
          {can(user, 'admin') && <button className="btn btn-sm btn-ghost" style={{ marginTop: 12 }} onClick={() => setClosing(true)}>Close expired subscriptions…</button>}
        </div>
      </div>

      {result && (
        <div className="card gap result fade">
          <div className="card-h"><h3>{result.dryRun ? 'Dry run — nothing was saved' : 'Billing run complete'}</h3><span className="spacer" />
            <span className="badge b-draft">{result.counts.due} due</span>
            <span className="badge b-active"><i className="dot" />{result.counts.created} {result.dryRun ? 'would be created' : 'created'}</span>
            {result.counts.alreadyBilled > 0 && <span className="badge b-paused">{result.counts.alreadyBilled} already billed</span>}
            {result.counts.failed > 0 && <span className="badge b-cancelled"><i className="dot" />{result.counts.failed} failed</span>}
            <button className="icon-btn sm" aria-label="Dismiss result" onClick={() => setResult(null)}><Icon name="x" /></button></div>
          {result.created.length === 0 && result.failed.length === 0
            ? <Empty icon="check" title="Nothing to bill" hint={`No subscription is due on or before ${nice(asOf)}.`} />
            : <div className="tbl-wrap"><table>
              <thead><tr><th>Subscription</th><th>Invoice</th><th>Customer</th><th className="num">Total</th></tr></thead>
              <tbody>
                {result.created.map(c => (
                  <tr key={c.id}><td className="mono">{c.subscriptionNumber}</td>
                    <td className="mono">{result.dryRun ? <span className="dim">{c.number}</span> : <Link className="link" to={`/invoices/${c.id}`}>{c.number}</Link>}</td>
                    <td>{c.customer.name}</td><td className="num">{inr(c.total)}</td></tr>))}
                {result.failed.map(f => (
                  <tr key={f.subscriptionId}><td className="mono">{f.number}</td><td colSpan="3" className="err-txt wrap">Failed: {f.reason}</td></tr>))}
              </tbody></table></div>}
        </div>
      )}

      <div className="card gap">
        <div className="card-h"><h3>Due for billing</h3><span className="spacer" /><span className="dim">As of {nice(asOf)}</span></div>
        <DataView r={due} rows={3} empty={<Empty icon="check" title="Nothing due" hint="All caught up for this date." />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Subscription</th><th>Customer</th><th>Next billing</th><th className="num">Estimated</th></tr></thead>
              <tbody>{data.data.map(s => (
                <tr key={s.subscriptionId}><td><Link className="mono link" to={`/subscriptions/${s.subscriptionId}`}>{s.number}</Link></td>
                  <td>{s.customer.name}</td><td className="dim">{nice(s.nextBillingDate)}</td><td className="num">{inr(s.estimatedTotal)}</td></tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={dueSt.setPage} />
          </>}
        </DataView>
      </div>

      <div className="card">
        <div className="card-h"><h3>Previous runs</h3></div>
        <DataView r={runs} rows={3} empty={<Empty icon="billing" title="No runs yet" />}>
          {data => <>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Started</th><th>As of</th><th className="num">Due</th><th className="num">Created</th><th className="num">Already billed</th><th className="num">Failed</th></tr></thead>
              <tbody>{data.data.map(x => (
                <tr key={x.runId}><td>{niceTime(x.startedAt)}</td><td className="dim">{nice(x.asOf)}</td>
                  <td className="num">{x.counts.due}</td><td className="num">{x.counts.created}</td><td className="num">{x.counts.alreadyBilled}</td>
                  <td className="num">{x.counts.failed > 0 ? <Badge status="cancelled" text={String(x.counts.failed)} /> : 0}</td></tr>))}</tbody>
            </table></div>
            <Pager meta={data.meta} onPage={runSt.setPage} />
          </>}
        </DataView>
      </div>

      {closing && <Confirm title="Close expired subscriptions?" confirmLabel="Close expired" danger onClose={() => setClosing(false)}
        body={`Closes every active subscription whose plan auto-closes and whose expiry is on or before ${nice(asOf)}.`}
        onConfirm={async () => { const r = await api.autoClose({ asOf }); setClosing(false); toast(`${r.closedCount} subscription(s) closed.`); due.reload(); }} />}
    </div>
  );
}
