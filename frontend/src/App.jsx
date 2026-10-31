import { useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import { api, setSessionExpiredHandler, TOKEN_KEY, USER_KEY } from './api';
import { Icon, ThemeSwitch, ToastProvider, FormModal, Field, useForm, useToast, initials } from './ui';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import { Subscriptions, SubscriptionDetail } from './pages/Subscriptions';
import { Invoices, InvoiceDetail } from './pages/Invoices';
import Payments from './pages/Payments';
import Billing from './pages/Billing';
import Customers from './pages/Customers';
import Products from './pages/Products';
import Plans from './pages/Plans';
import Templates from './pages/Templates';
import Taxes from './pages/Taxes';
import Discounts from './pages/Discounts';
import Users from './pages/Users';

/* nav + routes — roles mirror x-roles in the contract */
const STAFF = ['admin', 'staff'], ALL = ['admin', 'staff', 'customer'];
const NAV = [
  { section: 'Overview', items: [
    { to: '/',              label: 'Dashboard',     ico: 'dashboard',     roles: STAFF, el: Dashboard },
    { to: '/subscriptions', label: 'Subscriptions', ico: 'subscriptions', roles: ALL,   el: Subscriptions },
    { to: '/invoices',      label: 'Invoices',      ico: 'invoices',      roles: ALL,   el: Invoices },
    { to: '/payments',      label: 'Payments',      ico: 'payments',      roles: ALL,   el: Payments },
  ]},
  { section: 'Operations', items: [
    { to: '/billing',   label: 'Billing run', ico: 'billing',   roles: STAFF, el: Billing },
    { to: '/customers', label: 'Customers',   ico: 'customers', roles: STAFF, el: Customers },
  ]},
  { section: 'Configuration', items: [
    { to: '/products',  label: 'Products',  ico: 'products',  roles: STAFF,     el: Products },
    { to: '/plans',     label: 'Plans',     ico: 'plans',     roles: STAFF,     el: Plans },
    { to: '/templates', label: 'Templates', ico: 'templates', roles: STAFF,     el: Templates },
    { to: '/discounts', label: 'Discounts', ico: 'discounts', roles: STAFF,     el: Discounts },
    { to: '/taxes',     label: 'Taxes',     ico: 'taxes',     roles: STAFF,     el: Taxes },
    { to: '/users',     label: 'Users',     ico: 'users',     roles: ['admin'], el: Users },
  ]},
];
const ITEMS = NAV.flatMap(g => g.items);

function titleFor(path) {
  if (path.startsWith('/subscriptions/')) return 'Subscription';
  if (path.startsWith('/invoices/')) return 'Invoice';
  const item = ITEMS.find(i => i.to === path);
  return item ? (item.to === '/users' ? 'Users & staff' : item.label) : 'Brightloop';
}

function useTheme() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light');
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('bl_theme', theme); } catch { /* storage unavailable */ }
  }, [theme]);
  return [theme, () => setTheme(t => (t === 'dark' ? 'light' : 'dark'))];
}

function ChangePassword({ onClose }) {
  const toast = useToast();
  const f = useForm({ currentPassword: '', newPassword: '', confirm: '' });
  const v = f.values;
  const save = () => f.submit(
    x => ({
      currentPassword: !x.currentPassword && 'Enter your current password.',
      newPassword: !x.newPassword && 'Enter a new password.',
      confirm: x.confirm !== x.newPassword && 'Passwords do not match.',
    }),
    x => api.changePassword(x.currentPassword, x.newPassword),
  ).then(ok => { if (ok) { toast('Password changed.'); onClose(); } });
  return (
    <FormModal title="Change password" onClose={onClose} onSubmit={save} busy={f.busy} message={f.message} submitLabel="Change password">
      <Field label="Current password" error={f.errors.currentPassword}>
        <input className={`input ${f.errors.currentPassword ? 'err' : ''}`} type="password" autoComplete="current-password" value={v.currentPassword} onChange={f.set('currentPassword')} autoFocus /></Field>
      <Field label="New password" error={f.errors.newPassword} hint="More than 8 characters, with an uppercase letter, a lowercase letter and a symbol.">
        <input className={`input ${f.errors.newPassword ? 'err' : ''}`} type="password" autoComplete="new-password" value={v.newPassword} onChange={f.set('newPassword')} /></Field>
      <Field label="Confirm new password" error={f.errors.confirm}>
        <input className={`input ${f.errors.confirm ? 'err' : ''}`} type="password" autoComplete="new-password" value={v.confirm} onChange={f.set('confirm')} /></Field>
    </FormModal>
  );
}

