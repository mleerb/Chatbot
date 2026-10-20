'use client';

import { useEffect, useRef, useState } from 'react';
import { errorMessage, request, type Files, type Message, type Reply, type State, type User, type Conversation } from '../lib/api';
import Composer from './composer';
import Brand from './brand';
import Conversations from './conversations';
import { FileShelf } from './files';
import Icon from './icon';
import Messages from './messages';
import Auth from './auth';
import { guestToken, setGuestToken } from '../lib/guest';

const emptyFiles: Files = { uploads: [], generated_files: [] };

export default function Chat() {
  const [account, setAccount] = useState<User | null>(null);
  const [guest, setGuest] = useState(false);
  const ready = !!account || guest;
  const [selected, setSelected] = useState<number | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [files, setFiles] = useState<Files>(emptyFiles);
  const [busy, setBusy] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const working = useRef(true);
  const initialized = useRef(false);
  const sidebar = useRef<HTMLDialogElement>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)');
    function update() {
      const panel = sidebar.current;
      if (!panel) return;
      panel.close();
      if (!media.matches) panel.show();
      setSidebarOpen(false);
    }
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [account, guest]);

  useEffect(() => {
    const area = conversation.current;
    if (area) area.scrollTop = area.scrollHeight;
  }, [messages, files, pending]);

  function closeSidebar() {
    if (window.matchMedia('(max-width: 760px)').matches) sidebar.current?.close();
    setSidebarOpen(false);
  }

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
    if (initialized.current) return;
    initialized.current = true;
    void (async () => {
      try {
        let result: { user: User | null; guest: boolean };
        try { result = await request('/api/auth/me'); }
        catch (error) {
          if (!guestToken()) throw error;
          setGuestToken(null);
          result = await request('/api/auth/me');
        }
        setAccount(result.user);
        setGuest(result.guest);
        if (result.user || result.guest) applyState(await request<State>('/api/state'));
      } catch (error) { setError(errorMessage(error)); }
      finally { working.current = false; setBusy(false); }
    })();
  }, []);

  useEffect(() => {
    function leaving(event: PageTransitionEvent) {
      const token = guestToken();
      if (!token || event.persisted) return;
      void fetch('/api/auth/guest/close', {
        method: 'POST', keepalive: true, credentials: 'same-origin', headers: { 'x-guest-session': token },
      }).catch(() => {});
    }
    function returning() {
      if (guestToken()) void request('/api/auth/me').catch(() => {});
    }
    window.addEventListener('pagehide', leaving);
    window.addEventListener('pageshow', returning);
    return () => {
      window.removeEventListener('pagehide', leaving);
      window.removeEventListener('pageshow', returning);
    };
  }, []);

  function start(): boolean {
    if (working.current) return false;
    working.current = true;
    setBusy(true);
    setError('');
    return true;
  }
  function finish() {
    working.current = false;
    setBusy(false);
  }
  function applyState(state: State) {
    setSelected(state.user_id);
    setActive(state.conversation_id);
    setConversations(state.conversations);
    setMessages(state.messages);
    setFiles(state);
  }
  async function refreshFiles() {
    applyState(await request<State>('/api/state'));
  }
  async function conversationAction(path: string, method: string, changes?: { title?: string; pinned?: boolean }): Promise<boolean> {
    if (!start()) return false;
    try {
      await request(path, { method, ...(changes ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) } : {}) });
      await refreshFiles();
      setWarning('');
      if (method === 'POST') closeSidebar();
      return true;
    } catch (error) { setError(errorMessage(error)); return false; }
    finally { finish(); }
  }
  async function loggedIn(user: User) {
    setGuestToken(null);
    await refreshFiles();
    setAccount(user);
    setGuest(false);
    setError('');
  }
  async function continueAsGuest() {
    const result = await request<{ guest_token: string }>('/api/auth/guest', { method: 'POST' });
    setGuestToken(result.guest_token);
    await refreshFiles();
    setGuest(true);
    setError('');
  }
  async function logout() {
    if (!start()) return;
    try {
      await request('/api/auth/logout', { method: 'POST' });
      setGuestToken(null);
      closeSidebar();
      setAccount(null);
      setGuest(false);
      setSelected(null);
      setConversations([]);
      setActive(null);
      setMessages([]);
      setFiles(emptyFiles);
      setWarning('');
    } catch (error) { setError(errorMessage(error)); }
    finally { finish(); }
  }
  async function send(message: string) {
    if (!ready || !start()) return;
    setMessages(items => [...items, { role: 'user', content: message }]);
    setPending(true);
    try {
      const result = await request<Reply>('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }),
      });
      setMessages(items => [...items, { role: 'assistant', content: result.display_answer ?? result.answer, sources: result.sources }]);
      setFiles(result);
    } catch (error) { setError(errorMessage(error)); }
    finally {
      setPending(false);
      try { await refreshFiles(); } catch (error) { setError(errorMessage(error)); }
      finish();
    }
  }
  async function upload(items: File[]) {
    if (!ready || !start()) return;
    setWarning('');
    const failures: string[] = [];
    try {
      for (const file of items) {
        const body = new FormData();
        body.append('file', file);
        try { await request('/api/document', { method: 'POST', body }); }
        catch (error) { failures.push(`${file.name}: ${errorMessage(error)}`); }
      }
      await refreshFiles();
      setWarning(failures.join('\n'));
    } catch (error) { setWarning(errorMessage(error)); }
    finally { finish(); }
  }
  async function remove(id?: string) {
    if (!start()) return;
    setWarning('');
    try {
      await request(`/api/document${id ? `?file_id=${encodeURIComponent(id)}` : ''}`, { method: 'DELETE' });
      await refreshFiles();
    } catch (error) { setError(errorMessage(error)); }
    finally { finish(); }
  }
  function toggleTheme() {
    const next = theme === 'light' ? 'dark' : 'light';
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('aster-theme', next); } catch {}
  }

  const activeConversation = conversations.find(chat => chat.id === active);

  if (!ready) return <main className="app auth-app" data-theme={theme}>
    <button type="button" className="auth-theme icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}><Icon name={theme === 'light' ? 'moon' : 'sun'} /></button>
    {busy ? <p className="auth-loading" role="status">Opening Aster…</p> : <Auth onSuccess={loggedIn} onGuest={continueAsGuest} />}
    {error && <p className="auth-error error" role="alert">{error}</p>}
  </main>;

  return <main className="app" data-app data-theme={theme}>
    <dialog ref={sidebar} id="sidebar" className="sidebar" aria-label="Workspace sidebar" onClose={() => setSidebarOpen(false)}>
      <div className="sidebar-brand"><span className="brand-mark" aria-hidden="true">✳</span><Brand />
        <button type="button" className="icon-button close-sidebar" aria-label="Close sidebar" onClick={closeSidebar}><Icon name="close" /></button>
      </div>
      <div className="account-info"><span className="account-avatar" aria-hidden="true">{account?.name.slice(0, 1) ?? 'G'}</span><div><strong>{account?.name ?? 'Guest'}</strong><span>{guest ? 'This session only' : account?.email}</span></div></div>
      {guest && <div className="guest-notice"><strong>Temporary chat</strong><p>Nothing is saved to your account. Stays while this tab is open. Closing the tab or restarting the server ends it.</p><button type="button" className="primary-button" disabled={busy} onClick={() => { if (window.confirm('End this guest chat? Messages and files will be cleared.')) void conversationAction('/api/conversations', 'POST'); }}>New temporary chat</button></div>}
      {selected && !guest && <Conversations key={selected} conversations={conversations} selected={active} busy={busy}
        onCreate={async () => { await conversationAction('/api/conversations', 'POST'); }}
        onSelect={async id => { await conversationAction(`/api/conversations/${id}/select`, 'POST'); }}
        onUpdate={(id, changes) => conversationAction(`/api/conversations/${id}`, 'PATCH', changes)}
        onDelete={id => conversationAction(`/api/conversations/${id}`, 'DELETE')} />}
      <div className="sidebar-footer">
        <button className="theme-toggle" type="button" onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}>
          <Icon name={theme === 'light' ? 'moon' : 'sun'} />{theme === 'light' ? 'Dark mode' : 'Light mode'}
        </button>
        <button className="theme-toggle" type="button" disabled={busy} onClick={() => { if (!guest || window.confirm('End this guest session? Messages and files will be cleared before you log in.')) void logout(); }}>{guest ? 'End guest session / Log in' : 'Log out'}</button>
        <a className="workspace-home" href="/">Back to Aster</a>
        <p>{guest ? 'Guest history is not saved.' : 'History is saved. Files are temporary.'}</p>
      </div>
    </dialog>
    <section className="chat-panel" aria-label="Conversation">
      <header className="chat-header">
        <button type="button" className="icon-button open-sidebar" aria-label="Open sidebar" aria-controls="sidebar" aria-expanded={sidebarOpen}
          onClick={() => { sidebar.current?.showModal(); setSidebarOpen(true); }}><Icon name="menu" /></button>
        <div><h2>{activeConversation?.title ?? (guest ? 'Temporary chat' : 'Conversation')}</h2><p>{guest ? 'Guest mode · session-only history' : 'A little clarity, one message at a time.'}</p></div>
        {!!files.uploads.length && <span className="file-count"><Icon name="file" />{files.uploads.length} attached</span>}
      </header>
      <div ref={conversation} className="conversation-scroll">
        <Messages messages={messages} pending={pending} selected={ready}>
          <FileShelf files={files} busy={busy} onRemove={remove} />
        </Messages>
      </div>
      <div className="feedback" aria-live="polite">
        <p className="error" role="alert" hidden={!error}>{error}</p>
        <p className="error" role="alert" hidden={!warning}>{warning}</p>
        <p className="operation-status" role="status" hidden={!busy || pending}>{initialized.current ? 'Updating workspace…' : 'Loading workspace…'}</p>
      </div>
      <Composer disabled={busy || !ready} selected={ready} uploads={files.uploads} onSend={send} onUpload={upload} onRemove={remove} />
    </section>
  </main>;
}
