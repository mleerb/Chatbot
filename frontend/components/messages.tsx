import type { ReactNode } from 'react';
import { safeUrl, type Message } from '../lib/api';
import Brand from './brand';

export default function Messages({ messages, pending, selected, children }: {
  messages: Message[];
  pending: boolean;
  selected: boolean;
  children: ReactNode;
}) {
  return <div className="conversation-content">
    {!messages.length && !pending && <section className="empty-state">
      <div className="empty-brand"><Brand /></div>
      <h1>How can I help?</h1>
      <p>{selected ? 'Explore an idea, write something, or plan your next step. Start with a question.' : 'Log in to start your conversation.'}</p>
    </section>}
    <div className="messages" role="log" aria-live="polite" aria-label="Chat messages" aria-busy={pending}>
      {messages.map((message, index) => <article className={`message ${message.role}`} key={index}>
        <span className="message-author">{message.role === 'assistant' && <span className="message-avatar" aria-hidden="true">✳</span>}{message.role === 'user' ? 'You' : 'Aster'}</span>
        <div className="message-body">{message.content}</div>
        {!!message.sources?.length && <div className="sources">
          <span>Sources</span>
          {message.sources.map((source, index) => {
            const url = safeUrl(source.url);
            return url ? <a key={index} href={url} target="_blank" rel="noopener noreferrer">{source.title || url}</a> : null;
          })}
        </div>}
      </article>)}
      {pending && <article className="message assistant"><span className="message-author"><span className="message-avatar" aria-hidden="true">✳</span>Aster</span><p className="thinking">Thinking…</p></article>}
    </div>
    {children}
  </div>;
}
