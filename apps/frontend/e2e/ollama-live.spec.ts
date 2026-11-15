import { expect, test } from '@playwright/test';

test('live local Ollama response streams and survives reload', async ({ page }) => {
  test.skip(process.env.CLAIRE_LIVE_OLLAMA !== '1', 'Requires explicitly enabled local Ollama');
  test.setTimeout(180000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('alice@example.test');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  await expect(page.getByLabel('Local model', { exact: true })).toHaveValue('qwen3:8b', { timeout: 15000 });
  await page.getByLabel('Your message', { exact: true }).fill('Réponds en une courte phrase en français pour te présenter comme CLAIRE.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Response saved.', { timeout: 150000 });
  const response = await page.locator('.chat-message.assistant .markdown').innerText();
  expect(response.length).toBeGreaterThan(5);
  await page.screenshot({ path: '../../data/chat-desktop.png', fullPage: true });
  await page.reload();
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  await page.getByRole('navigation', { name: 'More conversations' }).getByRole('button').first().click();
  await expect(page.locator('.chat-message.assistant .markdown')).toHaveText(response);
  await page.getByLabel('Language').selectOption('fr');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: '../../data/chat-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});

test('stopping live generation releases the conversation lease', async ({ page }) => {
  test.skip(process.env.CLAIRE_LIVE_OLLAMA !== '1', 'Requires explicitly enabled local Ollama');
  test.setTimeout(60000);
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('alice@example.test');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  await expect(page.getByLabel('Local model', { exact: true })).toHaveValue('qwen3:8b', { timeout: 15000 });
  await page.getByLabel('Your message', { exact: true }).fill('Écris une longue histoire fictive de mille mots sur un jardin lunaire.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.locator('.chat-message.assistant')).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Generation stopped');
  await expect(async () => {
    const rows = await page.request.get('/api/v1/conversations').then(response => response.json());
    const current = rows.find((row: { title: string }) => row.title.startsWith('Écris une longue'));
    const history = await page.request.get(`/api/v1/conversations/${current.id}`).then(response => response.json());
    expect(history.messages.at(-1).status).toBe('cancelled');
  }).toPass({ timeout: 15000 });
});
