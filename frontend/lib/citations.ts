import type { Source } from './api';

export function citationMarkdown(content: string, sources: Source[]): string {
  const allowed = new Set(sources.map(source => source.marker).filter(Boolean));
  return content.replace(/(```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|`[^`\n]*`)|(\[([DW][1-9][0-9]*)\])/g,
    (_match: string, code: string | undefined, marker: string | undefined, id: string | undefined) => {
      if (code) return code;
      return marker && id && allowed.has(id) ? `[${id}](/__aster_citation/${id})` : '';
    });
}

export function draftText(content: string): string {
  return content.replace(/\[[DW][0-9]+\]/g, '').replace(/\[(?:[DW][0-9]*)?$/, '');
}
