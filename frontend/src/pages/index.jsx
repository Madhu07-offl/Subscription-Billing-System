import { useState, useCallback } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api, db } from '../api';
import { inr, nice, initials, Badge, Stat, Flow, Modal, Empty, Loading, useAsync, Field } from '../ui';

/* ============================== LOGIN ============================== */
export function Login({ onLogin }) {
  const [role, setRole]   = useState('admin');
  const [email, setEmail] = useState('admin@brightloop.io');
  const [pw, setPw]       = useState('Hackathon@2026');
  const [err, setErr]     = useState(null);
  const [busy, setBusy]   = useState(false);

  const pwOk = pw.length > 8 && /[A-Z]/.test(pw) && /[a-z]/.test(pw) && /[^A-Za-z0-9]/.test(pw);

  const submit = async e => {
    e.preventDefault();
    if (!pwOk) return setErr('Password needs 8+ characters with an uppercase, a lowercase and a special character.');
    setBusy(true); setErr(null);
    try {
      const { user } = await api.login(email, pw, role);
      onLogin(user);
    } catch (e) {
      setErr(e.message); setBusy(false);
    }
  };
  const pick = r => {
    setRole(r);
    setEmail(r === 'admin' ? 'admin@brightloop.io' : r === 'staff' ? 'staff@brightloop.io' : 'nithya@kochicafe.in');
  };

  return (
    <div className="auth">
      <div className="auth-art">
        <div className="brand" style={{padding:0,color:'#fff'}}><span className="brand-mark">B</span> Brightloop</div>
        <h2>Run plans, subscriptions<br/>and recurring billing<br/>in one place.</h2>
        <p>The digital backbone for a business that earns its money every month — not just once.</p>
        <div style={{display:'flex',flexDirection:'column',gap:11,marginTop:8}}>
          {['Automatic invoicing on billing day','Taxes and discounts applied for you','Revenue and overdue, answered instantly'].map(t =>
            <div className="auth-feat" key={t}><span className="tick">✓</span>{t}</div>)}
        </div>
      </div>
      <div className="auth-form">
        <form className="auth-box" onSubmit={submit}>
          <h2 style={{fontSize:21,fontWeight:700,letterSpacing:'-.5px'}}>Sign in</h2>
          <p className="dim" style={{marginBottom:20}}>Choose a role to explore the system.</p>
          <div className="role-pick">
            {['admin','staff','customer'].map(r =>
              <button type="button" key={r} className={`role-btn ${role===r?'on':''}`} onClick={()=>pick(r)}>
                {r.charAt(0).toUpperCase()+r.slice(1)}</button>)}
          </div>
          <Field label="Email">
            <input className="input" value={email} onChange={e=>setEmail(e.target.value)} type="email" required />
          </Field>
          <Field label="Password" error={pw && !pwOk ? 'Needs 8+ chars, upper, lower and a special character.' : null}
                 hint={!pw ? 'More than 8 characters, with A-Z, a-z and a symbol.' : null}>
            <input className={`input ${pw && !pwOk ? 'err':''}`} type="password" value={pw} onChange={e=>setPw(e.target.value)} required />
          </Field>
          {err && <div className="err-txt" style={{marginBottom:10}}>{err}</div>}
          <button className="btn btn-primary" style={{width:'100%',justifyContent:'center'}} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}</button>
          <p className="dim" style={{textAlign:'center',marginTop:14}}>Forgot password? A reset link is emailed, valid 30 minutes.</p>
        </form>
      </div>
    </div>
  );
}

/* ============================ DASHBOARD ============================ */
const tipStyle = { background:'#141615', border:'none', borderRadius:14, fontSize:12.5, color:'#fff', fontFamily:'Outfit' };

function Gauge({ ratio, value, label }) {
  const r = 80, cx = 100, cy = 104;
  const f = Math.max(0.02, Math.min(0.98, ratio));
  const a = Math.PI * (1 - f);
  const x = cx + r * Math.cos(a), y = cy - r * Math.sin(a);
  return (
    <svg viewBox="0 0 200 124" style={{width:'100%',maxWidth:300,display:'block'}}>
      <defs>
        <pattern id="hp" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="#1f3d12" strokeWidth="1.6" opacity=".55" />
        </pattern>
      </defs>
      <path d={`M ${x} ${y} A ${r} ${r} 0 0 1 ${cx+r} ${cy}`} fill="none" stroke="url(#hp)" strokeWidth="24" strokeLinecap="round" />
      <path d={`M ${x} ${y} A ${r} ${r} 0 0 1 ${cx+r} ${cy}`} fill="none" stroke="#1f3d12" strokeOpacity=".35" strokeWidth="1.2" />
      <path d={`M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`} fill="none" stroke="#141615" strokeWidth="24" strokeLinecap="round" />
      <circle cx={x} cy={y} r="6" fill="#a48df5" stroke="#bdf3a0" strokeWidth="2" />
      <text x={cx} y={cy-6} textAnchor="middle" fontFamily="Outfit" fontWeight="800" fontSize="23" fill="#141615" letterSpacing="-1">{value}</text>
      <text x={cx} y={cy+12} textAnchor="middle" fontFamily="Outfit" fontSize="9.5" fill="#1f3d12" opacity=".7">{label}</text>
    </svg>
  );
}

