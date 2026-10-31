import { useState } from 'react';
import { api } from '../api';
import { Field, Icon, useForm, errText } from '../ui';

const pwRule = p => p.length > 8 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /[^A-Za-z0-9]/.test(p);
const emailOk = e => /^\S+@\S+\.\S+$/.test(e);

function SignIn({ onLogin, go }) {
  const f = useForm({ email: '', password: '' });
  const submit = e => {
    e.preventDefault();
    f.submit(
      v => ({ email: !emailOk(v.email) && 'Enter your email address.', password: !v.password && 'Enter your password.' }),
      async v => { const r = await api.login(v.email.trim(), v.password); onLogin(r.user); },
    );
  };
  return (
    <form className="auth-box" onSubmit={submit} noValidate>
      <h2>Welcome back</h2>
      <p className="dim auth-lead">Sign in to manage plans, subscriptions and billing.</p>
      <Field label="Email" error={f.errors.email}>
        <input className={`input ${f.errors.email ? 'err' : ''}`} type="email" autoComplete="email" value={f.values.email} onChange={f.set('email')} autoFocus /></Field>
      <Field label="Password" error={f.errors.password}>
        <input className={`input ${f.errors.password ? 'err' : ''}`} type="password" autoComplete="current-password" value={f.values.password} onChange={f.set('password')} /></Field>
      <div className="auth-row"><button type="button" className="link" onClick={() => go('forgot')}>Forgot password?</button></div>
      {f.message && <div className="form-msg" role="alert"><Icon name="alert" />{f.message}</div>}
      <button className="btn btn-primary btn-block" disabled={f.busy}>{f.busy ? 'Signing in…' : 'Sign in'}</button>
      <p className="auth-switch">New customer? <button type="button" className="link" onClick={() => go('signup')}>Create an account</button></p>
    </form>
  );
}

function SignUp({ onLogin, go }) {
  const f = useForm({ name: '', email: '', company: '', phone: '', password: '' });
  const v = f.values;
  const submit = e => {
    e.preventDefault();
    f.submit(
      x => ({
        name: !x.name.trim() && 'Enter your name.',
        email: !emailOk(x.email) && 'Enter a valid email address.',
        password: !pwRule(x.password) && 'Use more than 8 characters with an uppercase letter, a lowercase letter and a symbol.',
      }),
      async x => {
        const body = { name: x.name.trim(), email: x.email.trim(), password: x.password };
        if (x.company.trim()) body.company = x.company.trim();
        if (x.phone.trim()) body.phone = x.phone.trim();
        const r = await api.signup(body); onLogin(r.user);
      },
    );
  };
  return (
    <form className="auth-box" onSubmit={submit} noValidate>
      <h2>Create your account</h2>
      <p className="dim auth-lead">Customers can request subscriptions and see their invoices.</p>
      <Field label="Full name" error={f.errors.name}>
        <input className={`input ${f.errors.name ? 'err' : ''}`} autoComplete="name" value={v.name} onChange={f.set('name')} autoFocus /></Field>
      <Field label="Email" error={f.errors.email}>
        <input className={`input ${f.errors.email ? 'err' : ''}`} type="email" autoComplete="email" value={v.email} onChange={f.set('email')} /></Field>
      <div className="row">
        <Field label="Company" hint="Optional"><input className="input" autoComplete="organization" value={v.company} onChange={f.set('company')} /></Field>
        <Field label="Phone" hint="Optional"><input className="input" autoComplete="tel" value={v.phone} onChange={f.set('phone')} /></Field>
      </div>
      <Field label="Password" error={f.errors.password}
        hint={v.password && pwRule(v.password) ? '✓ Strong enough' : 'More than 8 characters, with A–Z, a–z and a symbol.'}>
        <input className={`input ${f.errors.password ? 'err' : ''}`} type="password" autoComplete="new-password" value={v.password} onChange={f.set('password')} /></Field>
      {f.message && <div className="form-msg" role="alert"><Icon name="alert" />{f.message}</div>}
      <button className="btn btn-primary btn-block" disabled={f.busy}>{f.busy ? 'Creating account…' : 'Create account'}</button>
      <p className="auth-switch">Already have an account? <button type="button" className="link" onClick={() => go('signin')}>Sign in</button></p>
    </form>
  );
}

function Forgot({ go }) {
  const [email, setEmail] = useState('');
  const [state, setState] = useState({ busy: false, sent: false, err: null });
  const submit = async e => {
    e.preventDefault();
    if (!emailOk(email)) return setState({ busy: false, sent: false, err: 'Enter a valid email address.' });
    setState({ busy: true, sent: false, err: null });
    try { await api.forgotPassword(email.trim()); setState({ busy: false, sent: true, err: null }); }
    catch (x) { setState({ busy: false, sent: false, err: errText(x) }); }
  };
  return (
    <form className="auth-box" onSubmit={submit} noValidate>
      <h2>Reset your password</h2>
      <p className="dim auth-lead">We’ll email you a reset link. It stays valid for 30 minutes.</p>
      {state.sent
        ? <div className="form-ok"><Icon name="check" />If an account exists for {email}, a reset link is on its way.</div>
        : <>
          <Field label="Email" error={state.err}>
            <input className={`input ${state.err ? 'err' : ''}`} type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus /></Field>
          <button className="btn btn-primary btn-block" disabled={state.busy}>{state.busy ? 'Sending…' : 'Send reset link'}</button>
        </>}
      <p className="auth-switch"><button type="button" className="link" onClick={() => go('signin')}>← Back to sign in</button></p>
    </form>
  );
}

export default function Login({ onLogin, expired }) {
  const [view, setView] = useState('signin');
  return (
    <div className="auth">
      <div className="auth-art">
        <div className="brand" style={{ padding: 0, color: '#fff' }}><span className="brand-mark">B</span> Brightloop</div>
        <h2>Run plans, subscriptions<br />and recurring billing<br />in one place.</h2>
        <p>The digital backbone for a business that earns its money every month — not just once.</p>
        <div className="auth-feats">
          {['Automatic invoicing on billing day', 'Taxes and discounts applied for you', 'Revenue and overdue, answered instantly'].map(t =>
            <div className="auth-feat" key={t}><span className="tick"><Icon name="check" /></span>{t}</div>)}
        </div>
      </div>
      <div className="auth-form">
        <div style={{ width: '100%', maxWidth: 360 }}>
          <div className="brand auth-mobile-brand"><span className="brand-mark">B</span> Brightloop</div>
          {expired && view === 'signin' && <div className="form-msg" role="status" style={{ marginBottom: 18 }}><Icon name="alert" />Your session expired. Please sign in again.</div>}
          {view === 'signin' && <SignIn onLogin={onLogin} go={setView} />}
          {view === 'signup' && <SignUp onLogin={onLogin} go={setView} />}
          {view === 'forgot' && <Forgot go={setView} />}
        </div>
      </div>
    </div>
  );
}
