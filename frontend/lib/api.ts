import { guestToken } from './guest';

export type Source = { title: string; url: string };
export type DownloadInfo = { id: string; filename: string };
export type ExportFormat = 'md' | 'docx' | 'pdf';
export type Rating = 'up' | 'down' | null;
export type Message = { role: 'user' | 'assistant'; content: string; sources?: Source[]; attachments?: DownloadInfo[]; stopped?: boolean; rating?: Rating };
export type User = { id: number; name: string; email?: string };
export type Conversation = { id: number; user_id: number; title: string; pinned: boolean };
export type Upload = DownloadInfo & { status: string; sent: boolean; edits: DownloadInfo[] };
export type Files = { uploads: Upload[]; generated_files: DownloadInfo[] };
export type State = Files & { user_id: number | null; conversation_id: number | null; conversations: Conversation[]; messages: Message[]; guest_limited?: boolean; limit_resets_at?: string | null; upload_resets_at?: string | null };
export type Reply = Files & { answer: string; display_answer: string; stopped?: boolean; sources: Source[]; attachments?: DownloadInfo[]; guest_limited?: boolean; limit_resets_at?: string | null };
export type StreamEvent = { type: 'text'; text: string } | { type: 'step'; label: string } | ({ type: 'done' } & Reply) | { type: 'error'; status: number; detail: string };

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Request failed';
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = guestHeaders(options.headers);
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options, headers });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Request failed');
  return data as T;
}

function guestHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  const guest = guestToken();
  if (guest) headers.set('x-guest-session', guest);
  return headers;
}

export async function streamChat(body: { message: string; replace_from?: number }, onEvent: (event: StreamEvent) => void): Promise<Reply> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: guestHeaders({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }), body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Request failed');
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = block.split('\n').filter(line => line.startsWith('data: ')).map(line => line.slice(6)).join('\n');
      if (!data) continue;
      const event = JSON.parse(data) as StreamEvent;
      if (event.type === 'error') throw new Error(event.detail);
      if (event.type === 'done') return event;
      onEvent(event);
    }
  }
  throw new Error('The answer was interrupted. Try again.');
}

export async function stopChat() {
  await request('/api/chat/stop', { method: 'POST' });
}

export async function rateAnswer(index: number, rating: Rating) {
  return request<{ rating: Rating }>('/api/chat/rating', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ index, rating }),
  });
}

export async function exportAnswer(content: string, format: ExportFormat) {
  const headers = guestHeaders({ 'Content-Type': 'application/json' });
  const response = await fetch('/api/export', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', headers, body: JSON.stringify({ content, format }),
  });
  if (!response.ok) throw new Error('Could not export this answer');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `aster-answer.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function safeUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}