export function Dashboard() {
  const s   = useAsync(() => api.summary(), []);
  const rev = useAsync(() => api.revenueSeries(), []);
  const inv = useAsync(() => api.invoices({ limit:6 }), []);
  const nav = useNavigate();

  if (s.loading || rev.loading) return <Loading rows={6} />;
  const d = s.data;
  const series = rev.data.data.map(r => ({ ...r, pending: r.invoiced - r.collected }));
  const totInv = series.reduce((a,r)=>a+r.invoiced,0), totCol = series.reduce((a,r)=>a+r.collected,0);
  const rate = totCol / totInv;
  const last = series[series.length-1], prev = series[series.length-2];
  const growth = ((last.invoiced - prev.invoiced) / prev.invoiced * 100).toFixed(1);
  const upcoming = db.subscriptions.filter(x => x.status==='active' && x.nextBillingDate)
    .sort((a,b)=>a.nextBillingDate.localeCompare(b.nextBillingDate)).slice(0,4);
  const k = n => '₹' + (n >= 100000 ? (n/100000).toFixed(2)+'L' : (n/1000).toFixed(1)+'k');

  return (
    <div className="fade">
      <div className="bento">
        {/* dark revenue tile */}
        <div className="tile tile-dark span-7" style={{minHeight:330,display:'flex',flexDirection:'column'}}>
          <div className="tile-h">
            <div><h3>Revenue statistics</h3><div className="tile-sub">Invoiced vs collected · last 6 months</div>
              <div style={{display:'flex',gap:16,marginTop:14,fontSize:12.5,opacity:.85}}>
                <span style={{display:'flex',alignItems:'center',gap:7}}><i style={{width:10,height:10,borderRadius:3,background:'#bdf3a0'}} />Invoiced</span>
                <span style={{display:'flex',alignItems:'center',gap:7}}><i style={{width:10,height:10,borderRadius:3,background:'#a48df5'}} />Collected</span>
              </div></div>
            <span className="spacer" /><button className="ghost-pill">Monthly ⌄</button>
          </div>
          <div style={{display:'flex',alignItems:'flex-end',gap:24,marginTop:'auto'}}>
            <div style={{flexShrink:0,paddingBottom:6}}>
              <div style={{display:'flex',alignItems:'center',gap:9,opacity:.7,fontSize:13}}>
                Collected <span className="trend">↗</span></div>
              <div className="big-num" style={{marginTop:8}}>{k(totCol)}</div>
              <div style={{fontSize:12.5,opacity:.5,marginTop:8}}>of {k(totInv)} invoiced</div>
            </div>
            <div style={{flex:1,height:210,minWidth:0}}>
              <ResponsiveContainer>
                <BarChart data={series} margin={{top:8,right:0,left:-6,bottom:0}} barCategoryGap="28%" barGap={5}>
                  <CartesianGrid vertical={false} stroke="rgba(255,255,255,.08)" strokeDasharray="0" />
                  <XAxis dataKey="period" tick={{fill:'rgba(255,255,255,.55)',fontSize:12,fontFamily:'Outfit'}} axisLine={false} tickLine={false} dy={6} />
                  <YAxis tick={{fill:'rgba(255,255,255,.4)',fontSize:11,fontFamily:'Outfit'}} axisLine={false} tickLine={false} width={44}
                         tickFormatter={v=>v===0?'0':`₹${Math.round(v/1000)}k`} tickCount={5} />
                  <Tooltip contentStyle={tipStyle} cursor={{fill:'rgba(255,255,255,.04)'}} formatter={(v,n)=>[inr(v), n]} />
                  <Bar dataKey="invoiced"  name="Invoiced"  fill="#bdf3a0" radius={[6,6,0,0]} maxBarSize={18} />
                  <Bar dataKey="collected" name="Collected" fill="#a48df5" radius={[6,6,0,0]} maxBarSize={18} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* mint + lavender stack */}
        <div className="span-5" style={{display:'grid',gap:12}}>
          <div className="tile tile-mint">
            <span className="corner-arrow">↗</span>
            <div style={{fontSize:13,opacity:.7}}>Monthly recurring revenue</div>
            <div className="mid-num" style={{margin:'14px 0 18px'}}>{inr(d.mrr)}</div>
            <div style={{display:'flex',alignItems:'center',gap:12}}>
              <b style={{fontSize:14}}>+{growth}%</b>
              <div className="progress" style={{flex:1}}><i style={{width:`${Math.min(95,50+ +growth)}%`}} /></div>
            </div>
          </div>
          <div className="tile tile-lav">
            <span className="corner-arrow">↗</span>
            <div style={{fontSize:13,opacity:.7}}>Active subscriptions</div>
            <div style={{display:'flex',alignItems:'flex-end',gap:14,marginTop:14}}>
              <div className="mid-num">{d.activeSubscriptions}</div>
              <div style={{fontSize:13,opacity:.7,paddingBottom:4}}>{d.pausedSubscriptions} paused · {d.totalCustomers} customers</div>
            </div>
          </div>
        </div>

        {/* gauge tile */}
        <div className="tile tile-white span-5">
          <div className="tile-h"><h3>Collection health</h3><span className="spacer" />
            <button className="icon-btn" onClick={()=>nav('/invoices')}>→</button></div>
          <div className="tile tile-mint" style={{marginTop:18,padding:'20px 20px 14px',boxShadow:'none',borderRadius:24}}>
            <div style={{display:'flex',alignItems:'flex-end',gap:10}}>
              <div style={{flexShrink:0,paddingBottom:10}}>
                <div className="circle-ico ci-white" style={{width:46,height:46,marginBottom:28}}>₹</div>
                <div style={{fontSize:24,fontWeight:800,letterSpacing:'-.04em'}}>{(rate*100).toFixed(0)}%</div>
                <div style={{fontSize:12,opacity:.7}}>collected</div>
              </div>
              <div style={{flex:1}}><Gauge ratio={rate} value={inr(d.outstanding).replace('.00','')} label={`outstanding · ${d.overdueCount} overdue`} /></div>
            </div>
          </div>
        </div>

        {/* timeline tile */}
        <div className="tile tile-white span-7">
          <div className="tile-h">
            <div className="circle-ico ci-mint">◷</div>
            <div><h3>Next billing</h3><div className="tile-sub" style={{opacity:1,color:'var(--text-2)'}}>Upcoming invoices from active subscriptions</div></div>
            <span className="spacer" /><button className="btn btn-sm" onClick={()=>nav('/billing')}>Run billing</button>
          </div>
          <div className="timeline" style={{marginTop:16}}>
            {upcoming.map((u,i) => (
              <div key={u.id} className={`tl-item ${i===upcoming.length-1?'last':''}`} style={{display:'flex',justifyContent:'space-between',gap:12,cursor:'pointer'}}
                   onClick={()=>nav(`/subscriptions/${u.id}`)}>
                <div><b>{nice(u.nextBillingDate)}</b><span>{u.customer.name} · {u.plan.name}</span></div>
                <div style={{fontWeight:700,fontSize:15,alignSelf:'center'}}>{inr(u.total)}</div>
              </div>))}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-h"><h3>Recent invoices</h3><span className="spacer" />
          <Link to="/invoices" className="btn btn-sm">View all →</Link></div>
        {inv.loading ? <Loading /> :
          <div className="tbl-wrap"><table>
            <thead><tr><th>Invoice</th><th>Customer</th><th>Issued</th><th>Status</th><th className="num">Total</th><th className="num">Due</th></tr></thead>
            <tbody>{inv.data.data.map(i => (
              <tr key={i.id} className="row-link" onClick={()=>nav(`/invoices/${i.id}`)}>
                <td className="mono">{i.number}</td>
                <td><div style={{display:'flex',alignItems:'center',gap:10}}><span className="avatar">{initials(i.customerDetails.name)}</span>{i.customerDetails.name}</div></td>
                <td className="dim">{nice(i.issueDate)}</td>
                <td><Badge status={i.status} overdue={i.isOverdue} /></td>
                <td className="num">{inr(i.total)}</td>
                <td className="num" style={{color:+i.amountDue>0?'var(--amber)':'var(--text-3)'}}>{inr(i.amountDue)}</td>
              </tr>))}</tbody>
          </table></div>}
      </div>
    </div>
  );
}

