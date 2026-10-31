import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

/* ------------------------------ formatters ------------------------------ */
export const inr = v => (v === null || v === undefined || v === '') ? '—'
  : '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Date-only strings ("2026-10-31") are parsed as local dates so the day never shifts with the timezone.
const toDate = d => (typeof d === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d))
  ? new Date(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) : new Date(d);
export const nice = d => d ? toDate(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
export const niceTime = d => d ? new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
export const isoDate = (d = new Date()) => {
  const x = toDate(d); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 10);
};
export const addDays = (d, n) => { const x = toDate(d); x.setDate(x.getDate() + n); return x; };
export const initials = n => (n || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();
export const label = s => s ? String(s).replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase()) : '—';
export const TERMS = { immediate: 'Immediate', net_15: 'Net 15', net_30: 'Net 30', net_45: 'Net 45', net_60: 'Net 60' };

/* -------------------------------- icons -------------------------------- */
const PATHS = {
  dashboard:     <><rect x="3" y="3" width="7" height="9" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="12" width="7" height="9" rx="2"/><rect x="3" y="16" width="7" height="5" rx="2"/></>,
  subscriptions: <><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></>,
  invoices:      <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/></>,
  payments:      <><rect x="2.5" y="5" width="19" height="14" rx="3"/><path d="M2.5 10h19M6.5 15h4"/></>,
  billing:       <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  customers:     <><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.7-3.6 3.3-5.5 6.5-5.5s5.8 1.9 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 14.8c1.7.7 2.7 2.4 3 4.7"/></>,
  products:      <><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/></>,
  plans:         <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M8 14h4"/></>,
  templates:     <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></>,
  discounts:     <><path d="M20 12.5L12.5 20a2 2 0 0 1-2.8 0L3 13.3V4h9.3L20 11.7a1 1 0 0 1 0 .8z"/><circle cx="8" cy="8.5" r="1.3"/></>,
  taxes:         <><path d="M5 19L19 5"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/></>,
  users:         <><circle cx="12" cy="8" r="4"/><path d="M4 21c.6-4 3.8-6 8-6s7.4 2 8 6"/></>,
  signout:       <><path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5"/><path d="M15 8l4 4-4 4M19 12H9"/></>,
  key:           <><circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3"/></>,
  menu:          <path d="M4 7h16M4 12h16M4 17h16"/>,
  sun:           <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
  moon:          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>,
  plus:          <path d="M12 5v14M5 12h14"/>,
  edit:          <><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></>,
  trash:         <><path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13M9 7V4h6v3"/></>,
  search:        <><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></>,
  back:          <path d="M15 18l-6-6 6-6"/>,
  next:          <path d="M9 18l6-6-6-6"/>,
  arrow:         <path d="M5 12h14M13 6l6 6-6 6"/>,
  print:         <><path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/></>,
  send:          <><path d="M21 3L10 14"/><path d="M21 3l-7 18-4-7-7-4z"/></>,
  check:         <path d="M5 12.5l4.5 4.5L19 7"/>,
  x:             <path d="M6 6l12 12M18 6L6 18"/>,
  alert:         <><path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17.5v.01"/></>,
  inbox:         <><path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1.5 2.5h5L16 13h5"/></>,
  refresh:       <><path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"/><path d="M4 3v5h5M4 13a8 8 0 0 0 14.5 4.5L20 16"/><path d="M20 21v-5h-5"/></>,
  pause:         <path d="M9 5v14M15 5v14"/>,
  play:          <path d="M7 4l13 8-13 8z"/>,
  bolt:          <path d="M13 2L4 14h7l-1 8 9-12h-7z"/>,
};
export function Icon({ name, size }) {
  return <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{PATHS[name]}</svg>;
}

