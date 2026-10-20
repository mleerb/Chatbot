import { expect, test } from '@playwright/test';

for (const width of [1440, 360]) {
  test(`guest chat, refresh and ending session at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/chat');
    await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
    await expect(page.getByLabel('Your message')).toBeEnabled();
    await expect(page.getByRole('heading', { name: 'Temporary chat' })).toBeVisible();
    await page.getByLabel('Your message').fill('A guest question');
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(page.locator('.message.user')).toContainText('A guest question');
    await page.reload();
    await expect(page.locator('.message.user')).toContainText('A guest question');
    const otherPage = await page.context().newPage();
    await otherPage.goto('/chat');
    await expect(otherPage.getByRole('button', { name: 'Continue as guest' })).toBeVisible();
    await otherPage.getByRole('button', { name: 'Continue as guest' }).click();
    await expect(otherPage.locator('.message.user')).toHaveCount(0);
    await otherPage.close();
    await page.getByLabel('Choose files').setInputFiles({ name: 'temporary.txt', mimeType: 'text/plain', buffer: Buffer.from('guest file') });
    await expect(page.locator('.file-item')).toHaveCount(1);
    const downloading = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Download original', exact: true }).click();
    expect((await downloading).suggestedFilename()).toBe('temporary.txt');
    if (width <= 760) await page.getByRole('button', { name: 'Open sidebar' }).click();
    await expect(page.locator('.guest-notice')).toContainText('this tab is open');
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'New temporary chat', exact: true }).click();
    await expect(page.locator('.message.user')).toHaveCount(0);
    await expect(page.locator('.file-item')).toHaveCount(0);
    if (width <= 760) await page.getByRole('button', { name: 'Open sidebar' }).click();
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'End guest session / Log in', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
    await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
    await expect(page.locator('.message.user')).toHaveCount(0);
    await page.close();
    const reopened = await page.context().newPage();
    await reopened.goto('/chat');
    await expect(reopened.getByRole('button', { name: 'Continue as guest' })).toBeVisible();
    expect(await reopened.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
