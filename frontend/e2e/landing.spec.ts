import { expect, test } from '@playwright/test';

for (const theme of ['light', 'dark'] as const) {
  for (const width of [1440, 768, 390, 360, 320]) {
    test(`Aster landing at ${width}px in ${theme} mode`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      const errors: string[] = [];
      const requests: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) requests.push(request.url()); });
      await page.goto('/');
      await expect(page).toHaveTitle(/Aster/);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('A little clarity.A lot of possibility.');
      await expect(page.getByRole('figure')).toBeVisible();
      await expect(page.getByRole('figure')).toContainText('Illustrative preview');
      await expect(page.locator('#features')).toContainText('Bring the context with you.');
      await expect(page.locator('#pricing')).toHaveCount(0);
      await expect(page.locator('details')).toHaveCount(3);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await page.locator('h1').evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(43);
      expect(requests).toEqual([]);
      await page.screenshot({ path: `test-results/aster-${theme}-${width}.png`, fullPage: true });
      await page.getByRole('link', { name: 'Start a conversation', exact: true }).click();
      await expect(page).toHaveURL(/\/chat$/);
      await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
      expect(errors).toEqual([]);
    });
  }
}

test('theme toggle persists and login opens the account form', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.goto('/');
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.getByRole('link', { name: 'Log in', exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
});

test('mobile menu supports navigation, dismissal and focus', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/');
  const button = page.locator('#menu-toggle');
  await button.click();
  await expect(button).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(button).toHaveAttribute('aria-expanded', 'false');
  await expect(button).toBeFocused();
  await button.click();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Features' }).click();
  await expect(page).toHaveURL(/#features$/);
  await expect(button).toHaveAttribute('aria-expanded', 'false');
});

test('blocked storage does not break theme controls', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Blocked', 'SecurityError'); } });
  });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('landing renders without contacting external services', async ({ page, baseURL }) => {
  const external: string[] = [];
  const errors: string[] = [];
  await page.route('**/*', route => {
    if (new URL(route.request().url()).origin !== new URL(baseURL!).origin) {
      external.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.getByRole('button', { name: /Switch to .* theme/ }).click();
  await page.getByRole('link', { name: 'Start a conversation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
});

test('reduced motion, skip navigation and standalone file', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main$/);
  expect(await page.locator('.button-primary').first().evaluate(element => getComputedStyle(element).transitionDuration)).toBe('0s');
  expect(await page.locator('.orb').evaluate(element => getComputedStyle(element).animationName)).toBe('none');
  const ray = page.locator('.hero-mark .logo-ring').first();
  expect(await ray.evaluate(element => getComputedStyle(element).animationName)).toBe('none');
  expect(await ray.evaluate(element => getComputedStyle(element).strokeDashoffset)).toBe('0px');
  await page.goto('/landing.html');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});
