import { expect, test, type Page } from '@playwright/test';

async function login(page: Page) {
  await page.getByLabel('Email', { exact: true }).fill('tester@example.com');
  await page.getByLabel('Password', { exact: true }).fill('test-password-123');
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await expect(page.getByLabel('Your message')).toBeVisible();
}

test('users, multi-upload, revisions, downloads, theme and session isolation', async ({ page, browser }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/chat');
  await expect(page).toHaveTitle('Aster');
  await login(page);
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
  await expect(page.locator('.account-info')).toContainText('Tester');
  for (let version = 1; version <= 2; version++) {
    await page.getByLabel('Your message').fill('Edit note.txt');
    await page.getByRole('button', { name: 'Send', exact: false }).click();
    await expect(page.getByRole('link', { name: `Edited v${version}`, exact: true })).toBeVisible();
  }
  await expect(page.getByLabel('Generated files').getByRole('link')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true);
  await page.screenshot({ path: 'test-results/files-light.png', fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await page.screenshot({ path: 'test-results/files-dark.png', fullPage: true, animations: 'disabled' });
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
  await otherPage.goto('/chat');
  await expect(otherPage.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
  await expect(otherPage.locator('.file-item')).toHaveCount(0);
  await other.close();
  await page.locator('.file-item').first().getByRole('button', { name: 'Remove file', exact: true }).click();
  await expect(page.locator('.file-item')).toHaveCount(1);
  await page.getByRole('button', { name: 'Log out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
  await page.getByRole('button', { name: 'New here? Create an account' }).click();
  await page.getByLabel('Your name').fill('New tester');
  await page.getByLabel('Email', { exact: true }).fill(`new-${Date.now()}@example.com`);
  await page.getByLabel('Password', { exact: true }).fill('test-password-123');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.locator('.account-info')).toContainText('New tester');
  await expect(page.locator('.file-item')).toHaveCount(0);
  await page.screenshot({ path: 'test-results/desktop-dark.png', fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await page.screenshot({ path: 'test-results/desktop-light.png', fullPage: true, animations: 'disabled' });
  expect(errors).toEqual([]);
});

test('chat errors keep attachments and allow retry', async ({ page }) => {
  await page.goto('/chat');
  await login(page);
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

test('conversation rename, pin, switch, delete confirmation and persistence', async ({ page }) => {
  await page.goto('/chat');
  await login(page);
  await expect(page.getByRole('button', { name: '+ New conversation', exact: true })).toBeEnabled();
  const count = await page.locator('.conversation-item').count();
  await page.getByRole('button', { name: '+ New conversation', exact: true }).click();
  await expect(page.locator('.conversation-item')).toHaveCount(count + 1);
  await expect(page.locator('.conversation-item').first()).toHaveAttribute('data-selected', 'true');
  let current = page.locator('.conversation-item[data-selected="true"]');
  await expect(current.getByRole('button', { name: 'Rename New conversation', exact: true })).toHaveCount(0);
  const options = current.getByRole('button', { name: 'Options for New conversation', exact: true });
  await options.click();
  await expect(options).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Escape');
  await expect(options).toBeFocused();
  await expect(options).toHaveAttribute('aria-expanded', 'false');
  await options.click();
  await page.getByRole('heading', { name: 'New conversation', exact: true }).click();
  await expect(options).toHaveAttribute('aria-expanded', 'false');
  await options.focus();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await expect(current.getByRole('button', { name: 'Rename New conversation', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await current.getByLabel('Conversation title').fill('Project notes');
  await current.getByRole('button', { name: 'Save name' }).click();
  await expect(page.getByRole('heading', { name: 'Project notes', exact: true })).toBeVisible();
  await current.getByRole('button', { name: 'Options for Project notes', exact: true }).click();
  await current.getByRole('button', { name: 'Pin Project notes', exact: true }).click();
  await expect(current.getByRole('button', { name: 'Options for Project notes', exact: true })).toHaveAttribute('aria-expanded', 'false');
  await current.getByRole('button', { name: 'Options for Project notes', exact: true }).click();
  await expect(current.getByRole('button', { name: 'Unpin Project notes', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await page.getByLabel('Your message').fill('Keep this history');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('button', { name: '+ New conversation', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '+ New conversation', exact: true }).click();
  await expect(page.locator('.message.user')).toHaveCount(0);
  await expect(page.locator('.conversation-item').first()).toContainText('Project notes');
  await page.reload();
  await expect(page.locator('.conversation-item').first()).toContainText('Project notes');
  await page.getByRole('button', { name: 'Project notes (Pinned)', exact: true }).click();
  await expect(page.locator('.message.user')).toContainText('Keep this history');
  current = page.locator('.conversation-item[data-selected="true"]');
  await current.getByRole('button', { name: 'Options for Project notes', exact: true }).click();
  await current.getByRole('button', { name: 'Delete Project notes', exact: true }).click();
  await expect(page.getByRole('group', { name: 'Confirm deletion' })).toContainText('This cannot be undone');
  await current.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('group', { name: 'Confirm deletion' })).toHaveCount(0);
  await current.getByRole('button', { name: 'Options for Project notes', exact: true }).click();
  await current.getByRole('button', { name: 'Delete Project notes', exact: true }).click();
  await current.getByRole('button', { name: 'Delete conversation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Project notes', exact: true })).toHaveCount(0);
  await expect(page.locator('.message.user')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('.conversation-list')).not.toContainText('Project notes');
});

test('mobile layout keeps composer reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/chat');
  await login(page);
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByLabel('Your message')).toBeInViewport();
  await expect(page.locator('.empty-brand .wordmark')).toHaveText('Aster');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Open sidebar' }).click();
  const current = page.locator('.conversation-item[data-selected="true"]');
  const options = current.getByRole('button', { name: /^Options for / });
  await options.click();
  await expect(current.getByRole('button', { name: /^Rename / })).toBeInViewport();
  const nameBox = await current.locator('.conversation-link').boundingBox();
  const optionsBox = await options.boundingBox();
  expect(optionsBox!.x).toBeGreaterThan(nameBox!.x + nameBox!.width);
  expect(Math.abs(optionsBox!.y + optionsBox!.height / 2 - nameBox!.y - nameBox!.height / 2)).toBeLessThan(2);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(options).toHaveAttribute('aria-expanded', 'false');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Open sidebar' })).toBeFocused();
  await page.screenshot({ path: 'test-results/mobile.png', fullPage: true, animations: 'disabled' });
  await expect(page.getByRole('button', { name: 'Attach files' })).toBeEnabled();
  await page.getByLabel('Choose files').setInputFiles([
    { name: 'A long document name for the mobile layout.txt', mimeType: 'text/plain', buffer: Buffer.from('notes') },
    { name: 'second.txt', mimeType: 'text/plain', buffer: Buffer.from('notes') },
  ]);
  await expect(page.locator('.file-item')).toHaveCount(2);
  await expect(page.getByLabel('Your message')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/mobile-files.png', fullPage: true, animations: 'disabled' });
  await page.getByLabel('Your message').fill('Edit the file');
  await page.getByLabel('Your message').press('Enter');
  await expect(page.getByRole('link', { name: 'Edited v1', exact: true })).toBeVisible();
  await page.getByLabel('Your message').fill('First line');
  await page.getByLabel('Your message').press('Shift+Enter');
  await expect(page.getByLabel('Your message')).toHaveValue('First line\n');
});
