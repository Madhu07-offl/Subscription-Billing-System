import { useState, useCallback, useEffect } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import { Toast, initials } from './ui';
import { logout as apiLogout, BASE_URL, USE_MOCK } from './api';
console.log('%c[API TARGET]', 'background:#141615;color:#bdf3a0;padding:2px 6px;border-radius:4px', USE_MOCK ? 'MOCK DATA (offline)' : BASE_URL);
import {
  Login, Dashboard, Subscriptions, SubscriptionDetail,
  Invoices, InvoiceDetail, Billing, Products, Plans, Customers, Discounts, Taxes, Users,
} from './pages';

/* nav definition — roles mirror x-roles in the contract */
const NAV = [
  { section:'Overview', items:[
    { to:'/',              label:'Dashboard',     ico:'◫', roles:['admin','staff'] },
    { to:'/subscriptions', label:'Subscriptions', ico:'◎', roles:['admin','staff','customer'] },
    { to:'/invoices',      label:'Invoices',      ico:'▤', roles:['admin','staff','customer'] },
  ]},
  { section:'Operations', items:[
    { to:'/billing',   label:'Billing run', ico:'◷', roles:['admin','staff'] },
    { to:'/customers', label:'Customers',   ico:'◍', roles:['admin','staff'] },
  ]},
  { section:'Configuration', items:[
    { to:'/products',  label:'Products',  ico:'◰', roles:['admin'] },
    { to:'/plans',     label:'Plans',     ico:'◱', roles:['admin'] },
    { to:'/discounts', label:'Discounts', ico:'◲', roles:['admin'] },
    { to:'/taxes',     label:'Taxes',     ico:'◳', roles:['admin'] },
    { to:'/users',     label:'Users',     ico:'◴', roles:['admin'] },
  ]},
];

const TITLES = {
  '/':'Dashboard', '/subscriptions':'Subscriptions', '/invoices':'Invoices', '/billing':'Billing run',
  '/customers':'Customers', '/products':'Products', '/plans':'Plans', '/discounts':'Discounts',
  '/taxes':'Taxes', '/users':'Users & staff',
};

function Shell({ user, onLogout, toast, children }) {
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState('light');
  const loc = useLocation();

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => { setOpen(false); }, [loc.pathname]);

  const title = TITLES[loc.pathname] ||
    (loc.pathname.startsWith('/subscriptions/') ? 'Subscription' :
     loc.pathname.startsWith('/invoices/') ? 'Invoice' : 'Brightloop');

  return (
    <div className="app">
      <aside className={`sidebar ${open?'open':''}`}>
        <div className="brand"><span className="brand-mark">B</span> Brightloop</div>
        {NAV.map(g => {
          const items = g.items.filter(i => i.roles.includes(user.role));
          if (!items.length) return null;
          return (
            <div key={g.section}>
              <div className="nav-label">{g.section}</div>
              {items.map(i => (
                <NavLink key={i.to} to={i.to} end={i.to==='/'}
                  className={({isActive}) => `nav-item ${isActive?'active':''}`}>
                  <span className="ico">{i.ico}</span>{i.label}
                </NavLink>))}
            </div>
          );
        })}
        <div className="sidebar-foot">
          <div className="nav-item" style={{cursor:'default'}}>
            <span className="avatar">{initials(user.name)}</span>
            <div style={{minWidth:0}}>
              <div style={{fontSize:12.5,fontWeight:600,color:'var(--text)'}}>{user.name}</div>
              <div style={{fontSize:11,color:'var(--text-3)',textTransform:'capitalize'}}>{user.role}</div>
            </div>
          </div>
          <div className="nav-item" onClick={onLogout}><span className="ico">⇥</span>Sign out</div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="burger" onClick={()=>setOpen(o=>!o)}>☰</button>
          <h1>{title}</h1>
          <span className="spacer" />
          <button className="btn btn-sm btn-ghost" onClick={()=>setTheme(t=>t==='dark'?'light':'dark')}
            title="Switch theme">{theme==='dark'?'☀':'☾'}</button>
        </header>
        <main className="content">{children}</main>
      </div>
      {toast}
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem('bl_user') || 'null'));
  const [toast, setToast] = useState(null);

  const notify = useCallback((msg, bad=false) => setToast({ msg, bad, k:Date.now() }), []);
  const login  = u => { localStorage.setItem('bl_user', JSON.stringify(u)); setUser(u); };
  const logout = () => { apiLogout(); localStorage.removeItem('bl_user'); setUser(null); };

  if (!user) return <Login onLogin={login} />;

  const toastEl = toast && <Toast key={toast.k} msg={toast.msg} bad={toast.bad} onDone={()=>setToast(null)} />;
  const home = user.role === 'customer' ? '/subscriptions' : '/';

  return (
    <BrowserRouter>
      <Shell user={user} onLogout={logout} toast={toastEl}>
        <Routes>
          <Route path="/" element={user.role==='customer' ? <Navigate to="/subscriptions" replace /> : <Dashboard />} />
          <Route path="/subscriptions"      element={<Subscriptions toast={notify} user={user} />} />
          <Route path="/subscriptions/:id"  element={<SubscriptionDetail toast={notify} user={user} />} />
          <Route path="/invoices"           element={<Invoices user={user} />} />
          <Route path="/invoices/:id"       element={<InvoiceDetail toast={notify} user={user} />} />
          <Route path="/billing"            element={<Billing toast={notify} />} />
          <Route path="/customers"          element={<Customers />} />
          <Route path="/products"           element={<Products />} />
          <Route path="/plans"              element={<Plans />} />
          <Route path="/discounts"          element={<Discounts />} />
          <Route path="/taxes"              element={<Taxes />} />
          <Route path="/users"              element={<Users />} />
          <Route path="*"                   element={<Navigate to={home} replace />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