/* ========================== SUBSCRIPTIONS ========================== */
const SUB_TABS = ['all','draft','quotation','confirmed','active','closed'];

export function Subscriptions({ toast, user }) {
  const [tab, setTab]   = useState('all');
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const [v, bump]       = useState(0);
  const nav = useNavigate();
  const mine = user.role === 'customer' ? 'c1' : undefined;
  const r = useAsync(() => api.subscriptions({ status: tab==='all'?undefined:tab, q, customerId: mine }), [tab, q, v, mine]);

  return (
    <div className="fade">
      <div className="toolbar">
        <div className="pills">{SUB_TABS.map(t =>
          <button key={t} className={`pill ${tab===t?'on':''}`} onClick={()=>setTab(t)}>{t.charAt(0).toUpperCase()+t.slice(1)}</button>)}</div>
        <span className="spacer" />
        <input className="input" style={{maxWidth:220}} placeholder="Search number or customer…" value={q} onChange={e=>setQ(e.target.value)} />
        {user.role !== 'customer' &&
          <button className="btn btn-primary" onClick={()=>setOpen(true)}>+ New subscription</button>}
      </div>

      <div className="card">
        {r.loading ? <Loading /> : r.data.data.length === 0
          ? <Empty icon="📄" title="No subscriptions here" hint="Try another status tab, or create one." />
          : <div className="tbl-wrap"><table>
              <thead><tr><th>Number</th><th>Customer</th><th>Plan</th><th>Status</th><th>Next billing</th><th className="num">Total</th></tr></thead>
              <tbody>{r.data.data.map(s => (
                <tr key={s.id} className="row-link" onClick={()=>nav(`/subscriptions/${s.id}`)}>
                  <td className="mono">{s.number}</td>
                  <td><div style={{display:'flex',alignItems:'center',gap:9}}>
                    <span className="avatar">{initials(s.customer.name)}</span>{s.customer.name}</div></td>
                  <td>{s.plan.name}<div className="dim">{s.plan.billingPeriod}</div></td>
                  <td style={{display:'flex',gap:6,alignItems:'center',paddingTop:17}}>
                    <Badge status={s.status} />{s.isPaused && <span className="badge b-paused"><i className="dot"/>Paused</span>}</td>
                  <td className="dim">{nice(s.nextBillingDate)}</td>
                  <td className="num">{inr(s.total)}</td>
                </tr>))}</tbody>
            </table></div>}
        {r.data && <div className="card-h" style={{borderTop:'1px solid var(--border)',borderBottom:'none'}}>
          <span className="dim">{r.data.meta.total} subscription(s) · page {r.data.meta.page} of {r.data.meta.totalPages}</span></div>}
      </div>

      {open && <NewSubscription onClose={()=>setOpen(false)} onDone={m=>{setOpen(false);bump(x=>x+1);toast(m);}} />}
    </div>
  );
}