export function ThemeSwitch({ theme, onToggle }) {
  const dark = theme === 'dark';
  return (
    <button type="button" className="theme-switch" role="switch" aria-checked={dark}
      aria-label="Dark mode" title={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={onToggle}>
      <span className="thumb" />
    </button>
  );
}

/* -------------------------------- badges -------------------------------- */
const BADGE = {
  draft: 'b-draft', quotation: 'b-quotation', confirmed: 'b-confirmed', active: 'b-active', closed: 'b-closed',
  paid: 'b-paid', cancelled: 'b-cancelled', overdue: 'b-overdue', paused: 'b-paused',
  running: 'b-active', scheduled: 'b-quotation', expired: 'b-closed', exhausted: 'b-paused', inactive: 'b-closed',
  voided: 'b-cancelled', admin: 'b-quotation', staff: 'b-confirmed', customer: 'b-draft',
};
export function Badge({ status, overdue, text }) {
  const key = overdue ? 'overdue' : status;
  return <span className={`badge ${BADGE[key] || 'b-draft'}`}><i className="dot" />{text || label(key)}</span>;
}

/* ------------------------------- feedback ------------------------------- */
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  const [t, setT] = useState(null);
  const show = useCallback((msg, bad = false) => setT({ msg, bad, k: Date.now() }), []);
  useEffect(() => {
    if (!t) return;
    const id = setTimeout(() => setT(null), t.bad ? 5200 : 3200);
    return () => clearTimeout(id);
  }, [t]);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {t && <div key={t.k} className={`toast ${t.bad ? 'bad' : ''}`} role="status" aria-live="polite">
        <Icon name={t.bad ? 'alert' : 'check'} /><span>{t.msg}</span>
        <button className="toast-x" aria-label="Dismiss" onClick={() => setT(null)}><Icon name="x" /></button>
      </div>}
    </ToastCtx.Provider>
  );
}
export const errText = e => e?.message || 'Something went wrong.';

export function Empty({ icon = 'inbox', title, hint, action }) {
  return (
    <div className="empty">
      <div className="big"><Icon name={icon} /></div>
      <div className="empty-t">{title}</div>
      {hint && <div className="empty-h">{hint}</div>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

export function Loading({ rows = 5 }) {
  return <div className="card-b skeleton" aria-busy="true" aria-label="Loading">
    {Array.from({ length: rows }).map((_, i) => <div key={i} className="sk" style={{ width: `${96 - i * 8}%` }} />)}
  </div>;
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="empty" role="alert">
      <div className="big err"><Icon name="alert" /></div>
      <div className="empty-t">{error.code === 'NETWORK' ? 'Can’t reach the server' : error.status === 404 ? 'Not found' : 'Couldn’t load this'}</div>
      <div className="empty-h">{error.message}</div>
      {onRetry && <button className="btn btn-sm" style={{ marginTop: 16 }} onClick={onRetry}><Icon name="refresh" />Try again</button>}
    </div>
  );
}

/* --------------------------------- data --------------------------------- */
/** Runs fn when deps change. Keeps the previous data while reloading, so lists do not flash. */
export function useAsync(fn, deps = []) {
  const [state, set] = useState({ loading: true, data: null, error: null });
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  useEffect(() => { fnRef.current = fn; });
  useEffect(() => {
    let alive = true;
    set(s => ({ ...s, loading: true, error: null }));
    Promise.resolve().then(() => fnRef.current())
      .then(d => alive && set({ loading: false, data: d, error: null }))
      .catch(e => alive && set({ loading: false, data: null, error: e }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick(t => t + 1), []);
  return { ...state, reload };
}

export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const id = setTimeout(() => setV(value), ms); return () => clearTimeout(id); }, [value, ms]);
  return v;
}

/** Shows error / first-load skeleton / empty state, else renders children(data). */
export function DataView({ r, empty, rows, children }) {
  if (r.error) return <ErrorBox error={r.error} onRetry={r.reload} />;
  if (!r.data) return <Loading rows={rows} />;
  const list = Array.isArray(r.data) ? r.data : r.data.data;
  if (Array.isArray(list) && list.length === 0 && empty) return empty;
  return <div className={r.loading ? 'reloading' : undefined}>{children(r.data)}</div>;
}

export function Pager({ meta, onPage }) {
  if (!meta || meta.total === 0) return null;
  const { page, limit, total, totalPages } = meta;
  const from = (page - 1) * limit + 1, to = Math.min(total, page * limit);
  return (
    <div className="pager">
      <span className="dim">{from}–{to} of {total}</span>
      {totalPages > 1 && <div className="pager-btns">
        <button className="icon-btn sm" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}><Icon name="back" /></button>
        <span className="pager-n">{page} / {totalPages}</span>
        <button className="icon-btn sm" aria-label="Next page" disabled={page >= totalPages} onClick={() => onPage(page + 1)}><Icon name="next" /></button>
      </div>}
    </div>
  );
}

export function SearchBox({ value, onChange, placeholder }) {
  return (
    <label className="search">
      <Icon name="search" />
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      {value && <button type="button" aria-label="Clear search" onClick={() => onChange('')}><Icon name="x" /></button>}
    </label>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="pills" role="tablist">
      {tabs.map(t => <button key={t} role="tab" aria-selected={value === t}
        className={`pill ${value === t ? 'on' : ''}`} onClick={() => onChange(t)}>{label(t)}</button>)}
    </div>
  );
}

/* --------------------------------- forms -------------------------------- */
export function Field({ label: text, hint, error, children, className }) {
  return <div className={`field ${className || ''}`}><label>{text}</label>{children}
    {error ? <span className="err-txt">{error}</span> : hint ? <span className="hint">{hint}</span> : null}</div>;
}

export function Check({ checked, onChange, children }) {
  return (
    <label className="check">
      <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
      <span className="box"><Icon name="check" /></span>{children}
    </label>
  );
}

/** Small form-state helper: values, field errors, a general message and a busy flag. */
export function useForm(initial) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = k => e => {
    const v = e?.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e;
    setValues(s => ({ ...s, [k]: v }));
    setErrors(s => (s[k] ? { ...s, [k]: undefined } : s));
  };
  /** Runs an async save; maps API errors to fields. Returns true on success. */
  const submit = async (validate, save) => {
    const local = validate ? validate(values) : {};
    const bad = Object.fromEntries(Object.entries(local).filter(([, v]) => v));
    setErrors(bad); setMessage(null);
    if (Object.keys(bad).length) return false;
    setBusy(true);
    try { await save(values); setBusy(false); return true; }
    catch (e) {
      const fields = e.fields || {};
      setErrors(fields);
      setMessage(Object.keys(fields).length && e.code === 'VALIDATION_ERROR' ? 'Please fix the highlighted fields.' : errText(e));
      setBusy(false); return false;
    }
  };
  return { values, setValues, set, errors, message, busy, submit };
}

