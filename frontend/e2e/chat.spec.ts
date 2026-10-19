import { expect, test } from '@playwright/test';

test('users, multi-upload, revisions, downloads, theme and session isolation', async ({ page, browser }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page).toHaveTitle('AGENTslop');
  await page.getByLabel('Select user').selectOption('1');
  await expect(page.getByRole('button', { name: 'Attach files' })).toBeEnabled();
  await page.getByLabel('Choose files').setInputFiles([
    { name: 'note.txt', mimeType: 'text/plain', buffer: Buffer.from('old') },
    { name: 'other.txt', mimeType: 'text/plain', buffer: Buffer.from('other') },
  ]);
  await expect(page.locator('.file-item')).toHaveCount(2);
  await expect(page.getByLabel('Active attachments').locator('.attachment')).toHaveCount(2);
  await expect(page.locator('.sidebar .file-item')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('.file-item')).toHaveCount(2);
  await expect(page.getByLabel('Select user')).toHaveValue('1');
  for (let version = 1; version <= 2; version++) {
    await page.getByLabel('Your message').fill('Edit note.txt');
    await page.getByRole('button', { name: 'Send', exact: false }).click();
    await expect(page.getByRole('link', { name: `Edited v${version}`, exact: true })).toBeVisible();
  }
  await expect(page.getByLabel('Generated files').getByRole('link')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true);
  await page.screenshot({ path: 'test-results/files-light.png', fullPage: true });
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await page.screenshot({ path: 'test-results/files-dark.png', fullPage: true });
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  for (let count = 0; count < 2; count++) {
    const downloading = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Edited v1', exact: true }).click();
    expect((await downloading).suggestedFilename()).toBe('note.txt');
  }
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await page.reload();
  await expect(page.locator('[data-app]')).toHaveAttribute('data-theme', 'dark');
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await otherPage.goto('/');
  await expect(otherPage.getByLabel('Select user')).toHaveValue('');
  await expect(otherPage.locator('.file-item')).toHaveCount(0);
  await other.close();
  await page.locator('.file-item').first().getByRole('button', { name: 'Remove file', exact: true }).click();
  await expect(page.locator('.file-item')).toHaveCount(1);
  await page.getByLabel('Select user').selectOption('2');
  await expect(page.locator('.file-item')).toHaveCount(0);
  await expect(page.getByLabel('Generated files').getByRole('link')).toHaveCount(0);
  await page.locator('.add-user summary').click();
  await page.getByLabel('New user name').fill('New tester');
  await page.getByRole('button', { name: 'Add user' }).click();
  await expect(page.getByLabel('Select user')).toHaveValue('3');
  await page.screenshot({ path: 'test-results/desktop-dark.png', fullPage: true });
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await page.screenshot({ path: 'test-results/desktop-light.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('chat errors keep attachments and allow retry', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Select user').selectOption('1');
  await expect(page.getByRole('button', { name: 'Attach files' })).toBeEnabled();
  await page.getByLabel('Choose files').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('notes') });
  await expect(page.locator('.file-item')).toHaveCount(1);
  await page.route('**/api/chat', route => route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'The model is unavailable. Check model settings and retry.' }) }));
  await page.getByLabel('Your message').fill('Review my file');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Check model settings' })).toBeVisible();
  await expect(page.getByLabel('Your message')).toBeEnabled();
  await expect(page.getByLabel('Active attachments').locator('.attachment')).toHaveCount(1);
  await page.unroute('**/api/chat');
  await page.getByLabel('Your message').fill('Try again');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('link', { name: 'Edited v1', exact: true })).toBeVisible();
});

test('mobile layout keeps composer reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Open sidebar' }).click();
  await page.getByLabel('Select user').selectOption('1');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByLabel('Your message')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Open sidebar' }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Open sidebar' })).toBeFocused();
  await page.screenshot({ path: 'test-results/mobile.png', fullPage: true });
  await expect(page.getByRole('button', { name: 'Attach files' })).toBeEnabled();
  await page.getByLabel('Choose files').setInputFiles([
    { name: 'A long document name for the mobile layout.txt', mimeType: 'text/plain', buffer: Buffer.from('notes') },
    { name: 'second.txt', mimeType: 'text/plain', buffer: Buffer.from('notes') },
  ]);
  await expect(page.locator('.file-item')).toHaveCount(2);
  await expect(page.getByLabel('Your message')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/mobile-files.png', fullPage: true });
  await page.getByLabel('Your message').fill('Edit the file');
  await page.getByLabel('Your message').press('Enter');
  await expect(page.getByRole('link', { name: 'Edited v1', exact: true })).toBeVisible();
  await page.getByLabel('Your message').fill('First line');
  await page.getByLabel('Your message').press('Shift+Enter');
  await expect(page.getByLabel('Your message')).toHaveValue('First line\n');
});