function NewSubscription({ onClose, onDone }) {
  const [f, setF] = useState({ customerId:'c1', planId:'pl1', productId:'p1', quantity:1, startDate:new Date().toISOString().slice(0,10) });
  const [err, setErr] = useState(null); const [busy, setBusy] = useState(false);
  const set = k => e => setF({ ...f, [k]: e.target.value });

  const save = async () => {
    setBusy(true); setErr(null);
    try { const s = await api.createSubscription(f); onDone(`${s.number} created as a draft.`); }
    catch (e) { setErr(e); setBusy(false); }
  };
  const fieldErr = k => err?.details?.find(d => d.field === k)?.message;

  return (
    <Modal title="New subscription" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy?'Creating…':'Create draft'}</button></>}>
      {err && <div className="err-txt" style={{marginBottom:12}}>{err.message}</div>}
      <Field label="Customer">
        <select className="input" value={f.customerId} onChange={set('customerId')}>
          {db.customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      </Field>
      <Field label="Plan" hint="Minimum quantity and availability dates are enforced by the plan.">
        <select className="input" value={f.planId} onChange={set('planId')}>
          {db.plans.map(p => <option key={p.id} value={p.id}>{p.name} · {p.billingPeriod} · min {p.minQuantity}</option>)}</select>
      </Field>
      <div className="row">
        <Field label="Product">
          <select className="input" value={f.productId} onChange={set('productId')}>
            {db.products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        </Field>
        <Field label="Quantity" error={fieldErr('quantity')}>
          <input className={`input ${fieldErr('quantity')?'err':''}`} type="number" min="1" value={f.quantity} onChange={set('quantity')} />
        </Field>
      </div>
      <Field label="Start date"><input className="input" type="date" value={f.startDate} onChange={set('startDate')} /></Field>
    </Modal>
  );
}

/* ====================== SUBSCRIPTION DETAIL ====================== */
export function SubscriptionDetail({ toast }) {
  const { id } = useParams();
  const [v, bump] = useState(0);
  const r = useAsync(() => api.subscription(id), [id, v]);
  const h = useAsync(() => api.subscriptionHistory(id), [id, v]);
  const act = useCallback(async a => {
    try { await api.transition(id, a); bump(x=>x+1); toast(`Subscription ${a}d.`); }
    catch (e) { toast(e.message, true); }
  }, [id, toast]);

  if (r.loading) return <Loading rows={7} />;
  const s = r.data;
  if (!s) return <Empty title="Not found" />;
  const plan = db.plans.find(p => p.id === s.planId);
  const nextLabel = { draft:'Send quotation', quotation:'Confirm', confirmed:'Activate', active:'Close' }[s.status];

  return (
    <div className="fade">
      <div className="toolbar">
        <Link to="/subscriptions" className="btn btn-ghost btn-sm">← Back</Link>
        <h2 className="mono" style={{fontSize:17,fontWeight:700}}>{s.number}</h2>
        <Badge status={s.status} />{s.isPaused && <span className="badge b-paused"><i className="dot"/>Paused</span>}
        <span className="spacer" />
        {nextLabel && <button className="btn btn-primary" onClick={()=>act(s.status==='active'?'close':'next')}>{nextLabel}</button>}
        {s.status==='active' && !s.isPaused && <button className="btn" onClick={()=>act('pause')} disabled={!plan.allowPause}
          title={plan.allowPause?'':'This plan does not allow pausing'}>Pause</button>}
        {s.status==='active' && s.isPaused && <button className="btn" onClick={()=>act('resume')}>Resume</button>}
        {s.status==='active' && <button className="btn" onClick={()=>act('renew')} disabled={!plan.allowRenew}
          title={plan.allowRenew?'':'This plan does not allow renewal'}>Renew</button>}
      </div>

      <div className="card" style={{marginBottom:12}}><div className="card-b"><Flow status={s.status} /></div></div>

      <div className="grid-2">
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <div className="card">
            <div className="card-h"><h3>Lines</h3></div>
            <div className="tbl-wrap"><table>
              <thead><tr><th>Product</th><th className="num">Qty</th><th className="num">Unit price</th><th>Tax</th><th className="num">Amount</th></tr></thead>
              <tbody>{s.lines.map(l => (
                <tr key={l.id}><td>{l.productName}{l.variantName && <div className="dim">{l.variantName}</div>}</td>
                  <td className="num">{l.quantity}</td><td className="num">{inr(l.unitPrice)}</td>
                  <td className="dim">{l.taxName}</td><td className="num">{inr(l.amount)}</td></tr>))}</tbody>
            </table></div>
            <div className="card-b">
              <div className="kv"><span className="k">Subtotal</span><span className="v">{inr(s.subtotal)}</span></div>
              <div className="kv"><span className="k">Discount</span><span className="v" style={{color:'var(--green)'}}>−{inr(s.discountTotal)}</span></div>
              <div className="kv"><span className="k">Tax</span><span className="v">{inr(s.taxTotal)}</span></div>
              <div className="kv total-row"><span>Total</span><span>{inr(s.total)}</span></div>
            </div>
          </div>
          <SubInvoices id={s.id} />
        </div>

        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <div className="card"><div className="card-h"><h3>Details</h3></div><div className="card-b">
            <div className="kv"><span className="k">Customer</span><span className="v">{s.customer.name}</span></div>
            <div className="kv"><span className="k">Plan</span><span className="v">{s.plan.name}</span></div>
            <div className="kv"><span className="k">Billing</span><span className="v">{s.plan.billingPeriod}</span></div>
            <div className="kv"><span className="k">Start</span><span className="v">{nice(s.startDate)}</span></div>
            <div className="kv"><span className="k">Expiry</span><span className="v">{nice(s.expiryDate)}</span></div>
            <div className="kv"><span className="k">Next billing</span><span className="v">{nice(s.nextBillingDate)}</span></div>
            <div className="kv"><span className="k">Payment terms</span><span className="v">{s.paymentTerms} days</span></div>
          </div></div>
          <div className="card"><div className="card-h"><h3>Plan rules</h3></div><div className="card-b">
            {[['Close early','allowEarlyClose'],['Pause','allowPause'],['Renew','allowRenew'],['Auto-close at expiry','autoClose']].map(([l,k])=>
              <div className="kv" key={k}><span className="k">{l}</span>
                <span className="v" style={{color:plan[k]?'var(--green)':'var(--text-3)'}}>{plan[k]?'Allowed':'Not allowed'}</span></div>)}
          </div></div>
          <div className="card"><div className="card-h"><h3>History</h3></div><div className="card-b">
            {h.loading ? <Loading rows={3} /> : h.data.data.map(e => (
              <div className="kv" key={e.id}>
                <span className="k">{e.from ? `${e.from} → ${e.to}` : `Created as ${e.to}`}</span>
                <span className="v dim">{nice(e.at)}</span></div>))}
          </div></div>
        </div>
      </div>
    </div>
  );
}

