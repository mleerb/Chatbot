import { useRef, useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { safeUrl } from '../lib/api';

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

export default function Markdown({ content }: { content: string }) {
  return <div className="message-body markdown">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} skipHtml>{content}</ReactMarkdown>
  </div>;
}
