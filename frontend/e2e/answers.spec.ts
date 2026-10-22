import { expect, test } from '@playwright/test';

test('answers render Markdown safely and export from the options menu', async ({ page }) => {
  await page.goto('/chat');
  await page.getByRole('button', { name: 'Continue as guest', exact: true }).click();
  await expect(page.getByLabel('Answer format')).toHaveCount(0);
  await page.getByLabel('Your message').fill('Compare the plans as a table');
  await page.getByRole('button', { name: 'Send message' }).click();
  const answer = page.locator('.message.assistant').last();
  await expect(answer.getByRole('table')).toBeVisible();
  await expect(answer.getByRole('cell', { name: '$9' })).toBeVisible();
  await expect(answer).not.toContainText('| Plan |');
  await expect(answer.getByRole('button', { name: 'Export answer as Word (.docx)' })).toHaveCount(0);

  await answer.getByRole('button', { name: 'Answer options' }).click();
  const downloading = page.waitForEvent('download');
  await answer.getByRole('button', { name: 'Export answer as Word (.docx)' }).click();
  expect((await downloading).suggestedFilename()).toBe('aster-answer.docx');
  await expect(answer.getByRole('group', { name: 'Export answer' })).toHaveCount(0);
  await answer.getByRole('button', { name: 'Answer options' }).click();
  await page.keyboard.press('Escape');
  await expect(answer.getByRole('group', { name: 'Export answer' })).toHaveCount(0);
  await answer.getByRole('button', { name: 'Answer options' }).click();
  const markdown = page.waitForEvent('download');
  await answer.getByRole('button', { name: 'Export answer as Markdown (.md)' }).click();
  expect((await markdown).suggestedFilename()).toBe('aster-answer.md');

  await page.getByLabel('Your message').fill('Show it as a code sample');
  await page.getByRole('button', { name: 'Send message' }).click();
  const code = page.locator('.message.assistant').last();
  await expect(code.locator('pre code')).toContainText('print("hi")');
  await expect(code.getByRole('button', { name: 'Copy code' })).toBeVisible();
  await expect(code.locator('b')).toHaveCount(0);
  await expect(code.locator('img')).toHaveCount(0);
  await expect(code.locator('a[href^="javascript"]')).toHaveCount(0);
  await expect(code.getByRole('link', { name: 'good' })).toHaveAttribute('href', 'https://example.com/docs');
  await expect(code.getByText('[tracker]')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
