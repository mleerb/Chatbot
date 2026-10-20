import { spawn } from 'node:child_process';
import { cpSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const cwd = fileURLToPath(new URL('..', import.meta.url));
const children = [];
function start(args, env = {}) {
  const child = spawn(process.execPath, args, { cwd, stdio: 'inherit', env: { ...process.env, ...env } });
  children.push(child);
  return child;
}
async function ready(url) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (children.some(child => child.exitCode !== null)) throw new Error('Test server exited before startup');
    try { await fetch(url); return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`Test server did not start: ${url}`);
}
try {
  start(['e2e/backend.mjs']);
  cpSync(new URL('../.next/static', import.meta.url), new URL('../.next/standalone/.next/static', import.meta.url), { recursive: true });
  cpSync(new URL('../public', import.meta.url), new URL('../.next/standalone/public', import.meta.url), { recursive: true });
  start(['.next/standalone/server.js'], {
    HOSTNAME: '127.0.0.1', PORT: '3100',
    BACKEND_URL: 'http://127.0.0.1:8101', NEXT_TELEMETRY_DISABLED: '1',
  });
  await Promise.all([ready('http://127.0.0.1:8101/api/state'), ready('http://127.0.0.1:3100')]);
  const tests = start(['node_modules/@playwright/test/cli.js', 'test']);
  process.exitCode = await new Promise(resolve => tests.once('exit', code => resolve(code ?? 1)));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  for (const child of children) if (child.exitCode === null) child.kill();
}
