import { Link, useNavigate } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../api';
import { inr, nice, isoDate, addDays, initials, Badge, Icon, Empty, DataView, ErrorBox, Loading, useAsync } from '../ui';

const tipStyle = { background: '#141615', border: 'none', borderRadius: 14, fontSize: 12.5, color: '#fff', fontFamily: 'Geist', padding: '8px 12px' };
const short = n => '₹' + (n >= 1e7 ? (n / 1e7).toFixed(2) + 'Cr' : n >= 1e5 ? (n / 1e5).toFixed(2) + 'L' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : n.toFixed(0));
const monthName = d => new Date(+d.slice(0, 4), +d.slice(5, 7) - 1, 1).toLocaleDateString('en-IN', { month: 'short' });

function Gauge({ ratio, value, caption }) {
  const r = 80, cx = 100, cy = 104;
  const f = Math.max(0.02, Math.min(0.98, ratio || 0));
  const a = Math.PI * (1 - f);
  const x = cx + r * Math.cos(a), y = cy - r * Math.sin(a);
  return (
    <svg viewBox="0 0 200 124" style={{ width: '100%', maxWidth: 300, display: 'block' }} role="img" aria-label={`${value} ${caption}`}>
      <defs>
        <pattern id="hp" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="#1f3d12" strokeWidth="1.6" opacity=".55" />
        </pattern>
      </defs>
      <path d={`M ${x} ${y} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="url(#hp)" strokeWidth="24" strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`} fill="none" stroke="#141615" strokeWidth="24" strokeLinecap="round" />
      <circle cx={x} cy={y} r="6" fill="#a48df5" stroke="#bdf3a0" strokeWidth="2" />
      <text x={cx} y={cy - 6} textAnchor="middle" fontFamily="Bricolage Grotesque" fontWeight="800" fontSize="22" fill="#141615" letterSpacing="-1">{value}</text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontFamily="Geist" fontSize="9.5" fill="#1f3d12" opacity=".75">{caption}</text>
    </svg>
  );
}

