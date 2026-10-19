import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { after, before, test } from 'node:test';
import { proxy } from '../lib/proxy';
import { safeUrl } from '../lib/api';

const server = createServer(async (request, response) => {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  response.setHeader('set-cookie', 'chat_session=test-token; HttpOnly; Path=/; SameSite=strict');
  response.setHeader('content-type', 'application/octet-stream');
  response.setHeader('content-disposition', 'attachment; filename="note.txt"');
  response.setHeader('x-content-type-options', 'nosniff');
  if (request.url?.includes('missing')) response.statusCode = 404;
  response.end(JSON.stringify({
    path: request.url, cookie: request.headers.cookie, method: request.method,
    type: request.headers['content-type'], body: Buffer.concat(chunks).toString('base64'),
  }));
});
const previous = process.env.BACKEND_URL;

before(async () => {
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Missing server address');
  process.env.BACKEND_URL = `http://127.0.0.1:${address.port}`;
});
after(async () => {
  if (previous === undefined) delete process.env.BACKEND_URL;
  else process.env.BACKEND_URL = previous;
  await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
});

test('proxy preserves cookies, query parameters and download headers without caching', async () => {
  const response = await proxy(new Request('http://frontend/api/document/download?file_id=abc&revision_id=def', {
    headers: { cookie: 'chat_session=private' },
  }));
  assert.equal(response.status, 200);
  assert.match(response.headers.get('set-cookie') || '', /chat_session=test-token/);
  assert.match(response.headers.get('content-disposition') || '', /attachment/);
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('cache-control'), 'no-store');
  const body = await response.json();
  assert.equal(body.path, '/api/document/download?file_id=abc&revision_id=def');
  assert.equal(body.cookie, 'chat_session=private');
});

test('multipart upload is streamed without changing its bytes or boundary', async () => {
  const data = new FormData();
  data.append('file', new Blob([new Uint8Array([0, 1, 2, 255])]), 'sample.bin');
  const request = new Request('http://frontend/api/document', { method: 'POST', body: data });
  const original = Buffer.from(await request.clone().arrayBuffer());
  const response = await proxy(request);
  const body = await response.json();
  assert.equal(body.method, 'POST');
  assert.match(body.type, /multipart\/form-data; boundary=/);
  assert.deepEqual(Buffer.from(body.body, 'base64'), original);
});

test('proxy forwards upstream errors', async () => {
  const response = await proxy(new Request('http://frontend/api/missing', { method: 'DELETE' }));
  assert.equal(response.status, 404);
  assert.equal((await response.json()).method, 'DELETE');
});

test('backend connection failures return a generic uncached error', async () => {
  const backend = process.env.BACKEND_URL;
  process.env.BACKEND_URL = 'http://127.0.0.1:1';
  try {
    const response = await proxy(new Request('http://frontend/api/state'));
    assert.equal(response.status, 502);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.deepEqual(await response.json(), { detail: 'Backend unavailable. Check that FastAPI is running.' });
  } finally { process.env.BACKEND_URL = backend; }
});

test('source links allow only HTTP and HTTPS', () => {
  assert.equal(safeUrl('javascript:alert(1)'), null);
  assert.equal(safeUrl('file:///private'), null);
  assert.equal(safeUrl('not a url'), null);
  assert.equal(safeUrl('https://example.com'), 'https://example.com/');
});
