const key = 'aster-guest-tab';
let token: string | null = null;

export function guestToken(): string | null {
  if (token) return token;
  try { token = sessionStorage.getItem(key); } catch {}
  return token;
}

export function setGuestToken(value: string | null) {
  token = value;
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {}
}

export async function guestDownload(event: import('react').MouseEvent<HTMLAnchorElement>) {
  const current = guestToken();
  if (!current) return;
  event.preventDefault();
  const link = event.currentTarget;
  try {
    const response = await fetch(link.href, { headers: { 'x-guest-session': current }, cache: 'no-store' });
    if (!response.ok) throw new Error('Download unavailable');
    const url = URL.createObjectURL(await response.blob());
    const download = document.createElement('a');
    download.href = url;
    download.download = link.download || 'download';
    download.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch { window.alert('This file is no longer available. The guest tab may have ended.'); }
}
