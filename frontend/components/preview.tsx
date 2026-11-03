import { useEffect, useMemo, useRef, useState } from 'react';
import { previewBlob, request, type DownloadInfo } from '../lib/api';
import { guestDownload } from '../lib/guest';
import { safeHtml } from '../lib/preview';
import PdfPreview from './pdf';

type Preview = { filename: string; kind: string; text?: string; truncated: boolean; notice: string;
  sheets?: { name: string; rows: string[][] }[]; slides?: { name: string; text: string }[];
  entries?: { name: string; size: number }[] };

function HtmlPreview({ text }: { text: string }) {
  const [source, setSource] = useState(false);
  const html = useMemo(() => safeHtml(text), [text]);
  return <><div className="preview-toolbar" role="group" aria-label="HTML view">
    <button type="button" aria-pressed={!source} onClick={() => setSource(false)}>Rendered preview</button>
    <button type="button" aria-pressed={source} onClick={() => setSource(true)}>Source</button>
  </div>{source ? <pre className="source-text">{text}</pre> : <>
    <p className="source-note">Static HTML only. Scripts, external resources, forms and navigation are disabled.</p>
    <iframe className="html-preview" title="Rendered HTML preview" sandbox="" referrerPolicy="no-referrer" srcDoc={html} />
  </>}</>;
}

function ImagePreview({ id, filename }: { id: string; filename: string }) {
  const [url, setUrl] = useState('');
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let objectUrl = '';
    void previewBlob(id).then(blob => {
      objectUrl = URL.createObjectURL(blob);
      if (active) setUrl(objectUrl); else URL.revokeObjectURL(objectUrl);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [id]);
  return failed ? <p role="alert">Image preview unavailable.</p> : url ? <img className="file-preview-image" src={url} alt={filename} /> : <p role="status">Loading image…</p>;
}

function PreviewBody({ data, file }: { data: Preview; file: DownloadInfo }) {
  const [sheet, setSheet] = useState(0);
  if (data.kind === 'html') return <HtmlPreview text={data.text ?? ''} />;
  if (data.kind === 'pdf') return <PdfPreview id={file.id} />;
  if (data.kind === 'image') return <ImagePreview id={file.id} filename={file.filename} />;
  if (data.kind === 'spreadsheet') return <>
    <label>Sheet <select value={sheet} onChange={event => setSheet(Number(event.target.value))}>
      {data.sheets?.map((item, index) => <option value={index} key={index}>{item.name}</option>)}
    </select></label>
    <div className="preview-table"><table><tbody>{data.sheets?.[sheet]?.rows.map((row, index) => <tr key={index}>
      {row.map((value, column) => <td key={column}>{value}</td>)}
    </tr>)}</tbody></table></div>
  </>;
  if (data.kind === 'slides') return <>{data.slides?.map((slide, index) => <section className="preview-slide" key={index}>
    <h3>{slide.name}</h3><pre className="source-text">{slide.text}</pre></section>)}</>;
  if (data.kind === 'archive') return <ul className="preview-entries">{data.entries?.map((entry, index) => <li key={index}>
    <span>{entry.name}</span><span>{entry.size.toLocaleString()} bytes</span></li>)}</ul>;
  if (data.kind === 'text') return <pre className="source-text">{data.text}</pre>;
  return null;
}

export default function FilePreview({ file, onClose }: { file: DownloadInfo; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<Preview | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); previous?.focus(); };
  }, []);
  useEffect(() => {
    let active = true;
    void request<Preview>(`/api/files/preview?file_id=${encodeURIComponent(file.id)}`).then(value => {
      if (active) setData(value);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [file.id]);
  return <dialog ref={dialog} className="source-viewer file-preview" aria-labelledby="preview-title" onCancel={onClose}
    onClick={event => { if (event.currentTarget === event.target) onClose(); }}>
    <header><div><p>File preview</p><h2 id="preview-title">{file.filename}</h2></div>
      <button type="button" className="guest-button" autoFocus onClick={onClose}>Close preview</button></header>
    <a className="preview-download" href={`/api/files/download?file_id=${encodeURIComponent(file.id)}`} download={file.filename}
      onClick={guestDownload}>Download {file.filename}</a>
    {failed ? <p role="alert">File preview unavailable. The file may have been removed or this conversation is no longer active.</p>
      : data ? <>{data.notice && <p className="source-note">{data.notice}</p>}
        {data.truncated && <p role="status">Preview truncated for size. Download the complete file to see everything.</p>}
        <PreviewBody data={data} file={file} /></> : <p role="status">Loading preview…</p>}
  </dialog>;
}
