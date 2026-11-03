import { cpSync, mkdirSync } from 'node:fs';

const source = new URL('./node_modules/pdfjs-dist/', import.meta.url);
const target = new URL('./public/pdfjs/', import.meta.url);
mkdirSync(target, { recursive: true });
for (const name of ['build/pdf.worker.min.mjs', 'cmaps', 'standard_fonts', 'wasm', 'LICENSE']) {
  cpSync(new URL(name, source), new URL(name === 'build/pdf.worker.min.mjs' ? 'pdf.worker.min.mjs' : name, target), { recursive: true });
}
