import { expect, test } from '@playwright/test';

async function login(page: import('@playwright/test').Page, key: string) {
  await page.goto('/login');
  await page.locator('#apiKey').fill(key);
  await page.getByRole('button', { name: 'Accedi' }).click();
}

test('admin inspects read-only tools, activates an installed plugin and approves an immutable binding', async ({ page }) => {
  await login(page, 'admin-key');
  await page.getByRole('link', { name: 'Tool', exact: true }).click();
  await expect(page.getByText('example.lookup')).toBeVisible();
  await expect(page.getByText('read_only', { exact: true })).toBeVisible();
  await expect(page.locator('.card').first()).toContainText('example');
  await expect(page.locator('input[type="file"]')).toHaveCount(0);

  await page.getByRole('link', { name: 'Plugin', exact: true }).click();
  const pluginCard = page.locator('.card').first();
  await expect(pluginCard).toContainText('Hello plugin');
  await expect(pluginCard).toContainText('inactive');
  await pluginCard.getByRole('checkbox', { name: 'Abilitato' }).check();
  await pluginCard.getByRole('button', { name: 'Applica' }).click();
  await expect(page.locator('.card').first()).toContainText('active');
  await expect(page.locator('.card').first()).toContainText('ok');
  await expect(page.locator('input[type="file"]')).toHaveCount(0);

  await page.getByRole('link', { name: 'Approvazioni', exact: true }).click();
  await page.locator('.list li').first().getByRole('link').click();
  await expect(page.getByRole('heading', { name: 'example.write' })).toBeVisible();
  await expect(page.getByText('mutating', { exact: true })).toBeVisible();
  await expect(page.getByText('example', { exact: true })).toBeVisible();
  await expect(page.getByText('Digest argomenti')).toBeVisible();
  await expect(page.locator('input[name="arguments"]')).toHaveCount(0);
  await page.locator('input[name="confirm"]').first().check();
  await page.getByRole('button', { name: 'Approva' }).click();
  await expect(page.getByText(/Approvazione · approved/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approva' })).toHaveCount(0);
});

test('expired approvals cannot be approved', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/approvals/00000000-0000-4000-8000-0000000000e2');
  await expect(page.getByText('Approvazione scaduta')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approva' })).toHaveCount(0);
});

test('a token without approvals scope cannot approve', async ({ page }) => {
  await login(page, 'reader-key');
  await page.goto('/approvals');
  await expect(page.getByRole('alert')).toContainText('403');
  await expect(page.getByRole('button', { name: 'Approva' })).toHaveCount(0);
});