/* -------------------------------- dialogs ------------------------------- */
export function Modal({ title, onClose, children, footer, wide }) {
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });
  useEffect(() => {
    const k = e => e.key === 'Escape' && closeRef.current();
    window.addEventListener('keydown', k);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', k); document.body.style.overflow = prev; };
  }, []);
  return (
    <div className="modal-bg" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className={`modal pop ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-h"><h3>{title}</h3>
          <button className="icon-btn sm" aria-label="Close" onClick={onClose}><Icon name="x" /></button></div>
        <div className="modal-b">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

/** A modal whose body is a form; footer buttons submit it. */
export function FormModal({ title, onClose, onSubmit, busy, message, submitLabel = 'Save', danger, wide, children }) {
  return (
    <Modal title={title} onClose={onClose} wide={wide}
      footer={<>
        <button type="button" className="btn" onClick={onClose}>Cancel</button>
        <button type="submit" form="modal-form" className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} disabled={busy}>
          {busy ? 'Saving…' : submitLabel}</button>
      </>}>
      <form id="modal-form" onSubmit={e => { e.preventDefault(); onSubmit(); }} noValidate>
        {children}
        {message && <div className="form-msg" role="alert"><Icon name="alert" />{message}</div>}
      </form>
    </Modal>
  );
}

/** Confirmation dialog; onConfirm may be async and throw to show an error. */
export function Confirm({ title, body, confirmLabel = 'Confirm', danger, onClose, onConfirm, children }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try { await onConfirm(); } catch (e) { setErr(errText(e)); setBusy(false); }
  };
  return (
    <Modal title={title} onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} disabled={busy} onClick={go}>{busy ? 'Working…' : confirmLabel}</button>
      </>}>
      {body && <p className="muted">{body}</p>}
      {children}
      {err && <div className="form-msg" role="alert"><Icon name="alert" />{err}</div>}
    </Modal>
  );
}