function SubInvoices({ id }) {
  const r = useAsync(() => api.invoices({ subscriptionId:id }), [id]);
  const nav = useNavigate();
  return (
    <div className="card">
      <div className="card-h"><h3>Invoices</h3></div>
      {r.loading ? <Loading rows={3} /> : r.data.data.length === 0
        ? <Empty icon="🧾" title="No invoices yet" hint="They appear after the next billing run." />
        : <div className="tbl-wrap"><table>
            <thead><tr><th>Invoice</th><th>Issued</th><th>Status</th><th className="num">Total</th></tr></thead>
            <tbody>{r.data.data.map(i => (
              <tr key={i.id} className="row-link" onClick={()=>nav(`/invoices/${i.id}`)}>
                <td className="mono">{i.number}</td><td className="dim">{nice(i.issueDate)}</td>
                <td><Badge status={i.status} overdue={i.isOverdue} /></td>
                <td className="num">{inr(i.total)}</td></tr>))}</tbody>
          </table></div>}
    </div>
  );
}

/* ============================= INVOICES ============================= */
const INV_TABS = ['all','draft','confirmed','paid','cancelled','overdue'];

export function Invoices({ user }) {
  const [tab, setTab] = useState('all');
  const [q, setQ] = useState('');
  const nav = useNavigate();
  const mine = user.role === 'customer' ? 'c1' : undefined;
  const r = useAsync(() => api.invoices({
    status: ['all','overdue'].includes(tab) ? undefined : tab,
    isOverdue: tab === 'overdue' || undefined, q, customerId: mine,
  }), [tab, q, mine]);

  return (
    <div className="fade">
      <div className="toolbar">
        <div className="pills">{INV_TABS.map(t =>
          <button key={t} className={`pill ${tab===t?'on':''}`} onClick={()=>setTab(t)}>{t.charAt(0).toUpperCase()+t.slice(1)}</button>)}</div>
        <span className="spacer" />
        <input className="input" style={{maxWidth:220}} placeholder="Search invoice or customer…" value={q} onChange={e=>setQ(e.target.value)} />
      </div>
      <div className="card">
        {r.loading ? <Loading /> : r.data.data.length === 0
          ? <Empty icon="🧾" title="No invoices here" />
          : <div className="tbl-wrap"><table>
              <thead><tr><th>Invoice</th><th>Customer</th><th>Issued</th><th>Due</th><th>Status</th><th className="num">Total</th><th className="num">Outstanding</th></tr></thead>
              <tbody>{r.data.data.map(i => (
                <tr key={i.id} className="row-link" onClick={()=>nav(`/invoices/${i.id}`)}>
                  <td className="mono">{i.number}</td>
                  <td>{i.customerDetails.name}</td>
                  <td className="dim">{nice(i.issueDate)}</td>
                  <td className="dim" style={{color:i.isOverdue?'var(--red)':undefined}}>{nice(i.dueDate)}</td>
                  <td><Badge status={i.status} overdue={i.isOverdue} /></td>
                  <td className="num">{inr(i.total)}</td>
                  <td className="num" style={{color:+i.amountDue>0?'var(--amber)':'var(--text-3)'}}>{inr(i.amountDue)}</td>
                </tr>))}</tbody>
            </table></div>}
      </div>
    </div>
  );
}

