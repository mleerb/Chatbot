import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '@playwright/test';

const target = new URL(process.env.CHATBOT_URL || 'http://127.0.0.1:18080');
if (!['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname) || target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
  throw new Error('CHATBOT_URL must be a loopback origin without credentials, a path or query parameters.');
}
const output = new URL('../test-results/', import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
try {
  for (const [name, width, colorScheme] of [['desktop', 1440, 'light'], ['mobile', 390, 'dark']]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme });
    const page = await context.newPage();
    const errors = [];
    const external = [];
    const failures = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      if (response.status() >= 400) failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
    });
    await page.route('**/*', route => {
      if (new URL(route.request().url()).origin !== target.origin) {
        external.push(new URL(route.request().url()).origin);
        return route.abort();
      }
      if (route.request().method() === 'POST' && new URL(route.request().url()).pathname === '/api/chat') {
        failures.push('Unexpected model request');
        return route.abort();
      }
      return route.continue();
    });
    try {
      const response = await page.goto(target.origin, { waitUntil: 'networkidle' });
      expect(response.status()).toBe(200);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: fileURLToPath(new URL(`live-${name}-landing.png`, output)) });
      await page.getByRole('link', { name: 'Start a conversation', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
      await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
      await expect(page.locator('textarea')).toBeEnabled();
      await page.reload({ waitUntil: 'networkidle' });
      await expect(page.locator('textarea')).toBeEnabled();
      await page.screenshot({ path: fileURLToPath(new URL(`live-${name}-chat.png`, output)) });
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
      expect(failures).toEqual([]);
      console.log(`${name}: landing → guest workspace → refresh passed; no external requests, HTTP errors or JavaScript errors.`);
    } finally {
      await page.evaluate(async () => {
        let token;
        try { token = sessionStorage.getItem('aster-guest-tab'); } catch {}
        if (token) await fetch('/api/auth/logout', { method: 'POST', headers: { 'x-guest-session': token } }).catch(() => {});
      }).catch(() => {});
      await context.close();
    }
  }
  console.log(`Screenshots: ${fileURLToPath(output)}`);
  console.log('No model calls or account/history writes were made.');
} finally {
  await browser.close();
}
