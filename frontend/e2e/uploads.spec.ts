import { expect, test } from '@playwright/test';

for (const width of [1440, 360]) {
  test(`upload help, queued processing and selective retry at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/chat');
    await page.getByRole('button', { name: 'Continue as guest' }).click();
    await page.getByText('File help', { exact: true }).click();
    await expect(page.locator('.upload-help')).toContainText('20 MiB per file');
    await expect(page.locator('.upload-help')).toContainText('Cloud parsing is not configured');
    await expect(page.locator('.upload-help')).toContainText('remain on the server until manually deleted');
    const requests: string[] = [];
    let fail = true;
    await page.route('**/api/document', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      const body = route.request().postDataBuffer()?.toString() ?? '';
      const name = body.match(/filename="([^"]+)"/)?.[1] ?? '';
      requests.push(name);
      await new Promise(resolve => setTimeout(resolve, 250));
      if (name === 'retry.txt' && fail) {
        fail = false;
        return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Parser connection unavailable. Try again.' }) });
      }
      return route.continue();
    });
    await page.getByLabel('Your message').fill('Keep this draft');
    await page.getByLabel('Choose files').setInputFiles([
      { name: 'ready.txt', mimeType: 'text/plain', buffer: Buffer.from('first') },
      { name: 'retry.txt', mimeType: 'text/plain', buffer: Buffer.from('second') },
    ]);
    await expect(page.locator('.attachment.pending').first()).toContainText('Uploading / processing');
    await expect(page.locator('.attachment.pending').nth(1)).toContainText('Queued');
    await expect(page.getByRole('button', { name: 'Send message' })).toBeDisabled();
    await expect(page.getByLabel('Retry retry.txt')).toBeVisible();
    await expect(page.getByLabel('Your message')).toHaveValue('Keep this draft');
    await expect(page.getByLabel('Download ready.txt')).toBeVisible();
    await page.getByLabel('Retry retry.txt').click();
    await expect(page.getByLabel('Download retry.txt')).toBeVisible();
    await expect(page.getByLabel('Failed uploads')).toHaveCount(0);
    expect(requests.filter(name => name === 'ready.txt')).toHaveLength(1);
    expect(requests.filter(name => name === 'retry.txt')).toHaveLength(2);
    await page.getByLabel('Processing details for ready.txt').click();
    await expect(page.locator('.file-processing[open]')).toContainText('Text ready');
    await expect(page.getByLabel('Your message')).toHaveValue('Keep this draft');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/upload-experience-${width}.png`, fullPage: true });
  });
}

test('configured client size rejection avoids network upload and can be dismissed', async ({ page }) => {
  await page.route('**/api/document/settings', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
    max_file_bytes: 4, max_conversation_files: 3, max_conversation_bytes: 20,
    parsing_enabled: true, text_extensions: ['.txt'], image_extensions: ['.png'], guest_inspection_enabled: false,
  }) }));
  await page.goto('/chat');
  await page.getByRole('button', { name: 'Continue as guest' }).click();
  await page.getByText('File help', { exact: true }).click();
  await expect(page.locator('.upload-help')).toContainText('Cloud parsing is enabled');
  let calls = 0;
  page.on('request', request => { if (request.url().endsWith('/api/document') && request.method() === 'POST') calls++; });
  await page.getByLabel('Choose files').setInputFiles({ name: 'large.txt', mimeType: 'text/plain', buffer: Buffer.from('too large') });
  await expect(page.getByLabel('Failed uploads')).toContainText('File is too large');
  expect(calls).toBe(0);
  await page.getByLabel('Dismiss large.txt').click();
  await expect(page.getByLabel('Failed uploads')).toHaveCount(0);
});

test('processing warnings remain readable after attachments are sent', async ({ page }) => {
  await page.route('**/api/document/settings', route => route.abort());
  await page.route('**/api/state', async route => {
    const response = await route.fetch();
    const state = await response.json();
    for (const upload of state.uploads ?? []) upload.status = 'LlamaParse timed out. Semantic search unavailable; keyword search will be used.';
    await route.fulfill({ response, json: state });
  });
  await page.goto('/chat');
  await page.getByRole('button', { name: 'Continue as guest' }).click();
  await page.getByText('File help', { exact: true }).click();
  await expect(page.locator('.upload-help')).toContainText('Upload settings could not be loaded');
  await page.getByLabel('Choose files').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('content') });
  await expect(page.getByLabel('Download notes.txt')).toBeVisible();
  await page.getByLabel('Your message').fill('Hello');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.locator('.message.assistant').last()).toBeVisible();
  await page.getByLabel('Processing details for notes.txt').click();
  await expect(page.locator('.file-processing[open]')).toContainText('keyword search');
  await expect(page.locator('.file-processing[open]')).toContainText('timed out');
  await expect(page.locator('.file-processing[open] summary')).toHaveText('Check file');
});
