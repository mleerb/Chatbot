import { useEffect, useRef, useState } from 'react';
import { previewBlob } from '../lib/api';
import type { PDFDocumentProxy } from 'pdfjs-dist';

export default function PdfPreview({ id }: { id: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    let active = true;
    let task: { destroy: () => Promise<void> } | undefined;
    void (async () => {
      const [library, blob] = await Promise.all([import('pdfjs-dist'), previewBlob(id)]);
      if (!active) return;
      library.GlobalWorkerOptions.workerSrc = '/pdfjs/pdf.worker.min.mjs';
      const loading = library.getDocument({ data: new Uint8Array(await blob.arrayBuffer()),
        cMapUrl: '/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: '/pdfjs/standard_fonts/',
        wasmUrl: '/pdfjs/wasm/', enableXfa: false, useWasm: false });
      task = loading;
      const document = await loading.promise;
      if (active) { setPdf(document); setPage(1); }
    })().catch(() => { if (active) { setFailed(true); setBusy(false); } });
    return () => { active = false; void task?.destroy(); };
  }, [id]);
  useEffect(() => {
    if (!pdf) return;
    let active = true;
    let render: { cancel: () => void } | undefined;
    setBusy(true);
    void pdf.getPage(page).then(async sheet => {
      if (!active || !canvas.current) return;
      const initial = sheet.getViewport({ scale: 1 });
      const scale = Math.min(zoom * Math.min(window.devicePixelRatio || 1, 2), 4096 / Math.max(initial.width, initial.height));
      const viewport = sheet.getViewport({ scale });
      const element = canvas.current;
      element.width = viewport.width;
      element.height = viewport.height;
      element.style.width = `${initial.width * zoom}px`;
      const rendering = sheet.render({ canvas: element, viewport });
      render = rendering;
      await rendering.promise;
      if (active) setBusy(false);
    }).catch(error => { if (active && error?.name !== 'RenderingCancelledException') { setFailed(true); setBusy(false); } });
    return () => { active = false; render?.cancel(); };
  }, [pdf, page, zoom]);
  if (failed) return <p role="alert">PDF preview unavailable. You can still download the file.</p>;
  return <div className="pdf-preview">
    <div className="preview-toolbar" role="group" aria-label="PDF controls">
      <button type="button" disabled={!pdf || page <= 1 || busy} onClick={() => setPage(value => value - 1)}>Previous page</button>
      <span>Page {page} of {pdf ? Math.min(pdf.numPages, 100) : '…'}</span>
      <button type="button" disabled={!pdf || page >= Math.min(pdf.numPages, 100) || busy} onClick={() => setPage(value => value + 1)}>Next page</button>
      <label>Zoom <select value={zoom} onChange={event => setZoom(Number(event.target.value))}>
        {[0.75, 1, 1.25, 1.5].map(value => <option key={value} value={value}>{value * 100}%</option>)}
      </select></label>
    </div>
    {pdf && pdf.numPages > 100 && <p role="status">Preview limited to the first 100 pages. Download the complete PDF for all pages.</p>}
    {busy && <p role="status">Rendering PDF…</p>}
    <div className="pdf-canvas"><canvas ref={canvas} aria-label={`PDF page ${page}`} role="img" /></div>
    <p className="source-note">Visual page preview. PDF links, forms and embedded scripts are not interactive.</p>
  </div>;
}
