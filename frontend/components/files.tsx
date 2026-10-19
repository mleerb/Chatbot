import type { Files, Upload } from '../lib/api';
import Icon from './icon';

export function AttachedFiles({ uploads, disabled, onRemove }: {
  uploads: Upload[];
  disabled: boolean;
  onRemove: (id: string) => Promise<void>;
}) {
  if (!uploads.length) return null;
  return <div className="attached-files" aria-label="Active attachments">
    {uploads.map(file => <div className="attachment" key={file.id}>
      <Icon name="file" /><span title={file.filename}>{file.filename}</span>
      <button type="button" className="icon-button" aria-label={`Remove ${file.filename}`} disabled={disabled}
        onClick={() => void onRemove(file.id)}><Icon name="close" /></button>
    </div>)}
  </div>;
}

export function FileShelf({ files, busy, onRemove }: {
  files: Files;
  busy: boolean;
  onRemove: (id?: string) => Promise<void>;
}) {
  if (!files.uploads.length && !files.generated_files.length) return null;
  return <section className="conversation-files" aria-label="Conversation files">
    {!!files.uploads.length && <>
      <div className="file-heading"><h2>Attached files</h2>
        <button type="button" className="text-button" disabled={busy} onClick={() => void onRemove()}>Remove all</button>
      </div>
      <div className="uploads" aria-label="Uploaded files">
        {files.uploads.map(file => {
          const query = `file_id=${encodeURIComponent(file.id)}`;
          return <article className="file-item" key={file.id}>
            <div className="file-identity"><span className="file-symbol"><Icon name="file" /></span>
              <div><h3>{file.filename}</h3><p>{file.status}</p></div>
            </div>
            <div className="file-actions">
              <a href={`/api/document/download?${query}`} download>Download original</a>
              <button type="button" className="text-button" disabled={busy} onClick={() => void onRemove(file.id)}>Remove file</button>
            </div>
            {!!file.edits.length && <div className="revisions" aria-label={`Edited versions of ${file.filename}`}>
              {file.edits.map((edit, index) => <a key={edit.id} className="revision" download
                href={`/api/document/edited?${query}&revision_id=${encodeURIComponent(edit.id)}`}>
                <Icon name="download" /> Edited v{index + 1}
              </a>)}
            </div>}
          </article>;
        })}
      </div>
    </>}
    {!!files.generated_files.length && <section className="generated" aria-label="Generated files">
      <h2>Created files</h2>
      {files.generated_files.map(file => <a key={file.id} className="generated-file" download
        href={`/api/files/download?file_id=${encodeURIComponent(file.id)}`}>
        <Icon name="file" /><span>{file.filename}</span><Icon name="download" /><span className="sr-only">Download</span>
      </a>)}
    </section>}
  </section>;
}
