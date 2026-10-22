import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import type { Upload } from '../lib/api';
import { AttachedFiles } from './files';
import Icon from './icon';

type Props = {
  disabled: boolean;
  selected: boolean;
  guest: boolean;
  limited: boolean;
  uploads: Upload[];
  pending: string[];
  onSend: (message: string) => Promise<void>;
  onUpload: (files: File[]) => Promise<void>;
  onRemove: (id?: string) => Promise<void>;
};

export default function Composer({ disabled, selected, guest, limited, uploads, pending, onSend, onUpload, onRemove }: Props) {
  const uploading = pending.length > 0;
  const unsent = uploads.filter(file => !file.sent);
  const [message, setMessage] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const question = message.trim();
    if (disabled || uploading || !question) return;
    setMessage('');
    if (input.current) input.current.style.height = '';
    await onSend(question);
    input.current?.focus();
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }
  return <div className="composer-area">
    <form className="composer" data-frozen={limited || undefined} onSubmit={submit}>
      <AttachedFiles uploads={unsent} pending={pending} disabled={disabled || uploading} onRemove={onRemove} />
      <label htmlFor="message" className="sr-only">Your message</label>
      <textarea ref={input} id="message" name="message" placeholder={limited ? 'Guest limit reached. Log in or sign up to keep chatting.' : selected ? 'Message Aster…' : 'Log in to start chatting'}
        rows={2} maxLength={10000} required disabled={disabled} value={message} onKeyDown={keyDown}
        onChange={event => {
          setMessage(event.target.value);
          event.currentTarget.style.height = 'auto';
          event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 180)}px`;
        }} />
      <div className="composer-toolbar">
        <input ref={fileInput} type="file" aria-label="Choose files" multiple hidden disabled={disabled || uploading}
          onChange={event => {
            const files = Array.from(event.currentTarget.files || []);
            event.currentTarget.value = '';
            if (files.length) void onUpload(files);
          }} />
        <button type="button" className="attach-button" aria-label="Attach files" disabled={disabled || uploading}
          onClick={() => fileInput.current?.click()}><Icon name="attach" /><span>Attach files</span></button>
        <button type="submit" className="send-button" aria-label="Send message" disabled={disabled || uploading || !message.trim()}>
          <Icon name="send" /><span>{uploading ? 'Uploading…' : 'Send'}</span>
        </button>
      </div>
    </form>
    <p className="composer-note">{uploading ? 'You can keep typing while files upload.' : unsent.length ? `${unsent.length} ${unsent.length === 1 ? 'file' : 'files'} will be sent with your message. ${guest ? 'Guest files last while this tab is open.' : 'Files are saved with this conversation.'}` : 'AI can make mistakes. Review important information.'}</p>
  </div>;
}
