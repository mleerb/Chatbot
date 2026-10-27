import { expect, test } from '@playwright/test';

test('answers stream with steps and can be stopped, copied, rated, edited and regenerated', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/chat');
  await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
  await page.getByLabel('Choose files').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('notes') });
  await expect(page.locator('.attachment:not(.pending)')).toHaveCount(1);
  await page.getByLabel('Your message').fill('Slow answer please');
  await page.getByRole('button', { name: 'Send message' }).click();
  const pending = page.locator('.message.assistant.pending');
  await expect(pending.getByRole('status')).toHaveText('Reading notes.txt…');
  await expect(pending).not.toContainText('Let me look.');
  await expect(pending).toContainText('This answer arrives');
  await expect(page.getByRole('button', { name: 'Send message' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Stop answer' }).click();
  await expect(pending).toHaveCount(0);
  const answer = page.locator('.message.assistant').last();
  await expect(answer.locator('.stopped-note')).toHaveText('Stopped');
  await expect(answer).not.toContainText('stopped early');
  await expect(page.getByRole('button', { name: 'Send message' })).toBeVisible();

  await answer.getByRole('button', { name: 'Copy answer' }).click();
  await expect(answer.getByRole('button', { name: 'Copied' })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/^This answer arrives/);
  await answer.getByRole('button', { name: 'Good answer' }).click();
  await expect(answer.getByRole('button', { name: 'Good answer' })).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(page.locator('.message.assistant').last().getByRole('button', { name: 'Good answer' })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('.message.assistant').last().getByRole('button', { name: 'Good answer' }).click();
  await expect(page.locator('.message.assistant').last().getByRole('button', { name: 'Good answer' })).toHaveAttribute('aria-pressed', 'false');

  const question = page.locator('.message.user').first();
  await question.getByRole('button', { name: 'Edit message' }).click();
  await page.keyboard.press('Escape');
  await expect(question.getByLabel('Message text')).toHaveCount(0);
  await question.getByRole('button', { name: 'Edit message' }).click();
  await question.getByLabel('Message text').fill('Again please');
  await question.getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('.message.assistant').last()).toContainText(/Answer number \d+\./);
  await expect(page.locator('.message')).toHaveCount(2);
  await expect(page.locator('.message.user').first()).toContainText('Again please');
  await expect(page.locator('.message.user').first().locator('.attachment')).toContainText('notes.txt');
  const first = await page.locator('.message.assistant').last().innerText();

  await page.getByRole('button', { name: 'Regenerate answer' }).click();
  await expect(page.locator('.message.assistant').last()).not.toHaveText(first);
  await expect(page.locator('.message')).toHaveCount(2);
  await expect(page.locator('.message.assistant').last().locator('.stopped-note')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Regenerate answer' })).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
