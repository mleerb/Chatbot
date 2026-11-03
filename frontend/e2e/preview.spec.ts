import { expect, test } from '@playwright/test';

for (const width of [1440, 360]) {
  test(`generated HTML/PDF previews are safe, local and usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const external: string[] = [];
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://example.com/**', route => { external.push(route.request().url()); return route.abort(); });
    await page.goto('/chat');
    await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
    await page.getByLabel('Your message').fill('Preview fixtures');
    await page.getByRole('button', { name: 'Send message' }).click();
    const htmlButton = page.getByRole('button', { name: 'Preview index.html', exact: true });
    await htmlButton.click();
    const html = page.getByRole('dialog', { name: 'index.html', exact: true });
    await expect(html).toBeVisible();
    const frame = page.frameLocator('iframe[title="Rendered HTML preview"]');
    await expect(frame.getByRole('heading', { name: 'Hello / Xin chào', exact: true })).toBeVisible();
    await expect(frame.locator('script, img, form, iframe, meta[http-equiv="refresh"]')).toHaveCount(0);
    await expect(frame.getByText('External link')).not.toHaveAttribute('href');
    expect(await page.locator('iframe').getAttribute('sandbox')).toBe('');
    expect(await page.evaluate(() => (window as Window & { previewPwned?: boolean }).previewPwned)).toBeUndefined();
    await html.getByRole('button', { name: 'Source', exact: true }).click();
    await expect(html.locator('.source-text')).toContainText('<script>parent.previewPwned=true</script>');
    await expect(html.locator('.source-text script')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(html).toHaveCount(0);
    await expect(htmlButton).toBeFocused();
    expect(external).toEqual([]);
    await page.getByRole('button', { name: 'Preview report.pdf', exact: true }).click();
    const pdf = page.getByRole('dialog', { name: 'report.pdf', exact: true });
    await expect(pdf.getByRole('button', { name: 'Next page', exact: true })).toBeEnabled({ timeout: 15000 });
    await expect(pdf.getByRole('img', { name: 'PDF page 1', exact: true })).toBeVisible();
    expect(await pdf.locator('canvas').evaluate(canvas => (canvas as HTMLCanvasElement).width)).toBeGreaterThan(100);
    await pdf.getByRole('button', { name: 'Next page', exact: true }).click();
    await expect(pdf).toContainText('Page 2 of 2');
    await pdf.getByLabel('Zoom').selectOption('1.25');
    await expect(pdf.getByRole('status')).toHaveCount(0);
    await page.screenshot({ path: `test-results/preview-pdf-${width}.png`, fullPage: true });
    const download = page.waitForEvent('download');
    await pdf.getByRole('link', { name: 'Download report.pdf', exact: true }).click();
    expect((await download).suggestedFilename()).toBeTruthy();
    await pdf.getByRole('button', { name: 'Close preview', exact: true }).click();
    await page.reload();
    await page.getByRole('button', { name: 'Preview index.html', exact: true }).click();
    await expect(frame.getByRole('heading', { name: 'Hello / Xin chào', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(external).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test('text, sheet, slide and archive previews use escaped non-executable content', async ({ page }) => {
  await page.goto('/chat');
  await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
  await page.getByLabel('Your message').fill('Preview fixtures');
  await page.getByRole('button', { name: 'Send message' }).click();
  for (const [filename, content] of [['notes.md', 'Hello / Xin chào'], ['budget.xlsx', '=1+1'], ['slides.pptx', 'Hello / Xin chào'], ['bundle.zip', 'README.md']]) {
    await page.getByRole('button', { name: `Preview ${filename}`, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: filename, exact: true });
    await expect(dialog).toContainText(content);
    if (filename === 'budget.xlsx') {
      await dialog.getByLabel('Sheet').selectOption('1');
      await expect(dialog).toContainText('Xin chào');
    }
    await dialog.getByRole('button', { name: 'Close preview', exact: true }).click();
  }
  await page.route('**/api/files/preview?*', route => route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }));
  await page.getByRole('button', { name: 'Preview notes.md', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'notes.md', exact: true }).getByRole('alert')).toContainText('File preview unavailable');
});