export function InvoiceDetail({ toast, user }) {
  const { id } = useParams();
  const [v, bump] = useState(0);
  const [pay, setPay] = useState(false);
  const r = useAsync(() => api.invoice(id), [id, v]);
  const p = useAsync(() => api.payments({ invoiceId:id }), [id, v]);

  const act = async a => {
    try { await api.invoiceAction(id, a); bump(x=>x+1); toast(`Invoice ${a}${a==='send'?'ed':'led'}.`); }
    catch (e) { toast(e.message, true); }
  };
  if (r.loading) return <Loading rows={7} />;
  const i = r.data;
  if (!i) return <Empty title="Not found" />;
  const staff = user.role !== 'customer';

  return (
    <div className="fade">
      <div className="toolbar">
        <Link to="/invoices" className="btn btn-ghost btn-sm">← Back</Link>
        <h2 className="mono" style={{fontSize:17,fontWeight:700}}>{i.number}</h2>
        <Badge status={i.status} overdue={i.isOverdue} />
        <span className="spacer" />
        {staff && i.status==='draft'     && <button className="btn btn-primary" onClick={()=>act('confirm')}>Confirm</button>}
        {staff && i.status==='confirmed' && <button className="btn btn-primary" onClick={()=>setPay(true)}>Record payment</button>}
        {staff && ['confirmed','paid'].includes(i.status) && <button className="btn" onClick={()=>act('send')}>Send</button>}
        <button className="btn" onClick={()=>window.print()}>Print</button>
        {staff && ['draft','confirmed'].includes(i.status) && +i.amountPaid===0 &&
          <button className="btn btn-danger" onClick={()=>act('cancel')}>Cancel</button>}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-h"><h3>Lines</h3><span className="spacer" />
            <span className="dim">Period {nice(i.periodStart)} → {nice(i.periodEnd)}</span></div>
          <div className="tbl-wrap"><table>
            <thead><tr><th>Product</th><th className="num">Qty</th><th className="num">Unit</th><th>Tax</th><th className="num">Amount</th></tr></thead>
            <tbody>{i.lines.map(l => (
              <tr key={l.id}><td>{l.productName}{l.variantName && <div className="dim">{l.variantName}</div>}</td>
                <td className="num">{l.quantity}</td><td className="num">{inr(l.unitPrice)}</td>
                <td className="dim">{l.taxName}</td><td className="num">{inr(l.amount)}</td></tr>))}</tbody>
          </table></div>
          <div className="card-b">
            <div className="kv"><span className="k">Subtotal</span><span className="v">{inr(i.subtotal)}</span></div>
            <div className="kv"><span className="k">Discount</span><span className="v" style={{color:'var(--green)'}}>−{inr(i.discountTotal)}</span></div>
            <div className="kv"><span className="k">Tax</span><span className="v">{inr(i.taxTotal)}</span></div>
            <div className="kv total-row"><span>Total</span><span>{inr(i.total)}</span></div>
            <div className="kv"><span className="k">Paid</span><span className="v" style={{color:'var(--green)'}}>{inr(i.amountPaid)}</span></div>
            <div className="kv"><span className="k">Still due</span>
              <span className="v" style={{color:+i.amountDue>0?'var(--amber)':'var(--green)'}}>{inr(i.amountDue)}</span></div>
          </div>
        </div>

        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <div className="card"><div className="card-h"><h3>Bill to</h3></div><div className="card-b">
            <div style={{fontWeight:600,marginBottom:3}}>{i.customerDetails.name}</div>
            <div className="dim">{i.customerDetails.company}</div>
            <div className="dim">{i.customerDetails.email}</div>
            <div style={{marginTop:12}}>
              <div className="kv"><span className="k">Subscription</span>
                <Link className="v mono" style={{textDecoration:'underline',textUnderlineOffset:3}} to={`/subscriptions/${i.subscriptionId}`}>{i.subscriptionNumber}</Link></div>
              <div className="kv"><span className="k">Issued</span><span className="v">{nice(i.issueDate)}</span></div>
              <div className="kv"><span className="k">Due</span><span className="v">{nice(i.dueDate)}</span></div>
            </div>
          </div></div>
          <div className="card"><div className="card-h"><h3>Payments</h3></div>
            {p.loading ? <Loading rows={2} /> : p.data.data.length === 0
              ? <Empty icon="💳" title="No payments yet" />
              : <div className="card-b">{p.data.data.map(x => (
                  <div className="kv" key={x.id}>
                    <span className="k">{x.method.replace('_',' ')}<div className="dim">{nice(x.paymentDate)} · {x.reference}</div></span>
                    <span className="v">{inr(x.amount)}</span></div>))}</div>}
          </div>
        </div>
      </div>

      {pay && <PaymentModal invoice={i} onClose={()=>setPay(false)}
        onDone={m=>{setPay(false);bump(x=>x+1);toast(m);}} />}
    </div>
  );
}

