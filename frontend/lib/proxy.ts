const hopHeaders = ['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade', 'host'];

function cleanHeaders(source: Headers): Headers {
  const headers = new Headers(source);
  for (const name of source.get('connection')?.split(',') || []) headers.delete(name.trim());
  for (const name of hopHeaders) headers.delete(name);
  return headers;
}

export async function proxy(request: Request): Promise<Response> {
  const incoming = new URL(request.url);
  const target = new URL(process.env.BACKEND_URL || 'http://127.0.0.1:8001');
  target.pathname = incoming.pathname;
  target.search = incoming.search;
  const headers = cleanHeaders(request.headers);
  headers.set('accept-encoding', 'identity');
  headers.set('x-forwarded-host', request.headers.get('host') || incoming.host);
  const init: RequestInit & { duplex: 'half' } = {
    method: request.method,
    headers,
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
    duplex: 'half',
    cache: 'no-store',
    redirect: 'manual',
    signal: request.signal,
  };
  try {
    const upstream = await fetch(target, init);
    const outgoing = cleanHeaders(upstream.headers);
    outgoing.delete('content-encoding');
    outgoing.delete('content-length');
    outgoing.set('cache-control', 'no-store');
    return new Response(upstream.body, { status: upstream.status, headers: outgoing });
  } catch {
    return Response.json({ detail: 'Backend unavailable. Check that FastAPI is running.' }, {
      status: 502,
      headers: { 'cache-control': 'no-store' },
    });
  }
}
