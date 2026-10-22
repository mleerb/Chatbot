import { useEffect, useRef, useState } from 'react';
import { exportAnswer, type ExportFormat } from '../lib/api';
import Icon from './icon';

const options: { format: ExportFormat; label: string }[] = [
  { format: 'md', label: 'Markdown (.md)' }, { format: 'docx', label: 'Word (.docx)' }, { format: 'pdf', label: 'PDF (.pdf)' },
];

export default function AnswerMenu({ content, index }: { content: string; index: number }) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = `answer-menu-${index}`;

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);

  async function choose(format: ExportFormat) {
    setOpen(false);
    trigger.current?.focus();
    try { await exportAnswer(content, format); }
    catch { window.alert('Could not export this answer. Try again.'); }
  }

  return <div className="answer-menu" ref={container}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
    onKeyDown={event => {
      if (event.key === 'Escape' && open) {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
    }}>
    <button ref={trigger} className="icon-button" type="button" aria-label="Answer options" title="Answer options"
      aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}><Icon name="more" /></button>
    {open && <div id={id} className="answer-dropdown" role="group" aria-label="Export answer">
      <span>Export as</span>
      {options.map(item => <button key={item.format} type="button" aria-label={`Export answer as ${item.label}`}
        onClick={() => void choose(item.format)}>{item.label}</button>)}
    </div>}
  </div>;
}