function PaymentModal({ invoice, onClose, onDone }) {
  const [f, setF] = useState({ amount: invoice.amountDue, method:'upi', paymentDate:new Date().toISOString().slice(0,10), reference:'' });
  const [err, setErr] = useState(null); const [busy, setBusy] = useState(false);
  const set = k => e => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true); setErr(null);
    try { await api.recordPayment({ invoiceId: invoice.id, ...f }); onDone(`Payment of ${inr(f.amount)} recorded.`); }
    catch (e) { setErr(e); setBusy(false); }
  };
  const fe = k => err?.details?.find(d => d.field === k)?.message;
  return (
    <Modal title={`Record payment · ${invoice.number}`} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy?'Saving…':'Record payment'}</button></>}>
      {err && <div className="err-txt" style={{marginBottom:12}}>{err.message}</div>}
      <Field label="Amount" error={fe('amount')} hint={`${inr(invoice.amountDue)} still due · partial payments allowed`}>
        <input className={`input ${fe('amount')?'err':''}`} type="number" step="0.01" value={f.amount} onChange={set('amount')} />
      </Field>
      <div className="row">
        <Field label="Method"><select className="input" value={f.method} onChange={set('method')}>
          {['upi','bank_transfer','card','cash','cheque'].map(m => <option key={m} value={m}>{m.replace('_',' ')}</option>)}</select></Field>
        <Field label="Date"><input className="input" type="date" value={f.paymentDate} onChange={set('paymentDate')} /></Field>
      </div>
      <Field label="Reference" hint="Optional — transaction id or note">
        <input className="input" value={f.reference} onChange={set('reference')} placeholder="TXN…" /></Field>
    </Modal>
  );
}

/* ============================== BILLING ============================== */
export function Billing({ toast }) {
  const [v, bump] = useState(0);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const due = useAsync(() => api.billingDue(), [v]);

  const run = async dryRun => {
    setBusy(true);
    const res = await api.billingRun({ dryRun });
    setResult(res); setBusy(false);
    if (!dryRun) { bump(x=>x+1); toast(`${res.createdCount} invoice(s) created.`); }
  };

  return (
    <div className="fade">
      <div className="card" style={{marginBottom:12}}>
        <div className="card-h"><h3>Billing day</h3><span className="spacer" />
          <button className="btn" onClick={()=>run(true)}  disabled={busy}>Preview (dry run)</button>
          <button className="btn btn-primary" onClick={()=>run(false)} disabled={busy}>{busy?'Running…':'Run billing'}</button></div>
        <div className="card-b">
          <p className="muted" style={{marginBottom:4}}>Creates one draft invoice per subscription that is due — customer, lines, taxes and totals already filled in.</p>
          <p className="dim">Safe to run more than once: a unique rule on (subscription, period) means nothing is billed twice or skipped.</p>
        </div>
      </div>

      {result && (
        <div className="card fade" style={{marginBottom:12,outline:'2px solid var(--mint-2)'}}>
          <div className="card-h"><h3>{result.dryRun ? 'Dry run — nothing saved' : 'Run complete'}</h3><span className="spacer" />
            <span className="badge b-active"><i className="dot"/>{result.createdCount} created</span>
            {result.failedCount>0 && <span className="badge b-cancelled"><i className="dot"/>{result.failedCount} failed</span>}</div>
          <div className="tbl-wrap"><table>
            <thead><tr><th>Subscription</th><th>Invoice</th><th className="num">Total</th></tr></thead>
            <tbody>{result.created.map((c,k) => (
              <tr key={k}><td className="mono">{c.subscriptionNumber}</td>
                <td className="mono">{c.invoiceNumber || <span className="dim">would create</span>}</td>
                <td className="num">{inr(c.total)}</td></tr>))}</tbody>
          </table></div>
        </div>
      )}

      <div className="card">
        <div className="card-h"><h3>Due for billing</h3><span className="spacer" />
          <span className="dim">Active, not paused, next billing date reached</span></div>
        {due.loading ? <Loading /> : due.data.data.length === 0
          ? <Empty icon="✅" title="Nothing due right now" hint="All caught up." />
          : <div className="tbl-wrap"><table>
              <thead><tr><th>Subscription</th><th>Customer</th><th>Plan</th><th>Next billing</th><th className="num">Amount</th></tr></thead>
              <tbody>{due.data.data.map(s => (
                <tr key={s.id}><td className="mono">{s.number}</td><td>{s.customer.name}</td>
                  <td>{s.plan.name}</td><td className="dim">{nice(s.nextBillingDate)}</td>
                  <td className="num">{inr(s.total)}</td></tr>))}</tbody>
            </table></div>}
      </div>
    </div>
  );
}

/* ============================= CATALOGUE ============================= */
export function Products() {
  const r = useAsync(() => api.products(), []);
  return (
    <div className="card fade">
      <div className="card-h"><h3>Products</h3><span className="spacer" /><button className="btn btn-primary btn-sm">+ New product</button></div>
      {r.loading ? <Loading /> : <div className="tbl-wrap"><table>
        <thead><tr><th>Name</th><th>Type</th><th>Variants</th><th className="num">Sales price</th><th className="num">Cost</th><th>Status</th></tr></thead>
        <tbody>{r.data.data.map(p => (
          <tr key={p.id}><td style={{fontWeight:550}}>{p.name}</td><td className="dim">{p.type}</td>
            <td>{p.variants.length === 0 ? <span className="dim">—</span> :
              p.variants.map(v => <span key={v.id} className="badge b-draft" style={{marginRight:5}}>
                {v.value} {+v.extraPrice>0 && `+${inr(v.extraPrice)}`}</span>)}</td>
            <td className="num">{inr(p.salesPrice)}</td><td className="num dim">{inr(p.costPrice)}</td>
            <td><Badge status={p.isActive?'active':'closed'} /></td></tr>))}</tbody>
      </table></div>}
    </div>
  );
}

