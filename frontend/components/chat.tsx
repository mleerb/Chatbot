'use client';

import { useEffect, useRef, useState } from 'react';
import { errorMessage, request, type Files, type Message, type Reply, type State, type User, type Conversation } from '../lib/api';
import Composer from './composer';
import Brand from './brand';
import Conversations from './conversations';
import { FileShelf } from './files';
import Icon from './icon';
import Messages from './messages';
import People from './people';

const emptyFiles: Files = { uploads: [], generated_files: [] };

export default function Chat() {
  const [users, setUsers] = useState<User[]>([]);
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
  }, []);

  useEffect(() => {
    const area = conversation.current;
    if (area) area.scrollTop = area.scrollHeight;
  }, [messages, files, pending]);

  function closeSidebar() {
    if (window.matchMedia('(max-width: 760px)').matches) sidebar.current?.close();
    setSidebarOpen(false);
  }

  useEffect(() => {
    try { setTheme(localStorage.getItem('chat-theme') === 'dark' ? 'dark' : 'light'); } catch {}
    if (initialized.current) return;
    initialized.current = true;
    void (async () => {
      try {
        const state = await request<State>('/api/state');
        applyState(state);
        setUsers(await request<User[]>('/api/users'));
      } catch (error) { setError(errorMessage(error)); }
      finally { working.current = false; setBusy(false); }
    })();
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
  async function select(id: number) {
    await request(`/api/users/${id}/select`, { method: 'POST' });
    setSelected(id);
    closeSidebar();
    setMessages([]);
    setFiles(emptyFiles);
    setWarning('');
    await refreshFiles();
  }
  async function selectUser(id: number) {
    if (!start()) return;
    try { await select(id); }
    catch (error) { setError(errorMessage(error)); }
    finally { finish(); }
  }
  async function createUser(name: string): Promise<boolean> {
    if (!name || !start()) return false;
    try {
      const user = await request<User>('/api/users', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
      });
      setUsers(await request<User[]>('/api/users'));
      await select(user.id);
      return true;
    } catch (error) { setError(errorMessage(error)); return false; }
    finally { finish(); }
  }
  async function send(message: string) {
    if (!selected || !start()) return;
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
    if (!selected || !start()) return;
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
    try { localStorage.setItem('chat-theme', next); } catch {}
  }

  const activeConversation = conversations.find(chat => chat.id === active);

  return <main className="app" data-app data-theme={theme}>
    <dialog ref={sidebar} id="sidebar" className="sidebar" aria-label="Workspace sidebar" onClose={() => setSidebarOpen(false)}>
      <div className="sidebar-brand"><span className="brand-mark" aria-hidden="true">a</span><Brand />
        <button type="button" className="icon-button close-sidebar" aria-label="Close sidebar" onClick={closeSidebar}><Icon name="close" /></button>
      </div>
      <People users={users} selected={selected} busy={busy} onSelect={selectUser} onCreate={createUser} />
      {selected && <Conversations key={selected} conversations={conversations} selected={active} busy={busy}
        onCreate={async () => { await conversationAction('/api/conversations', 'POST'); }}
        onSelect={async id => { await conversationAction(`/api/conversations/${id}/select`, 'POST'); }}
        onUpdate={(id, changes) => conversationAction(`/api/conversations/${id}`, 'PATCH', changes)}
        onDelete={id => conversationAction(`/api/conversations/${id}`, 'DELETE')} />}
      <div className="sidebar-footer">
        <button className="theme-toggle" type="button" onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}>
          <Icon name={theme === 'light' ? 'moon' : 'sun'} />{theme === 'light' ? 'Dark mode' : 'Light mode'}
        </button>
        <p>Files stay in this session.<br />Chat history is saved.</p>
      </div>
    </dialog>
    <section className="chat-panel" aria-label="Conversation">
      <header className="chat-header">
        <button type="button" className="icon-button open-sidebar" aria-label="Open sidebar" aria-controls="sidebar" aria-expanded={sidebarOpen}
          onClick={() => { sidebar.current?.showModal(); setSidebarOpen(true); }}><Icon name="menu" /></button>
        <div><h2>{activeConversation?.title ?? 'Conversation'}</h2><p>Ask questions, explore ideas, and get things done.</p></div>
        {!!files.uploads.length && <span className="file-count"><Icon name="file" />{files.uploads.length} attached</span>}
      </header>
      <div ref={conversation} className="conversation-scroll">
        <Messages messages={messages} pending={pending} selected={!!selected}>
          <FileShelf files={files} busy={busy} onRemove={remove} />
        </Messages>
      </div>
      <div className="feedback" aria-live="polite">
        <p className="error" role="alert" hidden={!error}>{error}</p>
        <p className="error" role="alert" hidden={!warning}>{warning}</p>
        <p className="operation-status" role="status" hidden={!busy || pending}>{initialized.current ? 'Updating workspace…' : 'Loading workspace…'}</p>
      </div>
      <Composer disabled={busy || !selected} selected={!!selected} uploads={files.uploads} onSend={send} onUpload={upload} onRemove={remove} />
    </section>
  </main>;
}
