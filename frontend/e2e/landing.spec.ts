import { expect, test } from '@playwright/test';

for (const width of [1440, 768, 390, 320]) {
  test(`landing page navigation and layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    const requests: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) requests.push(request.url()); });
    await page.goto('/');
    await expect(page).toHaveTitle('AGENTslop');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your ideas.Put to work.');
    await expect(page.locator('.landing-signature .wordmark')).toHaveText('AGENTslop.');
    const brand = await page.locator('.landing-signature .wordmark').boundingBox();
    expect(brand!.x + brand!.width).toBeLessThanOrEqual(width);
    await expect(page.getByRole('figure')).toBeVisible();
    await expect(page.getByRole('figure')).toContainText('Help me plan a launch for my new project.');
    await expect(page.getByRole('heading', { name: 'Start with a goal' })).toBeVisible();
    await expect(page.locator('.landing-steps')).toContainText('No upload needed.');
    await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /AI agent chatbot/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByRole('heading', { name: 'Three simple steps.' })).toBeVisible();
    await expect(page.locator('.landing-steps > li')).toHaveCount(3);
    await expect(page.getByRole('link', { name: 'Open workspace', exact: true })).toHaveCount(2);
    expect(requests).toEqual([]);
    await page.screenshot({ path: `test-results/landing-${width}.png`, fullPage: true });
    await page.getByRole('link', { name: 'Open workspace', exact: true }).last().click();
    await expect(page).toHaveURL(/\/chat$/);
    if (width <= 760) await page.getByRole('button', { name: 'Open sidebar' }).click();
    await expect(page.getByLabel('Select user')).toBeVisible();
    if (width <= 760) await page.getByRole('button', { name: 'Close sidebar' }).click();
    await expect(page.getByLabel('Your message')).toBeVisible();
    await page.goBack();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('landing page respects reduced motion and supports skip navigation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main$/);
  expect(await page.getByRole('link', { name: 'Open workspace', exact: true }).last().evaluate(element => getComputedStyle(element).transitionDuration)).toBe('0s');
});