export default function Dashboard() {
  const nav = useNavigate();
  const today = new Date();
  const from = isoDate(new Date(today.getFullYear(), today.getMonth() - 5, 1));
  const s   = useAsync(() => api.summary(), []);
  const rev = useAsync(() => api.revenue({ from, to: isoDate(today), groupBy: 'month' }), []);
  const due = useAsync(() => api.billingDue({ asOf: isoDate(addDays(today, 30)), limit: 4 }), []);
  const inv = useAsync(() => api.invoices({ limit: 6 }), []);

  if (s.error) return <div className="card"><ErrorBox error={s.error} onRetry={s.reload} /></div>;
  if (!s.data || !rev.data && !rev.error) return <div className="card"><Loading rows={8} /></div>;

  const d = s.data;
  const series = (rev.data?.data || []).map(p => ({ period: monthName(p.period), invoiced: +p.invoiced, collected: +p.collected }));
  const totInv = series.reduce((a, r) => a + r.invoiced, 0), totCol = series.reduce((a, r) => a + r.collected, 0);
  const monthInv = +d.revenueInvoiced, monthCol = +d.revenueCollected;
  const rate = monthInv > 0 ? monthCol / monthInv : 0;
  const last = series.at(-1), prev = series.at(-2);
  const growth = last && prev && prev.invoiced > 0 ? (last.invoiced - prev.invoiced) / prev.invoiced * 100 : null;
  const by = d.subscriptions.byStatus || {};
  const pipeline = (by.draft || 0) + (by.quotation || 0) + (by.confirmed || 0);

  return (
    <div className="fade">
      <div className="bento">
        <div className="tile tile-dark span-7 rev-tile">
          <div className="tile-h">
            <div><h3>Revenue</h3><div className="tile-sub">Invoiced vs collected · last 6 months</div>
              <div className="legend">
                <span><i style={{ background: '#bdf3a0' }} />Invoiced</span>
                <span><i style={{ background: '#a48df5' }} />Collected</span>
              </div></div>
          </div>
          <div className="rev-body">
            <div className="rev-num">
              <div className="rev-lbl">Collected</div>
              <div className="big-num">{short(totCol)}</div>
              <div className="rev-sub">of {short(totInv)} invoiced</div>
            </div>
            <div className="rev-chart">
              {rev.error ? <div className="rev-sub">Revenue chart unavailable: {rev.error.message}</div> :
                <ResponsiveContainer>
                  <BarChart data={series} margin={{ top: 8, right: 0, left: -6, bottom: 0 }} barCategoryGap="28%" barGap={5}>
                    <CartesianGrid vertical={false} stroke="rgba(255,255,255,.08)" />
                    <XAxis dataKey="period" tick={{ fill: 'rgba(255,255,255,.6)', fontSize: 12, fontFamily: 'Geist' }} axisLine={false} tickLine={false} dy={6} />
                    <YAxis tick={{ fill: 'rgba(255,255,255,.45)', fontSize: 11, fontFamily: 'Geist' }} axisLine={false} tickLine={false} width={48}
                      tickFormatter={v => v === 0 ? '0' : short(v)} tickCount={5} allowDecimals={false} />
                    <Tooltip contentStyle={tipStyle} itemStyle={{ color: '#fff' }} labelStyle={{ color: 'rgba(255,255,255,.6)' }}
                      cursor={{ fill: 'rgba(255,255,255,.05)' }} formatter={(v, n) => [inr(v), n]} />
                    <Bar dataKey="invoiced" name="Invoiced" fill="#bdf3a0" radius={[6, 6, 0, 0]} maxBarSize={18} />
                    <Bar dataKey="collected" name="Collected" fill="#a48df5" radius={[6, 6, 0, 0]} maxBarSize={18} />
                  </BarChart>
                </ResponsiveContainer>}
            </div>
          </div>
        </div>

        <div className="span-5 stack">
          <Link to="/subscriptions" className="tile tile-mint tile-link">
            <span className="corner-arrow"><Icon name="arrow" /></span>
            <div className="tile-lbl">Monthly recurring revenue</div>
            <div className="mid-num" style={{ margin: '14px 0 16px' }}>{inr(d.mrr)}</div>
            <div className="tile-foot">
              {growth === null ? <span>Invoiced this month: <b>{inr(monthInv)}</b></span>
                : <span><b>{growth >= 0 ? '+' : ''}{growth.toFixed(1)}%</b> invoiced vs last month</span>}
            </div>
          </Link>
          <Link to="/subscriptions" className="tile tile-lav tile-link">
            <span className="corner-arrow"><Icon name="arrow" /></span>
            <div className="tile-lbl">Active subscriptions</div>
            <div className="tile-row">
              <div className="mid-num">{d.subscriptions.active}</div>
              <div className="tile-lbl" style={{ paddingBottom: 4 }}>{pipeline} in the pipeline · {by.closed || 0} closed</div>
            </div>
          </Link>
        </div>

        <div className="tile tile-white span-5">
          <div className="tile-h"><div><h3>Collection health</h3><div className="tile-sub muted-sub">This month</div></div><span className="spacer" />
            <button className="icon-btn" aria-label="Open invoices" onClick={() => nav('/invoices')}><Icon name="arrow" /></button></div>
          <div className="tile tile-mint gauge-tile">
            <div className="gauge-l">
              <div className="circle-ico ci-white"><span style={{ fontWeight: 800 }}>₹</span></div>
              <div className="gauge-pct">{monthInv > 0 ? `${Math.round(rate * 100)}%` : '—'}</div>
              <div className="tile-lbl">{monthInv > 0 ? 'collected' : 'nothing invoiced yet'}</div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Gauge ratio={rate} value={inr(d.outstanding).replace('.00', '')}
                caption={`outstanding · ${d.overdue.count} overdue`} />
            </div>
          </div>
          {d.overdue.count > 0 && <Link to="/invoices?tab=overdue" className="overdue-note"><Icon name="alert" />{d.overdue.count} overdue invoice(s) worth {inr(d.overdue.amount)}</Link>}
        </div>

        <div className="tile tile-white span-7">
          <div className="tile-h">
            <div className="circle-ico ci-mint"><Icon name="billing" /></div>
            <div><h3>Next billing</h3><div className="tile-sub muted-sub">Due in the next 30 days</div></div>
            <span className="spacer" /><button className="btn btn-sm" onClick={() => nav('/billing')}>Billing run</button>
          </div>
          <DataView r={due} rows={3} empty={<Empty icon="billing" title="Nothing due in the next 30 days" hint="Active subscriptions show up here before their billing date." />}>
            {data => (
              <div className="timeline" style={{ marginTop: 16 }}>
                {data.data.map((u, i) => (
                  <Link key={u.subscriptionId} to={`/subscriptions/${u.subscriptionId}`} className={`tl-item ${i === data.data.length - 1 ? 'last' : ''}`}>
                    <div><b>{nice(u.nextBillingDate)}</b><span>{u.customer.name} · {u.number}</span></div>
                    <div className="tl-amt">{inr(u.estimatedTotal)}</div>
                  </Link>))}
              </div>)}
          </DataView>
        </div>
      </div>

      <div className="card">
        <div className="card-h"><h3>Recent invoices</h3><span className="spacer" />
          <Link to="/invoices" className="btn btn-sm">View all <Icon name="arrow" /></Link></div>
        <DataView r={inv} empty={<Empty icon="invoices" title="No invoices yet" hint="Invoices are created by the billing run." />}>
          {data => (
            <div className="tbl-wrap"><table>
              <thead><tr><th>Invoice</th><th>Customer</th><th>Issued</th><th>Status</th><th className="num">Total</th><th className="num">Due</th></tr></thead>
              <tbody>{data.data.map(i => (
                <tr key={i.id} className="row-link" tabIndex={0} onClick={() => nav(`/invoices/${i.id}`)} onKeyDown={e => e.key === 'Enter' && nav(`/invoices/${i.id}`)}>
                  <td className="mono">{i.number}</td>
                  <td><div className="who"><span className="avatar">{initials(i.customer.name)}</span>{i.customer.name}</div></td>
                  <td className="dim">{nice(i.issueDate)}</td>
                  <td><Badge status={i.status} overdue={i.isOverdue} /></td>
                  <td className="num">{inr(i.total)}</td>
                  <td className={`num ${+i.amountDue > 0 ? 'amt-due' : 'dim'}`}>{inr(i.amountDue)}</td>
                </tr>))}</tbody>
            </table></div>)}
        </DataView>
      </div>
    </div>
  );
}
