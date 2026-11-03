import { useMemo, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { safeUrl, type Source } from '../lib/api';
import { citationMarkdown } from '../lib/citations';

function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const block = useRef<HTMLPreElement>(null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(block.current?.innerText ?? '');
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  }
  return <div className="code-block">
    <button type="button" className="copy-code" onClick={() => void copy()}>{copied ? 'Copied' : 'Copy code'}</button>
    <pre ref={block}>{children}</pre>
  </div>;
}

const components: Components = {
  a: ({ href, children }) => {
    const url = href ? safeUrl(href) : null;
    return url ? <a href={url} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>;
  },
  img: ({ alt }) => <span className="markdown-image">[{alt || 'image'}]</span>,
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  table: ({ children }) => <div className="table-scroll"><table>{children}</table></div>,
};

export default function Markdown({ content, sources = [], onSource }: {
  content: string; sources?: Source[]; onSource?: (source: Source) => void;
}) {
  const renderers = useMemo<Components>(() => ({
    ...components,
    a: ({ href, children }) => {
      const marker = href?.match(/^\/__aster_citation\/([DW][1-9][0-9]*)$/)?.[1];
      if (marker) {
        const source = sources.find(item => item.marker === marker);
        if (!source) return null;
        if (source.kind === 'document') return <button type="button" className="citation-marker document-citation"
          aria-label={`Document ${marker}: ${source.title}, ${source.location}`} onClick={() => onSource?.(source)}>[{marker}]</button>;
        const url = safeUrl(source.url);
        return url ? <a className="citation-marker web-citation" href={url} target="_blank" rel="noopener noreferrer"
          aria-label={`Web ${marker}: ${source.title}`}>[{marker}]</a> : null;
      }
      const url = href ? safeUrl(href) : null;
      return url ? <a href={url} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>;
    },
  }), [sources, onSource]);
  return <div className="message-body markdown">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={renderers} skipHtml>{citationMarkdown(content, sources)}</ReactMarkdown>
  </div>;
}
