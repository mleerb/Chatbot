import { spawn } from 'node:child_process';
import { cpSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = new URL('./', import.meta.url);
cpSync(new URL('.next/static', root), new URL('.next/standalone/.next/static', root), { recursive: true });
cpSync(new URL('public', root), new URL('.next/standalone/public', root), { recursive: true });
const server = spawn(process.execPath, [fileURLToPath(new URL('.next/standalone/server.js', root))], {
  stdio: 'inherit',
  env: { ...process.env, HOSTNAME: '127.0.0.1', PORT: process.env.PORT || '3000' },
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.kill(signal));
server.on('exit', code => { process.exitCode = code ?? 1; });
