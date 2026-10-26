import { expect, test } from '@playwright/test';

async function login(page: import('@playwright/test').Page, key: string) {
  await page.goto('/login');
  await page.locator('#apiKey').fill(key);
  await page.getByRole('button', { name: 'Accedi' }).click();
}

test('admin can create and version an assistant without exposing the key', async ({ page }) => {
  await login(page, 'admin-key');
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('.identity strong')).toHaveText('admin');

  await page.getByRole('link', { name: 'Assistenti', exact: true }).click();
  await page.locator('#name').fill('Assistente test');
  await page.locator('#model').selectOption('test-model');
  await page.locator('#system_prompt').fill('Rispondi in italiano.');
  await page.locator('#directives').fill('rag, safety');
  await page.getByRole('button', { name: 'Crea assistente' }).click();

  await expect(page).toHaveURL(/\/assistants\/[^/]+$/);
  await expect(page.getByRole('heading', { name: 'Assistente test' })).toBeVisible();
  await expect(page.getByText(/Assistente · v1/)).toBeVisible();

  await page.locator('#system_prompt').fill('Rispondi in italiano, con fonti.');
  await page.getByRole('button', { name: 'Salva nuova versione' }).click();
  await expect(page.getByText(/Assistente · v2/)).toBeVisible();
  await expect(page.getByText('corrente')).toBeVisible();

  const exposed = await page.evaluate(() => ({
    html: document.documentElement.outerHTML,
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
    cookies: document.cookie,
  }));
  expect(exposed.html).not.toContain('admin-key');
  expect(exposed.local).not.toContain('admin-key');
  expect(exposed.session).not.toContain('admin-key');
  expect(exposed.cookies).not.toContain('admin-key');
});

test('reader sees read-only controls and cannot submit changes', async ({ page }) => {
  await login(page, 'reader-key');
  await expect(page.locator('.identity strong')).toHaveText('reader');
  await page.getByRole('link', { name: 'Assistenti', exact: true }).click();
  await expect(page.getByText('Accesso in sola lettura')).toBeVisible();
  await expect(page.locator('form[action="?/create"]')).toHaveCount(0);
});

test('widget tokens are rejected from the console', async ({ page }) => {
  await login(page, 'widget-key');
  await expect(page.getByRole('alert')).toContainText('token widget');
  await expect(page).toHaveURL(/\/login/);
});
