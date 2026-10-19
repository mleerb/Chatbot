import type { ReactNode } from 'react';
import { safeUrl, type Message } from '../lib/api';
import Icon from './icon';

export default function Messages({ messages, pending, selected, children }: {
  messages: Message[];
  pending: boolean;
  selected: boolean;
  children: ReactNode;
}) {
  return <div className="conversation-content">
    {!messages.length && !pending && <section className="empty-state">
      <span className="empty-symbol"><Icon name="chat" /></span>
      <h1>How can I help?</h1>
      <p>{selected ? 'Ask a question or attach files to get started.' : 'Select a user in the sidebar, then ask a question or attach files.'}</p>
    </section>}
    <div className="messages" role="log" aria-live="polite" aria-label="Chat messages" aria-busy={pending}>
      {messages.map((message, index) => <article className={`message ${message.role}`} key={index}>
        <span className="message-author">{message.role === 'user' ? 'You' : 'AGENTslop'}</span>
        <div className="message-body">{message.content}</div>
        {!!message.sources?.length && <div className="sources">
          <span>Sources</span>
          {message.sources.map((source, index) => {
            const url = safeUrl(source.url);
            return url ? <a key={index} href={url} target="_blank" rel="noopener noreferrer">{source.title || url}</a> : null;
          })}
        </div>}
      </article>)}
      {pending && <article className="message assistant"><span className="message-author">AGENTslop</span><p className="thinking">Thinking…</p></article>}
    </div>
    {children}
  </div>;
}
