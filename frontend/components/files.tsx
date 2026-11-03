import { useEffect, useState } from 'react';
import type { DownloadInfo, Files, Upload } from '../lib/api';
import Icon from './icon';
import FilePreview from './preview';
import { guestDownload, guestToken } from '../lib/guest';

export function AttachedFiles({ uploads, pending, disabled, onRemove }: {
  uploads: Upload[];
  pending: string[];
  disabled: boolean;
  onRemove: (id?: string) => Promise<void>;
}) {
  if (!uploads.length && !pending.length) return null;
  return <div className="attached-files" aria-label="Active attachments">
    {uploads.map(file => {
      const query = `file_id=${encodeURIComponent(file.id)}`;
      return <div className="attachment" key={file.id} title={`${file.filename} · ${file.status}`}>
        <Icon name="file" /><span className="attachment-name">{file.filename}</span>
        {file.edits.map((edit, index) => <a key={edit.id} className="attachment-revision" download={edit.filename} onClick={guestDownload}
          aria-label={`Edited v${index + 1}`} href={`/api/document/edited?${query}&revision_id=${encodeURIComponent(edit.id)}`}>v{index + 1}</a>)}
        <a className="icon-button" href={`/api/document/download?${query}`} download={file.filename} onClick={guestDownload}
          aria-label={`Download ${file.filename}`}><Icon name="download" /></a>
        <button type="button" className="icon-button" aria-label={`Remove ${file.filename}`} disabled={disabled}
          onClick={() => void onRemove(file.id)}><Icon name="close" /></button>
      </div>;
    })}
    {pending.map((name, index) => <div className="attachment pending" key={`pending-${index}`} role="status">
      <span className="attachment-spinner" aria-hidden="true" /><span className="attachment-name">{name}</span><span className="sr-only">Uploading</span>
    </div>)}
    {uploads.length > 1 && <button type="button" className="text-button attachment-clear" disabled={disabled}
      onClick={async () => { for (const file of uploads) await onRemove(file.id); }}>Remove all</button>}
  </div>;
}

export function MessageFiles({ attachments, uploads }: { attachments: DownloadInfo[]; uploads: Upload[] }) {
  return <div className="message-files" aria-label="Files sent with this message">
    {attachments.map(attachment => {
      const file = uploads.find(upload => upload.id === attachment.id);
      const query = `file_id=${encodeURIComponent(attachment.id)}`;
      if (!file) return <div className="attachment removed" key={attachment.id} title={`${attachment.filename} (removed)`}>
        <Icon name="file" /><span className="attachment-name">{attachment.filename}</span>
      </div>;
      return <div className="attachment" key={attachment.id} title={`${file.filename} · ${file.status}`}>
        <Icon name="file" /><span className="attachment-name">{file.filename}</span>
        {file.edits.map((edit, index) => <a key={edit.id} className="attachment-revision" download={edit.filename} onClick={guestDownload}
          aria-label={`Edited v${index + 1}`} href={`/api/document/edited?${query}&revision_id=${encodeURIComponent(edit.id)}`}>v{index + 1}</a>)}
        <a className="icon-button" href={`/api/document/download?${query}`} download={file.filename} onClick={guestDownload}
          aria-label={`Download ${file.filename}`}><Icon name="download" /></a>
      </div>;
    })}
  </div>;
}

export function GeneratedFiles({ files }: { files: Files }) {
  const [preview, setPreview] = useState<DownloadInfo | null>(null);
  if (!files.generated_files.length) return null;
  return <section className="conversation-files generated" aria-label="Generated files">
    <h2>Created files</h2>
    {files.generated_files.map(file => <div key={file.id} className="generated-file">
      <Icon name="file" /><span>{file.filename}</span>
      <button type="button" className="preview-button" aria-label={`Preview ${file.filename}`} onClick={() => setPreview(file)}>Preview</button>
      <a className="icon-button" download={file.filename} onClick={guestDownload} aria-label={`Download ${file.filename}`}
        href={`/api/files/download?file_id=${encodeURIComponent(file.id)}`}><Icon name="download" /></a>
    </div>)}
    {preview && <FilePreview key={preview.id} file={preview} onClose={() => setPreview(null)} />}
  </section>;
}

function GeneratedImage({ image }: { image: DownloadInfo }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    const token = guestToken();
    fetch(`/api/files/view?file_id=${encodeURIComponent(image.id)}`, {
      credentials: 'same-origin', cache: 'no-store', headers: token ? { 'x-guest-session': token } : {},
    }).then(response => {
      if (!response.ok) throw new Error('Image unavailable');
      return response.blob();
    }).then(blob => {
      objectUrl = URL.createObjectURL(blob);
      if (active) setUrl(objectUrl);
      else URL.revokeObjectURL(objectUrl);
    }).catch(() => { if (active) setFailed(true); });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image.id]);
  return <figure className="generated-image">
    {url ? <img src={url} alt={image.filename} /> : <div className="generated-image-placeholder" role="status">{failed ? 'Image unavailable' : 'Loading image…'}</div>}
    <figcaption><span>{image.filename}</span>
      <a className="icon-button" href={`/api/files/download?file_id=${encodeURIComponent(image.id)}`} download={image.filename} onClick={guestDownload}
        aria-label={`Download ${image.filename}`}><Icon name="download" /></a>
    </figcaption>
  </figure>;
}

export function GeneratedImages({ images }: { images: DownloadInfo[] }) {
  return <div className="message-images" aria-label="Images created for this answer">
    {images.map(image => <GeneratedImage key={image.id} image={image} />)}
  </div>;
}
