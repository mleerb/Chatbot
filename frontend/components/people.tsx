import { useState, type FormEvent } from 'react';
import type { User } from '../lib/api';
import Icon from './icon';

type Props = {
  users: User[];
  selected: number | null;
  busy: boolean;
  onSelect: (id: number) => Promise<void>;
  onCreate: (name: string) => Promise<boolean>;
};

export default function People({ users, selected, busy, onSelect, onCreate }: Props) {
  const [name, setName] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await onCreate(name.trim())) setName('');
  }
  const user = users.find(user => user.id === selected);
  return <section className="people" aria-label="Chat users">
    <label htmlFor="user-select">User</label>
    <select id="user-select" aria-label="Select user" value={selected || ''} disabled={busy}
      onChange={event => { if (event.target.value) void onSelect(Number(event.target.value)); }}>
      <option value="">Select a user</option>
      {users.map(user => <option key={user.id} value={user.id}>{user.name}</option>)}
    </select>
    <details className="add-user">
      <summary>Add user</summary>
      <form onSubmit={submit}>
        <label htmlFor="user-name">New user name</label>
        <input id="user-name" maxLength={100} placeholder="Enter a name" required disabled={busy}
          value={name} onChange={event => setName(event.target.value)} />
        <button className="primary-button" type="submit" disabled={busy || !name.trim()}>Add user</button>
      </form>
    </details>
    <div className="sidebar-conversation">
      <h2>Conversation</h2>
      {user ? <div className="current-conversation" aria-current="page"><Icon name="chat" />
        <span>{user.name}&apos;s chat</span><span className="current-dot" aria-hidden="true" />
      </div> : <p>Select or add a user to open a conversation.</p>}
    </div>
  </section>;
}
