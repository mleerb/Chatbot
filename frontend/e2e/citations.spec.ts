import { expect, test } from '@playwright/test';

for (const width of [1440, 360]) {
  test(`document source viewer escapes HTML and preserves English/Vietnamese text at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/chat');
    await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
    const content = 'Returns within thirty days.\nHoàn tiền trong ba mươi ngày.\n<script>window.sourceExecuted = true</script>\n<img src="https://example.com/tracker" onerror="window.sourceExecuted=true">\n# Not a heading\n[external](https://example.com)';
    await page.getByLabel('Choose files').setInputFiles({ name: 'chính-sách.html', mimeType: 'text/html', buffer: Buffer.from(content) });
    await expect(page.locator('.attachment:not(.pending)')).toHaveCount(1);
    await page.getByLabel('Your message').fill('Cite English and Vietnamese sources');
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(page.locator('.message.assistant.pending')).toHaveCount(0);
    const answer = page.locator('.message.assistant').last();
    const marker = answer.getByRole('button', { name: 'Document D1: chính-sách.html, Section 1', exact: true }).first();
    await expect(marker).toBeVisible();
    await expect(answer.getByRole('link', { name: 'Web W1: Evidence', exact: true })).toBeVisible();
    await expect(answer.locator('.document-sources')).toContainText('Document sources');
    await expect(answer.locator('.web-sources')).toContainText('Web sources');
    const requests: string[] = [];
    page.on('request', request => { if (request.url().startsWith('https://example.com')) requests.push(request.url()); });
    await marker.click();
    const dialog = page.getByRole('dialog', { name: 'chính-sách.html', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('.source-text')).toHaveText(content);
    await expect(dialog.locator('.source-text script, .source-text img, .source-text a, .source-text h1')).toHaveCount(0);
    expect(await page.evaluate(() => (window as Window & { sourceExecuted?: boolean }).sourceExecuted)).toBeUndefined();
    expect(requests).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/citation-source-${width}.png`, fullPage: true });
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(marker).toBeFocused();
    await page.reload();
    await page.getByRole('button', { name: 'Document D1: chính-sách.html, Section 1', exact: true }).first().click();
    await expect(page.getByRole('dialog', { name: 'chính-sách.html', exact: true }).locator('.source-text')).toHaveText(content);
    await page.getByRole('button', { name: 'Close source', exact: true }).click();
  });
}

test('deleted source shows a clear unavailable state without exposing other content', async ({ page }) => {
  await page.goto('/chat');
  await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
  await page.getByLabel('Choose files').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Private / Riêng tư') });
  await expect(page.locator('.attachment:not(.pending)')).toHaveCount(1);
  await page.getByLabel('Your message').fill('Cite sources');
  await page.getByRole('button', { name: 'Send message' }).click();
  const marker = page.getByRole('button', { name: 'Document D1: notes.txt, Section 1', exact: true }).first();
  await expect(marker).toBeVisible();
  await page.route('**/api/sources/*', route => route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Source no longer available"}' }));
  await marker.click();
  await expect(page.getByRole('dialog', { name: 'notes.txt', exact: true }).getByRole('alert')).toContainText('Source no longer available');
  await expect(page.locator('.source-text')).toHaveCount(0);
});
