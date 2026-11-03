import { useCallback, useState, type ReactNode } from 'react';
import { type DocumentSource, type Source, type Message, type Rating, type Upload } from '../lib/api';
import { draftText } from '../lib/citations';
import SourceViewer, { SourceList } from './sources';
import AnswerMenu from './answer-menu';
import Brand from './brand';
import { GeneratedImages, MessageFiles } from './files';
import Icon from './icon';
import Logo from './logo';
import Markdown from './markdown';

export type Draft = { text: string; step: string };

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch { window.alert('Could not copy. Select the text and copy it instead.'); }
  }
  return <button type="button" className="icon-button" aria-label={copied ? 'Copied' : label} title={copied ? 'Copied' : label}
    onClick={() => void copy()}><Icon name={copied ? 'check' : 'copy'} /></button>;
}

function Editor({ initial, onSave, onCancel }: { initial: string; onSave: (text: string) => void; onCancel: () => void }) {
  const [text, setText] = useState(initial);
  return <form className="message-editor" onSubmit={event => { event.preventDefault(); if (text.trim()) onSave(text.trim()); }}
    onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); onCancel(); } }}>
    <textarea aria-label="Message text" value={text} maxLength={10000} rows={3} autoFocus onChange={event => setText(event.target.value)} />
    <p>Saving replaces this message and every message after it.</p>
    <div><button type="button" className="guest-button" onClick={onCancel}>Cancel</button>
      <button type="submit" className="primary-button" disabled={!text.trim()}>Save</button></div>
  </form>;
}

export default function Messages({ messages, uploads, pending, draft, selected, locked, canChat, onEdit, onRate, children }: {
  messages: Message[];
  uploads: Upload[];
  pending: boolean;
  draft: Draft | null;
  selected: boolean;
  locked: boolean;
  canChat: boolean;
  onEdit: (index: number, text: string) => void;
  onRate: (index: number, rating: Rating) => void;
  children: ReactNode;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [source, setSource] = useState<DocumentSource | null>(null);
  const openSource = useCallback((item: Source) => { if (item.kind === 'document') setSource(item); }, []);
  const last = messages.length - 1;
  return <div className="conversation-content">
    {!messages.length && !pending && <section className="empty-state">
      <span className="empty-mark"><Logo className="logo-intro" /></span>
      <div className="empty-brand"><Brand /></div>
      <h1>How can I help?</h1>
      <p>{selected ? 'Explore an idea, write something, or plan your next step. Start with a question.' : 'Log in to start your conversation.'}</p>
    </section>}
    <div className="messages" role="log" aria-live="polite" aria-label="Chat messages" aria-busy={pending}>
      {messages.map((message, index) => <article className={`message ${message.role}`} key={index}>
        <span className="message-author">{message.role === 'assistant' && <span className="message-avatar"><Logo /></span>}{message.role === 'user' ? 'You' : 'Aster'}
          {message.role === 'assistant' && <AnswerMenu content={message.content} index={index} />}</span>
        {message.role === 'user' && !!message.attachments?.length && <MessageFiles attachments={message.attachments} uploads={uploads} />}
        {message.role === 'assistant' ? <Markdown content={message.content} sources={message.sources}
          onSource={openSource} />
          : editing === index ? <Editor initial={message.content} onCancel={() => setEditing(null)}
            onSave={text => { setEditing(null); onEdit(index, text); }} />
          : <div className="message-body">{message.content}</div>}
        {message.role === 'assistant' && message.stopped && <p className="stopped-note">{message.content ? 'Stopped' : 'Stopped before answering'}</p>}
        {message.role === 'assistant' && !!message.attachments?.length && <GeneratedImages images={message.attachments} />}
        {!!message.sources?.length && <SourceList sources={message.sources} onOpen={setSource} />}
        {editing !== index && <div className="message-actions" role="group" aria-label={message.role === 'user' ? 'Message actions' : 'Answer actions'}>
          {!!message.content && <CopyButton text={message.content} label={message.role === 'user' ? 'Copy message' : 'Copy answer'} />}
          {message.role === 'user' && <button type="button" className="icon-button" aria-label="Edit message" title="Edit message"
            disabled={locked || !canChat} onClick={() => setEditing(index)}><Icon name="edit" /></button>}
          {message.role === 'assistant' && <>
            {(['up', 'down'] as const).map(rating => <button key={rating} type="button" className="icon-button" disabled={locked}
              aria-label={rating === 'up' ? 'Good answer' : 'Bad answer'} title={rating === 'up' ? 'Good answer' : 'Bad answer'}
              aria-pressed={message.rating === rating} onClick={() => onRate(index, message.rating === rating ? null : rating)}>
              <Icon name={rating} /></button>)}
            {index === last && messages[index - 1]?.role === 'user' && <button type="button" className="icon-button" aria-label="Regenerate answer"
              title="Regenerate answer" disabled={locked || !canChat} onClick={() => onEdit(index - 1, messages[index - 1].content)}><Icon name="retry" /></button>}
          </>}
        </div>}
      </article>)}
      {pending && <article className="message assistant pending"><span className="message-author"><span className="message-avatar"><Logo thinking /></span>Aster</span>
        {draft?.text ? <Markdown content={draftText(draft.text)} /> : <p className="thinking" role="status">{draft?.step ? `${draft.step}…` : 'Thinking…'}</p>}
      </article>}
    </div>
    {children}
    {source && <SourceViewer source={source} onClose={() => setSource(null)} />}
  </div>;
}