function Shell({ user, onLogout, children }) {
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState(false);
  const [theme, toggleTheme] = useTheme();
  const loc = useLocation();
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);

  return (
    <div className="app">
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
        <div className="brand"><img className="brand-logo" src="/logo-full.png" alt="Brightloop" /></div>
        <nav>
          {NAV.map(g => {
            const items = g.items.filter(i => i.roles.includes(user.role));
            if (!items.length) return null;
            return (
              <div key={g.section}>
                <div className="nav-label">{g.section}</div>
                {items.map(i => (
                  <NavLink key={i.to} to={i.to} end={i.to === '/'} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                    <span className="ico"><Icon name={i.ico} /></span>{i.label}
                  </NavLink>))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <div className="me">
            <span className="avatar">{initials(user.name)}</span>
            <div style={{ minWidth: 0 }}>
              <div className="me-name">{user.name}</div>
              <div className="me-sub">{user.email}</div>
            </div>
          </div>
          <button className="nav-item" onClick={() => setPw(true)}><span className="ico"><Icon name="key" /></span>Change password</button>
          <button className="nav-item" onClick={onLogout}><span className="ico"><Icon name="signout" /></span>Sign out</button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="burger icon-btn" aria-label="Open menu" onClick={() => setOpen(o => !o)}><Icon name="menu" /></button>
          <h1>{titleFor(loc.pathname)}</h1>
          <span className="spacer" />
          <span className={`role-chip r-${user.role}`}>{user.role}</span>
          <ThemeSwitch theme={theme} onToggle={toggleTheme} />
        </header>
        <main className="content">{children}</main>
      </div>
      {pw && <ChangePassword onClose={() => setPw(false)} />}
    </div>
  );
}

function readUser() {
  try { return localStorage.getItem(TOKEN_KEY) ? JSON.parse(localStorage.getItem(USER_KEY) || 'null') : null; }
  catch { return null; }
}

export default function App() {
  const [user, setUser] = useState(readUser);
  const [expired, setExpired] = useState(false);

  const logout = useCallback((why) => {
    localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY);
    setExpired(why === 'expired');
    setUser(null);
  }, []);
  const login = u => { localStorage.setItem(USER_KEY, JSON.stringify(u)); setExpired(false); setUser(u); };

  useEffect(() => { setSessionExpiredHandler(() => logout('expired')); }, [logout]);
  // Refresh the stored profile once per load (role or name may have changed); a dead token signs out.
  useEffect(() => {
    if (!user) return;
    api.me().then(u => { localStorage.setItem(USER_KEY, JSON.stringify(u)); setUser(u); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!user) return <ToastProvider><Login onLogin={login} expired={expired} /></ToastProvider>;

  const home = user.role === 'customer' ? '/subscriptions' : '/';
  return (
    <ToastProvider>
      <BrowserRouter>
        <Shell user={user} onLogout={() => logout()}>
          <Routes>
            {ITEMS.filter(i => i.roles.includes(user.role)).map(i =>
              <Route key={i.to} path={i.to} element={<i.el user={user} />} />)}
            <Route path="/subscriptions/:id" element={<SubscriptionDetail user={user} />} />
            <Route path="/invoices/:id" element={<InvoiceDetail user={user} />} />
            <Route path="*" element={<Navigate to={home} replace />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </ToastProvider>
  );
}
