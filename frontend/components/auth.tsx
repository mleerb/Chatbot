'use client';

import { useState, type FormEvent } from 'react';
import { errorMessage, request, type User } from '../lib/api';
import Brand from './brand';
import Logo from './logo';

export default function Auth({ onSuccess, onGuest }: { onSuccess: (user: User) => Promise<void>; onGuest: () => Promise<void> }) {
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      const result = await request<{ user: User }>(`/api/auth/${register ? 'register' : 'login'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: form.get('email'), password: form.get('password'), ...(register ? { name: form.get('name') } : {}) }),
      });
      await onSuccess(result.user);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  async function continueAsGuest() {
    if (busy) return;
    setBusy(true);
    setError('');
    try { await onGuest(); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <section className="auth-screen" aria-labelledby="auth-title">
    <a href="/" className="auth-home"><Brand /></a>
    <div className="auth-card">
      <span className="auth-symbol"><Logo className="logo-intro" /></span>
      <h1 id="auth-title">{register ? 'A space of your own.' : 'Welcome back.'}</h1>
      <p>{register ? 'Create an account to start with Aster.' : 'Log in to pick up your conversation.'}</p>
      <form onSubmit={submit}>
        {register && <label>Your name<input name="name" autoComplete="name" maxLength={100} required disabled={busy} /></label>}
        <label>Email<input name="email" type="email" autoComplete="email" maxLength={254} required disabled={busy} /></label>
        <label>Password<input name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} minLength={register ? 12 : 1} maxLength={128} required disabled={busy} /></label>
        {register && <span className="auth-hint">Use at least 12 characters. Email verification and password recovery are not available yet.</span>}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary-button" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Log in'}</button>
      </form>
      <button type="button" className="guest-button" disabled={busy} onClick={continueAsGuest}>Continue as guest</button>
      <p className="auth-hint guest-hint">No account needed. Guest chats are temporary and aren’t saved to your account.</p>
      <button type="button" className="auth-switch" disabled={busy} onClick={() => { setRegister(!register); setError(''); }}>{register ? 'Already have an account? Log in' : 'New here? Create an account'}</button>
    </div>
    <p className="auth-footnote">Log in to keep your history, or try a temporary guest chat.<br />AI answers need review.</p>
  </section>;
}