export function Plans() {
  const r = useAsync(() => api.plans(), []);
  return (
    <div className="card fade">
      <div className="card-h"><h3>Plans</h3><span className="spacer" /><button className="btn btn-primary btn-sm">+ New plan</button></div>
      {r.loading ? <Loading /> : <div className="tbl-wrap"><table>
        <thead><tr><th>Name</th><th>Billing</th><th className="num">Price</th><th className="num">Min qty</th><th>Available</th><th>Rules</th></tr></thead>
        <tbody>{r.data.data.map(p => (
          <tr key={p.id}><td style={{fontWeight:550}}>{p.name}</td>
            <td><span className="badge b-confirmed"><i className="dot"/>{p.billingPeriod}</span></td>
            <td className="num">{inr(p.price)}</td><td className="num">{p.minQuantity}</td>
            <td className="dim">{nice(p.availableFrom)} → {nice(p.availableTo)}</td>
            <td>{[['Close',p.allowEarlyClose],['Pause',p.allowPause],['Renew',p.allowRenew],['Auto',p.autoClose]]
              .filter(([,on])=>on).map(([l])=><span key={l} className="badge b-active" style={{marginRight:4}}>{l}</span>)}</td>
          </tr>))}</tbody>
      </table></div>}
    </div>
  );
}

export function Customers() {
  const r = useAsync(() => api.customers(), []);
  return (
    <div className="card fade">
      <div className="card-h"><h3>Customers</h3><span className="spacer" /><button className="btn btn-primary btn-sm">+ New customer</button></div>
      {r.loading ? <Loading /> : <div className="tbl-wrap"><table>
        <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Tax ID</th></tr></thead>
        <tbody>{r.data.data.map(c => (
          <tr key={c.id}><td><div style={{display:'flex',alignItems:'center',gap:9}}>
            <span className="avatar">{initials(c.name)}</span><span style={{fontWeight:550}}>{c.name}</span></div></td>
            <td className="dim">{c.email}</td><td className="dim">{c.phone}</td><td className="mono dim">{c.taxId}</td></tr>))}</tbody>
      </table></div>}
    </div>
  );
}

export function Discounts() {
  const r = useAsync(() => api.discounts(), []);
  return (
    <div className="card fade">
      <div className="card-h"><h3>Discount rules</h3><span className="spacer" /><button className="btn btn-primary btn-sm">+ New discount</button></div>
      {r.loading ? <Loading /> : <div className="tbl-wrap"><table>
        <thead><tr><th>Name</th><th>Type</th><th className="num">Value</th><th>Scope</th><th>Valid</th><th className="num">Used</th></tr></thead>
        <tbody>{r.data.data.map(d => (
          <tr key={d.id}><td style={{fontWeight:550}}>{d.name}</td><td className="dim">{d.type}</td>
            <td className="num">{d.type==='percentage' ? `${d.value}%` : inr(d.value)}</td>
            <td><span className="badge b-quotation"><i className="dot"/>{d.scope}</span></td>
            <td className="dim">{nice(d.startDate)} → {nice(d.endDate)}</td>
            <td className="num">{d.usedCount} / {d.usageLimit}</td></tr>))}</tbody>
      </table></div>}
    </div>
  );
}

export function Taxes() {
  const r = useAsync(() => api.taxes(), []);
  return (
    <div className="card fade">
      <div className="card-h"><h3>Tax rules</h3><span className="spacer" /><button className="btn btn-primary btn-sm">+ New tax</button></div>
      {r.loading ? <Loading /> : <div className="tbl-wrap"><table>
        <thead><tr><th>Name</th><th>Computation</th><th className="num">Value</th><th>Applies to</th><th>Status</th></tr></thead>
        <tbody>{r.data.data.map(t => (
          <tr key={t.id}><td style={{fontWeight:550}}>{t.name}</td><td className="dim">{t.computation}</td>
            <td className="num">{t.value}%</td>
            <td>{t.appliesToProductTypes.map(x=><span key={x} className="badge b-draft" style={{marginRight:4}}>{x}</span>)}</td>
            <td><Badge status={t.isActive?'active':'closed'} /></td></tr>))}</tbody>
      </table></div>}
    </div>
  );
}

export function Users() {
  const r = useAsync(() => api.users(), []);
  return (
    <div className="card fade">
      <div className="card-h"><h3>Users &amp; staff</h3><span className="spacer" /><button className="btn btn-primary btn-sm">+ Add staff</button></div>
      {r.loading ? <Loading /> : <div className="tbl-wrap"><table>
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
        <tbody>{r.data.data.map(u => (
          <tr key={u.id}><td><div style={{display:'flex',alignItems:'center',gap:9}}>
            <span className="avatar">{initials(u.name)}</span><span style={{fontWeight:550}}>{u.name}</span></div></td>
            <td className="dim">{u.email}</td>
            <td><span className={`badge ${u.role==='admin'?'b-quotation':u.role==='staff'?'b-confirmed':'b-draft'}`}><i className="dot"/>{u.role}</span></td>
            <td><Badge status={u.isActive?'active':'closed'} /></td></tr>))}</tbody>
      </table></div>}
    </div>
  );
}
