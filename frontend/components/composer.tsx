import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import type { Upload, UploadFailure, UploadSettings } from '../lib/api';
import { AttachedFiles } from './files';
import Icon from './icon';

type Props = {
  settings: UploadSettings | null;
  failures: UploadFailure[];
  onRetry: (id: string) => Promise<void>;
  onDismiss: (id: string) => void;
  disabled: boolean;
  selected: boolean;
  guest: boolean;
  limited: boolean;
  uploadLimited: boolean;
  uploads: Upload[];
  pending: string[];
  streaming: boolean;
  stopping: boolean;
  onStop: () => void;
  onSend: (message: string) => Promise<void>;
  onUpload: (files: File[]) => Promise<void>;
  onRemove: (id?: string) => Promise<void>;
};

export default function Composer({ settings, failures, onRetry, onDismiss, disabled, selected, guest, limited, uploadLimited, uploads, pending, streaming, stopping, onStop, onSend, onUpload, onRemove }: Props) {
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
    {failures.length > 0 && <section className="upload-failures" aria-label="Failed uploads" aria-live="polite">
      {failures.map(item => <div className="upload-failure" key={item.id}>
        <div><strong>{item.file.name}</strong><p>{item.message}</p></div>
        <button type="button" className="text-button" disabled={disabled || uploading || uploadLimited}
          aria-label={`Retry ${item.file.name}`} onClick={() => void onRetry(item.id)}>Retry</button>
        <button type="button" className="icon-button" aria-label={`Dismiss ${item.file.name}`}
          onClick={() => onDismiss(item.id)}><Icon name="close" /></button>
      </div>)}
      <p>Only retry failed files. Successful attachments are kept. If the connection dropped after saving, check attachments before retrying to avoid duplicates. Retry files are kept in this tab until dismissed or you leave this conversation.</p>
    </section>}
    <form className="composer" data-frozen={limited || undefined} onSubmit={submit}>
      <AttachedFiles uploads={unsent} pending={pending} disabled={disabled || uploading} onRemove={onRemove} />
      <label htmlFor="message" className="sr-only">Your message</label>
      <textarea ref={input} id="message" name="message" placeholder={limited ? (guest ? 'Guest limit reached. Log in or sign up to keep chatting.' : 'Daily limit reached. Chat opens again at midnight.') : selected ? 'Message Aster…' : 'Log in to start chatting'}
        rows={2} maxLength={10000} required disabled={disabled} value={message} onKeyDown={keyDown}
        onChange={event => {
          setMessage(event.target.value);
          event.currentTarget.style.height = 'auto';
          event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 180)}px`;
        }} />
      <div className="composer-toolbar">
        <input ref={fileInput} type="file" aria-label="Choose files" multiple hidden disabled={disabled || uploading || uploadLimited}
          onChange={event => {
            const files = Array.from(event.currentTarget.files || []);
            event.currentTarget.value = '';
            if (files.length) void onUpload(files);
          }} />
        <button type="button" className="attach-button" aria-label="Attach files" disabled={disabled || uploading || uploadLimited}
          onClick={() => fileInput.current?.click()}><Icon name="attach" /><span>Attach files</span></button>
        {streaming ? <button type="button" className="send-button" aria-label="Stop answer" disabled={stopping} onClick={onStop}>
          <Icon name="stop" /><span>{stopping ? 'Stopping…' : 'Stop'}</span>
        </button> : <button type="submit" className="send-button" aria-label="Send message" disabled={disabled || uploading || !message.trim()}>
          <Icon name="send" /><span>{uploading ? 'Uploading…' : 'Send'}</span>
        </button>}
      </div>
    </form>
    <details className="upload-help">
      <summary>File help</summary>
      {settings ? <div>
        <p>Up to {settings.max_file_bytes / 1048576} MiB per file; {settings.max_conversation_files} original uploads and {settings.max_conversation_bytes / 1048576} MiB per conversation. Daily upload limits also apply. Existing files are never removed automatically.</p>
        <p>Text and Word: .docx, {settings.text_extensions.join(', ')}. Images: {settings.image_extensions.join(', ')} require a vision-capable chat model.</p>
        <p>{settings.parsing_enabled ? 'Cloud parsing is enabled: uploads are sent to LlamaParse and may incur charges. It can read PDFs, scans and additional Office formats. Parsing can take several minutes; failed extraction falls back to local readers.' : 'Cloud parsing is not configured. PDFs, scans, spreadsheets and slides cannot be read by the local text reader. They can still be uploaded and downloaded, but the assistant will report unavailable content.'}</p>
        <p>Upload and processing use one request; individual parsing stages and percentages are not reported. Open a file’s Processing details to see extraction and retrieval warnings.</p>
        {guest && <p>{settings.guest_inspection_enabled ? 'Upload inspection is enabled: extracted guest text and chunks remain on the server until manually deleted, even after this session ends.' : 'Live guest files last for this session. If the operator enables inspection exports later, extracted text and chunks may remain on the server.'}</p>}
      </div> : <p>Upload settings could not be loaded. Server limits still apply. DOCX and UTF-8 text use local readers; PDF/scan and additional Office extraction require cloud parsing. Images require a vision-capable chat model. Check each file’s Processing details after uploading.</p>}
    </details>
    <p className="composer-note">{uploading ? 'Uploading and processing the first file shown; other files are queued. You can keep typing. Large files or scans may take several minutes.' : unsent.length ? `${unsent.length} ${unsent.length === 1 ? 'file' : 'files'} will be sent with your message. ${guest ? 'Live guest files last for this session; inspection copies may remain on the server.' : 'Files are saved with this conversation.'}` : uploadLimited && !limited ? 'You’ve used today’s file uploads. You can attach more files after midnight.' : 'AI can make mistakes. Review important information.'}</p>
  </div>;
}
