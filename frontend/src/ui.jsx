import { useEffect, useState } from 'react';

export const inr = v => '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits:2, maximumFractionDigits:2 });
export const nice = d => d ? new Date(d).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'}) : '—';
export const initials = n => (n||'?').split(' ').map(w=>w[0]).slice(0,2).join('').toUpperCase();

export function Badge({ status, overdue }) {
  const label = overdue ? 'Overdue' : status;
  const cls   = overdue ? 'b-overdue' : `b-${status}`;
  return <span className={`badge ${cls}`}><i className="dot" />{String(label).charAt(0).toUpperCase()+String(label).slice(1)}</span>;
}

export function Stat({ label, value, sub }) {
  return <div className="stat"><div className="lbl">{label}</div><div className="val">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}

const STEPS = ['draft','quotation','confirmed','active','closed'];
export function Flow({ status }) {
  const at = STEPS.indexOf(status);
  return (
    <div className="flow">
      {STEPS.map((s,i) => (
        <span key={s} style={{display:'flex',alignItems:'center'}}>
          {i>0 && <i className={`flow-line ${i<=at?'done':''}`} />}
          <span className={`flow-step ${i<at?'done':''} ${i===at?'now':''}`}>
            <span className="n">{i<at?'✓':i+1}</span>{s.charAt(0).toUpperCase()+s.slice(1)}
          </span>
        </span>
      ))}
    </div>
  );
}

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => {
    const k = e => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="modal fade">
        <div className="card-h"><h3>{title}</h3><span className="spacer" />
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button></div>
        <div className="card-b">{children}</div>
        {footer && <div className="card-h" style={{borderTop:'1px solid var(--border)',borderBottom:'none',justifyContent:'flex-end'}}>{footer}</div>}
      </div>
    </div>
  );
}

export function Toast({ msg, bad, onDone }) {
  useEffect(() => { const t = setTimeout(onDone, 3200); return () => clearTimeout(t); }, [msg, onDone]);
  return <div className={`toast ${bad?'bad':''}`}>{bad?'⚠️  ':'✓  '}{msg}</div>;
}

export function Empty({ icon='∅', title, hint }) {
  return <div className="empty"><div className="big">{icon}</div><div style={{fontWeight:600,color:'var(--text-2)'}}>{title}</div>{hint && <div style={{marginTop:5,fontSize:12.5}}>{hint}</div>}</div>;
}

export function Loading({ rows=5 }) {
  return <div className="card-b">{Array.from({length:rows}).map((_,i)=>(
    <div key={i} style={{height:14,background:'var(--surface-2)',borderRadius:6,marginBottom:11,width:`${95-i*9}%`,animation:'fade .4s'}} />
  ))}</div>;
}

export function useAsync(fn, deps = []) {
  const [state, set] = useState({ loading:true, data:null, error:null });
  useEffect(() => {
    let alive = true;
    set(s => ({ ...s, loading:true }));
    Promise.resolve(fn())
      .then(d => alive && set({ loading:false, data:d, error:null }))
      .catch(e => alive && set({ loading:false, data:null, error:e }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function Field({ label, hint, error, children }) {
  return <div className="field"><label>{label}</label>{children}
    {error ? <span className="err-txt">{error}</span> : hint ? <span className="hint">{hint}</span> : null}</div>;
}
