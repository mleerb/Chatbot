import { useEffect, useRef, useState } from 'react';
import type { Conversation } from '../lib/api';
import Icon from './icon';

type Props = {
  conversation: Conversation;
  busy: boolean;
  onRename: () => void;
  onPin?: () => void;
  onDelete: () => void;
};

export default function Actions({ conversation, busy, onRename, onPin, onDelete }: Props) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = `conversation-actions-${conversation.id}`;

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);

  function choose(action: () => void) {
    setOpen(false);
    trigger.current?.focus();
    action();
  }

  return <div className="conversation-actions" ref={container}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
    onKeyDown={event => {
      if (event.key === 'Escape' && open) {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
    }}>
    <button ref={trigger} className="icon-button" type="button" disabled={busy}
      aria-label={`Options for ${conversation.title}`} title="Conversation options" aria-expanded={open}
      aria-controls={id} onClick={() => setOpen(!open)}><Icon name="more" /></button>
    {open && <div id={id} className="conversation-dropdown" role="group" aria-label={`Actions for ${conversation.title}`}>
      <button type="button" disabled={busy} aria-label={`Rename ${conversation.title}`} onClick={() => choose(onRename)}>
        <Icon name="edit" />Rename
      </button>
      {onPin && <button type="button" disabled={busy} aria-pressed={conversation.pinned}
        aria-label={`${conversation.pinned ? 'Unpin' : 'Pin'} ${conversation.title}`} onClick={() => choose(onPin)}>
        <Icon name="pin" />{conversation.pinned ? 'Unpin' : 'Pin'}
      </button>}
      <button type="button" className="delete-action" disabled={busy} aria-label={`Delete ${conversation.title}`}
        onClick={() => choose(onDelete)}><Icon name="trash" />Delete</button>
    </div>}
  </div>;
}
