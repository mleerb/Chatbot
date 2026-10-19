export type Source = { title: string; url: string };
export type Message = { role: 'user' | 'assistant'; content: string; sources?: Source[] };
export type User = { id: number; name: string };
export type DownloadInfo = { id: string; filename: string };
export type Upload = DownloadInfo & { status: string; edits: DownloadInfo[] };
export type Files = { uploads: Upload[]; generated_files: DownloadInfo[] };
export type State = Files & { user_id: number | null; messages: Message[] };
export type Reply = Files & { answer: string; display_answer: string; sources: Source[] };

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Request failed';
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Request failed');
  return data as T;
}

export function safeUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}
