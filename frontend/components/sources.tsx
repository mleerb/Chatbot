import { useEffect, useRef, useState } from 'react';
import { request, safeUrl, type DocumentSource, type Source, type SourceText } from '../lib/api';

export function SourceList({ sources, onOpen }: { sources: Source[]; onOpen: (source: DocumentSource) => void }) {
  const documents = sources.filter((source): source is DocumentSource => source.kind === 'document');
  const web = sources.filter(source => source.kind !== 'document');
  return <div className="source-groups">
    {!!documents.length && <div className="sources document-sources"><span>Document sources</span>
      {documents.map(source => <button type="button" key={source.id} onClick={() => onOpen(source)}>
        [{source.marker}] {source.title} — {source.location}</button>)}
    </div>}
    {!!web.length && <div className="sources web-sources"><span>Web sources</span>
      {web.map((source, index) => {
        const url = safeUrl(source.url);
        return url ? <a key={index} href={url} target="_blank" rel="noopener noreferrer">
          [{source.marker || `W${index + 1}`}] {source.title || url}</a> : null;
      })}
    </div>}
  </div>;
}

export default function SourceViewer({ source, onClose }: { source: DocumentSource; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<{ id: string; data?: SourceText; failed?: boolean }>({ id: source.id });
  useEffect(() => {
    const active = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); active?.focus(); };
  }, []);
  useEffect(() => {
    let cancelled = false;
    void request<SourceText>(`/api/sources/${encodeURIComponent(source.id)}`).then(data => {
      if (!cancelled) setState({ id: source.id, data });
    }).catch(() => { if (!cancelled) setState({ id: source.id, failed: true }); });
    return () => { cancelled = true; };
  }, [source.id]);
  const data = state.id === source.id ? state.data : undefined;
  const failed = state.id === source.id && state.failed;
  return <dialog ref={dialog} className="source-viewer" aria-labelledby="source-title" onCancel={onClose}
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <header><div><p>Document source [{source.marker}]</p><h2 id="source-title">{source.title}</h2></div>
      <button type="button" className="guest-button" onClick={onClose} autoFocus>Close source</button></header>
    <p className="source-location">{source.location} — {source.version}</p>
    <p className="source-note">Exact extracted text supplied to the assistant. A citation is not a guarantee that its claim is correct.</p>
    {failed ? <p role="alert">Source no longer available. The file may have been removed or this conversation is no longer active.</p>
      : data ? <pre className="source-text">{data.text}</pre> : <p role="status">Loading source…</p>}
  </dialog>;
}
