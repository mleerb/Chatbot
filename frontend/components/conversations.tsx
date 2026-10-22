import { useState, type FormEvent } from 'react';
import type { Conversation } from '../lib/api';
import Icon from './icon';
import Actions from './actions';

type Props = {
  conversations: Conversation[];
  selected: number | null;
  busy: boolean;
  canPin: boolean;
  onCreate: () => Promise<void>;
  onSelect: (id: number) => Promise<void>;
  onUpdate: (id: number, changes: { title?: string; pinned?: boolean }) => Promise<boolean>;
  onDelete: (id: number) => Promise<boolean>;
};

export default function Conversations({ conversations, selected, busy, canPin, onCreate, onSelect, onUpdate, onDelete }: Props) {
  const [editing, setEditing] = useState<{ id: number; title: string } | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  async function rename(event: FormEvent) {
    event.preventDefault();
    if (editing && await onUpdate(editing.id, { title: editing.title.trim() })) setEditing(null);
  }

  return <section className="sidebar-conversation" aria-label="Conversations">
    <div className="conversation-heading"><h2>Conversations</h2>
      <button className="text-button" type="button" disabled={busy} onClick={() => void onCreate()}>+ New conversation</button>
    </div>
    {!conversations.length && <p>No conversations yet. Start a new one.</p>}
    <ul className="conversation-list">
      {conversations.map(chat => <li key={chat.id} className="conversation-item" data-selected={chat.id === selected}>
        <div className="conversation-row"><button className="conversation-link" type="button" disabled={busy}
          aria-current={chat.id === selected ? 'page' : undefined} onClick={() => void onSelect(chat.id)}>
          <Icon name={chat.pinned ? 'pin' : 'chat'} /><span>{chat.title}</span>
          {chat.pinned && <span className="sr-only"> (Pinned)</span>}
        </button>
        <Actions conversation={chat} busy={busy}
          onPin={canPin ? () => void onUpdate(chat.id, { pinned: !chat.pinned }) : undefined}
          onRename={() => { setEditing({ id: chat.id, title: chat.title }); setDeleting(null); }}
          onDelete={() => { setDeleting(chat.id); setEditing(null); }} />
        </div>
        {editing?.id === chat.id && <form className="conversation-form" onSubmit={rename}>
          <label htmlFor={`title-${chat.id}`}>Conversation title</label>
          <input id={`title-${chat.id}`} value={editing.title} required maxLength={100} autoFocus disabled={busy}
            onChange={event => setEditing({ ...editing, title: event.target.value })} />
          <div className="conversation-form-actions">
            <button type="submit" className="primary-button" disabled={busy || !editing.title.trim()}>Save name</button>
            <button type="button" className="text-button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </form>}
        {deleting === chat.id && <div className="conversation-form" role="group" aria-label="Confirm deletion">
          <p>Delete “{chat.title}” and all its messages? This cannot be undone.</p>
          <div className="conversation-form-actions">
            <button className="danger-button" type="button" disabled={busy}
              onClick={async () => { if (await onDelete(chat.id)) setDeleting(null); }}>Delete conversation</button>
            <button className="text-button" type="button" disabled={busy} onClick={() => setDeleting(null)}>Cancel</button>
          </div>
        </div>}
      </li>)}
    </ul>
  </section>;
}
